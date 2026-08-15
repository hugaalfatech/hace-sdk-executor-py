"""
# Executor-Py SDK — IPO Feature

Mirrors `hace/sdk/executor-cep/src/orch/ipo.rs` (IpoFeature trait, IpoInput,
IpoProcess, IpoOutput, ExecutionMode, IpoOrchestrator).

IPO = Input → Process → Output (mandatory control-flow contract).

Every Fractal Executor MUST expose this contract.
- Governance/evidence are cross-cutting hooks, NOT part of IPO interface
- Capor resolves WHAT capacity; Racor resolves HOW/WHERE route
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar

from .core import (
    ExecuteParticle, ExecContext, ExecInput, ExecOutput, ExecuteError,
    FanId, SioStatus, ExecutionMode, SepiProof, Nep,
)


T = TypeVar("T")


# ─── IPO Types ──────────────────────────────────────────────────────────────────

@dataclass
class IpoInput:
    """IPO Input phase result — mirrors IpoInput struct in ipo.rs.

    Created by input() phase: Racee → SIO normalization.
    """
    context: ExecContext
    fan_id: FanId
    normalized_uri: str
    validated_payload: ExecInput


@dataclass
class IpoProcess:
    """IPO Process phase result — mirrors IpoProcess struct in ipo.rs.

    Contains the execution decision: capacity + route + particle.
    """
    capacity: Any                 # CaporDecision — WHAT capacity to execute
    route: Any                    # RacRoute — HOW/WHERE to execute
    mode: ExecutionMode           # Execution mode
    particle: ExecuteParticle     # Resolved particle to execute


@dataclass
class IpoOutput:
    """IPO Output phase result — mirrors IpoOutput struct in ipo.rs.

    Final execution result + evidence.
    """
    output: ExecOutput
    proof: SepiProof              # FEH + ALR sealed evidence


class IpoFeature(ABC, Generic[T]):
    """IPO Feature trait — mandatory orchestration contract for all Fractal Executors.

    Mirrors IpoFeature trait in executor-cep/src/orch/ipo.rs.

    Orchestration flow:
        Racee (rac://...)
          │ rac URI
          ▼
        IPO.input()
          ├── normalize RAC URI
          ├── validate SIO
          ├── resolve topology
          └── create ExecutionContext
          │
          ▼
        IPO.process()
          ├── Capor: resolve capacity (WHAT)
          ├── Racor: resolve route (HOW/WHERE)
          └── Execute domain operation
          │
          ▼
        IPO.output()
          ├── finalize SIO
          ├── invoke hooks
          └── return / forward / dispatch
    """

    @abstractmethod
    def input(self, request: T) -> IpoInput:
        """Input phase: Racee → SIO.

        - normalize RAC URI
        - validate SIO
        - resolve topology
        - create ExecutionContext
        """
        ...

    @abstractmethod
    def process(self, ipo_input: IpoInput) -> IpoProcess:
        """Process phase: execution decision point.

        - Capor: resolve capacity (WHAT)
        - Racor: resolve route (HOW/WHERE)
        - Select particle for execution
        """
        ...

    @abstractmethod
    def output(self, ipo_process: IpoProcess) -> Any:
        """Output phase: finalize and dispatch.

        - finalize SIO
        - invoke hooks
        - return / forward / dispatch
        """
        ...

    def execute(self, request: T) -> Any:
        """Full IPO orchestration — default implementation.

        Mirrors IpoFeature::execute() default method in ipo.rs.
        Input → Process → Output in sequence.
        """
        ipo_input = self.input(request)
        ipo_process = self.process(ipo_input)
        return self.output(ipo_process)


@dataclass
class CaporDecision:
    """Capacity resolution decision — mirrors CaporDecision.

    Result of Capor's WHAT resolution.
    """
    fan_id: FanId
    capability: str
    security_profile: Any  # SecurityProfile — from capor
    scorer: Any            # Scorer weights
    reason: str = "default"


@dataclass
class RacRoute:
    """Route resolution result — mirrors RacRoute.

    Result of Racor's HOW/WHERE resolution.
    """
    target: str
    transport: str
    machine: str        # "hace-lion-machine" | "hace-rion-machine"
    endpoint: Optional[str] = None
    adapter: Optional[str] = None


class IpoOrchestrator:
    """Default IPO orchestrator — mirrors IpoOrchestrator in ipo.rs.

    Delegates to injected CaporRouter and RacRouter.
    """

    def __init__(self, capor: "Any", racor: "Any"):
        self.capor = capor
        self.racor = racor

    def resolve_capacity(self, ctx: ExecContext, fan_id: FanId) -> CaporDecision:
        """Resolve capacity using Capor (WHAT).

        Mirrors IpoOrchestrator::resolve_capacity() in ipo.rs.
        """
        return self.capor.resolve(ctx, fan_id)

    def resolve_route(self, fan_id: FanId, uri: str) -> RacRoute:
        """Resolve route using Racor (HOW/WHERE).

        Mirrors IpoOrchestrator::resolve_route() in ipo.rs.
        """
        return self.racor.resolve_route(fan_id, uri)


class DefaultIpoOrchestrator(IpoFeature):
    """Default IPO orchestrator implementation.

    Mirrors the default IpoFeature execute() orchestration flow.
    Delegates to injected CaporRouter + RacRouter for resolution,
    then executes the resolved particle.
    """

    def __init__(self, capor: "Any", racor: "Any"):
        self.capor = capor
        self.racor = racor
        self.orchestrator = IpoOrchestrator(capor, racor)

    def input(self, request: dict) -> IpoInput:
        """Normalize request into IpoInput.

        Args:
            request: dict with keys:
                - rac_uri: RAC URI string
                - method: rac method (call, stream, instance, etc.)
                - payload: SIO payload {action, value, options}
                - headers: dict
                - context: dict
        """
        from .capor import CaporRouter
        from .racor import RacRouter

        # Parse RAC URI
        rac_uri = request.get("rac_uri", "")
        normalized_uri = rac_uri  # normalize_uri would be called here

        # Resolve FanId from URI
        fan_id = self._resolve_fan_id(rac_uri)

        # Create ExecContext
        ctx = ExecContext(
            workspace_root=request.get("context", {}).get("workspace_root"),
            actor_target=rac_uri,
            extra=request.get("context", {}),
        )

        # Create ExecInput
        payload = request.get("payload", {})
        validated_payload = ExecInput(
            action=payload.get("action", ""),
            payload=payload,
            headers=request.get("headers", {}),
            context=request.get("context", {}),
        )

        return IpoInput(
            context=ctx,
            fan_id=fan_id,
            normalized_uri=normalized_uri,
            validated_payload=validated_payload,
        )

    def process(self, ipo_input: IpoInput) -> IpoProcess:
        """Process: resolve capacity + route + select particle."""
        # Capor: resolve capacity (WHAT)
        capacity = self.orchestrator.resolve_capacity(
            ipo_input.context,
            ipo_input.fan_id,
        )

        # Racor: resolve route (HOW/WHERE)
        route = self.orchestrator.resolve_route(
            ipo_input.fan_id,
            ipo_input.normalized_uri,
        )

        # Select particle (simplified)
        particle = self._resolve_particle(capacity.fan_id, ipo_input.validated_payload.action)

        return IpoProcess(
            capacity=capacity,
            route=route,
            mode=ExecutionMode.LocalExecute,
            particle=particle,
        )

    def output(self, ipo_process: IpoProcess) -> "IpoOutput":
        """Execute + finalize output."""
        # Execute the particle
        try:
            from .evidence import build_proof
            particle = ipo_process.particle
            validated_input = ipo_process.validated_payload
            ctx = ipo_process.context
            
            result = particle.execute(
                validated_input,
                ctx,
            )
            if isinstance(result, IpoOutput):
                return result
            return IpoOutput(
                output=result,
                proof=build_proof(
                    fan_id=ipo_process.capacity.fan_id,
                    action=ipo_process.capacity.capability,
                    input_data=dict(validated_input.payload),
                    result=result.result,
                    ctx=ctx,
                    status=SioStatus.SUCCESS if result.status == SioStatus.SUCCESS else SioStatus.FAILED,
                ),
            )
        except Exception as e:
            raise ExecuteError(code="EXEC_ERROR", message=str(e))

    def _resolve_fan_id(self, rac_uri: str) -> FanId:
        """Resolve FanId from a RAC URI by querying the capor router's registry."""
        capor = getattr(self, 'capor', None) or getattr(self.orchestrator, 'capor', None)
        registry = getattr(capor, 'registry', None) or getattr(capor, '_registry', None)
        if registry:
            # Try matching capability by URI path segments
            parts = rac_uri.replace("rac://", "").split("/")
            path_parts = [p for p in parts if p]
            for i in range(len(path_parts)):
                suffix = ".".join(path_parts[i:])
                cap = registry.find(suffix)
                if cap:
                    return cap.fan_id
        return FanId("default")

    def _resolve_particle(
        self, fan_id: FanId, action: str
    ) -> ExecuteParticle:
        """Resolve the particle to execute for a given fan_id + action."""
        capor = getattr(self, 'capor', None) or getattr(self.orchestrator, 'capor', None)
        registry = getattr(capor, 'registry', None) or getattr(capor, '_registry', None)
        if registry:
            cap = registry.find(action)
            if cap and cap.handler:
                if callable(cap.handler):
                    return cap.handler
                # Handler could be a class instance with execute() method
                if hasattr(cap.handler, "execute") and callable(getattr(cap.handler, "execute")):
                    return cap.handler
                raise ExecuteError(
                    code="UNRESOLVED",
                    message=f"Particle not found for {fan_id.id}.{action}",
                )
            raise ExecuteError(
                code="UNRESOLVED",
                message=f"No capability registered for action: {action}",
            )
        raise ExecuteError(
            code="UNRESOLVED",
            message=f"No capability registered for action: {action}",
        )
