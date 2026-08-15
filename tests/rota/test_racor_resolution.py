# -*- coding: utf-8 -*-
"""
ROTA Test — Racor Resolution (HOW/WHERE)
Runtime Operation Test Audit for executor_py.racor
"""

import pytest
from executor_py.core import FanId
from executor_py.racor import (
    RacRouter, DefaultRacRouter,
    RacUri, RacTransportKind, RacRule, UriClassification, RacRoute,
)


class TestRacUri:
    """Test RacUri V4 parsing."""
    
    def test_parse_valid_fdi_uri(self):
        uri = RacUri.parse("rac://cri.hace.fdi/hace/executor-py/io/rac/cri/fdi")
        assert uri.raw == "rac://cri.hace.fdi/hace/executor-py/io/rac/cri/fdi"
        assert uri.rule == "cri"
        assert uri.ownerspace == "hace"
        assert uri.specs == "fdi"
        assert uri.path == "hace/executor-py/io/rac/cri/fdi"
        assert uri.transport == "Ffi"
    
    def test_parse_valid_fpi_uri(self):
        uri = RacUri.parse("rac://cri.hace.fpi/hace/executor-py/io/rac/cri/fpi")
        assert uri.rule == "cri"
        assert uri.ownerspace == "hace"
        assert uri.specs == "fpi"
        assert uri.transport == "HostCall"
    
    def test_parse_valid_ffi_uri(self):
        uri = RacUri.parse("rac://cri.local.ffi/hace/executor-py/io/rac/cri/diff")
        assert uri.specs == "ffi"
        assert uri.transport == "Ffi"
    
    def test_parse_valid_http_uri(self):
        uri = RacUri.parse("rac://api.hace.http/hace/text-editor/file/read")
        assert uri.rule == "api"
        assert uri.specs == "http"
        assert uri.transport == "HttpBridge"
    
    def test_parse_valid_grpc_uri(self):
        uri = RacUri.parse("rac://rpc.hace.grpc/hace/service/method")
        assert uri.rule == "rpc"
        assert uri.specs == "grpc"
        assert uri.transport == "GrpcBridge"
    
    def test_parse_valid_ws_uri(self):
        uri = RacUri.parse("rac://ws.hace.ws/hace/stream/events")
        assert uri.rule == "ws"
        assert uri.specs == "ws"
        assert uri.transport == "HttpBridge"  # WS maps to HttpBridge in current impl
    
    def test_parse_no_path(self):
        uri = RacUri.parse("rac://cri.hace.fdi")
        assert uri.path == ""
        assert uri.transport == "Ffi"
    
    def test_parse_invalid_no_rac_prefix(self):
        with pytest.raises(ValueError) as exc_info:
            RacUri.parse("http://example.com")
        assert "Not a RAC URI" in str(exc_info.value)
    
    def test_parse_invalid_spec_part(self):
        with pytest.raises(ValueError) as exc_info:
            RacUri.parse("rac://invalid")
        assert "Invalid RAC URI spec part" in str(exc_info.value)
    
    def test_canonical_string(self):
        uri = RacUri.parse("rac://cri.hace.fdi/hace/test")
        assert uri.canonical_string() == "rac://cri.hace.fdi/hace/test"
    
    def test_classify_fdi(self):
        uri = RacUri.parse("rac://cri.hace.fdi/hace/test")
        classification = uri.classify()
        assert classification.transport == RacTransportKind.Ffi
        assert classification.rns_owner == "hace"
        assert classification.is_classic_bridge is True
        assert classification.rule == "cri"
    
    def test_classify_fpi(self):
        uri = RacUri.parse("rac://cri.hace.fpi/hace/test")
        classification = uri.classify()
        assert classification.transport == RacTransportKind.HostCall
        assert classification.is_classic_bridge is True
    
    def test_classify_different_rule(self):
        uri = RacUri.parse("rac://api.hace.fdi/hace/test")
        classification = uri.classify()
        assert classification.rule == "api"
        assert classification.is_classic_bridge is False


class TestUriClassification:
    """Test UriClassification dataclass."""
    
    def test_creation(self):
        classification = UriClassification(
            transport=RacTransportKind.Ffi,
            rns_owner="hace",
            is_classic_bridge=True,
            rule="cri",
        )
        assert classification.transport == RacTransportKind.Ffi
        assert classification.rns_owner == "hace"
        assert classification.is_classic_bridge is True


class TestRacTransportKind:
    """Test RacTransportKind enum."""
    
    def test_all_kinds(self):
        assert RacTransportKind.Ffi.value == "ffi"
        assert RacTransportKind.HostCall.value == "host_call"
        assert RacTransportKind.Wasm.value == "wasm"
        assert RacTransportKind.Pipe.value == "pipe"
        assert RacTransportKind.SharedMem.value == "shm"
        assert RacTransportKind.HttpBridge.value == "http"
        assert RacTransportKind.GrpcBridge.value == "grpc"


class TestRacRule:
    """Test RacRule enum."""
    
    def test_all_rules(self):
        assert RacRule.Cri.value == "cri"
        assert RacRule.Api.value == "api"
        assert RacRule.Rpc.value == "rpc"
        assert RacRule.Rti.value == "rti"
        assert RacRule.Ws.value == "ws"
        assert RacRule.Ex.value == "ex"
        assert RacRule.On.value == "on"
        assert RacRule.Net.value == "net"
        assert RacRule.A2a.value == "a2a"


class TestDefaultRacRouter:
    """Test DefaultRacRouter implementation."""
    
    def test_resolve_target_fdi(self):
        uri = RacUri.parse("rac://cri.hace.fdi/hace/executor-py/test")
        router = DefaultRacRouter()
        target = router.resolve_target(uri)
        
        assert target["rule"] == "cri"
        assert target["ownerspace"] == "hace"
        assert target["specs"] == "fdi"
        assert target["transport"] == "Ffi"
        assert target["rns_owner"] == "hace"
        assert target["is_classic_bridge"] is True
    
    def test_resolve_target_fpi(self):
        uri = RacUri.parse("rac://cri.hace.fpi/hace/executor-py/test")
        router = DefaultRacRouter()
        target = router.resolve_target(uri)
        
        assert target["specs"] == "fpi"
        assert target["transport"] == "HostCall"
    
    def test_resolve_route_fdi(self):
        router = DefaultRacRouter()
        fan_id = FanId(id="test-fan")
        route = router.resolve_route(fan_id, "rac://cri.hace.fdi/hace/test/action")
        
        assert route.target == "rac://cri.hace.fdi/hace/test/action"
        assert route.transport == "Ffi"
        assert route.machine == "hace-lion-machine"
        assert route.adapter == "adapters/ffi"
        assert route.endpoint is None
    
    def test_resolve_route_fpi(self):
        router = DefaultRacRouter()
        fan_id = FanId(id="test-fan")
        route = router.resolve_route(fan_id, "rac://cri.hace.fpi/hace/test/action")
        
        assert route.transport == "HostCall"
        assert route.machine == "hace-rion-machine"
        assert route.adapter == "adapters/host_call"
    
    def test_resolve_route_http(self):
        router = DefaultRacRouter()
        fan_id = FanId(id="test-fan")
        route = router.resolve_route(fan_id, "rac://cri.hace.http/hace/test/action")
        
        assert route.transport == "HttpBridge"
        assert route.machine == "hace-rion-machine"
        assert route.adapter == "adapters/http"
    
    def test_resolve_route_grpc(self):
        router = DefaultRacRouter()
        fan_id = FanId(id="test-fan")
        route = router.resolve_route(fan_id, "rac://cri.hace.grpc/hace/test/action")
        
        assert route.transport == "GrpcBridge"
        assert route.machine == "hace-rion-machine"
        assert route.adapter == "adapters/grpc"
    
    def test_resolve_transport_fdi(self):
        router = DefaultRacRouter()
        uri = RacUri.parse("rac://cri.hace.fdi/hace/test")
        assert router.resolve_transport(uri) == RacTransportKind.Ffi
    
    def test_resolve_transport_fpi(self):
        router = DefaultRacRouter()
        uri = RacUri.parse("rac://cri.hace.fpi/hace/test")
        assert router.resolve_transport(uri) == RacTransportKind.HostCall
    
    def test_resolve_transport_wasm(self):
        router = DefaultRacRouter()
        uri = RacUri.parse("rac://cri.hace.wasm/hace/test")
        assert router.resolve_transport(uri) == RacTransportKind.Wasm
    
    def test_resolve_transport_pipe(self):
        router = DefaultRacRouter()
        uri = RacUri.parse("rac://cri.hace.pipe/hace/test")
        assert router.resolve_transport(uri) == RacTransportKind.Pipe
    
    def test_resolve_transport_shm(self):
        router = DefaultRacRouter()
        uri = RacUri.parse("rac://cri.hace.shm/hace/test")
        assert router.resolve_transport(uri) == RacTransportKind.SharedMem
    
    def test_resolve_transport_http(self):
        router = DefaultRacRouter()
        uri = RacUri.parse("rac://cri.hace.http/hace/test")
        assert router.resolve_transport(uri) == RacTransportKind.HttpBridge
    
    def test_resolve_transport_grpc(self):
        router = DefaultRacRouter()
        uri = RacUri.parse("rac://cri.hace.grpc/hace/test")
        assert router.resolve_transport(uri) == RacTransportKind.GrpcBridge


class TestRacRoute:
    """Test RacRoute dataclass."""
    
    def test_creation(self):
        route = RacRoute(
            target="rac://cri.hace.fdi/hace/test",
            transport="Ffi",
            machine="hace-lion-machine",
            endpoint="http://localhost:8080",
            adapter="adapters/ffi",
        )
        assert route.target == "rac://cri.hace.fdi/hace/test"
        assert route.transport == "Ffi"
        assert route.machine == "hace-lion-machine"
        assert route.endpoint == "http://localhost:8080"
        assert route.adapter == "adapters/ffi"
    
    def test_minimal_creation(self):
        route = RacRoute(
            target="rac://cri.hace.fdi/hace/test",
            transport="Ffi",
            machine="hace-lion-machine",
        )
        assert route.endpoint is None
        assert route.adapter is None


class TestRacRouterInterface:
    """Test RacRouter abstract interface."""
    
    def test_abstract_methods(self):
        with pytest.raises(TypeError):
            RacRouter()
    
    def test_custom_rac_router(self):
        class CustomRacRouter(RacRouter):
            def resolve_target(self, rac_uri):
                return {"custom": True}
            
            def resolve_route(self, fan_id, rac_uri):
                return RacRoute(
                    target=rac_uri,
                    transport="Custom",
                    machine="custom-machine",
                )
            
            def resolve_transport(self, uri):
                return RacTransportKind.Ffi
        
        router = CustomRacRouter()
        fan_id = FanId(id="test")
        
        target = router.resolve_target(RacUri.parse("rac://cri.hace.fdi/test"))
        assert target["custom"] is True
        
        route = router.resolve_route(fan_id, "rac://test")
        assert route.machine == "custom-machine"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])