"""
# Executor-Py SDK — Racor Router

Mirrors `hace/sdk/executor-cep/src/core/racor.rs` (RacRouter, RacUri, RacRoute,
RacTransportKind).

Racor resolves HOW/WHERE to route — not WHAT capacity (that's Capor).

Integration:
    - IPO Process phase calls RacRouter.resolve_route() to get route plan
    - Delegates to LION Machine (local) or RION Machine (remote) based on transport kind

Per `hace-racor-resolver.ail`:
    rac_uri = rac://{rule}.{ownerspace}.{specs}/{path}
    - rule: cri, api, rpc, rti, ws, ex, on, net, a2a
    - ownerspace: hace, hacex, google-ai, local
    - specs: fdi, ffi, fpi, grpc, http, wasm, ...
    - path: provider/actor/module/action
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .core import FanId
from .ipo import RacRoute


class RacTransportKind(Enum):
    """Transport kind enum — mirrors RacTransportKind in io/rac/src/racor.rs.

    Maps canonical specs to runtime transport enums.
    """
    Ffi = "ffi"              # Direct Rust FFI import
    HostCall = "host_call"   # Host function call
    Wasm = "wasm"            # In-memory WebAssembly
    Pipe = "pipe"            # Unix socket / named pipe
    SharedMem = "shm"        # Shared memory channel
    HttpBridge = "http"      # HTTP bridge
    GrpcBridge = "grpc"      # gRPC bridge


class RacRule(Enum):
    """RAC rule families — mirrors rule enum in uri.rs.

    From RAC-URI-MAP.ail V4.0.0.
    """
    Cri = "cri"   # Core RPC Interface
    Api = "api"   # API gateway
    Rpc = "rpc"   # RPC
    Rti = "rti"   # Remote Tool Interface
    Ws = "ws"     # WebSocket
    Ex = "ex"     # External
    On = "on"     # On-device
    Net = "net"   # Network
    A2a = "a2a"   # Agent-to-Agent


@dataclass
class RacUri:
    """Parsed RAC URI — mirrors RacUri in io/rac/src/uri.rs.

    Canonical V4 grammar: rac://{rule}.{ownerspace}.{specs}/{path}

    Example: rac://cri.local.hace.fdi/hace/py-text-editor/file/create_file
    """
    raw: str
    rule: str          # "cri"
    ownerspace: str    # "hace"
    specs: str         # "fdi"
    path: str         # "hace/py-text-editor/file/create_file"
    transport: str    # "Ffi" (mapped from specs)

    @classmethod
    def parse(cls, uri: str) -> "RacUri":
        """Parse a RAC URI following V4 grammar.

        rac://cri.hace.fdi/hace/py-text-editor/file/create_file
        → rule=cri, ownerspace=hace, specs=fdi, path=hace/py-text-editor/file/create_file
        """
        if not uri.startswith("rac://"):
            raise ValueError(f"Not a RAC URI: {uri}")

        # Split into spec_part + path
        rest = uri[6:]  # Remove "rac://"
        if "/" in rest:
            spec_part, path = rest.split("/", 1)
        else:
            spec_part, path = rest, ""

        # Split spec_part on "." → [rule, ownerspace, specs]
        parts = spec_part.split(".")
        if len(parts) < 3:
            raise ValueError(f"Invalid RAC URI spec part: {spec_part}")

        rule = parts[0]
        specs = parts[-1]  # Last part is always the transport spec
        ownerspace = ".".join(parts[1:-1])  # Join middle parts for multi-part ownerspace

        # Map specs to transport kind
        transport_map = {
            "fdi": RacTransportKind.Ffi,
            "ffi": RacTransportKind.Ffi,
            "fpi": RacTransportKind.HostCall,
            "wasm": RacTransportKind.Wasm,
            "grpc": RacTransportKind.GrpcBridge,
            "http": RacTransportKind.HttpBridge,
            "ws": RacTransportKind.HttpBridge,   # WS maps to HttpBridge in V4
            "pipe": RacTransportKind.Pipe,
            "shm": RacTransportKind.SharedMem,
        }
        transport = transport_map.get(specs, RacTransportKind.Ffi)
        # Store as string (capitalized name) for URI field — tests expect "Ffi"
        transport_str = transport.name
        return cls(
            raw=uri,
            rule=rule,
            ownerspace=ownerspace,
            specs=specs,
            path=path,
            transport=transport_str,
        )

    def canonical_string(self) -> str:
        """Return canonical URI string (preserved verbatim per RC §6)."""
        return self.raw

    def classify(self) -> "UriClassification":
        """Classify the URI — mirrors RacUri::classify() in uri.rs.

        Returns classification with transport, rns_owner, is_classic_bridge, rule.
        """
        transport = self.transport
        if isinstance(transport, str):
            transport = RacTransportKind.__members__.get(transport)
            if transport is None:
                # Try lowercase lookup
                for k, v in RacTransportKind.__members__.items():
                    if v.value == transport:
                        transport = v
                        break
            if transport is None:
                transport = RacTransportKind.Ffi
        return UriClassification(
            transport=transport,
            rns_owner=self.ownerspace,
            is_classic_bridge=self.rule == "cri",
            rule=self.rule,
        )


@dataclass
class UriClassification:
    """URI classification result — mirrors UriClassification in uri.rs."""
    transport: RacTransportKind
    rns_owner: str
    is_classic_bridge: bool
    rule: str


class RacRouter(ABC):
    """RACOR Router — resolves HOW/WHERE to route (not WHAT).

    Mirrors RacRouter in executor-cep/src/io/racor.rs.

    Responsible for:
    - Resolve rac_uri → resolved identity (provider, actor, engine, executor)
    - Resolve transport kind
    - Produce RoutePlan with machine binding (LION vs RION)
    """

    @abstractmethod
    def resolve_target(self, rac_uri: RacUri) -> dict:
        """Resolve RNS dimensions (rule, owner, specs, path).

        Mirrors resolve() in io/rac/src/resolver.rs.
        """
        ...

    @abstractmethod
    def resolve_route(self, fan_id: FanId, rac_uri: str) -> RacRoute:
        """Full resolve + route: produce RoutePlan.

        Mirrors resolve_orchestrate() in io/rac/src/racor.rs.
        """
        ...

    @abstractmethod
    def resolve_transport(self, uri: RacUri) -> RacTransportKind:
        """Resolve transport kind from URI specs.

        Mirrors RacTransportKind resolution in racor.rs.
        """
        ...


class DefaultRacRouter(RacRouter):
    """Default Racor router implementation.

    Maps canonical specs → RacTransportKind, then
    selects LION (local) or RION (remote) machine.
    """

    def resolve_target(self, rac_uri: RacUri) -> dict:
        """Resolve RNS dimensions from parsed URI."""
        classification = rac_uri.classify()
        # Reconstruct full ownerspace from raw URI for multi-part ownerspace
        rest = rac_uri.raw[6:]  # Remove "rac://"
        if "/" in rest:
            spec_part = rest.split("/")[0]
        else:
            spec_part = rest
        parts = spec_part.split(".")
        full_ownerspace = ".".join(parts[1:-1]) if len(parts) >= 3 else rac_uri.ownerspace

        return {
            "rule": rac_uri.rule,
            "ownerspace": full_ownerspace,
            "specs": rac_uri.specs,
            "path": rac_uri.path,
            "transport": rac_uri.transport,
            "rns_owner": full_ownerspace,
            "is_classic_bridge": classification.is_classic_bridge,
        }

    def resolve_route(self, fan_id: FanId, rac_uri: str) -> RacRoute:
        """Resolve + route: produce RoutePlan."""
        uri = RacUri.parse(rac_uri)
        transport = self.resolve_transport(uri)

        # LION for local native transports, RION for remote/wireless
        if transport in (RacTransportKind.Ffi, RacTransportKind.Wasm,
                         RacTransportKind.Pipe, RacTransportKind.SharedMem):
            machine = "hace-lion-machine"
            mode = "local"
        else:
            machine = "hace-rion-machine"
            mode = "remote"

        return RacRoute(
            target=uri.canonical_string(),
            transport=uri.transport,  # Capitalized name string: "Ffi", "HostCall", etc.
            machine=machine,
            endpoint=None,
            adapter=f"adapters/{transport.value}",
        )

    def resolve_transport(self, uri: RacUri) -> RacTransportKind:
        """Resolve transport kind from URI specs.

        Mirrors DefaultRacRouter::resolve_transport in racor.rs.
        """
        return uri.classify().transport
