# -*- coding: utf-8 -*-
"""
ROTA Test — Core Types
Runtime Operation Test Audit for executor_py.core
"""

import pytest
from executor_py.core import (
    ExecuteParticle, ExecContext, ExecInput, ExecOutput, SepiProof,
    ExecuteError, SioStatus, SioType, RacTransportError,
    ExecutionMode, ParticleClass, SecurityLevel,
    FanId, FanCapability, FanRegistry, Nep,
    SioEnvelope, SioResult, SioMetadata, TransportConfig, RetryPolicy,
    EnginePart, ExecutorDNA, ActorExecutorMapping, FesLayer,
)


class TestCoreTypes:
    """Test core type definitions and basic functionality."""
    
    def test_exec_context_creation(self):
        ctx = ExecContext(
            workspace_root="/workspace",
            actor_target="rac://cri.hace.fdi/hace/text-ractor",
            security_tier="local",
        )
        assert ctx.trace_id is not None
        assert ctx.workspace_root == "/workspace"
        assert ctx.security_tier == "local"
    
    def test_exec_input_creation(self):
        input = ExecInput(
            action="file.read_file",
            payload={"action": "file.read_file", "value": {"path": "test.txt"}},
            headers={"trace_id": "abc-123"},
            context={"workspace_root": "/workspace"},
        )
        assert input.action == "file.read_file"
        assert input.payload["value"]["path"] == "test.txt"
    
    def test_exec_output_creation(self):
        output = ExecOutput(
            result={"content": "hello"},
            status=SioStatus.SUCCESS,
        )
        assert output.result["content"] == "hello"
        assert output.status == SioStatus.SUCCESS
    
    def test_sepi_proof_creation(self):
        proof = SepiProof(
            fan_id="test-fan",
            action="test.action",
            status="accepted",
        )
        assert proof.execution_id is not None
        assert proof.fan_id == "test-fan"
    
    def test_execute_error(self):
        err = ExecuteError("TEST_CODE", "Test message", {"detail": "data"})
        assert err.code == "TEST_CODE"
        assert err.message == "Test message"
        assert err.data["detail"] == "data"
    
    def test_fan_id(self):
        fan = FanId(id="test-fan-id")
        assert str(fan) == "test-fan-id"
    
    def test_fan_capability(self):
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=lambda: None,
        )
        assert cap.id == "test.action"
        assert cap.transport == "FDI"
    
    def test_fan_registry(self):
        registry = FanRegistry()
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=lambda: None,
        )
        registry.register(cap)
        
        found = registry.find("test.action")
        assert found is not None
        assert found.id == "test.action"
        
        caps = registry.list_by_fan("test-fan")
        assert len(caps) == 1
    
    def test_sio_envelope(self):
        envelope = SioEnvelope(
            version=1,
            msg_id=123,
            source="test-source",
            target="test-target",
            sio_type=SioType.EXECUTE,
            payload={"action": "test"},
        )
        assert envelope.version == 1
        assert envelope.msg_id == 123
        assert envelope.sio_type == SioType.EXECUTE
    
    def test_sio_result_ok_err(self):
        ok = SioResult.ok(b"data")
        assert ok.code == 0
        assert ok.data == b"data"
        
        err = SioResult.err(500, "error message")
        assert err.code == 500
        assert err.error == "error message"
    
    def test_transport_config(self):
        config = TransportConfig(uri="rac://cri.hace.fdi/hace/test")
        assert config.uri == "rac://cri.hace.fdi/hace/test"
        assert config.timeout_ms == 5000
        assert config.retry is not None
    
    def test_engine_part(self):
        part = EnginePart(
            uri="rac://cri.hace.fdi/hace/executor-py/core",
            name="executor-py",
            layer=FesLayer.EXECUTOR,
        )
        assert part.layer == FesLayer.EXECUTOR
        assert part.name == "executor-py"
    
    def test_executor_dna(self):
        dna = ExecutorDNA(
            trait="IpoFeature",
            struct="DefaultIpoOrchestrator",
            features=["input", "process", "output"],
            bindings={"actor": "text-ractor"},
            lion_machine=True,
        )
        assert dna.trait == "IpoFeature"
        assert dna.lion_machine is True
    
    def test_actor_executor_mapping(self):
        mapping = ActorExecutorMapping(
            actor_uri="rac://cri.hace.fdi/hace/text-ractor",
            actor_name="text-ractor",
            executor_uri="rac://cri.hace.fdi/hace/executor-py/core",
            executor_name="executor-py",
            mode="mcv",
        )
        assert mapping.actor_name == "text-ractor"
        assert mapping.mode == "mcv"


class TestExecuteParticle:
    """Test ExecuteParticle abstract base class."""
    
    def test_abstract_execute(self):
        class TestParticle(ExecuteParticle):
            def execute(self, input, ctx):
                return ExecOutput(result="ok", status=SioStatus.SUCCESS)
        
        particle = TestParticle()
        input = ExecInput(action="test", payload={})
        ctx = ExecContext()
        result = particle.execute(input, ctx)
        assert result.result == "ok"
    
    def test_fan_id_optional(self):
        class TestParticle(ExecuteParticle):
            def execute(self, input, ctx):
                return ExecOutput(result="ok", status=SioStatus.SUCCESS)
        
        particle = TestParticle()
        assert particle.fan_id() is None


class TestEnums:
    """Test enum values."""
    
    def test_sio_status(self):
        assert SioStatus.SUCCESS.value == "success"
        assert SioStatus.FAILED.value == "failed"
        assert SioStatus.CANCELLED.value == "cancelled"
        assert SioStatus.TIMEOUT.value == "timeout"
    
    def test_sio_type(self):
        assert SioType.INTENT.value == "Intent"
        assert SioType.EXECUTE.value == "Execute"
        assert SioType.DATA.value == "Data"
    
    def test_execution_mode(self):
        assert ExecutionMode.PassThrough.value == "pass_through"
        assert ExecutionMode.LocalExecute.value == "local_execute"
        assert ExecutionMode.ChainExecute.value == "chain_execute"
    
    def test_particle_class(self):
        assert ParticleClass.Native.value == "native"
        assert ParticleClass.Python.value == "python"
        assert ParticleClass.Artifact.value == "artifact"
    
    def test_security_level(self):
        assert SecurityLevel.Local.value == "local"
        assert SecurityLevel.Shared.value == "shared"
        assert SecurityLevel.Restricted.value == "restricted"
    
    def test_fes_layer(self):
        assert FesLayer.ENGINE.value == "engine"
        assert FesLayer.EXECUTOR.value == "executor"
        assert FesLayer.MODULE.value == "module"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])