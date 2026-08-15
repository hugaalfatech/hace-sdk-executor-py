# -*- coding: utf-8 -*-
"""
executor_py.io.rac.contracts — RAC Method Contracts.

Canonical contracts for RAC methods: call, import, instance, ping, stream, transfer, teleport.
Mirrors text-editor/io/rac.py contracts and io/rac/src/core.rs method definitions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, AsyncIterator

from ...core import SioEnvelope, SioResult, SioType, ExecContext, FanId, ExecuteError
from .cri import resolve_fdi_target, resolve_fpi_target, resolve_ffi_target


class RacMethodName(Enum):
    """Canonical RAC method names."""
    CALL = "call"
    IMPORT = "import"
    INSTANCE = "instance"
    PING = "ping"
    STREAM = "stream"
    TRANSFER = "transfer"
    TELEPORT = "teleport"
    WATCH = "watch"
    CUSTOM = "custom"


@dataclass
class RacMethodContract:
    """Contract definition for a RAC method."""
    name: RacMethodName
    version: str = "1.0"
    status: str = "ACTIVE"  # ACTIVE | STUB | PLANNED | DEPRECATED
    description: str = ""
    
    # Input/Output schemas
    input_schema: str = ""
    output_schema: str = ""
    
    # Processing steps
    process_steps: list[str] = field(default_factory=list)
    
    # Transport affinity
    transports: list[str] = field(default_factory=list)
    
    # ROTA test count
    rota_test_count: int = 0
    
    # Known gaps
    gaps: list[str] = field(default_factory=list)


# ─── Canonical Method Contracts ───────────────────────────────────────────────

RAC_METHOD_CONTRACTS = {
    RacMethodName.CALL: RacMethodContract(
        name=RacMethodName.CALL,
        version="1.0",
        status="ACTIVE",
        description="Standard RPC call — execute capability and return result",
        input_schema="SIORequest {method: 'call', actor: '<rac_uri>', payload: {action, value, options}}",
        output_schema="SIOResponse {status, result, error}",
        process_steps=[
            "_resolve_handler() — cache lookup → URI parse → lazy import + alias",
            "execute handler with signature inspection",
            "wrap result in SIOResponse.from_actor_response()",
        ],
        transports=["FDI", "LION", "HTTP", "WS", "GRPC"],
        rota_test_count=28,
    ),
    
    RacMethodName.IMPORT: RacMethodContract(
        name=RacMethodName.IMPORT,
        version="1.0",
        status="ACTIVE",
        description="Import capability binding descriptor (not callable)",
        input_schema="SIORequest {method: 'import', actor: '<rac_uri>', payload: {action}}",
        output_schema="ImportDescriptor {invocation_ref, binding_type, handler_module, handler_function}",
        process_steps=[
            "resolve capability from URI",
            "return binding descriptor (module + function)",
        ],
        transports=["FDI"],
        rota_test_count=0,
        gaps=["Returns descriptor only, not actual callable — wire into dispatch"],
    ),
    
    RacMethodName.INSTANCE: RacMethodContract(
        name=RacMethodName.INSTANCE,
        version="1.0",
        status="STUB",
        description="Instance lifecycle management (open/execute/close)",
        input_schema="SIORequest {method: 'instance', actor: '<rac_uri>', payload: {action: 'open|execute|close', config}}",
        output_schema="InstanceResponse {instance_id, status, result}",
        process_steps=[
            "open: create instance with config",
            "execute: run operation on instance",
            "close: cleanup instance",
        ],
        transports=["FDI", "FPI"],
        rota_test_count=0,
        gaps=[
            "No open/execute/close lifecycle management",
            "Stub response only: {'status': 'instance created'}",
        ],
    ),
    
    RacMethodName.PING: RacMethodContract(
        name=RacMethodName.PING,
        version="1.0",
        status="ACTIVE",
        description="Health check and capability discovery",
        input_schema="SIORequest {method: 'ping', actor: '<rac_uri>'}",
        output_schema="PingResponse {status, latency_ms, rac_verbs_supported, server, version}",
        process_steps=[
            "measure round-trip latency",
            "return supported verbs and server info",
        ],
        transports=["FDI", "HTTP", "WS", "GRPC"],
        rota_test_count=4,
    ),
    
    RacMethodName.STREAM: RacMethodContract(
        name=RacMethodName.STREAM,
        version="1.0",
        status="ACTIVE",
        description="Streaming response (chunked NDJSON or async generator)",
        input_schema="SIORequest {method: 'stream', actor: '<rac_uri>', payload: {action, value, options}}",
        output_schema="AsyncIterator[SIOChunk] {stream_chunk, index, total_chunks, is_final}",
        process_steps=[
            "execute handler",
            "chunk response into NDJSON frames",
            "yield chunks with metadata",
        ],
        transports=["FDI", "FPI", "HTTP (SSE)", "WS"],
        rota_test_count=4,
        gaps=[
            "Current: SYNC execution then chunking, not true async",
            "Target: asyncio generator for true streaming",
        ],
    ),
    
    RacMethodName.TRANSFER: RacMethodContract(
        name=RacMethodName.TRANSFER,
        version="1.0",
        status="PLANNED",
        description="Large payload transfer (files, binaries)",
        input_schema="SIORequest {method: 'transfer', actor: '<rac_uri>', payload: {action, file_info}}",
        output_schema="TransferResponse {transfer_id, status, progress, url}",
        process_steps=[
            "initiate transfer session",
            "stream chunks via dedicated channel",
            "verify integrity on completion",
        ],
        transports=["HTTP", "WS", "GRPC"],
        rota_test_count=0,
        gaps=["Not implemented"],
    ),
    
    RacMethodName.TELEPORT: RacMethodContract(
        name=RacMethodName.TELEPORT,
        version="1.0",
        status="PLANNED",
        description="Execution migration across machines",
        input_schema="SIORequest {method: 'teleport', actor: '<rac_uri>', payload: {target_machine, state}}",
        output_schema="TeleportResponse {teleport_id, status, new_endpoint}",
        process_steps=[
            "serialize execution state",
            "transfer to target machine",
            "resume execution on target",
        ],
        transports=["GRPC", "WS"],
        rota_test_count=0,
        gaps=["Not implemented"],
    ),
    
    RacMethodName.WATCH: RacMethodContract(
        name=RacMethodName.WATCH,
        version="1.0",
        status="PLANNED",
        description="Watch/subscribe to capability events",
        input_schema="SIORequest {method: 'watch', actor: '<rac_uri>', payload: {filter, callback}}",
        output_schema="AsyncIterator[WatchEvent] {event_type, data, timestamp}",
        process_steps=[
            "register watch subscription",
            "filter events by criteria",
            "push events to subscriber",
        ],
        transports=["WS", "FPI"],
        rota_test_count=0,
        gaps=["Not implemented"],
    ),
}


# ─── Method Dispatcher ────────────────────────────────────────────────────────

class RacMethodDispatcher(ABC):
    """Abstract dispatcher for RAC methods."""
    
    @abstractmethod
    async def dispatch(self, envelope: SioEnvelope) -> SioResult:
        """Dispatch a RAC method call."""
        ...
    
    @abstractmethod
    async def dispatch_stream(self, envelope: SioEnvelope) -> AsyncIterator[SioResult]:
        """Dispatch a RAC stream call."""
        ...


class DefaultRacMethodDispatcher(RacMethodDispatcher):
    """Default RAC method dispatcher with contract validation."""
    
    def __init__(self):
        self.contracts = RAC_METHOD_CONTRACTS
    
    def get_contract(self, method: str) -> Optional[RacMethodContract]:
        """Get contract for a method name."""
        try:
            return self.contracts[RacMethodName(method)]
        except (KeyError, ValueError):
            return None
    
    def validate_method(self, method: str) -> bool:
        """Check if method is supported."""
        return method in [m.value for m in RacMethodName]
    
    async def dispatch(self, envelope: SioEnvelope) -> SioResult:
        """Dispatch based on method."""
        method = envelope.payload.get("method") if isinstance(envelope.payload, dict) else None
        if not method:
            # Extract from envelope
            method = getattr(envelope, 'method', None) or "call"
        
        contract = self.get_contract(method)
        if not contract:
            return SioResult.err(400, f"Unsupported RAC method: {method}")
        
        if contract.status == "STUB":
            return SioResult.err(501, f"Method {method} is stub: {contract.gaps}")
        elif contract.status == "PLANNED":
            return SioResult.err(501, f"Method {method} not implemented")
        
        # Delegate to specific handler
        handler_name = f"_handle_{method}"
        handler = getattr(self, handler_name, None)
        if handler:
            return await handler(envelope)
        
        return SioResult.err(500, f"No handler for method: {method}")
    
    async def dispatch_stream(self, envelope: SioEnvelope) -> AsyncIterator[SioResult]:
        """Dispatch streaming method."""
        method = envelope.payload.get("method") if isinstance(envelope.payload, dict) else "stream"
        contract = self.get_contract(method)
        
        if not contract or contract.status != "ACTIVE":
            yield SioResult.err(501, f"Streaming not supported for {method}")
            return
        
        # Delegate to stream handler
        handler_name = f"_handle_{method}_stream"
        handler = getattr(self, handler_name, None)
        if handler:
            async for chunk in handler(envelope):
                yield chunk
        else:
            # Default: execute once and yield as single chunk
            result = await self.dispatch(envelope)
            yield result
    
    # ─── Method Handlers ──────────────────────────────────────────────────────
    
    async def _handle_call(self, envelope: SioEnvelope) -> SioResult:
        """Handle rac:call."""
        # In production: resolve handler via UniversalRouter or FanRegistry
        # This is a stub implementation
        return SioResult.ok(b'{"status": "ok", "result": {}}')
    
    async def _handle_import(self, envelope: SioEnvelope) -> SioResult:
        """Handle rac:import."""
        action = envelope.payload.get("action", "") if isinstance(envelope.payload, dict) else ""
        return SioResult.ok(json.dumps({
            "invocation_ref": f"module.{action}",
            "binding_type": "FDI",
            "handler_module": f"executor_py.io.rac.cri.{action.split('.')[0]}",
            "handler_function": action.split('.')[-1] if '.' in action else action,
        }).encode())
    
    async def _handle_instance(self, envelope: SioEnvelope) -> SioResult:
        """Handle rac:instance (stub)."""
        return SioResult.ok(b'{"status": "instance created"}')
    
    async def _handle_ping(self, envelope: SioEnvelope) -> SioResult:
        """Handle rac:ping."""
        import time
        return SioResult.ok(json.dumps({
            "status": "healthy",
            "latency_ms": 0,  # Would measure actual
            "rac_verbs_supported": [m.value for m in RacMethodName],
            "server": "executor-py",
            "version": "0.1.0",
        }).encode())
    
    async def _handle_stream(self, envelope: SioEnvelope) -> SioResult:
        """Handle rac:stream (sync fallback)."""
        # Execute and chunk
        result = await self._handle_call(envelope)
        return result
    
    async def _handle_stream_stream(self, envelope: SioEnvelope) -> AsyncIterator[SioResult]:
        """Handle rac:stream (true async generator)."""
        # This would be the true async implementation
        yield SioResult.ok(b'{"stream_chunk": "chunk1", "index": 0, "total_chunks": 1, "is_final": true}')


# ─── URI Resolution Helpers ──────────────────────────────────────────────────

def resolve_rac_target(uri: str) -> dict:
    """Resolve any RAC URI to target dimensions (FDI/FPI/FFI/HTTP/GRPC/etc.)."""
    if not uri.startswith("rac://"):
        raise ValueError(f"Not a RAC URI: {uri}")
    
    rest = uri[6:]
    if "/" in rest:
        spec_part, path = rest.split("/", 1)
    else:
        spec_part, path = rest, ""
    
    parts = spec_part.split(".")
    if len(parts) < 3:
        raise ValueError(f"Invalid RAC URI spec: {spec_part}")
    
    rule, ownerspace, specs = parts[0], parts[1], parts[2]
    
    # Dispatch to spec-specific resolver
    if specs == "fdi":
        return resolve_fdi_target(uri)
    elif specs == "fpi":
        return resolve_fpi_target(uri)
    elif specs == "ffi":
        return resolve_ffi_target(uri)
    elif specs in ("http", "grpc", "ws", "pipe", "shm", "wasm"):
        return {
            "rule": rule,
            "ownerspace": ownerspace,
            "specs": specs,
            "path": path,
            "transport": specs,
            "machine": "hace-rion-machine" if specs in ("http", "grpc", "ws") else "hace-lion-machine",
        }
    else:
        return {
            "rule": rule,
            "ownerspace": ownerspace,
            "specs": specs,
            "path": path,
            "transport": "unknown",
            "machine": "unknown",
        }


import json

__all__ = [
    "RacMethodName",
    "RacMethodContract",
    "RAC_METHOD_CONTRACTS",
    "RacMethodDispatcher",
    "DefaultRacMethodDispatcher",
    "resolve_rac_target",
]