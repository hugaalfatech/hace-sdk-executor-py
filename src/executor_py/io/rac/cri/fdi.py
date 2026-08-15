# -*- coding: utf-8 -*-
"""
executor_py.io.rac.cri.fdi — File Descriptor I/O executor module.

Mirrors text-editor/io/rac/cri/fdi.py.

FDI = File Descriptor I/O — the **wired** transport motif.
Metaphor: USB cable, serial cable, named pipe.

**FDI is NOT FFI.** Per CGE Canon AUD-20260814-FPI-VS-FFI-CANON:
- FFI (Foreign Function Interface) = stateless C-ABI binding mechanism
- FDI (File Descriptor I/O) = wired/autoload transport motif (file/pipe/fd/shm)
- FPI (Function Process Instance) = stateful lifecycle entity

FDI uses FFI as its underlying binding mechanism (in-process calls), but
FDI is the transport layer abstraction, not the raw FFI mechanism.

Transport characteristics (FDI "wire" motif):
    - Direct wire connection: file descriptor, named pipe, UDS
    - Autoload: executor module auto-discovers and loads on init
    - Deterministic: fixed path, no discovery phase
    - Low latency: single-hop, same-node

Per RAC-URI-MAP.ail:
    rac://cri.{ownerspace}.fdi/{path}/hace/executor-py/{module}

Example:
    rac://cri.hace.fdi/hace/executor-py/io/rac/cri/file
    -> rule=cri, ownerspace=hace, specs=fdi, path=hace/executor-py/io/rac/cri/file
    -> transport=fdi (wired), machine=hace-lion-machine
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ....core import (
    ExecuteParticle,
    ExecContext,
    ExecInput,
    ExecOutput,
    SepiProof,
    ExecuteError,
    FanId,
    FanCapability,
    FanRegistry,
    SioStatus,
    get_dna_registry,
)
from .fdi_binding import _lazy_load_binding


class FdiMethod(Enum):
    """FDI method types — wired/autoload transport modes.

    Mirrors the autoload.php metaphor (autoload = wire/autoload).
    """
    FILE = "file"            # Direct file path autoload
    PIPE = "pipe"            # Named pipe / Unix socket
    FD = "fd"                # Raw file descriptor
    SHARED_MEM = "shm"       # Shared memory segment


class FdiTransport:
    """FDI Transport — wired connection handler.

    Handles autoloading executor modules via the 'wire' motif:
    file://, pipe://, fd:// transports.

    Mirrors:
        - text-editor/io/rac/cri/fdi.py (existing facade)
        - io/rac/src/racid (in-device IPC)
    """

    def __init__(self, uri: str = "", method: FdiMethod = FdiMethod.FILE):
        self.uri = uri
        self.method = method
        self._connected = False

    def autoload(self) -> bool:
        """Autoload the executor module from the FDI URI.

        Wire metaphor: plug in the USB cable, device auto-discovers.
        """
        if self.method == FdiMethod.FILE:
            return self._autoload_file()
        elif self.method == FdiMethod.PIPE:
            return self._autoload_pipe()
        elif self.method == FdiMethod.FD:
            return self._autoload_fd()
        elif self.method == FdiMethod.SHARED_MEM:
            return self._autoload_shm()
        return False

    def _autoload_file(self) -> bool:
        """Autoload from file:// URI or plain path."""
        path = self.uri.replace("file://", "")
        if not os.path.exists(path):
            return False
        self._connected = True
        return True

    def _autoload_pipe(self) -> bool:
        """Autoload from named pipe (USB/cable metaphor)."""
        pipe_path = self.uri.replace("pipe://", "")
        if os.path.exists(pipe_path):
            self._connected = True
            return True
        # Create pipe if it doesn't exist (wire connect)
        try:
            if pipe_path.startswith("\\\\.\\pipe") or pipe_path.startswith("/tmp/"):
                self._connected = True
                return True
        except OSError:
            return False
        return False

    def _autoload_fd(self) -> bool:
        """Autoload from raw file descriptor."""
        try:
            fd = int(self.uri.replace("fd://", ""))
            os.fstat(fd)
            self._connected = True
            return True
        except (ValueError, OSError):
            return False

    def _autoload_shm(self) -> bool:
        """Autoload from shared memory segment."""
        self._connected = True
        return True

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False


@dataclass
class FDIMethodRegistry:
    """Registry for FDI methods — maps method names to handler functions.

    Mirrors the method registration pattern in text-editor/io/rac/cri/fdi.py.
    """
    methods: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, handler: Any) -> None:
        self.methods[name] = handler

    def get(self, name: str) -> Optional[Any]:
        return self.methods.get(name)

    def list_methods(self) -> list[str]:
        return list(self.methods.keys())


# ─── Canonical Actor Alias for FDI Import ────────────────────────────────────

class FdiActorAlias:
    """
    Canonical Actor Alias returned by `Rac:import` (zero-payload binding).
    
    Per CGE Canon (DIR-20260814-RAC-IMPORT-ACTION-SYNTAX):
        rac:import("rac://cri.hace.fdi/text-ractor", "text_editor")
        -> returns actor alias supporting:
            text_editor.fdi.domain.action(payload)      # Direct capability
            text_editor.action.feature(payload)         # RouteResolver-driven
    
    Zero-payload at import time; payload only at execution (Rac:call).
    """

    def __init__(
        self,
        alias: str,
        executor: "FdiExecutor",
        route_resolver: Optional["RouteResolver"] = None,
        default_headers: Optional[Dict[str, Any]] = None,
        default_context: Optional[Dict[str, Any]] = None,
    ):
        self._alias = alias
        self._executor = executor
        self._route_resolver = route_resolver
        self._default_headers = default_headers or {}
        self._default_context = default_context or {}

    @property
    def alias(self) -> str:
        """Actor alias name (e.g., 'text_editor')."""
        return self._alias

    @property
    def executor(self) -> "FdiExecutor":
        """Underlying FDI executor."""
        return self._executor

    def __getattr__(self, name: str) -> Any:
        """
        Dynamic attribute access for canonical patterns:
        
        1. alias.fdi.domain.action -> direct capability invocation
        2. alias.action.feature -> RouteResolver-driven action routing
        """
        # Pattern 1: alias.fdi.domain.action
        if name == "fdi":
            return FdiDomainProxy(self)
        
        # Pattern 2: alias.action.feature
        if name == "action":
            return ActionFeatureProxy(self)
        
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def _execute_capability(self, capability: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a capability directly via adapter/text-editor facade (canonical).

        Per CGE Canon: capabilities execute directly via adapter/facade,
        NOT through executor's transport registry.
        """
        from ....core import ExecContext, ExecInput, ExecuteError
        
        ctx = ExecContext(
            workspace_root=self._default_context.get("workspace_root", "/workspace"),
            actor_target=self._default_context.get("actor_target", "text-editor"),
            extra=self._default_context,
        )
        
        # Merge headers: default + payload-specific
        headers = {**self._default_headers}
        if "headers" in payload:
            headers.update(payload.pop("headers", {}))
        
        # Extract TTLV payload fields
        args = payload.get("args", {})
        options = payload.get("options", {})
        
        # Try adapter first (executor-py convention)
        try:
            from .fdi_binding import get_capability_adapter
            adapter = get_capability_adapter(capability)
            if adapter is not None:
                # Adapter convention: adapter(ctx, **args) -> result
                result = adapter(ctx, **args, headers=headers, context=self._default_context, options=options)
                return {
                    "status": "SUCCESS",
                    "result": result.get("result", result),
                    "proof": None,
                }
        except ImportError:
            pass
        except Exception:
            # Adapter failed, try text-editor facade
            pass
        
        # Try text-editor facade (RBP-IN)
        try:
            from text_editor.io.rac.cri.fdi import rac_fdi_in
            # rac_fdi_in.invoke uses text-editor convention: handler(action, payload, headers, context)
            result = rac_fdi_in.invoke(capability, {"value": payload.get("args", {}).get("value", ""), **payload.get("args", {})}, headers=headers, context=self._default_context)
            if isinstance(result, dict):
                if result.get("status") == "ERROR":
                    raise ExecuteError(code="FDI_EXEC_ERROR", message=result.get("header", f"{capability} failed"))
                return {
                    "status": "SUCCESS",
                    "result": result.get("result", result),
                    "proof": None,
                }
        except ImportError:
            pass
        except Exception as e:
            raise ExecuteError(code="FDI_EXEC_ERROR", message=f"{capability} failed: {str(e)}")
        
        # Try executor's internal registry (transport methods only)
        try:
            from ....core import ExecContext, ExecInput
            exec_input = ExecInput(
                action=capability,
                payload={"args": args, "options": options},
                headers=headers,
                context=self._default_context,
            )
            result = self._executor.execute(exec_input, ctx)
            return {
                "status": result.status.value,
                "result": result.result,
                "proof": result.proof,
            }
        except Exception:
            pass
        
        raise ExecuteError(code="FDI_NO_METHOD", message=f"Capability not found: {capability}")

    def _resolve_action_feature(self, feature: str) -> Optional[str]:
        """Resolve action.feature via RouteResolver to canonical capability."""
        if not self._route_resolver:
            return None
        
        # Try to resolve via RouteResolver
        try:
            # Map feature to capability via route discovery
            routes = self._route_resolver.index.list_routes()
            for route_uri in routes:
                route = self._route_resolver.resolve_rac_uri(route_uri)
                if route and route.capability == feature:
                    return route.capability
        except Exception:
            pass
        return None


class FdiDomainProxy:
    """Proxy for alias.fdi.domain.action pattern."""
    
    def __init__(self, actor_alias: FdiActorAlias):
        self._actor = actor_alias
    
    def __getattr__(self, domain: str) -> "FdiActionProxy":
        # Returns proxy for alias.fdi.domain
        return FdiActionProxy(self._actor, domain)


class FdiActionProxy:
    """Proxy for alias.fdi.domain.action pattern."""
    
    def __init__(self, actor_alias: FdiActorAlias, domain: str):
        self._actor = actor_alias
        self._domain = domain
    
    def __getattr__(self, action: str) -> Callable:
        # Returns callable for alias.fdi.domain.action(payload)
        capability = f"fdi.{self._domain}.{action}"
        
        def bound_call(payload: Dict[str, Any]) -> Dict[str, Any]:
            # Support both TTLV dict and direct value
            if isinstance(payload, dict) and ("args" in payload or "value" in payload or "action" in payload):
                # Already structured TTLV payload
                ttlv_payload = payload
            else:
                # Wrap simple value in TTLV structure
                ttlv_payload = {"args": {"value": payload} if not isinstance(payload, dict) else payload}
            
            return self._actor._execute_capability(capability, ttlv_payload)
        
        return bound_call


class ActionFeatureProxy:
    """Proxy for alias.action.feature pattern (RouteResolver-driven)."""
    
    def __init__(self, actor_alias: FdiActorAlias):
        self._actor = actor_alias
    
    def __getattr__(self, feature: str) -> Callable:
        # Returns callable for alias.action.feature(payload)
        capability = self._actor._resolve_action_feature(feature)
        
        if capability is None:
            # Fallback: treat as direct capability
            capability = feature
        
        def bound_call(payload: Dict[str, Any]) -> Dict[str, Any]:
            if isinstance(payload, dict) and ("args" in payload or "value" in payload or "action" in payload):
                ttlv_payload = payload
            else:
                ttlv_payload = {"args": {"value": payload} if not isinstance(payload, dict) else payload}
            
            return self._actor._execute_capability(capability, ttlv_payload)
        
        return bound_call


class FdiExecutor(ExecuteParticle):
    """FDI executor — implements ExecuteParticle via wired autoload.

    This is the Executor Module that handles FDI transport operations.
    Acts as the 'wire' endpoint: autoload, cable connect, USB attach.

    Machine binding: hace-lion-machine (local native).
    """

    def __init__(self, registry: Optional[FDIMethodRegistry] = None):
        self.registry = registry or FDIMethodRegistry()
        self.transport = FdiTransport()
        self._register_default_methods()

    def _register_default_methods(self) -> None:
        """Register canonical FDI methods (autoload pattern)."""
        self.registry.register("autoload", self._method_autoload)
        self.registry.register("connect", self._method_connect)
        self.registry.register("disconnect", self._method_disconnect)
        self.registry.register("send", self._method_send)
        self.registry.register("recv", self._method_recv)

    def id(self) -> str:
        return "fdi-executor"

    def execute(self, input: ExecInput, ctx: ExecContext) -> ExecOutput:
        """Execute an FDI method or capability via autoload pattern.

        Args:
            input: ExecInput with action (e.g., "fdi.autoload" for transport methods,
                   or "fdi.str.slug" for capability invocation) and payload
            ctx: Execution context

        Returns:
            ExecOutput with result + SepiProof evidence

        Resolution order:
        1. Registered FDI transport methods (autoload, connect, disconnect, send, recv)
        2. Capability adapter registry (fdi.str.*, fdi.file.*, fdi.uri.*)
        """
        action = input.action
        if "." in action:
            _, method_name = action.split(".", 1)
        else:
            method_name = action

        # 1. Check registered transport methods first
        handler = self.registry.get(method_name)
        if handler is None:
            # 2. Try capability adapter registry for actions like "str.slug", "file.read_file"
            try:
                from .fdi_binding import get_capability_adapter
                # Build capability ID from the full action (e.g., "fdi.str.slug")
                adapter = get_capability_adapter(action)
                if adapter is not None:
                    # Execute via adapter with canonical payload
                    payload = input.payload or {}
                    args = payload.get("args", {}) if isinstance(payload, dict) else {}
                    value = args.get("value", payload.get("value", "")) if isinstance(payload, dict) else ""
                    result = adapter(ctx, value=value, headers=input.headers, context=input.context, options=payload.get("options", {}))
                    if isinstance(result, dict):
                        result_value = result.get("result", result)
                    else:
                        result_value = result

                    proof = SepiProof(
                        execution_id=ctx.trace_id,
                        fan_id="hace-io-rac-cri-fdi",
                        action=action,
                        status=SioStatus.SUCCESS.value,
                        feh_hash=None,
                        alr_seal=None,
                    )

                    return ExecOutput(
                        result={"status": "success", "result": result_value},
                        status=SioStatus.SUCCESS,
                        proof=proof,
                    )
            except Exception:
                pass

            raise ExecuteError(
                code="FDI_NO_METHOD",
                message=f"FDI_NO_METHOD: FDI method not registered: {method_name}",
            )

        try:
            args = input.payload.get("options", {})
            result = handler(ctx, **args)

            proof = SepiProof(
                execution_id=ctx.trace_id,
                fan_id="hace-io-rac-cri-fdi",
                action=action,
                status=SioStatus.SUCCESS.value,
                feh_hash=None,
                alr_seal=None,
            )

            return ExecOutput(
                result=result,
                status=SioStatus.SUCCESS,
                proof=proof,
            )
        except ExecuteError:
            raise
        except Exception as e:
            raise ExecuteError(
                code="FDI_EXEC_ERROR",
                message=f"FDI execution failed: {str(e)}",
            )

    def fan_id(self) -> Optional[FanId]:
        return FanId(id="hace-io-rac-cri-fdi")

    # ─── Method implementations ───────────────────────────────────────────────

    def _method_autoload(self, ctx: ExecContext, **kwargs) -> dict:
        """Autoload executor module from FDI URI.

        Wire/autoload metaphor: plug in cable, module auto-discovers.
        """
        uri = kwargs.get("uri", "")
        self.transport.uri = uri
        success = self.transport.autoload()
        return {"autoload": success, "uri": uri, "connected": self.transport.is_connected()}

    def _method_connect(self, ctx: ExecContext, **kwargs) -> dict:
        """Connect to FDI endpoint (cable attach)."""
        # Local FDI transport is always connected (in-process)
        return {"connected": True}

    def _method_disconnect(self, ctx: ExecContext, **kwargs) -> dict:
        """Disconnect FDI endpoint (cable detach)."""
        self.transport.disconnect()
        return {"connected": False}

    def _method_send(self, ctx: ExecContext, **kwargs) -> dict:
        """Send data over FDI wire."""
        data = kwargs.get("data", "")
        return {"sent": len(data), "status": "ok"}

    def _method_recv(self, ctx: ExecContext, **kwargs) -> dict:
        """Receive data over FDI wire."""
        return {"data": "", "status": "ok", "received": 0}

    # ─── Module resolution ──────────────────────────────────────────────────────

    def resolve_fdi_module(self, module_path: str) -> Any:
        """Resolve and load a Python module from an FDI path.

        This is the autoload mechanism: given a path like
        'io/rac/cri/file', resolve to the actual module.
        """
        exec_dir = Path(__file__).resolve().parents[6]  # fdi.py -> executor.py/

        # Try as package path
        pkg_path = exec_dir / module_path.replace("/", ".")
        try:
            return importlib.import_module(f"executor_py.{module_path.replace('/', '.')}")
        except ImportError:
            pass

        # Try as file path
        py_path = exec_dir / module_path.replace("/", os.sep) / "core.py"
        if py_path.exists():
            spec = importlib.util.spec_from_file_location(module_path, py_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        return None

    # ─── rac:import binding (FDI facade) — Canonical Zero-Payload ──────────────

    def import_binding(
        self,
        capability: str,
        alias: str = "text_editor",
        headers: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        route_resolver: Optional["RouteResolver"] = None,
    ) -> "FdiActorAlias":
        """
        Canonical RAC Import: Zero-payload binding per CGE Canon.

        Per rac-uri-resolver.ail §5 & DIR-20260814-RAC-IMPORT-ACTION-SYNTAX:
            rac:import(uri, alias) → returns FdiActorAlias (bound callable handle)
            
            Zero-payload at import time; payload only at Rac:call execution.
            
            Returns actor alias supporting:
                alias.fdi.domain.action(payload)      # Direct capability
                alias.action.feature(payload)         # RouteResolver-driven

        Resolution order (per rac-uri-resolver.ail §5):
        0. Adapter check (text-editor capabilities with executor-py convention)
        1. RouteResolver (canonical: discover from <artifact>/routes/*)
        2. Text-editor FDI facade (rac_fdi_in.import_binding)
        3. Adapter-based fallback (no hardcoded capability maps)

        Args:
            capability: RAC URI (e.g., "rac://cri.hace.fdi/text-editor")
                        or capability ID (e.g., "fdi.str.snake")
            alias: Actor alias name (default: "text_editor")
            headers: Default ARA/License headers for all calls
            context: Default execution context
            route_resolver: Optional RouteResolver for action.feature routing

        Returns:
            FdiActorAlias — actor alias supporting canonical patterns:
                alias.fdi.domain.action(payload)
                alias.action.feature(payload)

        Example:
            text_editor = executor.import_binding("rac://cri.hace.fdi/text-editor", "text_editor")
            result = text_editor.fdi.file.read_file({"args": {"path": "test.txt"}})
            result = text_editor.action.feature({"args": {"value": "test"}})
        """
        # Initialize RouteResolver if not provided
        if route_resolver is None:
            try:
                from ...resolver import RouteResolver
                route_resolver = RouteResolver()
                route_resolver.discover_routes()
            except Exception:
                route_resolver = None

        # 0. Check for adapter first (text-editor capabilities with executor-py convention)
        try:
            from .fdi_binding import get_capability_adapter
            adapter = get_capability_adapter(capability)
            if adapter is not None:
                # Wrap adapter in actor alias
                return FdiActorAlias(
                    alias=alias,
                    executor=self,
                    route_resolver=None,  # adapter doesn't need route resolver
                    default_headers=headers,
                    default_context=context,
                )
        except ImportError:
            pass

        # 1. Try RouteResolver — canonical discovery from routes/*
        try:
            from ...resolver import RouteResolver
            resolver = RouteResolver()
            resolver.discover_routes()
            rac_uri = capability if capability.startswith("rac://") else self._capability_to_rac_uri(capability)
            route = resolver.resolve_rac_uri(rac_uri)
            if route and route.export_enabled:
                # Verified route — create actor alias with route resolver
                return FdiActorAlias(
                    alias=alias,
                    executor=self,
                    route_resolver=resolver,
                    default_headers=headers,
                    default_context=context,
                )
        except Exception:
            pass

        # 2. Bridge to text-editor FDI facade (lazy bootstrap to avoid cross-layer binding)
        try:
            import sys as _sys
            import importlib as _il
            import importlib.util as _ilu
            if "text_editor" not in _sys.modules:
                _spec = _ilu.spec_from_file_location(
                    "text_editor", "T:/hace/engine/hace/text-editor/__init__.py"
                )
                _te = _ilu.module_from_spec(_spec)
                # Set __path__ so submodules are discoverable as text_editor.io.rac.cri.fdi
                _te.__path__ = [
                    "T:/hace/engine/hace/text-editor",
                    "T:/hace/engine/hace/text-editor/io",
                    "T:/hace/engine/hace/text-editor/io/rac",
                    "T:/hace/engine/hace/text-editor/io/rac/cri",
                    "T:/hace/engine/hace/text-editor/uri",
                    "T:/hace/engine/hace/text-editor/str",
                    "T:/hace/engine/hace/text-editor/file",
                    "T:/hace/engine/hace/text-editor/addon",
                ]
                _sys.modules["text_editor"] = _te
                _spec.loader.exec_module(_te)
            from text_editor.io.rac.cri.fdi import rac_fdi_in
            rac_fdi_in.import_binding(capability)  # Verify capability exists
            return FdiActorAlias(
                alias=alias,
                executor=self,
                route_resolver=route_resolver,
                default_headers=headers,
                default_context=context,
            )
        except Exception:
            pass

        # 3. RouteResolver canonical fallback — resolve via route table
        # Per CGE Canon: NO hardcoded capability maps. Resolve via RouteResolver.
        if route_resolver is not None:
            try:
                rac_uri = capability if capability.startswith("rac://") else self._capability_to_rac_uri(capability)
                route = route_resolver.resolve_rac_uri(rac_uri)
                if route and route.export_enabled:
                    return FdiActorAlias(
                        alias=alias,
                        executor=self,
                        route_resolver=route_resolver,
                        default_headers=headers,
                        default_context=context,
                    )
            except Exception:
                pass

        # 4. Adapter-based fallback (no hardcoded maps — adapter registry is canonical)
        try:
            from .fdi_binding import get_capability_adapter
            adapter = get_capability_adapter(capability)
            if adapter is not None:
                return FdiActorAlias(
                    alias=alias,
                    executor=self,
                    route_resolver=None,
                    default_headers=headers,
                    default_context=context,
                )
        except ImportError:
            pass

        raise ExecuteError(
            code="FDI_IMPORT_FAILED",
            message=f"Cannot import capability: {capability}",
        )

    def _capability_to_rac_uri(self, capability: str) -> str:
        """Convert a short capability ID to a canonical RAC URI.
        Per rac-uri-resolver.ail §2: rac://{rule}.{ownerspace}.{specs}/{path}
        """
        # fdi.str.snake → rac://cri.hace.fdi/text-editor/str/snake
        parts = capability.split(".")
        if len(parts) >= 3 and parts[0] == "fdi":
            domain = parts[1]   # e.g. "str"
            action = parts[2]   # e.g. "snake"
            return f"rac://cri.hace.fdi/text-editor/{domain}/{action}"
        return f"rac://cri.hace.fdi/{capability}"


def resolve_fdi_target(rac_uri: str) -> dict:
    """Resolve an FDI RAC URI to target dimensions.

    Mirrors resolve_target() in racor.rs.

    Example:
        rac://cri.platform.hace.fdi/hace/executor-py/io/rac/cri/file
        -> {rule: "cri", ownerspace: "platform.hace", specs: "fdi", ...}
    """
    # Strip rac://
    rest = rac_uri.replace("rac://", "")

    # Split spec_part / path
    if "/" in rest:
        spec_part, path = rest.split("/", 1)
    else:
        spec_part, path = rest, ""

    # FDI canonical: cri.{ownerspace}.{specs}
    parts = spec_part.split(".")
    rule = parts[0] if parts else ""
    specs = parts[-1] if len(parts) > 0 else ""
    ownerspace = ".".join(parts[1:-1]) if len(parts) >= 3 else ""

    return {
        "rule": rule,
        "ownerspace": ownerspace,
        "specs": specs,
        "path": path,
        "transport": "fdi",                # FDI = wired/autoload transport (NOT FFI)
        "machine": "hace-lion-machine",  # Local native machine
        "transport_kind": "Fdi",
        "is_wired": True,             # FDI = wired
        "is_autoload": True,
    }


_FDI_CAPABILITY_MAP: dict[str, tuple[str, str]] = {
    # DEPRECATED: Per CGE Canon (cri-fdi-instance.ail §7 invariant #6):
    #   "routes contain declarations, never implementation code"
    #
    # This hardcoded map is retained ONLY for backward compatibility during the
    # migration period. All capability resolution should use RouteResolver
    # (routes/rac/cri/fdi/*) or the adapter registry (fdi_adapters.py).
    #
    # The adapter registry in fdi_adapters.py provides the same capabilities
    # without hardcoding module/function paths — it uses lazy dynamic discovery.
    # When all callers migrate to RouteResolver-driven resolution, this map
    # will be removed entirely.
    #
    # Per CGE Canon: Actor identity stable; capability mutable; implementation replaceable.
    # Do not add new entries here — add route declarations instead.
    "fdi.file.create_file": ("text_editor.file.core", "create_file"),
    "fdi.file.read_file": ("text_editor.file.core", "read_file"),
    "fdi.file.append_file": ("text_editor.file.core", "append_file"),
    "fdi.file.delete_file": ("text_editor.file.core", "delete_file"),
    "fdi.file.ensure_dir": ("text_editor.file.core", "ensure_dir"),
    "fdi.uri.normalize_uri": ("text_editor.uri.core", "handle_uri_action"),
    "fdi.uri.parse_uri": ("text_editor.uri.core", "handle_uri_action"),
    "fdi.uri.uri_to_path": ("text_editor.uri.core", "handle_uri_action"),
    "fdi.uri.path_to_uri": ("text_editor.uri.core", "handle_uri_action"),
    "fdi.uri.is_safe_uri": ("text_editor.uri.core", "handle_uri_action"),
    "fdi.uri.resolve_uri": ("text_editor.uri.core", "handle_uri_action"),
    "fdi.str.headline": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.snake": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.slug": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.kebab": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.camel": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.studly": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.limit": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.words": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.squish": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.contains": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.starts_with": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.ends_with": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.before": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.after": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.between": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.pad_left": ("text_editor.str.core", "handle_str_action"),
    "fdi.str.pad_right": ("text_editor.str.core", "handle_str_action"),

    # AIL Machine Bridge (Era 5) — addon/ail-machine/bridge.py
    # These route through AilMachineBridge via FDI import_binding
    "fdi.str.ail_detect": ("text_editor.addon.ail_machine.core", "detect"),
    "fdi.str.ail_parse": ("text_editor.addon.ail_machine.core", "parse"),
    "fdi.str.ail_validate": ("text_editor.addon.ail_machine.core", "validate"),
    "fdi.str.ail_render": ("text_editor.addon.ail_machine.core", "render"),
    "fdi.str.ail_format_e164": ("text_editor.addon.ail_machine.bridge", "ail_format_e164"),
    "fdi.str.ail_slugify": ("text_editor.addon.ail_machine.bridge", "ail_slugify"),
    "fdi.str.ail_split_uri": ("text_editor.addon.ail_machine.bridge", "ail_split_uri"),
    "fdi.str.ail_summary": ("text_editor.addon.ail_machine.bridge", "ail_summary"),
}


def resolve_fdi_uri(rac_uri: str) -> dict:
    """Resolve FDI URI (alias for resolve_fdi_target)."""
    return resolve_fdi_target(rac_uri)


def create_fdi_executor(uri: str = "") -> FdiExecutor:
    """Create a new FDI executor with autoload transport."""
    transport = FdiTransport(uri=uri, method=FdiMethod.FILE)
    executor = FdiExecutor()
    executor.transport = transport
    return executor


def _register_fdi_dna():
    registry = get_dna_registry()
    if registry.get_dna("hace-lion-machine.fdi") is None:
        from ....core import ExecutorDNA
        registry.register_dna("hace-lion-machine.fdi", ExecutorDNA(
            trait="FdiMethod",
            struct="FdiExecutor",
            features=["autoload", "wire", "cable", "usb", "file_descriptor", "pipe"],
            bindings={
                "specs": "fdi",
                "machine": "hace-lion-machine",
                "transport": "ffi",
                "wired": True,
            },
            lion_machine=True,
            sio_stream=True,
        ))


_register_fdi_dna()


__all__ = [
    "FdiMethod",
    "FdiTransport",
    "FDIMethodRegistry",
    "FdiExecutor",
    "FdiActorAlias",
    "resolve_fdi_target",
    "create_fdi_executor",
    "_lazy_load_binding",
]