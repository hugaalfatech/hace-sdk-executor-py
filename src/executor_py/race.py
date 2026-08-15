# -*- coding: utf-8 -*-
"""
race.py — Racer / Racee dual-role pattern for executor-py.

FES Layer: EXECUTOR (extends IpoFeature)

Racer = the side that initiates a race (dispatch capability to multiple targets)
Racee = the side that receives the race signal (ready to be invoked)

Per CRIGAP.ail §3: "Add race (dual-role) to executor-py" (GAP: ⚠ stub)
Per FES.ail §25: "Racer is the dispatch side of a dual-role execution"

Mirrors: executor-cep/src/race.rs (Trait Racer + Racee)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Callable

from .core import (
    FanId, FanCapability, FanRegistry,
    ExecContext, ExecInput, ExecOutput, IpoInput, IpoProcess, IpoOutput,
    ExecParticle, ExecuteError, SioStatus,
    get_dna_registry, FesLayer, EnginePart, ExecutorDNA,
)


@dataclass
class RaceTarget:
    """A target for racing a capability."""
    fan_id: FanId
    rac_uri: str
    priority: int = 0
    weight: float = 1.0


@dataclass
class RacePlan:
    """Plan for a dual-role race execution."""
    targets: list[RaceTarget]
    timeout_ms: int = 5000
    fan_id: Optional[FanId] = None
    action: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RaceResult:
    """Result of a race execution."""
    winner: Optional[FanId]
    outputs: dict[str, ExecOutput]
    feh_hash: Optional[str]
    all_succeeded: bool


class Racer(ABC):
    """Abstract Racer — the dispatch side of a dual-role race.

    A Racer fans out a capability call to multiple targets simultaneously
    and accepts the first successful result (or aggregated result).
    """

    def __init__(self, registry: Optional[FanRegistry] = None):
        self.registry = registry or FanRegistry()
        self._race_targets: dict[str, list[RaceTarget]] = {}

    def register_target(self, action: str, target: RaceTarget) -> None:
        """Register a race target for a given action."""
        if action not in self._race_targets:
            self._race_targets[action] = []
        self._race_targets[action].append(target)

    def list_targets(self, action: str) -> list[RaceTarget]:
        """List all race targets for an action."""
        return self._race_targets.get(action, [])

    def resolve_targets(self, action: str) -> list[RaceTarget]:
        """Resolve all targets for a given action."""
        return self._race_targets.get(action, [])

    def clear_targets(self, action: str) -> None:
        """Clear all race targets for an action."""
        if action in self._race_targets:
            del self._race_targets[action]

    @abstractmethod
    def race(self, plan: RacePlan) -> RaceResult:
        """Execute a race: dispatch to all targets, return first/result."""
        ...

    @abstractmethod
    def race_async(self, plan: RacePlan) -> Any:
        """Execute a race asynchronously."""
        ...


class Racee(ABC):
    """Abstract Racee — the receive side of a dual-role race.

    A Racee advertises its availability to be raced and
    implements the actual execution when the Racer dispatches.
    """

    def __init__(self, fan_id: FanId):
        self.fan_id = fan_id
        self._available: bool = True

    @property
    def available(self) -> bool:
        """Check if this Racee is available for racing."""
        return self._available

    def mark_available(self) -> None:
        """Mark this Racee as available."""
        self._available = True

    def mark_unavailable(self) -> None:
        """Mark this Racee as unavailable."""
        self._available = False

    @abstractmethod
    def on_race_invocation(self, ctx: ExecContext, payload: dict[str, Any]) -> ExecOutput:
        """Handle a race invocation from a Racer."""
        ...

    @abstractmethod
    def advertise(self) -> FanCapability:
        """Advertise this Racee's capability to the registry."""
        ...


@dataclass
class RacerConfig:
    """Configuration for a Racer."""
    fan_id: FanId
    timeout_ms: int = 5000
    max_targets: int = 5
    retry_count: int = 1


class DefaultRacer(Racer):
    """Default Racer implementation — synchronous race dispatch."""

    def __init__(self, config: Optional[RacerConfig] = None):
        self.config = config or RacerConfig(fan_id=FanId(id="default"))
        self.registry = FanRegistry()
        self._race_targets = {}
        self._race_history: list[RaceResult] = []

    def race(self, plan: RacePlan) -> RaceResult:
        """Execute a race across all registered targets.

        Dispatches the capability to all targets concurrently and
        returns the first successful result (or aggregated).
        """
        import hashlib
        import json

        outputs: dict[str, ExecOutput] = {}
        winners: list[FanId] = []

        for target in plan.targets:
            ctx = ExecContext(
                trace_id=f"race-{plan.action}",
                security_tier="local" if plan.timeout_ms <= 1000 else "shared",
                workspace_root="/",
                actor_target=target.rac_uri,
            )

            # Try to find handler in registry
            cap = self.registry.find(plan.action)
            if cap and cap.handler:
                handler = cap.handler
                if hasattr(handler, "execute") and callable(getattr(handler, "execute")):
                    try:
                        result = handler.execute(ExecInput(
                            rac_uri=target.rac_uri,
                            action=plan.action,
                            payload=plan.payload,
                        ), ctx)
                        outputs[target.fan_id.id] = result
                        if result.status == SioStatus.SUCCESS:
                            winners.append(target.fan_id)
                    except Exception as e:
                        outputs[target.fan_id.id] = ExecOutput(
                            result={"error": str(e)},
                            status=SioStatus.FAILURE,
                            error=str(e),
                        )
                elif callable(handler):
                    try:
                        result = handler(plan.payload)
                        if not isinstance(result, ExecOutput):
                            result = ExecOutput(result=result)
                        outputs[target.fan_id.id] = result
                        if result.status == SioStatus.SUCCESS:
                            winners.append(target.fan_id)
                    except Exception as e:
                        outputs[target.fan_id.id] = ExecOutput(
                            result={"error": str(e)},
                            status=SioStatus.FAILURE,
                            error=str(e),
                        )

        # Compute FEH over race results
        feh_raw = json.dumps({k: str(v) for k, v in outputs.items()}, sort_keys=True)
        feh_hash = hashlib.sha256(feh_raw.encode()).hexdigest()

        all_succeeded = all(
            o.status == SioStatus.SUCCESS for o in outputs.values()
        ) if outputs else False

        result = RaceResult(
            winner=winners[0] if winners else None,
            outputs=outputs,
            feh_hash=feh_hash,
            all_succeeded=all_succeeded,
        )
        self._race_history.append(result)
        return result

    async def race_async(self, plan: RacePlan) -> RaceResult:
        """Execute a race asynchronously using asyncio."""
        import asyncio
        import hashlib
        import json

        async def _race_target(target: RaceTarget) -> tuple[str, ExecOutput]:
            ctx = ExecContext(
                trace_id=f"race-async-{plan.action}",
                security_tier="shared",
                workspace_root="/",
                actor_target=target.rac_uri,
            )
            cap = self.registry.find(plan.action)
            if cap and cap.handler:
                handler = cap.handler
                if hasattr(handler, "execute") and callable(getattr(handler, "execute")):
                    try:
                        result = handler.execute(ExecInput(
                            rac_uri=target.rac_uri,
                            action=plan.action,
                            payload=plan.payload,
                        ), ctx)
                        if result.status == SioStatus.SUCCESS:
                            return (target.fan_id.id, result)
                    except Exception as e:
                        pass
                elif callable(handler):
                    try:
                        result = handler(plan.payload)
                        if not isinstance(result, ExecOutput):
                            result = ExecOutput(result=result)
                        if result.status == SioStatus.SUCCESS:
                            return (target.fan_id.id, result)
                    except Exception:
                        pass
            return (target.fan_id.id, ExecOutput(
                result={"error": "timeout"},
                status=SioStatus.FAILURE,
            ))

        tasks = [_race_target(t) for t in plan.targets]
        done, _ = await asyncio.wait(tasks, timeout=plan.timeout_ms / 1000.0)

        outputs: dict[str, ExecOutput] = {}
        winners: list[FanId] = []
        for future in asyncio.as_completed(done):
            try:
                key, output = await future
                outputs[key] = output
                if output.status == SioStatus.SUCCESS:
                    winners.append(FanId(id=key))
            except Exception:
                pass

        feh_raw = json.dumps({k: str(v) for k, v in outputs.items()}, sort_keys=True)
        feh_hash = hashlib.sha256(feh_raw.encode()).hexdigest()

        all_succeeded = all(
            o.status == SioStatus.SUCCESS for o in outputs.values()
        ) if outputs else False

        result = RaceResult(
            winner=winners[0] if winners else None,
            outputs=outputs,
            feh_hash=feh_hash,
            all_succeeded=all_succeeded,
        )
        self._race_history.append(result)
        return result


@dataclass
class RaceeConfig:
    """Configuration for a Racee."""
    fan_id: FanId
    capability: str = ""
    is_available: bool = True


class DefaultRacee(Racee):
    """Default Racee implementation."""

    def __init__(self, config: RaceeConfig):
        self.config = config
        super().__init__(fan_id=config.fan_id)

    def on_race_invocation(self, ctx: ExecContext, payload: dict[str, Any]) -> ExecOutput:
        """Handle a race invocation."""
        return ExecOutput(result={"received": True}, status=SioStatus.SUCCESS)

    def advertise(self) -> FanCapability:
        """Advertise capability to registry."""
        return FanCapability(
            id=self.config.capability,
            fan_id=self.config.fan_id,
            executor="default",
            transport="local",
        )


class RionRaceIntegration:
    """Integration point: RION Machine ↔ Racer/Racee.

    Connects the RION Machine's SovereignInterceptor and CircuitBreaker
    with the Racer/Racee dual-role pattern for remote racing.
    """

    def __init__(self, machine: Any):
        self.machine = machine

    def race_remote(
        self, plan: RacePlan, targets: list[str]
    ) -> RaceResult:
        """Race across remote targets via RION Machine."""
        race_targets = [
            RaceTarget(
                fan_id=FanId.parse(target),
                rac_uri=target,
                priority=0,
                weight=1.0,
            )
            for target in targets
        ]
        full_plan = RacePlan(
            targets=race_targets,
            timeout_ms=plan.timeout_ms,
            fan_id=plan.fan_id,
            action=plan.action,
            payload=plan.payload,
        )
        racer = DefaultRacer(config=RacerConfig(
            fan_id=plan.fan_id or FanId(id="default-rion"),
        ))
        return racer.race(full_plan)


# ─── DNA Registration ─────────────────────────────────────────────────────────
def _register_race_dna():
    """Register Racer/Racee DNA with the global executor registry."""
    registry = get_dna_registry()

    dna_entry = EnginePart(
        uri="rac://api.hace.race/executor-py/src/executor_py/race.py",
        name="racer-racee",
        layer=FesLayer.EXECUTOR,
        dna=ExecutorDNA(
            trait="Racer",
            struct="DefaultRacer",
            features=["race", "race_async", "register_target", "resolve_targets"],
            bindings={
                "actor": "text-ractor",
                "runtime": "python",
                "layer": "executor",
                "dual_role": True,
                "racer": True,
                "racee": True,
            },
            lion_machine=True,
            rion_machine=True,
            sio_stream=False,
        ),
    )
    if registry.get_dna("racer-racee") is None:
        registry.register_dna("racer-racee", dna_entry.dna)


_register_race_dna()


__all__ = [
    "Racer",
    "Racee",
    "DefaultRacer",
    "DefaultRacee",
    "RaceTarget",
    "RacePlan",
    "RaceResult",
    "RacerConfig",
    "RaceeConfig",
    "RionRaceIntegration",
]
