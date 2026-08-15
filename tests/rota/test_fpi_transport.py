# -*- coding: utf-8 -*-
"""
ROTA Test — FPI Transport (Function Process Instance)

Runtime Operation Test Audit for executor_py.io.rac.cri.fpi

Per CGE Canon AUD-20260814-FPI-VS-FFI-CANON:
- FPI = Function Process Instance (stateful lifecycle entity)
- FFI = Foreign Function Interface (stateless C-ABI binding — NOT FPI)
- FPI lifecycle: init → running → finalize → terminated
- RAC methods: instance (create), call (execute), stream (continuous), ping (health), finalize (terminate)
"""

import pytest
from executor_py.io.rac.cri.fpi import (
    FpiMethod, FpiTransport, FPIMethodRegistry,
    FpiExecutor, FpiInstance, FpiLifecycleState,
    resolve_fpi_target, create_fpi_executor,
)
from executor_py.core import ExecContext, ExecInput, ExecOutput, SioStatus, FanId, ExecuteError


class TestFpiMethod:
    """Test FPI method enum — canonical RAC verbs, NOT transport mechanisms."""

    def test_fpi_methods(self):
        """FPI methods are RAC verbs for Function Process Instance lifecycle."""
        assert FpiMethod.INSTANCE.value == "instance"
        assert FpiMethod.CALL.value == "call"
        assert FpiMethod.STREAM.value == "stream"
        assert FpiMethod.PING.value == "ping"
        assert FpiMethod.FINALIZE.value == "finalize"


class TestFpiLifecycleState:
    """Test FPI lifecycle states per CGE Canon."""

    def test_lifecycle_states(self):
        assert FpiLifecycleState.INIT.value == "init"
        assert FpiLifecycleState.RUNNING.value == "running"
        assert FpiLifecycleState.FINALIZE.value == "finalize"
        assert FpiLifecycleState.TERMINATED.value == "terminated"
        assert FpiLifecycleState.ERROR.value == "error"


class TestFpiTransport:
    """Test FPI Transport — host_call execution channel (NOT wireless)."""

    def test_fpi_transport_initial_state(self):
        transport = FpiTransport()
        assert transport._paired is False
        assert transport._session_id is None

    def test_fpi_transport_pair(self):
        transport = FpiTransport()
        success = transport.pair("fpi://instance")

        assert success is True
        assert transport.is_paired() is True
        assert transport._session_id is not None

    def test_fpi_transport_unpair(self):
        transport = FpiTransport()
        transport.pair("fpi://test")
        assert transport.is_paired() is True

        transport.unpair()
        assert transport.is_paired() is False
        assert transport._session_id is None

    def test_fpi_transport_invoke_not_paired(self):
        transport = FpiTransport()

        with pytest.raises(ExecuteError) as exc_info:
            transport.invoke("test_method", {})

        assert exc_info.value.code == "FPI_NOT_PAIRED"

    def test_fpi_transport_invoke_host_call(self):
        transport = FpiTransport()
        transport.pair("fpi://test")

        # Register a test handler
        def test_handler(**kwargs):
            return {"called": True, "args": kwargs}

        transport.set_registry(FPIMethodRegistry())
        transport._registry.register("test_method", test_handler)

        result = transport.invoke("test_method", {"arg1": "value1"})
        assert result["called"] is True
        assert result["args"]["arg1"] == "value1"

    def test_fpi_transport_invoke_no_handler(self):
        """Error code should be FPI_NO_METHOD, not FPI_NO_PROCEDURE (FFI terminology)."""
        transport = FpiTransport()
        transport.pair("fpi://test")
        transport.set_registry(FPIMethodRegistry())

        with pytest.raises(ExecuteError) as exc_info:
            transport.invoke("nonexistent", {})

        assert exc_info.value.code == "FPI_NO_METHOD"


class TestFPIMethodRegistry:
    """Test FPI Method Registry."""

    def test_register_with_metadata(self):
        registry = FPIMethodRegistry()
        handler = lambda: None

        registry.register("test_method", handler, transport="host_call", endpoint="fpi://test")

        info = registry.get_method_info("test_method")
        assert info is not None
        assert info["handler"] == handler
        assert info["transport"] == "host_call"
        assert info["endpoint"] == "fpi://test"

    def test_get_handler(self):
        registry = FPIMethodRegistry()
        handler = lambda: "result"
        registry.register("test", handler)

        found = registry.get("test")
        assert found == handler

    def test_list_methods(self):
        registry = FPIMethodRegistry()
        registry.register("method1", lambda: None)
        registry.register("method2", lambda: None)

        methods = registry.list_methods()
        assert "method1" in methods
        assert "method2" in methods


class TestFpiExecutor:
    """Test FPI Executor (ExecuteParticle implementation).

    Per CGE Canon: FPI is Function Process Instance, NOT Foreign Procedure Interface.
    """

    def test_fpi_executor_creation(self):
        executor = FpiExecutor()
        assert executor.registry is not None
        assert executor.transport is not None
        # Canonical RAC methods, NOT bluetooth/NFC
        assert "instance" in executor.registry.list_methods()
        assert "call" in executor.registry.list_methods()
        assert "stream" in executor.registry.list_methods()
        assert "ping" in executor.registry.list_methods()
        assert "finalize" in executor.registry.list_methods()

    def test_fpi_executor_instance(self):
        """rac:instance — create FPI lifecycle, NOT execute."""
        executor = FpiExecutor()
        ctx = ExecContext()
        input = ExecInput(
            action="fpi.instance",
            payload={"options": {"capability": "fpi.ail.machine", "endpoint": "fpi://instance"}},
        )

        result = executor.execute(input, ctx)

        assert result.status == SioStatus.SUCCESS
        assert "instance_id" in result.result
        assert result.result["state"] == "running"

    def test_fpi_executor_ping(self):
        """rac:ping — health/liveness check."""
        executor = FpiExecutor()
        ctx = ExecContext()
        input = ExecInput(action="fpi.ping", payload={})

        result = executor.execute(input, ctx)

        assert result.status == SioStatus.SUCCESS
        assert result.result["pong"] is True
        assert result.result["status"] == "healthy"

    def test_fpi_executor_finalize(self):
        """rac:finalize — terminate lifecycle."""
        executor = FpiExecutor()
        ctx = ExecContext()
        input = ExecInput(
            action="fpi.finalize",
            payload={"options": {"instance_id": "test-instance"}},
        )

        result = executor.execute(input, ctx)

        assert result.status == SioStatus.SUCCESS
        assert result.result["finalized"] is True
        assert result.result["state"] == "terminated"

    def test_fpi_executor_stream(self):
        """rac:stream — continuous data flow on FPI."""
        executor = FpiExecutor()
        ctx = ExecContext()
        input = ExecInput(action="fpi.stream", payload={})

        result = executor.execute(input, ctx)

        assert result.status == SioStatus.SUCCESS
        assert result.result["stream"] is True

    def test_fpi_executor_unknown_method(self):
        executor = FpiExecutor()
        ctx = ExecContext()
        input = ExecInput(action="fpi.unknown", payload={})

        with pytest.raises(ExecuteError) as exc_info:
            executor.execute(input, ctx)

        assert "FPI_NO_METHOD" in str(exc_info.value)

    def test_fpi_executor_fan_id(self):
        executor = FpiExecutor()
        fan_id = executor.fan_id()
        assert fan_id is not None
        assert fan_id.id == "hace-io-rac-cri-fpi"


class TestFpiInstance:
    """Test FPI Instance lifecycle per CGE Canon."""

    def test_instance_creation(self):
        """Instance starts in INIT state."""
        instance = FpiInstance(capability="fpi.test")
        assert instance.state == FpiLifecycleState.INIT
        assert instance.is_open is False

    def test_instance_open(self):
        """open() transitions INIT → RUNNING."""
        instance = FpiInstance(capability="fpi.test", endpoint="fpi://test")
        result = instance.open()

        assert result["opened"] is True
        assert instance.is_open is True
        assert instance.state == FpiLifecycleState.RUNNING
        assert instance.instance_id is not None

    def test_instance_ping(self):
        """ping() returns health status."""
        instance = FpiInstance(capability="fpi.test", endpoint="fpi://test")
        instance.open()

        result = instance.ping()
        assert result["pong"] is True
        assert result["status"] == "healthy"

    def test_instance_close(self):
        """close() transitions to TERMINATED."""
        instance = FpiInstance(capability="fpi.test", endpoint="fpi://test")
        instance.open()
        assert instance.is_open is True

        result = instance.close()
        assert result["closed"] is True
        assert instance.is_open is False
        assert instance.state == FpiLifecycleState.TERMINATED

    def test_instance_finalize(self):
        """finalize() transitions RUNNING → FINALIZE → TERMINATED."""
        instance = FpiInstance(capability="fpi.test", endpoint="fpi://test")
        instance.open()
        assert instance.state == FpiLifecycleState.RUNNING

        result = instance.finalize()
        assert result["closed"] is True
        assert instance.state == FpiLifecycleState.TERMINATED

    def test_instance_execute_not_open(self):
        """Execute on unopened instance raises error."""
        instance = FpiInstance(capability="fpi.test", endpoint="fpi://test")

        with pytest.raises(ExecuteError) as exc_info:
            instance.execute("test.action", {})

        assert exc_info.value.code == "FPI_INSTANCE_NOT_OPEN"

    def test_instance_execute_with_canonical_payload(self):
        """Execute with canonical SIO-CRI-FPI-V2 payload structure."""
        instance = FpiInstance(capability="fpi.test", endpoint="fpi://test")
        instance.open()

        result = instance.execute("ail.parse", {
            "action": {"name": "execute", "feature": "ail.parse"},
            "process": {"mode": "instance", "id": instance.instance_id, "state": "running"},
            "input": {"text": "test content"},
            "options": {"stream": False},
        })

        assert "result" in result
        assert "action" in result
        assert result["action"] == "ail.parse"

    def test_instance_auto_open_via_executor(self):
        """FpiExecutor.instance() auto-opens the instance."""
        executor = FpiExecutor()
        instance = executor.instance("fpi.ail.machine", endpoint="fpi://ail-machine")

        assert instance is not None
        assert instance.is_open
        assert instance.capability == "fpi.ail.machine"
        assert instance.state == FpiLifecycleState.RUNNING


class TestResolveFpiTarget:
    """Test FPI target resolution."""

    def test_resolve_fpi_target(self):
        uri = "rac://cri.platform.hace.fpi/hace/executor-py/io/rac/cri/text"
        target = resolve_fpi_target(uri)

        assert target["rule"] == "cri"
        assert target["ownerspace"] == "platform.hace"
        assert target["specs"] == "fpi"
        assert target["path"] == "hace/executor-py/io/rac/cri/text"
        assert target["transport"] == "host_call"
        assert target["machine"] == "hace-rion-machine"
        assert target["transport_kind"] == "Fpi"
        assert target["is_wired"] is False
        assert target["is_wireless"] is True

    def test_resolve_fpi_target_no_path(self):
        uri = "rac://cri.hace.fpi"
        target = resolve_fpi_target(uri)

        assert target["rule"] == "cri"
        assert target["ownerspace"] == "hace"
        assert target["specs"] == "fpi"
        assert target["path"] == ""


class TestCreateFpiExecutor:
    """Test FPI executor factory."""

    def test_create_fpi_executor(self):
        executor = create_fpi_executor(uri="fpi://test")
        assert isinstance(executor, FpiExecutor)
        assert executor.transport.uri == "fpi://test"
        assert executor.transport.method == FpiMethod.HOST_CALL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
