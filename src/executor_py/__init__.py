# -*- coding: utf-8 -*-
"""
executor_py — Python Native Fractal Executor SDK.

FES (Fractal Execute Structure) Model:
    Actor (Engine) → Executor (Engine Part) → Executor Module (Capability)

This SDK implements the **Executor** layer — the engine part acting as
IPO processor (MCV Controller) in the RAC router.

    ┌───────┐    ┌──────────────┐    ┌──────────────────┐
    │ Actor │    │   Executor   │    │  Executor Module   │
    │ (Eng) │    │  (IPO/MCV)   │    │  (Capability Impl) │
    │ text- │    │ executor-py  │    │  io/rac/cri/fdi   │
    │ ractor│◄───│  .io.rac.*   │◄───│  io/mcp/server/   │
    └───────┘    └──────────────┘    └──────────────────┘

    IPO: Input → Process → Output (mandatory control-flow contract)
    MCV: Model = Domain operation, View = SIO envelope,
         Controller = IPO orchestration

Authority: CSA
Mirrors:  hace/sdk/executor-cep (Rust)
"""

from __future__ import annotations

# ─── Core CEP types ────────────────────────────────────────────────────────────
from .core import (
    ExecuteParticle,
    ExecContext,
    ExecInput,
    ExecOutput,
    SepiProof,
    ExecuteError,
    SioStatus,
    SioType,
    RacTransportError,
    ExecutionMode,
    ParticleClass,
    SecurityLevel,
    FanId,
    FanCapability,
    FanRegistry,
    Nep,
    SioEnvelope,
    SioResult,
    SioMetadata,
    TransportConfig,
    RetryPolicy,
    # FES DNA types
    EnginePart,
    ExecutorDNA,
    ActorExecutorMapping,
    FesLayer,
)

# ─── Actor (Engine) ─────────────────────────────────────────────────────────────
from .actor import (
    Actor,
    ActorConfig,
    CompositeActor,
    CompositeActorConfig,
)

# ─── Executor (Engine Part) ─────────────────────────────────────────────────────
from .executor import (
    Executor,
    ExecutorConfig,
    SimpleExecutor,
)

# ─── Module (Capability) ────────────────────────────────────────────────────────
from .module import (
    ExecutorModule,
    ModuleConfig,
    FdiModule,
    FpiModule,
    LibraryModule,
)

# ─── IPO orchestration ─────────────────────────────────────────────────────────
from .ipo import (
    IpoFeature,
    IpoInput,
    IpoProcess,
    IpoOutput,
    IpoOrchestrator,
    CaporDecision,
    RacRoute,
    DefaultIpoOrchestrator,
)

# ─── Capor (WHAT capacity) ────────────────────────────────────────────────────
from .capor import (
    CaporRouter,
    DefaultCaporRouter,
    SecurityProfile,
    Scorer,
)

# ─── Racor (HOW/WHERE route) ──────────────────────────────────────────────────
from .racor import (
    RacRouter,
    DefaultRacRouter,
    RacUri,
    RacTransportKind,
    RacRule,
    UriClassification,
)

# ─── Evidence (FEH/ALR) ───────────────────────────────────────────────────────
from .evidence import (
    compute_feh_hash,
    seal_alr_record,
    build_proof,
)

# ─── Adapter (transport) ──────────────────────────────────────────────────────
from .adapter import (
    RacTransport,
    TransportError,
    TransportStats,
    LocalNativeAdapter,
    StdioIpcAdapter,
)

# ─── IPO Payload extraction ───────────────────────────────────────────────────
from .payload import (
    IpoPayload,
    ValidatedPayload,
    extract_payload,
    validate_payload,
    build_payload_for_handler,
)

# ─── IO / RAC / CRI subpackage ────────────────────────────────────────────────
from .io.rac.cri.fdi import (
    FdiExecutor, FdiMethod, FdiTransport, FDIMethodRegistry,
    resolve_fdi_target, create_fdi_executor,
    _lazy_load_binding,
)
from .io.rac.cri.fpi import (
    FpiExecutor, FpiMethod, FpiTransport, FPIMethodRegistry,
    FpiInstance,
    resolve_fpi_target, create_fpi_executor,
)
from .io.rac.cri.ffi import (
    FfiExecutor, FfiMethod, FfiTransport, FFIMethodRegistry,
    resolve_ffi_target, create_ffi_executor,
)
from .io.rac.resolver import (
    RouteResolver, RouteIndex, NormalizedRoute, SIOFrame,
    create_resolver, resolve_rac_uri,
)
from .io.rac.contracts import (
    RacMethodName, RacMethodContract, RAC_METHOD_CONTRACTS,
    RacMethodDispatcher, DefaultRacMethodDispatcher,
    resolve_rac_target,
)
from .io.transport import (
    StdioTransport, StdioConfig, StdioServerTransport,
    HttpTransport, HttpConfig, HttpServerTransport,
    WsTransport, WsConfig, WsServerTransport,
)

__version__ = "0.1.0"

__all__ = [
    # Core types
    "ExecuteParticle", "ExecContext", "ExecInput", "ExecOutput",
    "SepiProof", "ExecuteError", "SioStatus", "SioType", "RacTransportError",
    "ExecutionMode", "ParticleClass", "SecurityLevel", "Nep",
    # FES DNA
    "EnginePart", "ExecutorDNA", "ActorExecutorMapping", "FesLayer",
    # Fan
    "FanId", "FanCapability", "FanRegistry",
    # Actor (Engine)
    "Actor", "ActorConfig", "CompositeActor", "CompositeActorConfig",
    # Executor (Engine Part)
    "Executor", "ExecutorConfig", "SimpleExecutor",
    # Module (Capability)
    "ExecutorModule", "ModuleConfig", "FdiModule", "FpiModule", "LibraryModule",
    # IPO
    "IpoFeature", "IpoInput", "IpoProcess", "IpoOutput",
    "IpoOrchestrator", "CaporDecision", "RacRoute",
    "DefaultIpoOrchestrator",
    # IPO Payload
    "IpoPayload", "ValidatedPayload", "extract_payload", "validate_payload",
    "build_payload_for_handler",
    # Capor
    "CaporRouter", "DefaultCaporRouter", "SecurityProfile", "Scorer",
    # Racor
    "RacRouter", "DefaultRacRouter", "RacUri", "RacTransportKind", "RacRule", "UriClassification",
    # Evidence
    "compute_feh_hash", "seal_alr_record", "build_proof",
    # Adapter
    "RacTransport", "TransportError", "TransportStats",
    "LocalNativeAdapter", "StdioIpcAdapter",
    # SIO
    "SioEnvelope", "SioResult", "SioMetadata", "TransportConfig", "RetryPolicy",
    # IO/RAC/CRI — FDI (wired)
    "FdiExecutor", "FdiMethod", "FdiTransport", "FDIMethodRegistry",
    "resolve_fdi_target", "create_fdi_executor",
    "_lazy_load_binding",
    # IO/RAC/CRI — FPI (wireless)
    "FpiExecutor", "FpiMethod", "FpiTransport", "FPIMethodRegistry",
    "FpiInstance",
    "resolve_fpi_target", "create_fpi_executor",
    # IO/RAC/CRI — FFI (native bridge)
    "FfiExecutor", "FfiMethod", "FfiTransport", "FFIMethodRegistry",
    "resolve_ffi_target", "create_ffi_executor",
    # RAC Method Contracts
    "RacMethodName", "RacMethodContract", "RAC_METHOD_CONTRACTS",
    "RacMethodDispatcher", "DefaultRacMethodDispatcher",
    "resolve_rac_target",
    # Route Resolver (CGE/CRD CANON-20260814)
    "RouteResolver", "RouteIndex", "NormalizedRoute", "SIOFrame",
    "create_resolver", "resolve_rac_uri",
    # RION Transports
    "StdioTransport", "StdioConfig", "StdioServerTransport",
    "HttpTransport", "HttpConfig", "HttpServerTransport",
    "WsTransport", "WsConfig", "WsServerTransport",
]
