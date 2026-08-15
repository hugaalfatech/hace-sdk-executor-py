# -*- coding: utf-8 -*-
"""
executor_py.io.rac.cri.fpi — Function Process Instance executor module.

FPI = Function Process Instance — a **stateful lifecycle entity**, NOT a stateless function call.
FFI (Foreign Function Interface) is the low-level transport mechanism that FPI uses
under the hood. FPI and FFI are distinct concepts per CGE Canon AUD-20260814-FPI-VS-FFI-CANON:

- FFI = stateless C-ABI binding mechanism (ctypes, JNI, extern "C")
- FPI = stateful Function Process Instance with lifecycle (init → running → finalize → terminated)

Per CRD Directive AUD-20260814-CRI-FPI-FEATURE-CONTRACT-V1:
- FPI = Function Process Instance (Sovereign Process Entity)
- Lifecycle: resolve → authorize → create → init → running → finalize → terminated
- RAC URI identifies Actor, not implementation
- action.feature identifies executable capability
- process identifies FPI lifecycle
- input carries execution data

Transport: stdio, host_call (host function call, NOT FFI bridge)
Machine binding: hace-rion-machine (remote native)
"""

from __future__ import annotations

import uuid
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Callable, Dict, List

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


class FpiLifecycleState(Enum):
    """FPI Instance Lifecycle States per CGE Canon §4 & §6.

    Canonical lifecycle: resolve → authorize → create → init → running → finalize → terminated
    (ERROR is a terminal failure state that can occur at any point)
    """
    INIT = "init"
    RUNNING = "running"
    FINALIZE = "finalize"
    TERMINATED = "terminated"
    ERROR = "error"


class FpiMethod(Enum):
    """FPI method types — Canonical RAC verbs for Function Process Instance.

    Per CGE Canon §4: rac:instance creates an FPI lifecycle, rac:call executes
    a capability on the instance, rac:stream handles continuous data flow,
    rac:ping checks liveness, rac:finalize terminates the lifecycle.

    NOTE: These are RAC method verbs, NOT transport mechanisms.
    FPI uses host_call/stdio as its transport substrate, which uses FFI
    as the underlying binding mechanism — but FPI itself is NOT FFI.
    """
    INSTANCE = "instance"      # rac:instance — create FPI lifecycle
    CALL = "call"              # rac:call — execute capability on FPI
    STREAM = "stream"          # rac:stream — continuous data stream
    PING = "ping"              # rac:ping — health/liveness
    FINALIZE = "finalize"      # rac:finalize — terminate lifecycle
    HOST_CALL = "host_call"    # Transport substrate: host function call


class FpiTransport:
    """FPI Transport — function process instance execution channel.

    Handles FPI instance lifecycle and capability invocation through host_call.
    NOT a wireless transport (no bluetooth/NFC). FPI = Function Process Instance,
    a stateful lifecycle entity, per CGE Canon AUD-20260814-FPI-VS-FFI-CANON.
    """

    def __init__(self, uri: str = "", method: str = "host_call"):
        self.uri = uri
        self.method = method
        self._paired = False
        self._session_id: Optional[str] = None

    def pair(self, endpoint: str) -> bool:
        """Establish transport session."""
        self._session_id = str(uuid.uuid4())
        self._paired = True
        return True

    def is_paired(self) -> bool:
        return self._paired

    def unpair(self) -> None:
        self._paired = False
        self._session_id = None

    def invoke(self, method: str, args: dict[str, Any]) -> Any:
        """Invoke a method over the transport."""
        if not self._paired:
            raise ExecuteError(
                code="FPI_NOT_PAIRED",
                message="FPI transport not paired — call pair() first",
            )
        return self._invoke_host_call(method, args)

    def _invoke_host_call(self, method: str, args: dict) -> Any:
        """Invoke via host function call (NOT FFI bridge — FPI uses host_call transport).

        Per CGE Canon: FPI is a Function Process Instance, not a Foreign Function Interface.
        host_call is the transport substrate that invokes a registered handler.
        """
        handler = self._resolve_handler(method)
        if handler is None:
            raise ExecuteError(
                code="FPI_NO_METHOD",
                message=f"FPI method not registered: {method}",
            )
        return handler(**args)

    def _resolve_handler(self, method: str) -> Optional[Callable]:
        """Resolve a method name to its registered handler."""
        reg = getattr(self, "_registry", None)
        if reg:
            return reg.get(method)
        return None

    def set_registry(self, registry: "FPIMethodRegistry") -> None:
        self._registry = registry


@dataclass
class FPIMethodRegistry:
    """Registry for FPI procedures — maps method names to handler functions."""
    methods: dict[str, dict] = field(default_factory=dict)

    def register(self, name: str, handler: Any, *,
                 transport: str = "host_call",
                 endpoint: str = "") -> None:
        self.methods[name] = {
            "handler": handler,
            "transport": transport,
            "endpoint": endpoint,
        }

    def get(self, name: str) -> Optional[Any]:
        entry = self.methods.get(name)
        return entry["handler"] if entry else None

    def list_methods(self) -> list[str]:
        return list(self.methods.keys())

    def get_method_info(self, name: str) -> Optional[dict]:
        return self.methods.get(name)


class FpiExecutor(ExecuteParticle):
    """FPI executor — implements ExecuteParticle via Function Process Instance.

    Per CRD Canon AUD-20260814-CRI-FPI-FEATURE-CONTRACT-V1 and AUD-20260814-FPI-VS-FFI-CANON:
    - FPI = Function Process Instance (Sovereign Process Entity), NOT FFI
    - FFI (Foreign Function Interface) is the low-level binding mechanism used under the hood
    - FPI has lifecycle: resolve → authorize → create → init → running → finalize → terminated
    - RAC URI identifies Actor, not implementation
    - Machine binding: hace-rion-machine (remote native)
    """

    def __init__(self, registry: Optional[FPIMethodRegistry] = None):
        self.registry = registry or FPIMethodRegistry()
        self.transport = FpiTransport()
        self._register_default_methods()

    def _register_default_methods(self) -> None:
        """Register canonical FPI methods (CRI verbs)."""
        self.registry.register("instance", self._method_instance, transport="host_call")
        self.registry.register("call", self._method_call, transport="host_call")
        self.registry.register("stream", self._method_stream, transport="host_call")
        self.registry.register("ping", self._method_ping, transport="host_call")
        self.registry.register("finalize", self._method_finalize, transport="host_call")

    def id(self) -> str:
        return "fpi-executor"

    def execute(self, input: ExecInput, ctx: ExecContext) -> ExecOutput:
        """Execute an FPI method via CRI verbs.

        Canonical input payload:
            {
                "action": {"name": "execute", "feature": "str.slug"},
                "process": {"mode": "instance", "id": "fpi_xxx", "state": "running"},
                "input": {"text": "Hello World"},
                "options": {"stream": false}
            }
        """
        action = input.action
        if "." in action:
            _, method_name = action.split(".", 1)
        else:
            method_name = action

        handler = self.registry.get(method_name)
        if handler is None:
            raise ExecuteError(
                code="FPI_NO_METHOD",
                message=f"FPI_NO_METHOD: FPI method not registered: {method_name}",
            )

        try:
            args = input.payload.get("options", {})
            result = handler(ctx, **args)

            proof = SepiProof(
                execution_id=ctx.trace_id,
                fan_id="hace-io-rac-cri-fpi",
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
                code="FPI_EXEC_ERROR",
                message=f"FPI execution failed: {str(e)}",
            )

    def fan_id(self) -> Optional[FanId]:
        return FanId(id="hace-io-rac-cri-fpi")

    # ─── CRI Method implementations ──────────────────────────────────────────────

    def _method_instance(self, ctx: ExecContext, **kwargs) -> dict:
        """rac:instance — Create FPI instance with lifecycle."""
        capability = kwargs.get("capability", "")
        endpoint = kwargs.get("endpoint", "fpi://instance")
        
        instance = FpiInstance(
            capability=capability,
            transport=self.transport,
            endpoint=endpoint,
        )
        instance.open()
        
        return {
            "instance_id": instance.instance_id,
            "capability": capability,
            "state": instance.state.value,
            "status": "created",
        }

    def _method_call(self, ctx: ExecContext, **kwargs) -> dict:
        """rac:call — Execute capability on FPI instance via adapter delegation."""
        instance_id = kwargs.get("instance_id", "")
        action_feature = kwargs.get("action", {}).get("feature", "")
        input_data = kwargs.get("input", {})
        options = kwargs.get("options", {})

        # Delegate to adapter registry for capability execution
        try:
            from .fdi_adapters import get_adapter  # noqa: F401
            cap_id = f"fdi.{action_feature}" if not action_feature.startswith("fdi.") else action_feature
            adapter = get_adapter(cap_id)
            if adapter is not None:
                value = input_data.get("text", input_data.get("value", ""))
                result = adapter(ctx, value=value, headers={}, context={}, options=options)
                if isinstance(result, dict):
                    return {"status": "ok", "result": result.get("result", result), "action": action_feature}
                return {"status": "ok", "result": result, "action": action_feature}
        except Exception:
            pass

        return {
            "status": "ok",
            "action": action_feature,
            "instance_id": instance_id,
        }

    def _method_stream(self, ctx: ExecContext, **kwargs) -> dict:
        """rac:stream — Continuous data stream on FPI."""
        return {
            "stream": True,
            "status": "streaming",
        }

    def _method_ping(self, ctx: ExecContext, **kwargs) -> dict:
        """rac:ping — Health/liveness check."""
        return {
            "pong": True,
            "status": "healthy",
        }

    def _method_finalize(self, ctx: ExecContext, **kwargs) -> dict:
        """rac:finalize — Terminate FPI lifecycle."""
        instance_id = kwargs.get("instance_id", "")
        return {
            "finalized": True,
            "instance_id": instance_id,
            "state": FpiLifecycleState.TERMINATED.value,
        }

    # ─── rac:instance lifecycle management ──────────────────────────────────────

    def instance(self, capability: str, **init_kwargs) -> "FpiInstance":
        """Create/acquire a runtime capability instance with lifecycle.

        rac:instance(uri, **init_kwargs) → returns FpiInstance with lifecycle.

        Lifecycle: init → running → finalize → terminated
        """
        endpoint = init_kwargs.pop("endpoint", "fpi://instance")
        instance = FpiInstance(
            capability=capability,
            transport=self.transport,
            endpoint=endpoint,
            **init_kwargs,
        )
        instance.open()
        return instance


def resolve_fpi_target(rac_uri: str) -> dict:
    """Resolve an FPI RAC URI to target dimensions.

    Per rac-uri-resolver.ail §2: rac://{rule}.{ownerspace}.{specs}/{path}

    Example:
        rac://cri.hace.fpi/ail-machine
        -> {rule: "cri", ownerspace: "hace", specs: "fpi", path: "ail-machine", ...}
    """
    rest = rac_uri.replace("rac://", "")

    if "/" in rest:
        spec_part, path = rest.split("/", 1)
    else:
        spec_part, path = rest, ""

    parts = spec_part.split(".")
    rule = parts[0] if parts else ""
    specs = parts[-1] if len(parts) > 0 else ""
    ownerspace = ".".join(parts[1:-1]) if len(parts) >= 3 else ""

    return {
        "rule": rule,
        "ownerspace": ownerspace,
        "specs": specs,
        "path": path,
        "transport": "host_call",        # FPI = host function call
        "machine": "hace-rion-machine",   # Remote native machine
        "transport_kind": "Fpi",
        "is_wired": False,               # FPI = wireless/remote
        "is_wireless": True,
    }


class FpiInstance:
    """FPI runtime instance with canonical lifecycle management.

    Lifecycle: init → running → finalize → terminated
    """

    def __init__(
        self,
        capability: str,
        transport: Optional[FpiTransport] = None,
        endpoint: str = "fpi://instance",
        **init_kwargs,
    ):
        self.capability = capability
        self.transport = transport or FpiTransport()
        self.endpoint = endpoint
        self.init_kwargs = init_kwargs
        
        # Lifecycle state
        self.state = FpiLifecycleState.INIT
        self._opened = False
        self.instance_id: Optional[str] = None
        self._features: Dict[str, Callable] = {}
        
        # Load features from route resolution (lazy)
        self._features_loaded = False

    def _load_features(self) -> None:
        """Load features from route resolution (RouteResolver-driven).

        Per CGE Canon: routes contain declarations, never implementation code.
        FPI features are resolved via RouteResolver from routes/rac/cri/fpi/*
        or via adapters for known capabilities (str.*, file.*, etc.).
        """
        if self._features_loaded:
            return

        try:
            # Resolve features via RouteResolver
            from ...resolver import RouteResolver
            resolver = RouteResolver()
            resolver.discover_routes()

            # Resolve FPI route for this capability
            rac_uri = f"rac://cri.hace.fpi/{self.capability}"
            route = resolver.resolve_rac_uri(rac_uri)

            if route and route.export_enabled:
                # Load features from route's capability list via RouteResolver
                self._features = self._resolve_capabilities(route.capability)
        except Exception:
            # Fallback: resolve via adapter registry for known FPI capabilities
            self._features = self._resolve_capabilities(self.capability)
        finally:
            self._features_loaded = True

    def _resolve_capabilities(self, capability: str) -> Dict[str, Callable]:
        """Resolve capability implementations via RouteResolver + adapter registry.

        Per CGE Canon: features are resolved dynamically, not hardcoded.
        Uses adapter registry for text-editor capabilities (str.*, file.*, uri.*).
        """
        features = {}

        try:
            from .fdi_adapters import get_adapter
            from executor_py.core import ExecContext

            ctx = ExecContext(workspace_root="/workspace", actor_target="ail-machine")

            # Derive feature name from capability (e.g., "ail.parse" from "fpi.ail.machine.ail.parse")
            cap_parts = capability.split(".")
            if len(cap_parts) >= 2:
                # Try as direct capability (e.g., "ail.parse")
                feature_name = ".".join(cap_parts[-2:])

                # Check adapter registry for matching capability
                possible_caps = [
                    f"fdi.{feature_name}",
                    feature_name,
                ]
                for cap_id in possible_caps:
                    adapter = get_adapter(cap_id)
                    if adapter:
                        features[feature_name] = lambda ctx=ctx, a=adapter, f=feature_name: a(
                            ctx, **{"value": "", "headers": {}, "context": {}, "options": {}},
                        )
                        break
        except Exception:
            pass

        return features

    def open(self, **kwargs) -> dict:
        """Open the instance — establish transport session and initialize lifecycle."""
        endpoint = kwargs.get("endpoint", self.endpoint)
        self.transport.uri = endpoint
        success = self.transport.pair(endpoint)
        
        if success:
            self._opened = True
            self.instance_id = str(uuid.uuid4())
            self.state = FpiLifecycleState.RUNNING
            
            # Load features after successful open
            self._load_features()
        
        return {
            "opened": success,
            "instance_id": self.instance_id,
            "capability": self.capability,
            "state": self.state.value,
            "status": "open" if success else "failed",
        }

    def execute(self, action: str, payload: dict = None) -> dict:
        """Execute an action on this instance.

        Canonical SIO-CRI-FPI-V2 payload:
            {
                "action": {"name": "execute", "feature": "str.slug"},
                "process": {"mode": "instance", "id": "fpi_xxx", "state": "running"},
                "input": {"text": "Hello World"},
                "options": {"stream": false}
            }

        Also supports simple payload shortcuts:
            {"raw_text": "..."} → input.value = "raw_text"
            {"value": "..."} → input.value = "value"
        """
        if not self._opened:
            raise ExecuteError(
                code="FPI_INSTANCE_NOT_OPEN",
                message="Instance not opened — call open() first",
            )

        # Parse canonical payload
        action_name = action
        action_feature = action
        process_info = {}
        input_data = {}
        options = {}

        if payload:
            if isinstance(payload, dict):
                if "action" in payload and isinstance(payload["action"], dict):
                    action_feature = payload["action"].get("feature", action)
                if "process" in payload:
                    process_info = payload["process"]
                if "input" in payload:
                    input_data = payload["input"]
                if "options" in payload:
                    options = payload["options"]

        # Support simple payload shortcuts
        if payload and "raw_text" in payload and "input" not in payload:
            input_data = {"text": payload["raw_text"]}
        elif payload and "value" in payload and "input" not in payload:
            input_data = {"text": payload["value"]}

        # Try adapter registry directly for capabilities (str.*, file.*, uri.*)
        # Also handle ail.* features via AIL machine bridge adapters
        try:
            from .fdi_adapters import get_adapter

            # Build candidate capability IDs — try multiple formats
            # For ail.* actions (ail.parse, ail.validate), also try fdi.str.ail_* mapping
            cap_ids = [
                action,
                f"fdi.{action}",
                action_feature,
                f"fdi.{action_feature}",
            ]
            # For ail.* actions, also check fdi.str.ail_<action> variants
            if action.startswith("ail.") or action_feature.startswith("ail."):
                ail_func = action.split(".")[-1] if "." in action else action_feature.split(".")[-1]
                cap_ids.insert(0, f"fdi.str.ail_{ail_func}")

            for cap_id in cap_ids:
                adapter = get_adapter(cap_id)
                if adapter is not None:
                    from executor_py.core import ExecContext

                    ctx = ExecContext(
                        workspace_root="/workspace",
                        actor_target=self.capability,
                    )
                    value = input_data.get("text", input_data.get("value", ""))
                    adapter_input = {
                        "value": value,
                        "headers": options.get("headers", {}),
                        "context": options.get("context", {}),
                        "options": options,
                    }
                    result = adapter(ctx, **adapter_input)

                    # Unwrap result (some adapters return dict, some return objects)
                    if isinstance(result, dict):
                        if "content" in result:
                            result_value = result["content"]
                        elif "result" in result:
                            result_value = result["result"]
                        else:
                            result_value = result.get("uri", str(result))
                    else:
                        result_value = str(result)

                    return {
                        "result": {
                            "status": "success",
                            "result": result_value,
                        },
                        "action": action_feature,
                        "instance_id": self.instance_id,
                        "state": self.state.value,
                    }
        except Exception:
            pass

        try:
            # Try to execute via loaded feature adapter (from _load_features)
            if action_feature in self._features:
                feature_handler = self._features[action_feature]
                adapter_input = {
                    "value": input_data.get("text", input_data.get("value", "")),
                    "headers": {},
                    "context": {},
                    "options": options,
                }
                if process_info:
                    adapter_input["options"]["process"] = process_info

                from executor_py.core import ExecContext
                ctx = ExecContext(workspace_root="/workspace", actor_target=self.capability)
                result = self._features[action_feature](ctx, **adapter_input)
                return {
                    "result": result,
                    "action": action_feature,
                    "instance_id": self.instance_id,
                    "state": self.state.value,
                }
        except Exception:
            pass  # Fallback to stub

        # Fallback stub
        return {
            "status": "ok",
            "method": action_feature,
            "stub": True,
            "instance_id": self.instance_id,
            "state": self.state.value,
        }

    def finalize(self) -> dict:
        """Finalize the FPI lifecycle — transition to finalize state."""
        self.state = FpiLifecycleState.FINALIZE
        return self.close()

    def close(self) -> dict:
        """Close the instance — release transport and terminate lifecycle."""
        self.transport.unpair()
        self._opened = False
        closed_id = self.instance_id
        self.instance_id = None
        self.state = FpiLifecycleState.TERMINATED
        return {
            "closed": True,
            "instance_id": closed_id,
            "state": self.state.value,
            "status": "terminated",
        }

    def ping(self) -> dict:
        """Health/liveness check."""
        return {
            "pong": True,
            "instance_id": self.instance_id,
            "state": self.state.value,
            "status": "healthy" if self._opened else "closed",
        }

    @property
    def is_open(self) -> bool:
        return self._opened

    def __repr__(self) -> str:
        return f"FpiInstance(capability={self.capability!r}, state={self.state.value}, opened={self._opened})"


def create_fpi_executor(uri: str = "") -> FpiExecutor:
    """Create a new FPI executor with host_call transport."""
    transport = FpiTransport(uri=uri, method=FpiMethod.HOST_CALL)
    executor = FpiExecutor()
    transport.set_registry(executor.registry)
    executor.transport = transport
    return executor


# Register FPI in global DNA registry
def _register_fpi_dna():
    registry = get_dna_registry()
    if registry.get_dna("hace-rion-machine.fpi") is None:
        from ....core import ExecutorDNA
        registry.register_dna("hace-rion-machine.fpi", ExecutorDNA(
            trait="FpiMethod",
            struct="FpiExecutor",
            features=["function_process_instance", "lifecycle", "stateful", "host_call", "stdio"],
            bindings={
                "specs": "fpi",
                "machine": "hace-rion-machine",
                "transport": "host_call",
                "wireless": True,
                "lifecycle": True,
            },
            rion_machine=True,
            sio_stream=True,
        ))


_register_fpi_dna()


__all__ = [
    "FpiLifecycleState",
    "FpiMethod",
    "FpiTransport",
    "FPIMethodRegistry",
    "FpiExecutor",
    "FpiInstance",
    "resolve_fpi_target",
    "create_fpi_executor",
]