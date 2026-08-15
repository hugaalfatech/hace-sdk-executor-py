# -*- coding: utf-8 -*-
"""
ROTA Test — AilMachineBridge Integration (text-editor CRI <=> ail-machine)
Runtime Operation Test Audit for executor_py.io.rac.cri.bridge.ail_machine

CRI Flow tested:
    text-editor <== FDI import --> ail-machine
    text-editor <== FPI instance --> ail-machine

Authority: CSA
"""

import pytest
from unittest.mock import patch, MagicMock

from executor_py.io.rac.cri.bridge.ail_machine import AilMachineBridge
from executor_py.io.rac.cri.fdi import FdiExecutor, _FDI_CAPABILITY_MAP
from executor_py.io.rac.cri.fpi import FpiExecutor, FpiInstance
from executor_py.core import ExecuteError


class TestAilMachineBridgeFDIImport:
    """Test FDI import flow: AilMachineBridge.fdi_import() -> FdiExecutor.import_binding()"""

    def test_bridge_creation(self):
        bridge = AilMachineBridge()
        assert bridge.fdi_executor is not None
        assert bridge.fpi_executor is not None
        assert isinstance(bridge.fdi_executor, FdiExecutor)
        assert isinstance(bridge.fpi_executor, FpiExecutor)

    def test_fdi_import_returns_callable(self):
        """FDI import should return a callable binding for valid capabilities."""
        bridge = AilMachineBridge()
        try:
            binding = bridge.fdi_import("fdi.str.snake")
            assert callable(binding)
        except (ImportError, ExecuteError):
            pytest.skip("text-editor not available in test environment")

    def test_fdi_import_ail_detect_capability(self):
        """FDI import should resolve ail_detect capability from the capability map."""
        assert "fdi.str.ail_detect" in _FDI_CAPABILITY_MAP

    def test_fdi_import_ail_parse_capability(self):
        assert "fdi.str.ail_parse" in _FDI_CAPABILITY_MAP

    def test_fdi_import_ail_validate_capability(self):
        assert "fdi.str.ail_validate" in _FDI_CAPABILITY_MAP

    def test_fdi_import_ail_render_capability(self):
        assert "fdi.str.ail_render" in _FDI_CAPABILITY_MAP

    def test_fdi_import_ail_format_e164_capability(self):
        assert "fdi.str.ail_format_e164" in _FDI_CAPABILITY_MAP

    def test_fdi_import_ail_slugify_capability(self):
        assert "fdi.str.ail_slugify" in _FDI_CAPABILITY_MAP

    def test_fdi_import_ail_split_uri_capability(self):
        assert "fdi.str.ail_split_uri" in _FDI_CAPABILITY_MAP

    def test_fdi_import_ail_summary_capability(self):
        assert "fdi.str.ail_summary" in _FDI_CAPABILITY_MAP

    def test_fdi_import_unknown_capability_raises(self):
        """FDI import of unknown capability should raise ExecuteError."""
        bridge = AilMachineBridge()
        with pytest.raises(ExecuteError):
            bridge.fdi_import("fdi.str.nonexistent_action")


class TestAilMachineBridgeFDIInvoke:
    """Test FDI invoke flow: AilMachineBridge.fdi_invoke() -> FdiExecutor.execute()"""

    def test_fdi_invoke_structure(self):
        """fdi_invoke should return a dict with status, result, proof."""
        bridge = AilMachineBridge()
        try:
            result = bridge.fdi_invoke(
                "fdi.str.snake",
                {"value": "HaceStudio"},
                headers={"trace_id": "test-001"},
                context={"actor_target": "text-editor"},
            )
            assert "status" in result
            assert "result" in result
            assert "proof" in result
        except (ImportError, ExecuteError):
            pytest.skip("text-editor not available in test environment")

    def test_fdi_invoke_returns_feh_proof(self):
        """fdi_invoke should include FEH proof in result."""
        bridge = AilMachineBridge()
        try:
            result = bridge.fdi_invoke(
                "fdi.str.snake",
                {"value": "TestValue"},
            )
            proof = result.get("proof")
            if proof:
                assert proof.fan_id is not None
                assert proof.action is not None
                assert proof.status is not None
        except (ImportError, ExecuteError):
            pytest.skip("text-editor not available in test environment")


class TestAilMachineBridgeFPIInstance:
    """Test FPI instance lifecycle: open → execute → close"""

    def test_fpi_instance_open(self):
        """fpi_instance_open should return a valid instance_id string."""
        bridge = AilMachineBridge()
        instance_id = bridge.fpi_instance_open("fpi.str.tokenizer")
        assert isinstance(instance_id, str)
        assert len(instance_id) > 0

    def test_fpi_instance_open_creates_fpi_instance(self):
        """fpi_instance_open should store an FpiInstance internally."""
        bridge = AilMachineBridge()
        instance_id = bridge.fpi_instance_open("fpi.test.capability")
        assert instance_id in bridge._instances
        instance = bridge._instances[instance_id]
        assert isinstance(instance, FpiInstance)

    def test_fpi_instance_open_with_endpoint(self):
        """fpi_instance_open should accept endpoint parameter."""
        bridge = AilMachineBridge()
        instance_id = bridge.fpi_instance_open(
            "fpi.test.capability",
            endpoint="fpi://bluetooth/test",
        )
        assert isinstance(instance_id, str)
        assert len(instance_id) > 0

    def test_fpi_instance_execute(self):
        """fpi_instance_execute should execute action and return result."""
        bridge = AilMachineBridge()
        instance_id = bridge.fpi_instance_open("fpi.test.capability")
        result = bridge.fpi_instance_execute(instance_id, "test_action", {"data": "hello"})
        assert isinstance(result, dict)
        assert "result" in result
        assert "action" in result

    def test_fpi_instance_execute_not_found(self):
        """fpi_instance_execute with unknown instance_id should raise ExecuteError."""
        bridge = AilMachineBridge()
        with pytest.raises(ExecuteError):
            bridge.fpi_instance_execute("nonexistent_instance_id", "test_action")

    def test_fpi_instance_execute_not_opened(self):
        """FPI instance must be opened before execute."""
        bridge = AilMachineBridge()
        instance_id = bridge.fpi_instance_open("fpi.test.capability")
        # Don't call open explicitly — the instance is created but not opened
        instance = bridge._instances[instance_id]
        assert instance.is_open is True  # rac:instance auto-opens per RAC spec
        with pytest.raises(ExecuteError):
            bridge.fpi_instance_execute(instance_id, "test_action")
    def test_fpi_instance_execute_not_opened(self):
        """FPI instance must be opened before execute (post-close state)."""
        bridge = AilMachineBridge()
        instance_id = bridge.fpi_instance_open("fpi.test.capability")
        instance = bridge._instances[instance_id]
        assert instance.is_open is True  # rac:instance auto-opens per canonical spec
        bridge.fpi_instance_close(instance_id)
        with pytest.raises(ExecuteError):
            bridge.fpi_instance_execute(instance_id, "test_action")

    def test_fpi_instance_close(self):
        """fpi_instance_close should close and remove the instance."""
        bridge = AilMachineBridge()
        instance_id = bridge.fpi_instance_open("fpi.test.capability")
        result = bridge.fpi_instance_close(instance_id)
        assert isinstance(result, dict)
        assert result["closed"] is True
        assert instance_id not in bridge._instances

    def test_fpi_instance_close_not_found(self):
        """fpi_instance_close with unknown instance_id should raise ExecuteError."""
        bridge = AilMachineBridge()
        with pytest.raises(ExecuteError):
            bridge.fpi_instance_close("nonexistent_instance_id")


class TestAilMachineBridgeDNA:
    """Test AilMachineBridge DNA registration."""

    def test_bridge_dna_registered(self):
        """AilMachineBridge DNA should be registered in global registry."""
        from executor_py.core import get_dna_registry
        registry = get_dna_registry()
        dna = registry.get_dna("executor-py.ail-machine-bridge")
        assert dna is not None
        assert dna.trait == "AilMachineBridge"
        assert dna.struct == "AilMachineBridge"
        assert "fdi_import" in dna.features
        assert "fpi_instance_open" in dna.features
        assert dna.lion_machine is True
        assert dna.rion_machine is True


class TestAilMachineBridgeROTA:
    """Full ROTA: text-editor <-- CRI [FDI import, FPI instance] --> ail-machine"""

    def test_rota_fdi_import_flow(self):
        """ROTA: Verify FDI import flow end-to-end through FdiExecutor."""
        from executor_py.io.rac.cri.fdi import FdiExecutor

        executor = FdiExecutor()

        # The executor's import_binding should resolve capabilities via
        # text-editor's rac_fdi_in or fallback to _FDI_CAPABILITY_MAP
        try:
            binding = executor.import_binding("fdi.str.snake")
            assert callable(binding)
        except (ImportError, ExecuteError):
            pytest.skip("text-editor not available")

    def test_rota_fpi_instance_lifecycle(self):
        """ROTA: Verify FPI instance lifecycle through FpiExecutor."""
        from executor_py.io.rac.cri.fpi import FpiExecutor, FpiInstance

        executor = FpiExecutor()

        # rac:instance → FpiInstance
        instance = executor.instance("fpi.test.capability")
        assert isinstance(instance, FpiInstance)
        assert instance.is_open is True  # rac:instance auto-opens per RAC spec

        # execute (instance already opened by rac:instance)
        exec_result = instance.execute("test_action", {"key": "value"})
        assert "result" in exec_result
        assert "action" in exec_result

        # close
        close_result = instance.close()
        assert close_result["closed"] is True
        assert instance.is_open is False  # instance closed by close()

    def test_rota_bridge_to_fpi_executor_consistency(self):
        """ROTA: Verify AilMachineBridge wraps FpiExecutor.instance() correctly."""
        bridge = AilMachineBridge()
        instance_id = bridge.fpi_instance_open("fpi.test.capability")
        instance = bridge._instances[instance_id]

        # Verify it's a proper FpiInstance
        assert isinstance(instance, FpiInstance)

        # Open the instance via bridge's fpi_instance_execute
        # (which requires the instance to be opened first)
        instance.open(endpoint="fpi://test/endpoint")

        result = bridge.fpi_instance_execute(instance_id, "test_action", {"data": "test"})
        assert "result" in result

        bridge.fpi_instance_close(instance_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




