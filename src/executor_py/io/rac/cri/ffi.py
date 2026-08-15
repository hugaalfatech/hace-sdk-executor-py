# -*- coding: utf-8 -*-
"""
executor_py.io.rac.cri.ffi — Foreign Function Interface executor module.

FFI = Foreign Function Interface — the **native** transport motif.
Metaphor: Direct memory access, syscalls, native bridges.

Transport characteristics (FFI "native" motif):
    - Direct native calls: C ABI, Rust FFI, Go CGO
    - Zero-copy: shared memory, pointer passing
    - Unsafe: manual memory management, no GC
    - Highest performance: no serialization overhead

Per rac-uri-resolver.ail:
    rac://cri.{ownerspace}.ffi/{path}/hace/executor-py/{module}

Example:
    rac://cri.hace.ffi/native
    -> rule=cri, ownerspace=hace, specs=ffi, path=native
    -> transport=native, machine=hace-lion-machine
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from ....core import (
    ExecuteParticle,
    ExecContext,
    ExecInput,
    ExecOutput,
    SepiProof,
    ExecuteError,
    FanId,
    SioStatus,
    get_dna_registry,
)


class FfiMethod(Enum):
    """FFI method types — native transport modes."""
    CDLL = "cdll"                    # C dynamic library
    RUST = "rust"                    # Rust FFI (cdylib)
    GO = "go"                        # Go CGO shared library
    NATIVE = "native"                # Platform native (kernel syscalls)
    WASM = "wasm"                    # WebAssembly module


class FfiTransport:
    """FFI Transport — native connection handler.

    Handles native library loading, symbol resolution, and direct calls.
    """

    def __init__(self, library_path: str = "", method: FfiMethod = FfiMethod.CDLL):
        self.library_path = library_path
        self.method = method
        self._library: Optional[ctypes.CDLL] = None
        self._symbols: dict[str, Callable] = {}

    def load_library(self, path: Optional[str] = None) -> bool:
        """Load a native shared library."""
        lib_path = path or self.library_path
        if not lib_path:
            return False

        try:
            if sys.platform == "win32":
                self._library = ctypes.CDLL(lib_path)
            else:
                self._library = ctypes.CDLL(lib_path, ctypes.RTLD_GLOBAL)
            return True
        except OSError:
            return False

    def resolve_symbol(self, name: str, restype: Any = None, argtypes: list = None) -> Optional[Callable]:
        """Resolve a symbol from the loaded library."""
        if not self._library:
            return None

        try:
            symbol = getattr(self._library, name)
            if restype:
                symbol.restype = restype
            if argtypes:
                symbol.argtypes = argtypes
            self._symbols[name] = symbol
            return symbol
        except AttributeError:
            return None

    def call(self, name: str, *args) -> Any:
        """Call a resolved native function."""
        if name not in self._symbols:
            return None
        return self._symbols[name](*args)

    def is_loaded(self) -> bool:
        return self._library is not None


@dataclass
class FFIMethodRegistry:
    """Registry for FFI methods — maps method names to native handlers."""
    methods: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, handler: Any, *,
                 transport: FfiMethod = FfiMethod.CDLL,
                 library: str = "") -> None:
        """Register an FFI method with native transport metadata."""
        self.methods[name] = {
            "handler": handler,
            "transport": transport.value,
            "library": library,
        }

    def get(self, name: str) -> Optional[Any]:
        entry = self.methods.get(name)
        return entry["handler"] if entry else None

    def list_methods(self) -> list[str]:
        return list(self.methods.keys())


class FfiExecutor(ExecuteParticle):
    """FFI executor — implements ExecuteParticle via native transport.

    This is the Executor Module that handles FFI transport operations.
    Acts as the 'native' endpoint: library loading, symbol resolution, direct calls.

    Machine binding: hace-lion-machine (local native).
    """

    def __init__(self, registry: Optional[FFIMethodRegistry] = None):
        self.registry = registry or FFIMethodRegistry()
        self.transport = FfiTransport()
        self._register_default_methods()

    def _register_default_methods(self) -> None:
        """Register canonical FFI methods (native pattern)."""
        self.registry.register("load_library", self._method_load_library, transport=FfiMethod.CDLL)
        self.registry.register("resolve_symbol", self._method_resolve_symbol, transport=FfiMethod.CDLL)
        self.registry.register("call", self._method_call, transport=FfiMethod.CDLL)
        self.registry.register("spawn", self._method_spawn, transport=FfiMethod.NATIVE)
        self.registry.register("alloc", self._method_alloc, transport=FfiMethod.NATIVE)
        self.registry.register("free", self._method_free, transport=FfiMethod.NATIVE)

    def id(self) -> str:
        return "ffi-executor"

    def execute(self, input: ExecInput, ctx: ExecContext) -> ExecOutput:
        """Execute an FFI method via native transport.

        Args:
            input: ExecInput with action (e.g., "ffi.load_library") and payload
            ctx: Execution context

        Returns:
            ExecOutput with result + SepiProof evidence
        """
        action = input.action
        if "." in action:
            _, method_name = action.split(".", 1)
        else:
            method_name = action

        handler = self.registry.get(method_name)
        if handler is None:
            raise ExecuteError(
                code="FFI_NO_METHOD",
                message=f"FFI_NO_METHOD: FFI method not registered: {method_name}",
            )

        try:
            args = input.payload.get("options", {})
            result = handler(ctx, **args)

            proof = SepiProof(
                execution_id=ctx.trace_id,
                fan_id="hace-io-rac-cri-ffi",
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
                code="FFI_EXEC_ERROR",
                message=f"FFI execution failed: {str(e)}",
            )

    def fan_id(self) -> Optional[FanId]:
        return FanId(id="hace-io-rac-cri-ffi")

    # ─── Method implementations ───────────────────────────────────────────────

    def _method_load_library(self, ctx: ExecContext, **kwargs) -> dict:
        """Load a native shared library."""
        path = kwargs.get("path", "")
        success = self.transport.load_library(path)
        return {"loaded": success, "path": path}

    def _method_resolve_symbol(self, ctx: ExecContext, **kwargs) -> dict:
        """Resolve a symbol from the loaded library."""
        name = kwargs.get("name", "")
        restype = kwargs.get("restype")
        argtypes = kwargs.get("argtypes", [])
        symbol = self.transport.resolve_symbol(name, restype, argtypes)
        return {"resolved": symbol is not None, "name": name}

    def _method_call(self, ctx: ExecContext, **kwargs) -> dict:
        """Call a resolved native function."""
        name = kwargs.get("name", "")
        args = kwargs.get("args", [])
        result = self.transport.call(name, *args)
        return {"result": result, "name": name}

    def _method_spawn(self, ctx: ExecContext, **kwargs) -> dict:
        """Spawn a native process (OS-level)."""
        import subprocess
        cmd = kwargs.get("cmd", [])
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return {"pid": proc.pid, "status": "spawned"}
        except Exception as e:
            raise ExecuteError(
                code="FFI_SPAWN_FAILED",
                message=f"Failed to spawn process: {str(e)}",
            )

    def _method_alloc(self, ctx: ExecContext, **kwargs) -> dict:
        """Allocate native memory."""
        size = kwargs.get("size", 0)
        try:
            ptr = ctypes.create_string_buffer(size)
            return {"ptr": ctypes.addressof(ptr), "size": size}
        except Exception as e:
            raise ExecuteError(
                code="FFI_ALLOC_FAILED",
                message=f"Failed to allocate memory: {str(e)}",
            )

    def _method_free(self, ctx: ExecContext, **kwargs) -> dict:
        """Free native memory (no-op in Python, real impl in C)."""
        ptr = kwargs.get("ptr", 0)
        return {"freed": True, "ptr": ptr}

    # ─── Module resolution ──────────────────────────────────────────────────────

    def resolve_ffi_module(self, module_path: str) -> Any:
        """Resolve and load a native module from an FFI path."""
        # In production: load .so/.dll/.dylib
        return None


def resolve_ffi_target(rac_uri: str) -> dict:
    """Resolve an FFI RAC URI to target dimensions.

    Mirrors resolve_target() in racor.rs.

    Example:
        rac://cri.hace.ffi/native
        -> {rule: "cri", ownerspace: "hace", specs: "ffi", ...}
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
        "transport": "native",              # FFI = native
        "machine": "hace-lion-machine",     # Local native machine
        "transport_kind": "Ffi",
        "is_wired": True,                   # FFI = direct native
        "is_native": True,
    }


def create_ffi_executor(library_path: str = "") -> FfiExecutor:
    """Create a new FFI executor with native transport."""
    transport = FfiTransport(library_path=library_path, method=FfiMethod.CDLL)
    executor = FfiExecutor()
    executor.transport = transport
    return executor


# Register FFI in global DNA registry
def _register_ffi_dna():
    registry = get_dna_registry()
    if registry.get_dna("hace-lion-machine.ffi") is None:
        from ....core import ExecutorDNA
        registry.register_dna("hace-lion-machine.ffi", ExecutorDNA(
            trait="FfiMethod",
            struct="FfiExecutor",
            features=["native", "cgo", "c_abi", "syscall", "zero_copy"],
            bindings={
                "specs": "ffi",
                "machine": "hace-lion-machine",
                "transport": "native",
                "native": True,
            },
            lion_machine=True,
            sio_stream=True,
        ))


_register_ffi_dna()


__all__ = [
    "FfiMethod",
    "FfiTransport",
    "FFIMethodRegistry",
    "FfiExecutor",
    "resolve_ffi_target",
    "create_ffi_executor",
]