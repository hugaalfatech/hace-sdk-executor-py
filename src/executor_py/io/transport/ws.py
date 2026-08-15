# -*- coding: utf-8 -*-
"""
executor_py.io.transport.ws — WebSocket Transport.

Mirrors io/rac/src/transports/ws.rs (RION WebSocket Bridge).

WebSocket Transport — bidirectional JSON over WebSocket.
Used for RION (Remote IO Network) machine binding with persistent connections.
"""

from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass
from typing import Any, Optional, AsyncIterator
from urllib.parse import urljoin

import websockets

from ...core import SioEnvelope, SioResult, TransportConfig, RacTransportError
from ...adapter import RacTransport, TransportStats


@dataclass
class WsConfig:
    """WebSocket transport configuration."""
    url: str = ""
    ping_interval: float = 20.0
    ping_timeout: float = 10.0
    max_size: int = 2**20  # 1MB
    headers: dict[str, str] = None
    
    def __post_init__(self):
        if self.headers is None:
            self.headers = {}


class WsTransport(RacTransport):
    """WebSocket Transport.
    
    Implements bidirectional JSON-RPC over WebSocket for RION machine binding.
    Supports persistent connections with ping/pong keepalive.
    """
    
    def __init__(self, config: Optional[WsConfig] = None):
        self.config = config or WsConfig()
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._stats = TransportStats()
        self._receive_task: Optional[asyncio.Task] = None
        self._response_futures: dict[int, asyncio.Future] = {}
        self._msg_id = 0
    
    def id(self) -> str:
        return "ws"
    
    def scheme(self) -> str:
        return "ws://"
    
    def open(self, config: TransportConfig) -> None:
        """Initialize WebSocket transport (sync - connects lazily)."""
        self.config.url = config.uri
        self._connected = True
    
    async def _ensure_connection(self) -> websockets.WebSocketClientProtocol:
        """Ensure WebSocket connection exists."""
        if self._ws is None or self._ws.closed:
            self._ws = await websockets.connect(
                self.config.url,
                ping_interval=self.config.ping_interval,
                ping_timeout=self.config.ping_timeout,
                max_size=self.config.max_size,
                extra_headers=self.config.headers,
            )
            # Start background receive task
            self._receive_task = asyncio.create_task(self._receive_loop())
        return self._ws
    
    async def _receive_loop(self) -> None:
        """Background task to receive messages and resolve futures."""
        try:
            async for message in self._ws:
                data = json.loads(message)
                msg_id = data.get("msg_id", 0)
                if msg_id in self._response_futures:
                    future = self._response_futures.pop(msg_id)
                    future.set_result(data)
        except Exception:
            # Connection closed or error
            for future in self._response_futures.values():
                if not future.done():
                    future.set_exception(RacTransportError.receive_failed("Connection closed"))
            self._response_futures.clear()
    
    def _next_msg_id(self) -> int:
        self._msg_id += 1
        return self._msg_id
    
    async def send_async(self, envelope: SioEnvelope) -> SioResult:
        """Send SIO envelope via WebSocket."""
        ws = await self._ensure_connection()
        
        msg_id = envelope.msg_id or self._next_msg_id()
        
        payload = {
            "version": envelope.version,
            "msg_id": msg_id,
            "source": envelope.source,
            "target": envelope.target,
            "sio_type": envelope.sio_type.value if hasattr(envelope.sio_type, 'value') else str(envelope.sio_type),
            "payload": envelope.payload,
            "metadata": {
                "timestamp": envelope.metadata.timestamp,
                "trace_id": envelope.metadata.trace_id,
                "retry_count": envelope.metadata.retry_count,
                "priority": envelope.metadata.priority,
            } if envelope.metadata else None,
        }
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self._response_futures[msg_id] = future
        
        try:
            await ws.send(json.dumps(payload))
            self._stats.bytes_sent += len(json.dumps(payload))
            self._stats.request_count += 1
            
            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=self.config.ping_timeout * 3)
            
            response_data = json.dumps(response).encode()
            self._stats.bytes_received += len(response_data)
            
            return SioResult.ok(response_data)
        except asyncio.TimeoutError:
            self._response_futures.pop(msg_id, None)
            self._stats.error_count += 1
            return SioResult.err(408, "Response timeout")
        except Exception as e:
            self._response_futures.pop(msg_id, None)
            self._stats.error_count += 1
            return SioResult.err(500, str(e))
    
    def send(self, envelope: SioEnvelope) -> SioResult:
        """Sync send."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.send_async(envelope))
    
    async def stream(self, envelope: SioEnvelope) -> AsyncIterator[SioResult]:
        """Stream via WebSocket (persistent connection)."""
        ws = await self._ensure_connection()
        
        msg_id = envelope.msg_id or self._next_msg_id()
        
        payload = {
            "version": envelope.version,
            "msg_id": msg_id,
            "source": envelope.source,
            "target": envelope.target,
            "sio_type": "stream",
            "payload": envelope.payload,
            "metadata": {
                "timestamp": envelope.metadata.timestamp,
                "trace_id": envelope.metadata.trace_id,
                "retry_count": envelope.metadata.retry_count,
                "priority": envelope.metadata.priority,
            } if envelope.metadata else None,
        }
        
        future = asyncio.get_event_loop().create_future()
        self._response_futures[msg_id] = future
        
        try:
            await ws.send(json.dumps(payload))
            
            # For streaming, we yield chunks as they arrive
            # This is simplified - real impl would use a dedicated stream handler
            while True:
                try:
                    response = await asyncio.wait_for(future, timeout=5.0)
                    if response.get("is_final"):
                        yield SioResult.ok(json.dumps(response).encode())
                        break
                    else:
                        yield SioResult.ok(json.dumps(response).encode())
                        # Create new future for next chunk
                        future = asyncio.get_event_loop().create_future()
                        self._response_futures[msg_id] = future
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            yield SioResult.err(500, str(e))
        finally:
            self._response_futures.pop(msg_id, None)
    
    def close(self) -> None:
        """Close WebSocket transport."""
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
        if self._ws and not self._ws.closed:
            asyncio.create_task(self._ws.close())
    
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None and not self._ws.closed
    
    def stats(self) -> TransportStats:
        return self._stats


class WsServerTransport:
    """WebSocket server transport — handles incoming RAC connections."""
    
    def __init__(self, handler, host: str = "0.0.0.0", port: int = 8081):
        self.handler = handler
        self.host = host
        self.port = port
        self._server = None
    
    async def start(self) -> None:
        """Start WebSocket server."""
        self._server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10,
        )
    
    async def _handle_connection(self, ws, path):
        """Handle incoming WebSocket connection."""
        try:
            async for message in ws:
                data = json.loads(message)
                envelope = SioEnvelope(
                    version=data.get("version", 1),
                    msg_id=data.get("msg_id", 0),
                    source=data.get("source", ""),
                    target=data.get("target", ""),
                    sio_type=data.get("sio_type", "Execute"),
                    payload=data.get("payload"),
                    metadata=data.get("metadata"),
                )
                
                if envelope.sio_type == "stream" or data.get("method") == "stream":
                    # Streaming response
                    async for chunk in self.handler.stream(envelope):
                        await ws.send(json.dumps({
                            "msg_id": envelope.msg_id,
                            "code": chunk.code,
                            "data": chunk.data.decode() if chunk.data else "",
                            "error": chunk.error,
                            "is_final": chunk.data is None or "is_final" in str(chunk.data),
                        }))
                else:
                    # Single request/response
                    result = await self.handler(envelope)
                    await ws.send(json.dumps({
                        "msg_id": envelope.msg_id,
                        "code": result.code,
                        "data": result.data.decode() if result.data else "",
                        "error": result.error,
                        "processing_time_us": result.processing_time_us,
                    }))
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception:
            pass
    
    async def stop(self) -> None:
        """Stop WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()


__all__ = ["WsTransport", "WsConfig", "WsServerTransport"]