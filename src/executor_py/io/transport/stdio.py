# -*- coding: utf-8 -*-
"""
executor_py.io.transport.stdio — STDIO JSON-RPC 2.0 Transport.

Mirrors text-editor/io/mcp/server/core.py run_stdio().

STDIO Transport — line-delimited JSON-RPC 2.0 over stdin/stdout.
Used by MCP servers, LION IPC, local process communication.
"""

from __future__ import annotations

import json
import sys
import asyncio
from dataclasses import dataclass
from typing import Any, Optional, AsyncIterator

from ...core import SioEnvelope, SioResult, TransportConfig, RacTransportError
from ...adapter import RacTransport, TransportStats


@dataclass
class StdioConfig:
    """STDIO transport configuration."""
    read_fd: int = 0      # stdin
    write_fd: int = 1     # stdout
    buffer_size: int = 8192
    line_delimiter: str = "\n"


class StdioTransport(RacTransport):
    """STDIO JSON-RPC 2.0 Transport.
    
    Implements line-delimited JSON-RPC 2.0 over stdin/stdout.
    Used for MCP server communication and local IPC.
    """
    
    def __init__(self, config: Optional[StdioConfig] = None):
        self.config = config or StdioConfig()
        self._connected = False
        self._stats = TransportStats()
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
    
    def id(self) -> str:
        return "stdio"
    
    def scheme(self) -> str:
        return "stdio://"
    
    def open(self, config: TransportConfig) -> None:
        """Initialize STDIO transport."""
        # In async context, create reader/writer
        self._connected = True
    
    async def open_async(self) -> None:
        """Async open for STDIO."""
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        
        # Writer
        transport, _ = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        self._writer = asyncio.StreamWriter(transport, None, None, asyncio.get_event_loop())
        self._connected = True
    
    def send(self, envelope: SioEnvelope) -> SioResult:
        """Send SIO envelope synchronously (blocking)."""
        if not self._connected:
            return SioResult.err(1, "Not connected")
        
        try:
            # Serialize envelope to JSON
            data = json.dumps({
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
            }).encode() + b"\n"
            
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            
            self._stats.bytes_sent += len(data)
            self._stats.request_count += 1
            
            # Read response (blocking)
            line = sys.stdin.buffer.readline()
            if line:
                self._stats.bytes_received += len(line)
                response = json.loads(line.decode())
                return SioResult.ok(json.dumps(response).encode())
            
            return SioResult.err(1, "No response")
        except Exception as e:
            self._stats.error_count += 1
            return SioResult.err(1, str(e))
    
    async def send_async(self, envelope: SioEnvelope) -> SioResult:
        """Send SIO envelope asynchronously."""
        if not self._connected or not self._writer:
            await self.open_async()
        
        try:
            data = json.dumps({
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
            }) + "\n"
            
            self._writer.write(data.encode())
            await self._writer.drain()
            
            self._stats.bytes_sent += len(data)
            self._stats.request_count += 1
            
            # Read response
            line = await self._reader.readline()
            if line:
                self._stats.bytes_received += len(line)
                response = json.loads(line.decode())
                return SioResult.ok(json.dumps(response).encode())
            
            return SioResult.err(1, "No response")
        except Exception as e:
            self._stats.error_count += 1
            return SioResult.err(1, str(e))
    
    async def stream(self, envelope: SioEnvelope) -> AsyncIterator[SioResult]:
        """Stream responses (for rac:stream)."""
        result = await self.send_async(envelope)
        yield result
        
        # For true streaming, would continue reading chunks
        # This is a simplified implementation
    
    def close(self) -> None:
        """Close STDIO transport."""
        self._connected = False
        if self._writer:
            self._writer.close()
    
    def is_connected(self) -> bool:
        return self._connected
    
    def stats(self) -> TransportStats:
        return self._stats


class StdioServerTransport:
    """STDIO server transport — listens for incoming JSON-RPC requests.
    
    Mirrors text-editor/io/mcp/server/core.py McpServer.run_stdio().
    """
    
    def __init__(self, handler):
        self.handler = handler
        self._running = False
    
    async def run(self) -> None:
        """Run STDIO server loop."""
        self._running = True
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        
        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break
                
                request = json.loads(line.decode())
                response = await self.handler(request)
                
                if response:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except json.JSONDecodeError:
                continue
            except Exception:
                break
    
    def stop(self) -> None:
        self._running = False


__all__ = ["StdioTransport", "StdioConfig", "StdioServerTransport"]