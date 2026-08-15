# -*- coding: utf-8 -*-
"""
ROTA Test — Capor Resolution (WHAT)
Runtime Operation Test Audit for executor_py.capor
"""

import pytest
from executor_py.core import (
    ExecContext, ExecInput, ExecOutput, SepiProof, ExecuteError,
    FanId, FanCapability, FanRegistry, SioStatus, SecurityLevel,
)
from executor_py.capor import (
    CaporRouter, DefaultCaporRouter, SecurityProfile, Scorer,
)
from executor_py.ipo import CaporDecision


class MockParticle:
    """Mock ExecuteParticle for testing."""
    def __init__(self, result="ok"):
        self.result = result
    
    def execute(self, input, ctx):
        return ExecOutput(result=self.result, status=SioStatus.SUCCESS)


class TestCaporDecision:
    """Test CaporDecision dataclass."""
    
    def test_capor_decision_creation(self):
        fan_id = FanId(id="test-fan")
        decision = CaporDecision(
            fan_id=fan_id,
            capability="test.action",
            security_profile=SecurityProfile(level="local"),
            scorer=Scorer(),
            reason="matched",
        )
        assert decision.fan_id == fan_id
        assert decision.capability == "test.action"
        assert decision.reason == "matched"


class TestSecurityProfile:
    """Test SecurityProfile."""
    
    def test_default_profile(self):
        profile = SecurityProfile()
        assert profile.level == "local"
        assert profile.capabilities == []
        assert profile.resource_limits == {}
    
    def test_custom_profile(self):
        profile = SecurityProfile(
            level="restricted",
            capabilities=["file.read", "file.write"],
            resource_limits={"max_memory_mb": 512},
            allowed_actors=["text-ractor"],
        )
        assert profile.level == "restricted"
        assert "file.read" in profile.capabilities
        assert profile.resource_limits["max_memory_mb"] == 512


class TestScorer:
    """Test Scorer weights."""
    
    def test_default_scorer(self):
        scorer = Scorer()
        assert scorer.capability_relevance == 1.0
        assert scorer.security_match == 1.0
        assert scorer.resource_availability == 0.5
        assert scorer.context_proximity == 0.3
    
    def test_custom_scorer(self):
        scorer = Scorer(
            capability_relevance=0.8,
            security_match=1.2,
            resource_availability=0.3,
            context_proximity=0.5,
        )
        assert scorer.capability_relevance == 0.8


class TestDefaultCaporRouter:
    """Test DefaultCaporRouter implementation."""
    
    def test_resolve_single_capability(self):
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
        assert decision.security_profile.level == "local"
    
    def test_resolve_multiple_capabilities_first_match(self):
        registry = FanRegistry()
        fan_id = FanId(id="test-fan")
        
        cap1 = FanCapability(
            id="test.action1",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=MockParticle(),
        )
        cap2 = FanCapability(
            id="test.action2",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=MockParticle(),
        )
        registry.register(cap1)
        registry.register(cap2)
        
        router = DefaultCaporRouter(registry)
        ctx = ExecContext(security_tier="local")
        
        decision = router.resolve(ctx, fan_id)
        
        assert decision.capability == "test.action1"  # First registered
        assert decision.reason == "matched"
    
    def test_resolve_no_capabilities_fallback(self):
        registry = FanRegistry()
        fan_id = FanId(id="empty-fan")
        
        router = DefaultCaporRouter(registry)
        ctx = ExecContext(security_tier="local")
        
        decision = router.resolve(ctx, fan_id)
        
        # Should still return a decision but with restricted profile
        assert decision.fan_id == fan_id
        assert decision.reason == "fallback_no_match"
        assert decision.security_profile.level == "restricted"
    
    def test_evaluate_capability_allowed_actor(self):
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
        ctx = ExecContext(security_tier="local", actor_target="test-fan")
        
        assert router.evaluate_capability(ctx, cap) is True
    
    def test_evaluate_capability_security_tier(self):
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
        
        # Local tier - allowed
        ctx_local = ExecContext(security_tier="local")
        assert router.evaluate_capability(ctx_local, cap) is True
        
        # Shared tier - default allows
        ctx_shared = ExecContext(security_tier="shared")
        assert router.evaluate_capability(ctx_shared, cap) is True
        
        # Restricted tier - default denies
        ctx_restricted = ExecContext(security_tier="restricted")
        assert router.evaluate_capability(ctx_restricted, cap) is False


class TestCaporRouterInterface:
    """Test CaporRouter abstract interface."""
    
    def test_abstract_methods(self):
        # Cannot instantiate abstract class
        with pytest.raises(TypeError):
            CaporRouter()
    
    def test_custom_capor_router(self):
        class CustomCaporRouter(CaporRouter):
            def resolve(self, ctx, fan_id):
                return CaporDecision(
                    fan_id=fan_id,
                    capability="custom.action",
                    security_profile=SecurityProfile(level="local"),
                    scorer=Scorer(),
                    reason="custom",
                )
            
            def evaluate_capability(self, ctx, cap):
                return True
        
        router = CustomCaporRouter()
        ctx = ExecContext()
        fan_id = FanId(id="test")
        
        decision = router.resolve(ctx, fan_id)
        assert decision.capability == "custom.action"
        assert decision.reason == "custom"
        
        assert router.evaluate_capability(ctx, None) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])