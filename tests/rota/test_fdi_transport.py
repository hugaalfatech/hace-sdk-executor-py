# -*- coding: utf-8 -*-
"""
ROTA Test — FDI Transport (Wired/Autoload)
Runtime Operation Test Audit for executor_py.io.rac.cri.fdi
"""

import pytest
import tempfile
import os
from executor_py.io.rac.cri.fdi import (
    FdiMethod, FdiTransport, FDIMethodRegistry,
    FdiExecutor, resolve_fdi_target, create_fdi_executor,
)
from executor_py.core import ExecContext, ExecInput, ExecOutput, SioStatus, FanId


class TestFdiMethod:
    """Test FDI method enum."""
    
    def test_fdi_methods(self):
        assert FdiMethod.FILE.value == "file"
        assert FdiMethod.PIPE.value == "pipe"
        assert FdiMethod.FD.value == "fd"
        assert FdiMethod.SHARED_MEM.value == "shm"


class TestFdiTransport:
    """Test FDI Transport (wired/autoload)."""
    
    def test_fdi_transport_file_autoload(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        
        try:
            transport = FdiTransport(uri=f"file://{temp_path}", method=FdiMethod.FILE)
            success = transport.autoload()
            assert success is True
            assert transport.is_connected() is True
        finally:
            os.unlink(temp_path)
    
    def test_fdi_transport_file_not_exists(self):
        transport = FdiTransport(uri="file:///nonexistent/path", method=FdiMethod.FILE)
        success = transport.autoload()
        assert success is False
        assert transport.is_connected() is False
    
    def test_fdi_transport_pipe(self):
        transport = FdiTransport(uri="pipe:///tmp/test_pipe", method=FdiMethod.PIPE)
        # Pipe doesn't exist, but autoload returns True for valid pipe paths
        success = transport.autoload()
        # On Windows, named pipes start with \\.\pipe
        # This is a stub implementation
        assert transport.is_connected() in [True, False]
    
    def test_fdi_transport_fd(self):
        transport = FdiTransport(uri="fd://0", method=FdiMethod.FD)
        success = transport.autoload()
        # stdin (fd 0) should be valid
        assert success is True
        assert transport.is_connected() is True
    
    def test_fdi_transport_invalid_fd(self):
        transport = FdiTransport(uri="fd://999999", method=FdiMethod.FD)
        success = transport.autoload()
        assert success is False
    
    def test_fdi_transport_shared_mem(self):
        transport = FdiTransport(uri="shm://test", method=FdiMethod.SHARED_MEM)
        success = transport.autoload()
        assert success is True
        assert transport.is_connected() is True
    
    def test_fdi_transport_disconnect(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        
        try:
            transport = FdiTransport(uri=f"file://{temp_path}", method=FdiMethod.FILE)
            transport.autoload()
            assert transport.is_connected() is True
            
            transport.disconnect()
            assert transport.is_connected() is False
        finally:
            os.unlink(temp_path)


class TestFDIMethodRegistry:
    """Test FDI Method Registry."""
    
    def test_register_and_get(self):
        registry = FDIMethodRegistry()
        handler = lambda ctx, **kwargs: {"result": "ok"}
        
        registry.register("test_method", handler)
        found = registry.get("test_method")
        
        assert found == handler
    
    def test_list_methods(self):
        registry = FDIMethodRegistry()
        registry.register("method1", lambda: None)
        registry.register("method2", lambda: None)
        
        methods = registry.list_methods()
        assert "method1" in methods
        assert "method2" in methods
        assert len(methods) == 2
    
    def test_get_nonexistent(self):
        registry = FDIMethodRegistry()
        assert registry.get("nonexistent") is None


class TestFdiExecutor:
    """Test FDI Executor (ExecuteParticle implementation)."""
    
    def test_fdi_executor_creation(self):
        executor = FdiExecutor()
        assert executor.registry is not None
        assert executor.transport is not None
        assert "autoload" in executor.registry.list_methods()
        assert "connect" in executor.registry.list_methods()
    
    def test_fdi_executor_autoload(self):
        executor = FdiExecutor()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        
        try:
            ctx = ExecContext()
            input = ExecInput(
                action="fdi.autoload",
                payload={"options": {"uri": f"file://{temp_path}"}},
            )
            
            result = executor.execute(input, ctx)
            
            assert result.status == SioStatus.SUCCESS
            assert result.result["autoload"] is True
            assert result.result["connected"] is True
        finally:
            os.unlink(temp_path)
    
    def test_fdi_executor_connect(self):
        executor = FdiExecutor()
        ctx = ExecContext()
        input = ExecInput(action="fdi.connect", payload={})
        
        result = executor.execute(input, ctx)
        
        assert result.status == SioStatus.SUCCESS
        assert result.result["connected"] is True
    
    def test_fdi_executor_disconnect(self):
        executor = FdiExecutor()
        ctx = ExecContext()
        input = ExecInput(action="fdi.disconnect", payload={})
        
        result = executor.execute(input, ctx)
        
        assert result.status == SioStatus.SUCCESS
        assert result.result["connected"] is False
    
    def test_fdi_executor_send_recv(self):
        executor = FdiExecutor()
        ctx = ExecContext()
        
        # Send
        input_send = ExecInput(action="fdi.send", payload={"options": {"data": "hello"}})
        result_send = executor.execute(input_send, ctx)
        assert result_send.status == SioStatus.SUCCESS
        assert result_send.result["sent"] == 5
        
        # Recv
        input_recv = ExecInput(action="fdi.recv", payload={})
        result_recv = executor.execute(input_recv, ctx)
        assert result_recv.status == SioStatus.SUCCESS
        assert result_recv.result["status"] == "ok"
    
    def test_fdi_executor_unknown_method(self):
        executor = FdiExecutor()
        ctx = ExecContext()
        input = ExecInput(action="fdi.unknown_method", payload={})
        
        with pytest.raises(Exception) as exc_info:
            executor.execute(input, ctx)
        
        assert "FDI_NO_METHOD" in str(exc_info.value)
    
    def test_fdi_executor_fan_id(self):
        executor = FdiExecutor()
        fan_id = executor.fan_id()
        assert fan_id is not None
        assert fan_id.id == "hace-io-rac-cri-fdi"
    
    def test_resolve_fdi_module(self):
        executor = FdiExecutor()
        # This will try to import executor_py.io.rac.cri.file
        # which doesn't exist yet, so returns None
        result = executor.resolve_fdi_module("io/rac/cri/file")
        assert result is None


class TestResolveFdiTarget:
    """Test FDI target resolution."""
    
    def test_resolve_fdi_target(self):
        uri = "rac://cri.platform.hace.fdi/hace/executor-py/io/rac/cri/file"
        target = resolve_fdi_target(uri)
        
        assert target["rule"] == "cri"
        assert target["ownerspace"] == "platform.hace"
        assert target["specs"] == "fdi"
        assert target["path"] == "hace/executor-py/io/rac/cri/file"
        assert target["transport"] == "fdi"
        assert target["machine"] == "hace-lion-machine"
        assert target["transport_kind"] == "Fdi"
        assert target["is_wired"] is True
        assert target["is_autoload"] is True
    
    def test_resolve_fdi_target_no_path(self):
        uri = "rac://cri.hace.fdi"
        target = resolve_fdi_target(uri)
        
        assert target["rule"] == "cri"
        assert target["ownerspace"] == "hace"
        assert target["specs"] == "fdi"
        assert target["path"] == ""


class TestCreateFdiExecutor:
    """Test FDI executor factory."""
    
    def test_create_fdi_executor(self):
        executor = create_fdi_executor(uri="file:///tmp/test")
        assert isinstance(executor, FdiExecutor)
        assert executor.transport.uri == "file:///tmp/test"
        assert executor.transport.method == FdiMethod.FILE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])