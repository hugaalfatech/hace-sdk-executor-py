"""
# Executor-Py SDK — Simple IPO Orchestrator

Mirrors `hace/sdk/executor-rs/src/simple.rs`.

Default IPO orchestrator implementation that wires Capor + Racor + adapter.
"""

from __future__ import annotations

from typing import Optional

from .core import ExecContext, FanId, ExecuteError, Nep
from .ipo import DefaultIpoOrchestrator, IpoInput, IpoProcess, IpoOutput, CaporDecision, RacRoute
from .capor import CaporRouter, DefaultCaporRouter, Scorer
from .racor import RacRouter, DefaultRacRouter
from .adapter import RacTransport
from .fan import FanRegistry


class SimpleExecutor(DefaultIpoOrchestrator):
    """Simple executor — wires Capor + Racor + adapter for local execution.

    This is the entry point for Python-native Fractal Executors.

    Usage:
        from executor_py import SimpleExecutor

        executor = SimpleExecutor()
        result = executor.execute(request={
            "rac_uri": "rac://cri.hace.fdi/hace/py-text-editor/file/read_file",
            "method": "call",
            "payload": {"action": "file.read_file", "value": {"path": "test.txt"}},
            "headers": {"trace_id": "abc-123"},
            "context": {"workspace_root": "/workspace"},
        })
        print(result.result)
    """

    def __init__(
        self,
        capor: Optional[CaporRouter] = None,
        racor: Optional[RacRouter] = None,
    ):
        super().__init__(
            capor or DefaultCaporRouter(),
            racor or DefaultRacRouter(),
        )

    def output(self, ipo_process: IpoProcess) -> IpoOutput | None:
        """Simplified output — execute particle directly."""
        try:
            # Execute the particle
            result = ipo_process.particle.execute(
                ipo_process.validated_payload,
                ipo_process.context,
            )
            from .core import SepiProof
            from .evidence import build_proof
            from .core import SioStatus

            proof = build_proof(
                ipo_process.fan_id,
                ipo_process.validated_payload.action,
                dict(ipo_process.validated_payload.payload),
                result.result,
                ipo_process.context,
                status=SioStatus.SUCCESS if result.status == SioStatus.SUCCESS else SioStatus.FAILED,
            )

            return IpoOutput(
                output=result,
                proof=proof,
            )
        except Exception as e:
            raise ExecuteError(code="EXEC_ERROR", message=str(e))
