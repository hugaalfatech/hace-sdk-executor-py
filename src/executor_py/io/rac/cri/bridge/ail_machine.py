# -*- coding: utf-8 -*-
"""
executor_py.io.rac.cri.bridge.ail_machine — AIL Machine Bridge

FES Layer: MODULE (Bridge)

Bridge between executor-py SDK and the text-editor's ail-machine addon,
enabling CRI flows: text-editor ← FDI import → ail-machine.

Authority: CSA
Spec: SIO-CRI-FPI-V2, DIR-20260814-CRI-FPI-FEATURE-CONTRACT-V1

Integration:
    - FDI import: text-editor capabilities → ail-machine document processing
    - FPI instance: ail-machine FPI instance → ail-machine execution

CRI Flow (FDI — wired/autoload):
    text-editor
        │ rac:import (FDI — zero-payload binding)
        ▼
    executor-py.FdiExecutor.import_binding()
        │ bridges via rac_fdi_in (text-editor FDI facade)
        ▼
    text-editor/io/rac/cri/fdi.py handlers (fdi.str.slug, etc.)
        │ result
        ▼
    ail-machine receives parsed AIL document for processing

FPI Flow (FPI — Function Process Instance lifecycle):
    ail-machine
        │ rac:instance (FPI — create lifecycle)
        ▼
    executor-py.FpiExecutor.instance()
        │ FpiInstance lifecycle: init → running → execute → finalize → terminated
        ▼
    text-editor/io/mcp/server/core/__init__.py (MCP dispatch)
        │ SIO envelope
        ▼
    ail-machine receives response
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Dict
from uuid import uuid4

from .....core import (
    ExecContext,
    ExecInput,
    ExecuteError,
    get_dna_registry,
    ExecutorDNA,
    )
from ..fdi import FdiExecutor, _lazy_load_binding
from ..fpi import FpiExecutor, FpiInstance
from ...resolver import RouteResolver, SIOFrame


class AilMachineBridge:
    """Bridge between executor-py SDK and ail-machine addon.

    Provides canonical CRI integration paths:
    - FDI import: Import text-editor capabilities for AIL document processing
    - FPI instance: Create wireless instances for AIL machine discovery/pairing

    Machine bindings:
    - FDI: hace-lion-machine (local native)
    - FPI: hace-rion-machine (remote native)
    """

    def __init__(self):
        self.fdi_executor = FdiExecutor()
        self.fpi_executor = FpiExecutor()
        self._instances: Dict[str, FpiInstance] = {}

    def fdi_import(self, capability: str) -> Callable:
        """FDI import: acquire a callable binding for a text-editor capability.

        Per rac-uri-resolver.ail §5: rac:import → resolve_rac_uri →
        verify_export → verify_ara/license → bind_execution_substrate.
        """
        return self.fdi_executor.import_binding(capability)

    def fdi_invoke(self, capability: str, payload: Dict[str, Any],
                   headers: Optional[Dict[str, Any]] = None,
                   context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """FDI invoke: execute a text-editor capability via rac:call.

        Uses canonical SIOFrame: {uri, method, payload[action, ...],
        headers[ara, licence, visibility], context}
        """
        ctx = ExecContext(
            workspace_root=(context or {}).get("workspace_root"),
            actor_target=(context or {}).get("actor_target", "text-editor"),
            extra=context or {},
        )
        exec_input = ExecInput(
            action=capability,
            payload=payload,
            headers=headers or {},
            context=context or {},
        )
        result = self.fdi_executor.execute(exec_input, ctx)
        return {
            "status": result.status.value,
            "result": result.result,
            "proof": result.proof,
        }

    def fpi_instance_open(self, capability: str, endpoint: str = "") -> str:
        """FPI instance: create a wireless instance with lifecycle.

        Per rac-uri-resolver.ail §5: rac:instance → resolve_rac_uri →
        authorize → spawn/process/handshake → SIO-CRI-FPI-V2.
        """
        instance = self.fpi_executor.instance(
            capability,
            endpoint=endpoint,
        )
        instance_id = str(uuid4())
        self._instances[instance_id] = instance
        return instance_id

    def fpi_instance_execute(self, instance_id: str, action: str,
                            payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """FPI instance: execute an action on an open instance."""
        instance = self._instances.get(instance_id)
        if instance is None:
            raise ExecuteError(
                code="FPI_INSTANCE_NOT_FOUND",
                message=f"Instance not found: {instance_id}",
            )
        return instance.execute(action, payload)

    def fpi_instance_close(self, instance_id: str) -> Dict[str, Any]:
        """FPI instance: close and release an instance."""
        instance = self._instances.pop(instance_id, None)
        if instance is None:
            raise ExecuteError(
                code="FPI_INSTANCE_NOT_FOUND",
                message=f"Instance not found: {instance_id}",
            )
        return instance.close()

    def get_fdi_executor(self) -> FdiExecutor:
        """Get the underlying FDI executor."""
        return self.fdi_executor

    def get_fpi_executor(self) -> FpiExecutor:
        """Get the underlying FPI executor."""
        return self.fpi_executor


def _register_bridge_dna():
    """Register AIL Machine Bridge DNA with the global executor registry."""
    registry = get_dna_registry()
    if registry.get_dna("executor-py.ail-machine-bridge") is None:
        registry.register_dna("executor-py.ail-machine-bridge", ExecutorDNA(
            trait="AilMachineBridge",
            struct="AilMachineBridge",
            features=["fdi_import", "fpi_instance_open", "fpi_instance_execute", "fpi_instance_close"],
            bindings={
                "actor": "text-ractor",
                "runtime": "python",
                "layer": "module",
                "parent": "executor-py",
                "specs": "cri",
            },
            lion_machine=True,
            rion_machine=True,
            sio_stream=True,
        ))


_register_bridge_dna()


__all__ = [
    "AilMachineBridge",
]
