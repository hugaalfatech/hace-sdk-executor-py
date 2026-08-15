# -*- coding: utf-8 -*-
"""
executor_py.adapter — LION/RION Adapter Interface

Mirrors `hace/io/rac/src/core.rs` (RacTransport trait) and the transport
resolution in racor.rs.

Adapters bind native local protocol (CRI/FDI/FPI/FFI/MCP) to the RAC SIO
envelope. They implement the transport contract for a specific protocol family.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .core import SioEnvelope, SioResult, SioType, RacTransportError, TransportConfig


# Backward-compatible alias
TransportError = RacTransportError


# ─── Transport Error ───────────────────────────────────────────────────────────

@dataclass
class TransportStats:
    """Transport statistics — mirrors TransportStats in io/rac/src/core.rs."""
    bytes_sent: int = 0
    bytes_received: int = 0
    request_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0.0


# ─── RacTransport Trait ─────────────────────────────────────────────────────────

class RacTransport(ABC):
    """The canonical trait that ALL RAC transports must implement.

    Mirrors `RacTransport` trait in `io/rac/src/core.rs`.

    This follows the OS kernel driver pattern:
    - hace/io/rac* = transport DNA (like kernel drivers)
    - hace/me/race = RAC execution runtime (like OS kernel)
    - Executor particles = consumers (like user applications)

    Implementors:
    - LocalNativeAdapter — CRI/FDI/FPI (same-process FFI)
    - LocalIpcAdapter — UDS/named pipe IPC
    - HttpBridgeAdapter — HTTP/JSON bridge (RION)
    - GrpcBridgeAdapter — gRPC bridge (RION)
    - McpAdapter — MCP JSON-RPC over stdio
    """

    @abstractmethod
    def id(self) -> str:
        """Transport identifier (e.g., 'cri', 'fdi', 'mcp', 'http')."""
        ...

    @abstractmethod
    def scheme(self) -> str:
        """URI scheme (e.g., 'rac://', 'mcp://', 'http://')."""
        ...

    @abstractmethod
    def open(self, config: TransportConfig) -> None:
        """Initialize the transport."""
        ...

    @abstractmethod
    def send(self, envelope: SioEnvelope) -> SioResult:
        """Send an SIO envelope and receive result."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the transport."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        ...

    @abstractmethod
    def stats(self) -> TransportStats:
        """Get transport statistics."""
        ...


# ─── Concrete Adapters ──────────────────────────────────────────────────────────

class LocalNativeAdapter(RacTransport):
    """FDI/FFI native adapter — mirrors RacinTransport (same-process FFI).

    Used for rac://cri.* and rac://fdi.* URIs.
    """

    def __init__(self):
        self._connected = False
        self._stats = TransportStats()

    def id(self) -> str:
        return "fdi"

    def scheme(self) -> str:
        return "rac://"

    def open(self, config: TransportConfig) -> None:
        self._connected = True

    def send(self, envelope: SioEnvelope) -> SioResult:
        # In production: actual FFI call
        self._stats.request_count += 1
        return SioResult.ok(b'{"status":"ok"}')

    def close(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def stats(self) -> TransportStats:
        return self._stats


class StdioIpcAdapter(RacTransport):
    """STDIO IPC adapter — mirrors IPC transport via process stdin/stdout.

    Used by MCP server (io/mcp/server/core.py run_stdio).
    """

    def __init__(self):
        self._connected = False
        self._stats = TransportStats()

    def id(self) -> str:
        return "ipc"

    def scheme(self) -> str:
        return "stdio://"

    def open(self, config: TransportConfig) -> None:
        self._connected = True

    def send(self, envelope: SioEnvelope) -> SioResult:
        # In production: write JSON-RPC to subprocess stdin, read stdout
        self._stats.request_count += 1
        return SioResult.ok(b'{"jsonrpc":"2.0","result":{}}')

    def close(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def stats(self) -> TransportStats:
        return self._stats
