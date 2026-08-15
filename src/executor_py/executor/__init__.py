# Executor Base Class
# FES Layer: EXECUTOR (Engine Part — IPO Processor / MCV Controller)
# Authority: CSA-sealed

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..core import (
    ExecContext, ExecInput, ExecOutput, SepiProof, ExecuteError,
    FanId, FanCapability, FanRegistry, SioStatus, ExecutionMode,
    EnginePart, ExecutorDNA, ActorExecutorMapping, FesLayer, get_dna_registry
)
from ..ipo import (
    IpoFeature, IpoInput, IpoProcess, IpoOutput, CaporDecision, RacRoute,
    DefaultIpoOrchestrator, IpoOrchestrator
)
from ..capor import CaporRouter, DefaultCaporRouter, SecurityProfile, Scorer
from ..racor import RacRouter, DefaultRacRouter, RacUri, RacTransportKind
from ..evidence import build_proof
from ..adapter import RacTransport


@dataclass
class ExecutorConfig:
    """Executor configuration — Engine Part descriptor."""
    uri: str                              # Canonical URI (e.g., rac://cri.hace.fdi/hace/executor-py/core)
    name: str                             # Short name (e.g., executor-py)
    parent_actor_uri: str                 # Parent Actor URI
    layer: FesLayer = FesLayer.EXECUTOR   # Always EXECUTOR
    dna: Optional[ExecutorDNA] = None     # DNA definition
    transports: list[str] = field(default_factory=lambda: ["fdi", "fpi"])


class Executor(IpoFeature):
    """
    Base class for all Executors (Engine Parts).
    
    FES Layer: EXECUTOR
    An Executor is an Engine Part — IPO Processor / MCV Controller.
    
    Properties:
    - Input → Process → Output (IPO mandatory)
    - NO Authority
    - NO Identity (uses Actor's identity)
    - NO Lifecycle (managed by Actor)
    - NO RAC URI (uses Actor's RAC URI)
    
    Executor CANNOT run independently.
    Executor runs via RAC call through Actor.
    
    RAC Router Role: MCV Controller
    - Model = Capor (WHAT) + Racor (HOW/WHERE)
    - Controller = IPO orchestration
    - View = SIO envelope serialization
    """
    
    def __init__(self, config: ExecutorConfig):
        self.config = config
        self.name = config.name
        self.uri = config.uri
        self.parent_actor_uri = config.parent_actor_uri
        
        # FES DNA registration
        self.dna = config.dna or ExecutorDNA(
            trait="IpoFeature",
            struct=self.__class__.__name__,
            features=["input", "process", "output", "execute"],
            bindings={
                "actor": config.parent_actor_uri,
                "runtime": "python",
                "layer": "executor",
            },
            lion_machine=True,
            rion_machine=True,
            sio_stream=False,
        )
        
        # Register in global DNA registry
        registry = get_dna_registry()
        registry.register_dna(self.name, self.dna)
        
        # IPO components
        self.capor: CaporRouter = DefaultCaporRouter()
        self.racor: RacRouter = DefaultRacRouter()
        self.orchestrator = IpoOrchestrator(self.capor, self.racor)
        
        # Capability registry
        self.capabilities: dict[str, FanCapability] = {}
        self.fan_registry = FanRegistry()
        
        # Transport adapters
        self.transports: dict[str, RacTransport] = {}
    
    @abstractmethod
    def get_capabilities(self) -> list[FanCapability]:
        """Return list of capabilities this Executor provides."""
        ...
    
    def register_capability(self, cap: FanCapability) -> None:
        """Register a capability."""
        self.capabilities[cap.id] = cap
        self.fan_registry.register(cap)
    
    def register_transport(self, transport: RacTransport) -> None:
        """Register a transport adapter."""
        self.transports[transport.id()] = transport
    
    # ─── IpoFeature Implementation ────────────────────────────────────────────
    
    def input(self, request: dict) -> IpoInput:
        """Input phase: Racee → SIO normalization."""
        # Parse RAC URI
        rac_uri = request.get("rac_uri", "")
        
        # Resolve FanId from URI
        fan_id = self._resolve_fan_id(rac_uri)
        
        # Create ExecContext
        ctx = ExecContext(
            workspace_root=request.get("context", {}).get("workspace_root"),
            actor_target=rac_uri,
            extra=request.get("context", {}),
        )
        
        # Create ExecInput from payload
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
            normalized_uri=rac_uri,
            validated_payload=validated_payload,
        )
    
    def process(self, ipo_input: IpoInput) -> IpoProcess:
        """Process phase: Capor (WHAT) + Racor (HOW/WHERE) → ExecuteParticle."""
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
        
        # Select ExecuteParticle
        particle = self._resolve_particle(ipo_input.fan_id, ipo_input.validated_payload.action)
        
        return IpoProcess(
            capacity=capacity,
            route=route,
            mode=ExecutionMode.LocalExecute,
            particle=particle,
        )
    
    def output(self, ipo_process: IpoProcess) -> IpoOutput:
        """Output phase: Execute + seal evidence + finalize."""
        try:
            # Execute the particle with proper ExecInput
            particle = ipo_process.particle
            validated_input = ipo_process.validated_payload
            ctx = ipo_process.context
            
            result = particle.execute(
                validated_input,
                ctx,
            )
            
            # Build SepiProof evidence (FEH + ALR)
            proof = build_proof(
                fan_id=ipo_process.capacity.fan_id,
                action=ipo_process.capacity.capability,
                input_data=dict(validated_input.payload),
                result=result.result,
                ctx=ctx,
                status=SioStatus.SUCCESS if result.status == SioStatus.SUCCESS else SioStatus.FAILED,
            )
            
            return IpoOutput(
                output=result,
                proof=proof,
            )
        except ExecuteError:
            raise
        except Exception as e:
            raise ExecuteError(code="EXEC_ERROR", message=str(e))
    
    def execute(self, request: dict) -> Any:
        """Full IPO orchestration: Input → Process → Output."""
        ipo_input = self.input(request)
        ipo_process = self.process(ipo_input)
        return self.output(ipo_process)
    
    def _resolve_fan_id(self, rac_uri: str) -> FanId:
        """Resolve FanId from RAC URI."""
        # Extract capability from URI path
        parts = rac_uri.replace("rac://", "").split("/")
        if parts:
            capability = parts[-1] if len(parts) > 1 else parts[0]
            cap = self.fan_registry.find(capability)
            if cap:
                return cap.fan_id
        return FanId.parse("default")
    
    def _resolve_particle(self, fan_id: FanId, action: str) -> Any:
        """Resolve ExecuteParticle for a capability."""
        cap = self.fan_registry.find(action)
        if cap and cap.handler:
            if callable(cap.handler):
                return cap.handler
            raise ExecuteError(
                code="UNRESOLVED",
                message=f"Particle not found for {fan_id.id}.{action}",
            )
        raise ExecuteError(
            code="UNRESOLVED",
            message=f"No capability registered for action: {action}",
        )


class SimpleExecutor(Executor):
    """
    Simple executor — default IPO orchestrator for local execution.
    
    Usage:
        from executor_py.executor import SimpleExecutor
        
        executor = SimpleExecutor(config=ExecutorConfig(...))
        result = executor.execute(request={
            "rac_uri": "rac://cri.hace.fdi/hace/executor-py/core",
            "method": "call",
            "payload": {"action": "fdi.autoload", "value": {"uri": "file:///path"}},
        })
    """
    
    def __init__(
        self,
        config: ExecutorConfig,
        capor: Optional[CaporRouter] = None,
        racor: Optional[RacRouter] = None,
    ):
        super().__init__(config)
        self.capor = capor or DefaultCaporRouter()
        self.racor = racor or DefaultRacRouter()
        self.orchestrator = IpoOrchestrator(self.capor, self.racor)
    
    def output(self, ipo_process: IpoProcess) -> IpoOutput:
        """Simplified output — execute particle directly with evidence."""
        try:
            # Execute the particle with the actual validated payload
            particle = ipo_process.particle
            # Need access to the original input - simplified for now
            result = particle.execute(
                ipo_process,  # Using IpoProcess as input for now
                ExecContext(),
            )
            
            proof = build_proof(
                fan_id=ipo_process.capacity.fan_id,
                action=ipo_process.capacity.capability,
                input_data={},
                result=result.result,
                ctx=ExecContext(),
                status=SioStatus.SUCCESS if result.status == SioStatus.SUCCESS else SioStatus.FAILED,
            )
            
            return IpoOutput(output=result, proof=proof)
        except Exception as e:
            raise ExecuteError(code="EXEC_ERROR", message=str(e))


__all__ = ["Executor", "ExecutorConfig", "SimpleExecutor"]
