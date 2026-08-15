# -*- coding: utf-8 -*-
"""
ROTA Test — IPO Pipeline
Runtime Operation Test Audit for executor_py.ipo
"""

import pytest
from executor_py.core import (
    ExecContext, ExecInput, ExecOutput, SepiProof, ExecuteError,
    FanId, FanCapability, FanRegistry, SioStatus, ExecutionMode,
)
from executor_py.ipo import (
    IpoFeature, IpoInput, IpoProcess, IpoOutput,
    IpoOrchestrator, CaporDecision, RacRoute,
    DefaultIpoOrchestrator,
)
from executor_py.capor import CaporRouter, DefaultCaporRouter, SecurityProfile, Scorer
from executor_py.racor import RacRouter, DefaultRacRouter, RacUri, RacTransportKind


class MockParticle:
    """Mock ExecuteParticle for testing."""
    def __init__(self, result="ok"):
        self.result = result
    
    def execute(self, input, ctx):
        return ExecOutput(result=self.result, status=SioStatus.SUCCESS)
    
    def fan_id(self):
        return FanId(id="mock-fan")


class TestCaporRouter:
    """Test Capor (WHAT) resolution."""
    
    def test_default_capor_router(self):
        registry = FanRegistry()
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=MockParticle(),
        )
        registry.register(cap)
        
        router = DefaultCaporRouter(registry)
        ctx = ExecContext(security_tier="local")
        
        decision = router.resolve(ctx, fan_id)
        assert decision.fan_id == fan_id
        assert decision.capability == "test.action"
        assert decision.reason == "matched"
    
    def test_capor_evaluate_capability(self):
        registry = FanRegistry()
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=MockParticle(),
        )
        registry.register(cap)
        
        router = DefaultCaporRouter(registry)
        ctx = ExecContext(security_tier="local", actor_target="test")
        
        assert router.evaluate_capability(ctx, cap) is True


class TestRacRouter:
    """Test Racor (HOW/WHERE) resolution."""
    
    def test_rac_uri_parse(self):
        uri = RacUri.parse("rac://cri.hace.fdi/hace/executor-py/io/rac/cri/fdi")
        assert uri.rule == "cri"
        assert uri.ownerspace == "hace"
        assert uri.specs == "fdi"
        assert uri.path == "hace/executor-py/io/rac/cri/fdi"
        assert uri.transport == "Ffi"
    
    def test_rac_uri_classify(self):
        uri = RacUri.parse("rac://cri.hace.fdi/hace/executor-py/io/rac/cri/fdi")
        classification = uri.classify()
        assert classification.transport == RacTransportKind.Ffi
        assert classification.rns_owner == "hace"
        assert classification.is_classic_bridge is True
        assert classification.rule == "cri"
    
    def test_default_rac_router_resolve_target(self):
        uri = RacUri.parse("rac://cri.hace.fdi/hace/executor-py/io/rac/cri/fdi")
        router = DefaultRacRouter()
        target = router.resolve_target(uri)
        
        assert target["rule"] == "cri"
        assert target["ownerspace"] == "hace"
        assert target["specs"] == "fdi"
        assert target["transport"] == "Ffi"
        assert target["rns_owner"] == "hace"
    
    def test_default_rac_router_resolve_route(self):
        router = DefaultRacRouter()
        fan_id = FanId(id="test-fan")
        route = router.resolve_route(fan_id, "rac://cri.hace.fdi/hace/test/action")
        
        assert route.target == "rac://cri.hace.fdi/hace/test/action"
        assert route.transport == "Ffi"
        assert route.machine == "hace-lion-machine"
        assert route.adapter == "adapters/ffi"
    
    def test_racor_transport_mapping(self):
        router = DefaultRacRouter()
        
        # FDI -> LION
        uri_fdi = RacUri.parse("rac://cri.hace.fdi/hace/test")
        assert router.resolve_transport(uri_fdi) == RacTransportKind.Ffi
        
        # FPI -> RION
        uri_fpi = RacUri.parse("rac://cri.hace.fpi/hace/test")
        assert router.resolve_transport(uri_fpi) == RacTransportKind.HostCall
        
        # HTTP -> RION
        uri_http = RacUri.parse("rac://cri.hace.http/hace/test")
        assert router.resolve_transport(uri_http) == RacTransportKind.HttpBridge


class TestIpoOrchestrator:
    """Test IPO Orchestrator (Input → Process → Output)."""
    
    def test_ipo_orchestrator_resolve_capacity(self):
        registry = FanRegistry()
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=MockParticle(),
        )
        registry.register(cap)
        
        capor = DefaultCaporRouter(registry)
        racor = DefaultRacRouter()
        orchestrator = IpoOrchestrator(capor, racor)
        
        ctx = ExecContext(security_tier="local")
        decision = orchestrator.resolve_capacity(ctx, fan_id)
        
        assert decision.fan_id == fan_id
        assert decision.capability == "test.action"
    
    def test_ipo_orchestrator_resolve_route(self):
        capor = DefaultCaporRouter()
        racor = DefaultRacRouter()
        orchestrator = IpoOrchestrator(capor, racor)
        
        fan_id = FanId(id="test-fan")
        route = orchestrator.resolve_route(fan_id, "rac://cri.hace.fdi/hace/test/action")
        
        assert route.machine == "hace-lion-machine"
        assert route.transport == "Ffi"


class TestDefaultIpoOrchestrator:
    """Test DefaultIpoOrchestrator implementation."""
    
    def test_input_phase(self):
        registry = FanRegistry()
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=MockParticle(),
        )
        registry.register(cap)
        
        orchestrator = DefaultIpoOrchestrator(
            DefaultCaporRouter(registry),
            DefaultRacRouter(),
        )
        
        request = {
            "rac_uri": "rac://cri.hace.fdi/hace/test/action",
            "method": "call",
            "payload": {"action": "test.action", "value": {"key": "value"}},
            "headers": {"trace_id": "abc-123"},
            "context": {"workspace_root": "/workspace"},
        }
        
        ipo_input = orchestrator.input(request)
        
        assert isinstance(ipo_input, IpoInput)
        assert ipo_input.fan_id.id == "test-fan"
        assert ipo_input.validated_payload.action == "test.action"
        assert ipo_input.context.workspace_root == "/workspace"
    
    def test_process_phase(self):
        registry = FanRegistry()
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=MockParticle(),
        )
        registry.register(cap)
        
        orchestrator = DefaultIpoOrchestrator(
            DefaultCaporRouter(registry),
            DefaultRacRouter(),
        )
        
        # Create IpoInput manually
        ipo_input = IpoInput(
            context=ExecContext(security_tier="local"),
            fan_id=fan_id,
            normalized_uri="rac://cri.hace.fdi/hace/test/action",
            validated_payload=ExecInput(action="test.action", payload={}),
        )
        
        ipo_process = orchestrator.process(ipo_input)
        
        assert isinstance(ipo_process, IpoProcess)
        assert ipo_process.capacity.capability == "test.action"
        assert ipo_process.route.machine == "hace-lion-machine"
        assert ipo_process.mode == ExecutionMode.LocalExecute
        assert isinstance(ipo_process.particle, MockParticle)
    
    def test_full_ipo_execute(self):
        registry = FanRegistry()
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=MockParticle("executed"),
        )
        registry.register(cap)
        
        orchestrator = DefaultIpoOrchestrator(
            DefaultCaporRouter(registry),
            DefaultRacRouter(),
        )
        
        request = {
            "rac_uri": "rac://cri.hace.fdi/hace/test/action",
            "method": "call",
            "payload": {"action": "test.action", "value": {}},
            "headers": {},
            "context": {},
        }
        
        result = orchestrator.execute(request)
        
        assert isinstance(result, IpoOutput)
        assert result.output.result == "executed"
        assert result.output.status == SioStatus.SUCCESS
        assert result.proof is not None
        assert result.proof.fan_id == "test-fan"
        assert result.proof.action == "test.action"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])