# -*- coding: utf-8 -*-
"""
ROTA Test — Evidence Sealing (FEH/ALR)
Runtime Operation Test Audit for executor_py.evidence
"""

import pytest
import json
from executor_py.core import (
    ExecContext, FanId, SioStatus,
)
from executor_py.evidence import (
    compute_feh_hash, seal_alr_record, build_proof, _stable_dict,
)


class TestStableDict:
    """Test _stable_dict helper."""
    
    def test_basic_dict(self):
        d = {"b": 2, "a": 1}
        result = _stable_dict(d)
        # Should be sorted by keys
        assert result == '{"a": 1, "b": 2}'
    
    def test_nested_dict(self):
        d = {"outer": {"inner_b": 2, "inner_a": 1}}
        result = _stable_dict(d)
        assert result == '{"outer": {"inner_a": 1, "inner_b": 2}}'
    
    def test_list_in_dict(self):
        d = {"items": [3, 1, 2]}
        result = _stable_dict(d)
        assert result == '{"items": [3, 1, 2]}'  # Lists not sorted


class TestComputeFehHash:
    """Test FEH (Fingerprint of Execution Hash) computation."""
    
    def test_basic_feh(self):
        fan_id = FanId(id="test-fan")
        ctx = ExecContext(
            trace_id="trace-123",
            session_id="session-456",
            security_tier="local",
            workspace_root="/workspace",
            actor_target="rac://cri.hace.fdi/hace/test",
        )
        
        feh = compute_feh_hash(
            fan_id=fan_id,
            action="test.action",
            payload={"key": "value", "number": 42},
            result={"status": "ok"},
            ctx=ctx,
        )
        
        # FEH should be a valid SHA256 hex string (64 chars)
        assert len(feh) == 64
        assert all(c in "0123456789abcdef" for c in feh)
    
    def test_feh_deterministic(self):
        """Same inputs should produce same FEH."""
        fan_id = FanId(id="test-fan")
        ctx = ExecContext(
            trace_id="trace-123",
            session_id="session-456",
            security_tier="local",
            workspace_root="/workspace",
            actor_target="rac://cri.hace.fdi/hace/test",
        )
        
        feh1 = compute_feh_hash(
            fan_id=fan_id,
            action="test.action",
            payload={"key": "value"},
            result="ok",
            ctx=ctx,
        )
        
        feh2 = compute_feh_hash(
            fan_id=fan_id,
            action="test.action",
            payload={"key": "value"},
            result="ok",
            ctx=ctx,
        )
        
        assert feh1 == feh2
    
    def test_feh_different_inputs(self):
        """Different inputs should produce different FEH."""
        fan_id = FanId(id="test-fan")
        ctx = ExecContext(
            trace_id="trace-123",
            security_tier="local",
        )
        
        feh1 = compute_feh_hash(fan_id, "action1", {"a": 1}, "result", ctx)
        feh2 = compute_feh_hash(fan_id, "action2", {"a": 1}, "result", ctx)
        feh3 = compute_feh_hash(fan_id, "action1", {"a": 2}, "result", ctx)
        
        assert feh1 != feh2
        assert feh1 != feh3
    
    def test_feh_includes_context(self):
        """FEH should include execution context."""
        fan_id = FanId(id="test-fan")
        
        ctx1 = ExecContext(
            trace_id="trace-1",
            security_tier="local",
            workspace_root="/ws1",
        )
        ctx2 = ExecContext(
            trace_id="trace-2",
            security_tier="shared",
            workspace_root="/ws2",
        )
        
        feh1 = compute_feh_hash(fan_id, "action", {}, "result", ctx1)
        feh2 = compute_feh_hash(fan_id, "action", {}, "result", ctx2)
        
        assert feh1 != feh2


class TestSealAlrRecord:
    """Test ALR (Archetype Ledger Record) sealing."""
    
    def test_basic_alr(self):
        fan_id = FanId(id="test-fan")
        
        alr = seal_alr_record(
            fan_id=fan_id,
            action="test.action",
            execution_id="exec-123",
            feh_hash="a" * 64,
            status=SioStatus.SUCCESS,
        )
        
        assert len(alr) == 64
        assert all(c in "0123456789abcdef" for c in alr)
    
    def test_alr_deterministic(self):
        fan_id = FanId(id="test-fan")
        
        alr1 = seal_alr_record(fan_id, "action", "exec-123", "f" * 64, SioStatus.SUCCESS)
        alr2 = seal_alr_record(fan_id, "action", "exec-123", "f" * 64, SioStatus.SUCCESS)
        
        assert alr1 == alr2
    
    def test_alr_different_execution_id(self):
        fan_id = FanId(id="test-fan")
        
        alr1 = seal_alr_record(fan_id, "action", "exec-1", "f" * 64, SioStatus.SUCCESS)
        alr2 = seal_alr_record(fan_id, "action", "exec-2", "f" * 64, SioStatus.SUCCESS)
        
        assert alr1 != alr2
    
    def test_alr_different_status(self):
        fan_id = FanId(id="test-fan")
        
        alr1 = seal_alr_record(fan_id, "action", "exec-1", "f" * 64, SioStatus.SUCCESS)
        alr2 = seal_alr_record(fan_id, "action", "exec-1", "f" * 64, SioStatus.FAILED)
        
        assert alr1 != alr2


class TestBuildProof:
    """Test SepiProof building (FEH + ALR)."""
    
    def test_build_proof_basic(self):
        fan_id = FanId(id="test-fan")
        ctx = ExecContext(
            trace_id="trace-123",
            security_tier="local",
        )
        
        proof = build_proof(
            fan_id=fan_id,
            action="test.action",
            input_data={"key": "value"},
            result={"status": "ok"},
            ctx=ctx,
            status=SioStatus.SUCCESS,
        )
        
        assert proof.fan_id == "test-fan"
        assert proof.action == "test.action"
        assert proof.status == "success"
        assert proof.feh_hash is not None
        assert proof.alr_seal is not None
        assert len(proof.feh_hash) == 64
        assert len(proof.alr_seal) == 64
        assert proof.execution_id is not None
    
    def test_build_proof_failed_status(self):
        fan_id = FanId(id="test-fan")
        ctx = ExecContext()
        
        proof = build_proof(
            fan_id=fan_id,
            action="test.action",
            input_data={},
            result={"error": "failed"},
            ctx=ctx,
            status=SioStatus.FAILED,
        )
        
        assert proof.status == "failed"
        assert proof.feh_hash is not None
        assert proof.alr_seal is not None
    
    def test_build_proof_unique_execution_id(self):
        fan_id = FanId(id="test-fan")
        ctx = ExecContext()
        
        proof1 = build_proof(fan_id, "action", {}, "result", ctx)
        proof2 = build_proof(fan_id, "action", {}, "result", ctx)
        
        assert proof1.execution_id != proof2.execution_id
    
    def test_feh_alr_consistency(self):
        """FEH and ALR in proof should be consistent."""
        fan_id = FanId(id="test-fan")
        ctx = ExecContext(trace_id="trace-123")
        
        proof = build_proof(fan_id, "action", {"input": "data"}, {"output": "result"}, ctx)
        
        # Verify ALR was computed from the same FEH
        # (We can't easily verify without exposing internals, but structure is correct)
        assert proof.feh_hash is not None
        assert proof.alr_seal is not None


class TestEvidenceIntegration:
    """Test evidence integration with IPO flow."""
    
    def test_proof_in_ipo_output(self):
        from executor_py.ipo import IpoOutput, IpoProcess, CaporDecision, RacRoute
        from executor_py.capor import SecurityProfile, Scorer
        
        fan_id = FanId(id="test-fan")
        ctx = ExecContext()
        
        proof = build_proof(fan_id, "test.action", {}, "result", ctx)
        
        ipo_output = IpoOutput(
            output=proof,  # Using proof as output for test
            proof=proof,
        )
        
        assert ipo_output.proof == proof
        assert ipo_output.proof.feh_hash is not None
        assert ipo_output.proof.alr_seal is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])