# -*- coding: utf-8 -*-
"""
executor_py.io.transport.http — HTTP/JSON Bridge Transport.

Mirrors io/rac/src/transports/http.rs (RION HTTP Bridge).

HTTP Transport — JSON over HTTP/1.1 or HTTP/2.
Used for RION (Remote IO Network) machine binding.
"""

from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass
from typing import Any, Optional, AsyncIterator
from urllib.parse import urljoin

import aiohttp

from ...core import SioEnvelope, SioResult, TransportConfig, RacTransportError
from ...adapter import RacTransport, TransportStats


@dataclass
class HttpConfig:
    """HTTP transport configuration."""
    base_url: str = ""
    timeout_seconds: float = 30.0
    max_connections: int = 100
    keepalive_timeout: float = 15.0
    headers: dict[str, str] = None
    
    def __post_init__(self):
        if self.headers is None:
            self.headers = {"Content-Type": "application/json"}


class HttpTransport(RacTransport):
    """HTTP/JSON Bridge Transport.
    
    Implements JSON-RPC over HTTP for RION machine binding.
    Supports both request/response and streaming (SSE).
    """
    
    def __init__(self, config: Optional[HttpConfig] = None):
        self.config = config or HttpConfig()
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        self._stats = TransportStats()
    
    def id(self) -> str:
        return "http"
    
    def scheme(self) -> str:
        return "http://"
    
    def open(self, config: TransportConfig) -> None:
        """Initialize HTTP transport (sync - creates session lazily)."""
        self.config.base_url = config.uri
        self._connected = True
    
    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session exists."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            connector = aiohttp.TCPConnector(
                limit=self.config.max_connections,
                keepalive_timeout=self.config.keepalive_timeout,
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers=self.config.headers,
            )
        return self._session
    
    async def send_async(self, envelope: SioEnvelope) -> SioResult:
        """Send SIO envelope via HTTP POST."""
        session = await self._ensure_session()
        
        url = urljoin(self.config.base_url, "/rac/call")
        
        payload = {
            "version": envelope.version,
            "msg_id": envelope.msg_id,
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
        
        try:
            async with session.post(url, json=payload) as response:
                data = await response.read()
                self._stats.bytes_sent += len(json.dumps(payload))
                self._stats.bytes_received += len(data)
                self._stats.request_count += 1
                
                if response.status == 200:
                    return SioResult.ok(data)
                else:
                    self._stats.error_count += 1
                    return SioResult.err(response.status, data.decode())
        except asyncio.TimeoutError:
            self._stats.error_count += 1
            return SioResult.err(408, "Request timeout")
        except Exception as e:
            self._stats.error_count += 1
            return SioResult.err(500, str(e))
    
    def send(self, envelope: SioEnvelope) -> SioResult:
        """Sync send (runs async in event loop)."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.send_async(envelope))
    
    async def stream(self, envelope: SioEnvelope) -> AsyncIterator[SioResult]:
        """Stream via Server-Sent Events (SSE)."""
        session = await self._ensure_session()
        
        url = urljoin(self.config.base_url, "/rac/stream")
        
        payload = {
            "version": envelope.version,
            "msg_id": envelope.msg_id,
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
        
        try:
            async with session.post(url, json=payload) as response:
                async for line in response.content:
                    line = line.decode().strip()
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: "
                        if data == "[DONE]":
                            break
                        yield SioResult.ok(data.encode())
        except Exception as e:
            yield SioResult.err(500, str(e))
    
    def close(self) -> None:
        """Close HTTP transport."""
        self._connected = False
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())
    
    def is_connected(self) -> bool:
        return self._connected and self._session is not None and not self._session.closed
    
    def stats(self) -> TransportStats:
        return self._stats


class HttpServerTransport:
    """HTTP server transport — handles incoming RAC requests.
    
    Would integrate with aiohttp.web or FastAPI in production.
    """
    
    def __init__(self, handler, host: str = "0.0.0.0", port: int = 8080):
        self.handler = handler
        self.host = host
        self.port = port
        self._app = None
        self._runner = None
    
    async def start(self) -> None:
        """Start HTTP server."""
        from aiohttp import web
        
        self._app = web.Application()
        self._app.router.add_post("/rac/call", self._handle_call)
        self._app.router.add_post("/rac/stream", self._handle_stream)
        self._app.router.add_get("/health", self._handle_health)
        
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
    
    async def _handle_call(self, request):
        """Handle rac:call."""
        data = await request.json()
        envelope = SioEnvelope(
            version=data.get("version", 1),
            msg_id=data.get("msg_id", 0),
            source=data.get("source", ""),
            target=data.get("target", ""),
            sio_type=data.get("sio_type", "Execute"),
            payload=data.get("payload"),
            metadata=data.get("metadata"),
        )
        result = await self.handler(envelope)
        return web.json_response({
            "code": result.code,
            "data": result.data.decode() if result.data else "",
            "error": result.error,
            "processing_time_us": result.processing_time_us,
        })
    
    async def _handle_stream(self, request):
        """Handle rac:stream (SSE)."""
        from aiohttp import web
        data = await request.json()
        envelope = SioEnvelope(
            version=data.get("version", 1),
            msg_id=data.get("msg_id", 0),
            source=data.get("source", ""),
            target=data.get("target", ""),
            sio_type=data.get("sio_type", "Execute"),
            payload=data.get("payload"),
            metadata=data.get("metadata"),
        )
        
        response = web.StreamResponse()
        response.headers["Content-Type"] = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        await response.prepare(request)
        
        async for chunk in self.handler.stream(envelope):
            if chunk.code == 0:
                await response.write(f"data: {chunk.data.decode()}\n\n".encode())
            else:
                await response.write(f"data: [ERROR] {chunk.error}\n\n".encode())
        
        await response.write(b"data: [DONE]\n\n")
        return response
    
    async def _handle_health(self, request):
        """Health check."""
        from aiohttp import web
        return web.json_response({"status": "healthy", "transport": "http"})
    
    async def stop(self) -> None:
        """Stop HTTP server."""
        if self._runner:
            await self._runner.cleanup()


__all__ = ["HttpTransport", "HttpConfig", "HttpServerTransport"]