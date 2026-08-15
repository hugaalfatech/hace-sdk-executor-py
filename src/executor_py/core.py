"""
# Executor-Py SDK — Core Types

Mirrors `hace/sdk/executor-cep/src/core/types.rs` (ExecuteParticle, ExecContext,
ExecInput, ExecOutput, SepiProof, ExecuteError, Particle types, FanId, FanCapability,
FanRegistry).

Architecture:
    - executor-py provides Python-native Fractal Executor primitives
    - Each type mirrors the Rust counterpart for CAN (Canonical Architecture Nucleotide) alignment
    - IPO pipeline: Input → Process → Output (mandatory control-flow)

Integration:
    - py-text-editor actor packages register concrete ExecuteParticle implementations
    - Each registration is a FanCapability under a FanId
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Optional, TypeVar
from uuid import uuid4


# ─── Core Enums ─────────────────────────────────────────────────────────────────

class SioStatus(Enum):
    """Mirrors SIOStatus in io/envelope.py."""
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class SioType(Enum):
    """Mirrors SIOType in io/rac/src/core.rs SioEnvelope.

    Canonical SIO message types (Intent, Reasoning, Execute, Legal,
    Finance, Memory, Data, Vision).
    """
    INTENT = "Intent"
    REASONING = "Reasoning"
    EXECUTE = "Execute"
    LEGAL = "Legal"
    FINANCE = "Finance"
    MEMORY = "Memory"
    DATA = "Data"
    VISION = "Vision"


class ExecutionMode(Enum):
    """Mirrors ExecutionMode in executor-cep/src/orch/ipo.rs."""
    PassThrough = "pass_through"
    SubExecute = "sub_execute"
    ChainExecute = "chain_execute"
    AggregateExecute = "aggregate_execute"
    LocalExecute = "local_execute"


class ParticleClass(Enum):
    """Particle classification — mirrors Rust ParticleClass."""
    Native = "native"          # Rust native (LEP)
    Python = "python"          # Python native (PEP)
    Artifact = "artifact"      # Pre-built binary artifact
    Substrate = "substrate"    # FFI/native library
    Network = "network"        # Remote service


class SecurityLevel(Enum):
    """Security level — mirrors Rust SecurityLevel in capor."""
    Local = "local"
    Shared = "shared"
    Restricted = "restricted"


# ─── Core Types ─────────────────────────────────────────────────────────────────

T_in = TypeVar("T_in")
T_out = TypeVar("T_out")


@dataclass
class ExecContext:
    """Execution context — mirrors ExecContext in executor-cep/src/core/types.rs.

    Carries authority, context, and runtime metadata for a single execution.
    """
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    session_id: Optional[str] = None
    security_tier: str = "local"  # local | shared | restricted
    workspace_root: Optional[str] = None
    actor_target: Optional[str] = None
    mactor_id: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecInput:
    """Execution input — mirrors ExecInput in executor-cep/src/core/types.rs.

    Carries the payload for a single particle execution.
    """
    action: str                       # e.g., "str.snake", "file.create_file"
    payload: dict[str, Any]           # SIO payload {action, value, options}
    rac_uri: str = ""                  # Canonical RAC URI
    headers: dict[str, str] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecOutput:
    """Execution output — mirrors ExecOutput in executor-cep/src/core/types.rs.

    Result of a single particle execution.
    """
    result: Any                       # The output value (could be dict, str, etc.)
    status: SioStatus = SioStatus.SUCCESS
    error: Optional[dict[str, Any]] = None  # {code, message, data}
    proof: Optional["SepiProof"] = None     # Evidence seal (FEH + ALR)


@dataclass
class SepiProof:
    """SEP (Sovereign Execution Proof) + ALR (Archetype Ledger Record).

    Mirrors SepiProof in executor-cep/src/core/types.rs.
    Every execute() MUST produce a SepiProof for audit/evidence.
    """
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    fan_id: str = ""
    action: str = ""
    status: str = "accepted"
    timestamp: float = 0.0
    feh_hash: Optional[str] = None   # Fingerprint of Execution Hash
    alr_seal: Optional[str] = None   # Archetype Ledger Record seal


class ExecuteError(Exception):
    """Execution error — mirrors ExecuteError in executor-cep/src/core/types.rs."""

    def __init__(self, code: str, message: str, data: Optional[dict] = None):
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(message)


# ─── Fan & Capability Types ─────────────────────────────────────────────────────

@dataclass
class FanId:
    """FAN identifier — mirrors FanId in executor-cep/src/core/types.rs.

    FAN = Feature ↔ Artifact ↔ Name mapping identifier.
    """
    id: str                           # e.g., "text-editor-io-mcp-server-core-file"

    def __str__(self) -> str:
        return self.id

    @staticmethod
    def parse(s: str) -> "FanId":
        """Parse a string into a FanId.

        Accepts both '/' and '_' as separators; normalizes to underscore.
        """
        normalized = s.replace("/", "_")
        return FanId(normalized)

    @property
    def ownerspace(self) -> str:
        """Extract ownerspace (first segment before '/' or '_')."""
        if "/" in self.id:
            return self.id.split("/")[0]
        if "_" in self.id:
            return self.id.split("_")[0]
        return self.id

    @property
    def namespace(self) -> str:
        """Extract namespace (second segment)."""
        if "/" in self.id:
            parts = self.id.split("/")
        else:
            parts = self.id.split("_", 1)
        return parts[1] if len(parts) > 1 else ""


@dataclass
class FanCapability:
    """FAN capability — mirrors FanCapability in executor-cep/src/core/types.rs.

    Registers a single capability under a FanId.
    """
    id: str                           # capability ID (e.g., "file.create_file")
    fan_id: FanId
    executor: str                     # e.g., "py-text-editor"
    transport: str                    # FDI, FFI, LION, RION
    handler: Any                      # callable or module path


class FanRegistry:
    """FAN registry — mirrors FanRegistry in executor-cep/src/core/types.rs.

    Holds all registered capabilities by FanId.
    """

    def __init__(self):
        self._capabilities: dict[str, list[FanCapability]] = {}
        self._by_id: dict[str, FanCapability] = {}

    def register(self, cap: FanCapability) -> None:
        """Register a capability under its FanId."""
        if cap.fan_id.id not in self._capabilities:
            self._capabilities[cap.fan_id.id] = []
        self._capabilities[cap.fan_id.id].append(cap)
        self._by_id[cap.id] = cap

    def find(self, capability_id: str) -> Optional[FanCapability]:
        """Find a capability by its ID."""
        return self._by_id.get(capability_id)

    def list_by_fan(self, fan_id: str) -> list[FanCapability]:
        """List all capabilities under a FanId."""
        return self._capabilities.get(fan_id, [])


# ─── SIO Envelope Types (mirrors io/rac/src/core.rs SioEnvelope) ────────────────

@dataclass
class SioMetadata:
    """SIO metadata — mirrors SioMetadata in io/rac/src/core.rs."""
    timestamp: int = 0
    trace_id: Optional[int] = None
    retry_count: int = 0
    priority: int = 0


@dataclass
class SioEnvelope:
    """SIO Envelope — mirrors SioEnvelope in io/rac/src/core.rs.

    Canonical message format for all RAC transports.
    """
    version: int = 1
    msg_id: int = 0
    source: str = ""
    target: str = ""
    sio_type: SioType = SioType.EXECUTE
    payload: Any = None
    metadata: SioMetadata = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = SioMetadata()


@dataclass
class SioResult:
    """Transport result — mirrors SioResult in io/rac/src/core.rs."""
    code: int = 0
    data: bytes = b""
    error: Optional[str] = None
    processing_time_us: int = 0

    @classmethod
    def ok(cls, data: bytes) -> "SioResult":
        return cls(code=0, data=data)

    @classmethod
    def err(cls, code: int, error: str) -> "SioResult":
        return cls(code=code, data=b"", error=error)


@dataclass
class TransportConfig:
    """Transport configuration — mirrors TransportConfig in io/rac/src/core.rs."""
    uri: str = ""
    timeout_ms: int = 5000
    security: str = "local"  # local, shared, restricted
    retry: Optional[RetryPolicy] = None

    def __post_init__(self):
        if self.retry is None:
            self.retry = RetryPolicy()


@dataclass
class RetryPolicy:
    """Retry policy for transport operations."""
    max_retries: int = 3
    backoff_ms: int = 100
    backoff_multiplier: float = 1.5


class RacTransportError(Exception):
    """Transport error — mirrors RacTransportError in io/rac/src/core.rs.

    Canonical transport error type used by RacTransport adapter implementations.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")

    @classmethod
    def not_connected(cls) -> "RacTransportError":
        return cls("NOT_CONNECTED", "Transport not connected")

    @classmethod
    def connection_failed(cls, detail: str) -> "RacTransportError":
        return cls("CONNECTION_FAILED", detail)

    @classmethod
    def send_failed(cls, detail: str) -> "RacTransportError":
        return cls("SEND_FAILED", detail)

    @classmethod
    def receive_failed(cls, detail: str) -> "RacTransportError":
        return cls("RECEIVE_FAILED", detail)

    @classmethod
    def timeout(cls) -> "RacTransportError":
        return cls("TIMEOUT", "Operation timed out")

    @classmethod
    def security_violation(cls, detail: str) -> "RacTransportError":
        return cls("SECURITY_VIOLATION", detail)

    @classmethod
    def invalid_scheme(cls, detail: str) -> "RacTransportError":
        return cls("INVALID_SCHEME", detail)

    @classmethod
    def closed(cls) -> "RacTransportError":
        return cls("CLOSED", "Transport closed")


# ─── ExecuteParticle (abstract) ───────────────────────────────────────────────────

class ExecuteParticle(ABC, Generic[T_in, T_out]):
    """Abstract base for all Logic Execution Particles (LEP/PEP).

    Mirrors ExecuteParticle trait in executor-cep/src/core/types.rs.
    Concrete implementations provide the domain logic for a single capability.

    A particle:
    - Receives ExecInput (action + payload + context)
    - Produces ExecOutput (result + proof)
    - Does NOT handle transport, routing, or authorization (that's IPO's job)
    """

    @abstractmethod
    def execute(self, input: ExecInput, ctx: ExecContext) -> ExecOutput:
        """Execute the particle.

        Args:
            input: The execution input (action + payload + headers + context)
            ctx: Execution context (trace_id, security tier, etc.)

        Returns:
            ExecOutput with result + SepiProof evidence
        """
        ...

    def fan_id(self) -> Optional[FanId]:
        """Optional: return the FanId this particle belongs to."""
        return None


# ─── Nep (uni-payload type) ───────────────────────────────────────────────────────

@dataclass
class Nep:
    """NEP — Native Execution Particle payload type.

    Mirrors Nep in executor-cep/src/core/types.rs.
    A generic payload-driven executor type.
    """
    data: Any
    meta: dict[str, Any] = field(default_factory=dict)
    encoding: str = "native"


# ─── FES DNA Types ─────────────────────────────────────────────────────────────────
# FES (Fractal Execute Structure) Model:
#   Actor (Engine) -> Executor (Engine Part) -> Executor Module (Capability)
#
# Mirrors the DNA/trait/struct pattern in conda-artifact-build skills.
# These types define the canonical mapping contract between Actor, Executor,
# and their constituent modules.


class FesLayer(Enum):
    """FES layer classification.

    Canonical three-layer FES model:
    - ENGINE: Runtime with Authority + Lifecycle (Actor)
    - EXECUTOR: Engine Part (IPO processor / MCV Controller)
    - MODULE: Capability implementation (engine part constituent)
    """
    ENGINE = "engine"
    EXECUTOR = "executor"
    MODULE = "module"


@dataclass
class EnginePart:
    """Base descriptor for an Engine Part (Executor or Module).

    Mirrors the ExecutorPart concept in actor-executor.ail.
    Both Executor and ExecutorModule inherit from this.
    """
    uri: str                           # Canonical URI
    name: str                          # Short name
    layer: FesLayer                    # ENGINE, EXECUTOR, or MODULE
    parent_uri: Optional[str] = None   # Parent engine/executor URI
    dna: Optional[dict[str, Any]] = None  # DNA definition


@dataclass
class ExecutorDNA:
    """Executor DNA — canonical definition of an Executor.

    Mirrors the .know/canon DNA pattern in conda-artifact-build skills.
    Contains: trait contract, struct definition, core features.
    """
    trait: str                         # e.g., "IpoFeature" / "RacTransport"
    struct: str                        # e.g., "DefaultIpoOrchestrator" / "StdioIpcAdapter"
    features: list[str] = field(default_factory=list)   # e.g., ["input", "process", "output"]
    bindings: dict[str, Any] = field(default_factory=dict)  # Actor<->Executor<->Module
    lion_machine: bool = False         # Binds to hace-lion-machine (local native)
    rion_machine: bool = False         # Binds to hace-rion-machine (remote native)
    sio_stream: bool = False           # Uses hace-sio-stream for I/O


@dataclass
class ActorExecutorMapping:
    """Actor -> Executor mapping contract.

    Defines how an Actor (Engine) maps to its Executor (Engine Part).
    Mirrors the actor->executor boundary in actor-executor.ail.
    """
    actor_uri: str                     # e.g., "rac://cri.hace.fdi/hace/text-ractor"
    actor_name: str                    # e.g., "text-ractor"
    executor_uri: str                  # e.g., "rac://cri.hace.fdi/hace/executor-py/core"
    executor_name: str                 # e.g., "executor-py"
    modules: list[str] = field(default_factory=list)  # Module URIs
    mode: str = "mcv"                  # "mcv" or "ipoc"


class ExecutorDNARegistry:
    """Registry for Executor DNA definitions.

    Used by IPO orchestrator / RAC router to resolve which executor
    implements a given capability, following the FES model.
    """

    def __init__(self):
        self._dna: dict[str, ExecutorDNA] = {}
        self._bindings: dict[str, ActorExecutorMapping] = {}

    def register_dna(self, key: str, dna: ExecutorDNA) -> None:
        self._dna[key] = dna

    def register_mapping(self, mapping: ActorExecutorMapping) -> None:
        self._bindings[mapping.actor_name] = mapping

    def get_dna(self, key: str) -> Optional[ExecutorDNA]:
        return self._dna.get(key)

    def get_mapping(self, actor_name: str) -> Optional[ActorExecutorMapping]:
        return self._bindings.get(actor_name)

    def get_executor_for_fan(self, fan_id: str) -> Optional[ExecutorDNA]:
        for dna in self._dna.values():
            if fan_id in (dna.bindings.get("fan_ids") or []):
                return dna
        return None


_global_dna_registry: Optional[ExecutorDNARegistry] = None


def get_dna_registry() -> ExecutorDNARegistry:
    """Get or create global FES DNA registry."""
    global _global_dna_registry
    if _global_dna_registry is None:
        _global_dna_registry = ExecutorDNARegistry()
        _register_builtin_dna(_global_dna_registry)
    return _global_dna_registry


def _register_builtin_dna(registry: ExecutorDNARegistry) -> None:
    """Register canonical ExecutorDNA definitions for the Executor-PEP."""

    # Executor-py core DNA: IPO processor / MCV Controller
    registry.register_dna("executor-py", ExecutorDNA(
        trait="IpoFeature",
        struct="DefaultIpoOrchestrator",
        features=["input", "process", "output", "execute"],
        bindings={
            "actor": "text-ractor",
            "runtime": "python",
            "layer": "executor",
        },
        lion_machine=True,
        rion_machine=True,
        sio_stream=False,
    ))

    # Executor-py FDI DNA: wired autoload (USB/cable motif)
    registry.register_dna("executor-py.fdi", ExecutorDNA(
        trait="FdiMethod",
        struct="FdiExecutor",
        features=["autoload", "wire", "cable", "usb"],
        bindings={
            "actor": "text-ractor",
            "runtime": "python",
            "layer": "module",
            "parent": "executor-py",
            "specs": "fdi",
        },
        lion_machine=True,
        sio_stream=True,
    ))

    # Executor-py FPI DNA: wireless (bluetooth/NFC motif)
    registry.register_dna("executor-py.fpi", ExecutorDNA(
        trait="FpiMethod",
        struct="FpiExecutor",
        features=["wireless", "bluetooth", "nfc", "discovery"],
        bindings={
            "actor": "text-ractor",
            "runtime": "python",
            "layer": "module",
            "parent": "executor-py",
            "specs": "fpi",
        },
        rion_machine=True,
        sio_stream=True,
    ))

    # Actor -> Executor mapping
    registry.register_mapping(ActorExecutorMapping(
        actor_uri="rac://cri.hace.fdi/hace/text-ractor",
        actor_name="text-ractor",
        executor_uri="rac://cri.hace.fdi/hace/executor-py/core",
        executor_name="executor-py",
        mode="mcv",
    ))
