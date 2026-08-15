# Module Base Class
# FES Layer: MODULE (Atomic Capability Implementation)
# Authority: CSA-sealed

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..core import (
    ExecuteParticle, ExecContext, ExecInput, ExecOutput, SepiProof, ExecuteError,
    FanId, FanCapability, SioStatus, EnginePart, FesLayer
)
from ..evidence import build_proof


@dataclass
class ModuleConfig:
    """Module configuration — Atomic Capability descriptor."""
    uri: str                              # Canonical URI (e.g., rac://cri.hace.fdi/hace/executor-py/io/rac/cri/fdi)
    name: str                             # Short name (e.g., fdi-executor)
    parent_executor_uri: str              # Parent Executor URI
    layer: FesLayer = FesLayer.MODULE     # Always MODULE
    specs: str = "fdi"                    # fdi | fpi | ffi | wasm | ...
    machine: str = "hace-lion-machine"    # Target machine binding
    transport: str = "fdi"                # Transport spec

    def __post_init__(self):
        """Parse specs/machine/transport from URI if not explicitly set."""
        if self.specs == "fdi" and self.uri:
            # Extract specs from URI pattern: rac://cri.hace.fdi/...
            rest = self.uri.replace("rac://", "")
            if "/" in rest:
                spec_part = rest.split("/")[0]
            else:
                spec_part = rest
            parts = spec_part.split(".")
            if len(parts) >= 3:
                parsed_specs = parts[-1]
                parsed_machine = "hace-lion-machine" if parsed_specs in ("fdi",) else "hace-rion-machine"
                if self.specs == "fdi":
                    self.specs = parsed_specs
                if self.machine == "hace-lion-machine" and parsed_specs == "fpi":
                    self.machine = parsed_machine
                if self.transport == "fdi":
                    self.transport = parsed_specs


class ExecutorModule(ExecuteParticle):
    """
    Base class for all Executor Modules (Atomic Capabilities).
    
    FES Layer: MODULE
    A Module is an atomic capability implementation.
    
    Properties:
    - Single responsibility
    - IPO compliant (Input → Process → Output)
    - Composed by Executor
    
    Module CANNOT run independently.
    Module is invoked by Executor via ExecuteParticle.execute().
    """
    
    def __init__(self, config: ModuleConfig):
        self.config = config
        self.name = config.name
        self.uri = config.uri
        self.parent_executor_uri = config.parent_executor_uri
        self.specs = config.specs
        self.machine = config.machine
        self.transport = config.transport
        
        # FES EnginePart descriptor
        self.engine_part = EnginePart(
            uri=self.uri,
            name=self.name,
            layer=FesLayer.MODULE,
            parent_uri=self.parent_executor_uri,
            dna={
                "trait": "ExecuteParticle",
                "struct": self.__class__.__name__,
                "specs": self.specs,
                "machine": self.machine,
                "transport": self.transport,
            },
        )
        
        # Capability registration
        self._capabilities: dict[str, Any] = {}
    
    @abstractmethod
    def execute(self, input: ExecInput, ctx: ExecContext) -> ExecOutput:
        """
        Execute the module capability.
        
        Args:
            input: ExecInput with action + payload + headers + context
            ctx: ExecContext with trace_id, security_tier, etc.
        
        Returns:
            ExecOutput with result + SepiProof evidence
        """
        ...
    
    def register_method(self, name: str, handler: Any) -> None:
        """Register a method handler for this module."""
        self._capabilities[name] = handler
    
    def get_method(self, name: str) -> Optional[Any]:
        """Get a method handler by name."""
        return self._capabilities.get(name)
    
    def list_methods(self) -> list[str]:
        """List all registered method names."""
        return list(self._capabilities.keys())
    
    def fan_id(self) -> Optional[FanId]:
        """Return the FanId this module belongs to."""
        return FanId(id=f"hace-executor-py-{self.specs}")


# ─── Specialized Module Base Classes ─────────────────────────────────────────

class FdiModule(ExecutorModule):
    """
    FDI Module — Wired transport (USB/cable/autoload motif).
    
    Specs: fdi
    Machine: hace-lion-machine
    Transport: Ffi (in-process)
    
    Methods: autoload, connect, disconnect, send, recv
    """
    
    def __init__(self, config: ModuleConfig):
        # Force FDI specs
        config.specs = "fdi"
        config.machine = "hace-lion-machine"
        config.transport = "fdi"
        super().__init__(config)
        
        # Register default FDI methods
        self.register_method("autoload", self.method_autoload)
        self.register_method("connect", self.method_connect)
        self.register_method("disconnect", self.method_disconnect)
        self.register_method("send", self.method_send)
        self.register_method("recv", self.method_recv)
    
    def method_autoload(self, ctx: ExecContext, **kwargs) -> dict:
        """Autoload executor module from FDI URI (plug in cable)."""
        return {"autoload": True, "uri": kwargs.get("uri", ""), "connected": True}
    
    def method_connect(self, ctx: ExecContext, **kwargs) -> dict:
        """Connect to FDI endpoint (cable attach)."""
        return {"connected": True}
    
    def method_disconnect(self, ctx: ExecContext, **kwargs) -> dict:
        """Disconnect FDI endpoint (cable detach)."""
        return {"connected": False}
    
    def method_send(self, ctx: ExecContext, **kwargs) -> dict:
        """Send data over FDI wire."""
        data = kwargs.get("data", "")
        return {"sent": len(data), "status": "ok"}
    
    def method_recv(self, ctx: ExecContext, **kwargs) -> dict:
        """Receive data over FDI wire."""
        return {"data": "", "status": "ok", "received": 0}

    def execute(self, input: ExecInput, ctx: ExecContext) -> ExecOutput:
        """Execute the FDI module capability."""
        return ExecOutput(result={"fdi": "ready"}, status=SioStatus.SUCCESS)


class FpiModule(ExecutorModule):
    """
    FPI Module — Wireless transport (Bluetooth/NFC motif).
    
    Specs: fpi
    Machine: hace-rion-machine
    Transport: HostCall (host function call)
    
    Methods: discover, pair, unpair, invoke, broadcast
    """
    
    def __init__(self, config: ModuleConfig):
        # Force FPI specs
        config.specs = "fpi"
        config.machine = "hace-rion-machine"
        config.transport = "fpi"
        super().__init__(config)
        
        # Register default FPI methods
        self.register_method("discover", self.method_discover)
        self.register_method("pair", self.method_pair)
        self.register_method("unpair", self.method_unpair)
        self.register_method("invoke", self.method_invoke)
        self.register_method("broadcast", self.method_broadcast)
    
    def method_discover(self, ctx: ExecContext, **kwargs) -> dict:
        """Wireless service discovery (bluetooth scan)."""
        return {"endpoints": [], "count": 0}
    
    def method_pair(self, ctx: ExecContext, **kwargs) -> dict:
        """Pair with wireless endpoint (bluetooth pairing / NFC touch)."""
        return {"paired": True, "session_id": "auto-generated"}
    
    def method_unpair(self, ctx: ExecContext, **kwargs) -> dict:
        """Unpair from wireless endpoint (bluetooth disconnect)."""
        return {"paired": False}
    
    def method_invoke(self, ctx: ExecContext, **kwargs) -> dict:
        """Invoke a remote procedure over the wireless link."""
        return {"result": None, "method": kwargs.get("method", "")}
    
    def method_broadcast(self, ctx: ExecContext, **kwargs) -> dict:
        """Broadcast to multiple wireless listeners (multicast)."""
        return {"broadcast": True, "method": kwargs.get("method", ""), "listeners": 0}

    def execute(self, input: ExecInput, ctx: ExecContext) -> ExecOutput:
        """Execute the FPI module capability."""
        return ExecOutput(result={"fpi": "ready"}, status=SioStatus.SUCCESS)


class LibraryModule:
    """
    Library / Pure Algorithm Module.
    
    FES Layer: LIBRARY (Pure Algorithm/Data)
    NOT a runtime component — no ExecuteParticle, no IPO.
    Just pure functions/classes used by Executor/Module/Addon.
    
    Examples: rope, myers-diff, utf8, line-index, ast
    """
    
    def __init__(self, name: str, version: str = "0.1.0"):
        self.name = name
        self.version = version
    
    def __repr__(self) -> str:
        return f"LibraryModule({self.name} v{self.version})"


__all__ = ["ExecutorModule", "ModuleConfig", "FdiModule", "FpiModule", "LibraryModule"]
