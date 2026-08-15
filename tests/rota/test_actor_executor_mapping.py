# -*- coding: utf-8 -*-
"""
ROTA Test — Actor ↔ Executor Mapping
Runtime Operation Test Audit for Actor-Executor binding
"""

import pytest
from executor_py.core import (
    FanId, FanCapability, FanRegistry, ExecContext, ExecInput, ExecOutput,
    SioStatus, EnginePart, ExecutorDNA, ActorExecutorMapping, FesLayer,
    get_dna_registry,
)
from executor_py.actor import Actor, ActorConfig
from executor_py.executor import Executor, ExecutorConfig, SimpleExecutor
from executor_py.module import ExecutorModule, ModuleConfig, FdiModule, FpiModule


class MockParticle:
    """Mock ExecuteParticle for testing."""
    def __init__(self, result="ok"):
        self.result = result
    
    def execute(self, input, ctx):
        return ExecOutput(result=self.result, status=SioStatus.SUCCESS)


class TestActorConfig:
    """Test ActorConfig."""
    
    def test_actor_config_creation(self):
        config = ActorConfig(
            uri="rac://cri.hace.fdi/hace/text-ractor",
            name="text-ractor",
            authority="local",
            capabilities=["text.read", "text.write"],
            executors=["executor-py"],
            transport="fdi",
        )
        assert config.uri == "rac://cri.hace.fdi/hace/text-ractor"
        assert config.name == "text-ractor"
        assert config.authority == "local"
    
    def test_actor_config_defaults(self):
        config = ActorConfig(
            uri="rac://cri.hace.fdi/hace/test",
            name="test",
        )
        assert config.authority == "local"
        assert config.capabilities == []
        assert config.executors == []


class TestActor:
    """Test Actor base class."""
    
    def test_actor_creation(self):
        config = ActorConfig(
            uri="rac://cri.hace.fdi/hace/test-actor",
            name="test-actor",
        )
        
        class TestActor(Actor):
            def start(self): pass
            def stop(self): pass
            def health(self): return {"status": "healthy"}
            def receipt(self): return {}
            def telemetry(self): return {}
        
        actor = TestActor(config)
        assert actor.uri == config.uri
        assert actor.name == config.name
        assert actor.config == config
    
    def test_actor_register_executor(self):
        config = ActorConfig(
            uri="rac://cri.hace.fdi/hace/test-actor",
            name="test-actor",
        )
        
        class TestActor(Actor):
            def start(self): pass
            def stop(self): pass
            def health(self): return {"status": "healthy"}
            def receipt(self): return {}
            def telemetry(self): return {}
        
        actor = TestActor(config)
        
        exec_config = ExecutorConfig(
            uri="rac://cri.hace.fdi/hace/executor-py",
            name="executor-py",
            parent_actor_uri=config.uri,
        )
        
        class TestExecutor(Executor):
            def get_capabilities(self):
                return []
        
        executor = TestExecutor(exec_config)
        actor.register_executor(executor)
        
        assert "executor-py" in actor._executors
    
    def test_actor_register_capability(self):
        config = ActorConfig(
            uri="rac://cri.hace.fdi/hace/test-actor",
            name="test-actor",
        )
        
        class TestActor(Actor):
            def start(self): pass
            def stop(self): pass
            def health(self): return {"status": "healthy"}
            def receipt(self): return {}
            def telemetry(self): return {}
        
        actor = TestActor(config)
        
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="test-executor",
            transport="FDI",
            handler=MockParticle(),
        )
        
        actor.register_capability(cap)
        
        found = actor.fan_registry.find("test.action")
        assert found is not None
        assert found.id == "test.action"
    
    def test_actor_execute_delegates_to_executor(self):
        config = ActorConfig(
            uri="rac://cri.hace.fdi/hace/test-actor",
            name="test-actor",
        )
        
        class TestActor(Actor):
            def start(self): pass
            def stop(self): pass
            def health(self): return {"status": "healthy"}
            def receipt(self): return {}
            def telemetry(self): return {}
        
        actor = TestActor(config)
        
        # Register executor with capability
        exec_config = ExecutorConfig(
            uri="rac://cri.hace.fdi/hace/executor-py",
            name="executor-py",
            parent_actor_uri=config.uri,
        )
        
        class TestExecutor(Executor):
            def get_capabilities(self):
                fan_id = FanId(id="test-fan")
                return [FanCapability(
                    id="test.action",
                    fan_id=fan_id,
                    executor="executor-py",
                    transport="FDI",
                    handler=MockParticle("executed"),
                )]
        
        executor = TestExecutor(exec_config)
        actor.register_executor(executor)
        
        # Execute via actor
        ctx = ExecContext()
        result = actor.execute(
            rac_uri="rac://cri.hace.fdi/hace/test-actor",
            action="test.action",
            payload={"key": "value"},
            ctx=ctx,
        )
        
        assert result.result == "executed"
        assert result.status == SioStatus.SUCCESS


class TestExecutorConfig:
    """Test ExecutorConfig."""
    
    def test_executor_config_creation(self):
        config = ExecutorConfig(
            uri="rac://cri.hace.fdi/hace/executor-py",
            name="executor-py",
            parent_actor_uri="rac://cri.hace.fdi/hace/text-ractor",
        )
        assert config.layer == FesLayer.EXECUTOR
        assert config.name == "executor-py"
    
    def test_executor_config_with_dna(self):
        dna = ExecutorDNA(
            trait="IpoFeature",
            struct="CustomExecutor",
            features=["custom"],
            bindings={"actor": "text-ractor"},
        )
        config = ExecutorConfig(
            uri="rac://cri.hace.fdi/hace/executor-py",
            name="executor-py",
            parent_actor_uri="rac://cri.hace.fdi/hace/text-ractor",
            dna=dna,
        )
        assert config.dna == dna


class TestExecutor:
    """Test Executor base class."""
    
    def test_executor_creation(self):
        config = ExecutorConfig(
            uri="rac://cri.hace.fdi/hace/executor-py",
            name="executor-py",
            parent_actor_uri="rac://cri.hace.fdi/hace/text-ractor",
        )
        
        class TestExecutor(Executor):
            def get_capabilities(self):
                return []
        
        executor = TestExecutor(config)
        assert executor.name == "executor-py"
        assert executor.uri == config.uri
        assert executor.dna.trait == "IpoFeature"
    
    def test_executor_register_capability(self):
        config = ExecutorConfig(
            uri="rac://cri.hace.fdi/hace/executor-py",
            name="executor-py",
            parent_actor_uri="rac://cri.hace.fdi/hace/text-ractor",
        )
        
        class TestExecutor(Executor):
            def get_capabilities(self):
                return []
        
        executor = TestExecutor(config)
        
        fan_id = FanId(id="test-fan")
        cap = FanCapability(
            id="test.action",
            fan_id=fan_id,
            executor="executor-py",
            transport="FDI",
            handler=MockParticle(),
        )
        
        executor.register_capability(cap)
        
        assert "test.action" in executor.capabilities
        found = executor.fan_registry.find("test.action")
        assert found is not None
    
    def test_executor_dna_registration(self):
        config = ExecutorConfig(
            uri="rac://cri.hace.fdi/hace/executor-py",
            name="executor-py",
            parent_actor_uri="rac://cri.hace.fdi/hace/text-ractor",
        )
        
        class TestExecutor(Executor):
            def get_capabilities(self):
                return []
        
        executor = TestExecutor(config)
        
        # DNA should be registered in global registry
        registry = get_dna_registry()
        dna = registry.get_dna("executor-py")
        assert dna is not None
        assert dna.trait == "IpoFeature"


class TestModuleConfig:
    """Test ModuleConfig."""
    
    def test_module_config_creation(self):
        config = ModuleConfig(
            uri="rac://cri.hace.fdi/hace/executor-py/io/rac/cri/fdi",
            name="fdi-executor",
            parent_executor_uri="rac://cri.hace.fdi/hace/executor-py",
        )
        assert config.layer == FesLayer.MODULE
        assert config.specs == "fdi"
        assert config.machine == "hace-lion-machine"
    
    def test_module_config_fpi(self):
        config = ModuleConfig(
            uri="rac://cri.hace.fpi/hace/executor-py/io/rac/cri/fpi",
            name="fpi-executor",
            parent_executor_uri="rac://cri.hace.fdi/hace/executor-py",
            specs="fpi",
            machine="hace-rion-machine",
            transport="fpi",
        )
        assert config.specs == "fpi"
        assert config.machine == "hace-rion-machine"


class TestExecutorModule:
    """Test ExecutorModule base class."""
    
    def test_module_creation(self):
        config = ModuleConfig(
            uri="rac://cri.hace.fdi/hace/executor-py/test-module",
            name="test-module",
            parent_executor_uri="rac://cri.hace.fdi/hace/executor-py",
        )
        
        class TestModule(ExecutorModule):
            def execute(self, input, ctx):
                return ExecOutput(result="module-result", status=SioStatus.SUCCESS)
        
        module = TestModule(config)
        assert module.name == "test-module"
        assert module.engine_part.layer == FesLayer.MODULE
        assert module.engine_part.parent_uri == config.parent_executor_uri
    
    def test_module_register_method(self):
        config = ModuleConfig(
            uri="rac://cri.hace.fdi/hace/executor-py/test-module",
            name="test-module",
            parent_executor_uri="rac://cri.hace.fdi/hace/executor-py",
        )
        
        class TestModule(ExecutorModule):
            def execute(self, input, ctx):
                return ExecOutput(result="ok", status=SioStatus.SUCCESS)
        
        module = TestModule(config)
        module.register_method("custom_method", lambda: "custom")
        
        assert "custom_method" in module.list_methods()
        assert module.get_method("custom_method") is not None
    
    def test_module_fan_id(self):
        config = ModuleConfig(
            uri="rac://cri.hace.fdi/hace/executor-py/test-module",
            name="test-module",
            parent_executor_uri="rac://cri.hace.fdi/hace/executor-py",
            specs="fdi",
        )
        
        class TestModule(ExecutorModule):
            def execute(self, input, ctx):
                return ExecOutput(result="ok", status=SioStatus.SUCCESS)
        
        module = TestModule(config)
        fan_id = module.fan_id()
        assert fan_id is not None
        assert fan_id.id == "hace-executor-py-fdi"


class TestFdiModule:
    """Test FdiModule (FDI specialization)."""
    
    def test_fdi_module_creation(self):
        config = ModuleConfig(
            uri="rac://cri.hace.fdi/hace/executor-py/fdi",
            name="fdi-module",
            parent_executor_uri="rac://cri.hace.fdi/hace/executor-py",
        )
        
        module = FdiModule(config)
        assert module.specs == "fdi"
        assert module.machine == "hace-lion-machine"
        assert module.transport == "fdi"
        assert "autoload" in module.list_methods()
        assert "connect" in module.list_methods()
        assert "send" in module.list_methods()
    
    def test_fdi_module_methods(self):
        config = ModuleConfig(
            uri="rac://cri.hace.fdi/hace/executor-py/fdi",
            name="fdi-module",
            parent_executor_uri="rac://cri.hace.fdi/hace/executor-py",
        )
        
        module = FdiModule(config)
        ctx = ExecContext()
        
        # Test autoload method
        result = module.method_autoload(ctx, uri="file:///tmp/test")
        assert result["autoload"] is True
        
        # Test connect
        result = module.method_connect(ctx)
        assert result["connected"] is True
        
        # Test send
        result = module.method_send(ctx, data="hello")
        assert result["sent"] == 5


class TestFpiModule:
    """Test FpiModule (FPI specialization)."""
    
    def test_fpi_module_creation(self):
        config = ModuleConfig(
            uri="rac://cri.hace.fpi/hace/executor-py/fpi",
            name="fpi-module",
            parent_executor_uri="rac://cri.hace.fdi/hace/executor-py",
            specs="fpi",
        )
        
        module = FpiModule(config)
        assert module.specs == "fpi"
        assert module.machine == "hace-rion-machine"
        assert module.transport == "fpi"
        assert "discover" in module.list_methods()
        assert "pair" in module.list_methods()
        assert "invoke" in module.list_methods()
    
    def test_fpi_module_methods(self):
        config = ModuleConfig(
            uri="rac://cri.hace.fpi/hace/executor-py/fpi",
            name="fpi-module",
            parent_executor_uri="rac://cri.hace.fdi/hace/executor-py",
            specs="fpi",
        )
        
        module = FpiModule(config)
        ctx = ExecContext()
        
        # Test discover
        result = module.method_discover(ctx)
        assert "endpoints" in result
        assert "count" in result
        
        # Test pair
        result = module.method_pair(ctx, endpoint="fpi://test")
        assert result["paired"] is True


class TestActorExecutorMapping:
    """Test ActorExecutorMapping contract."""
    
    def test_mapping_creation(self):
        mapping = ActorExecutorMapping(
            actor_uri="rac://cri.hace.fdi/hace/text-ractor",
            actor_name="text-ractor",
            executor_uri="rac://cri.hace.fdi/hace/executor-py/core",
            executor_name="executor-py",
            mode="mcv",
        )
        assert mapping.actor_name == "text-ractor"
        assert mapping.executor_name == "executor-py"
        assert mapping.mode == "mcv"
    
    def test_mapping_with_modules(self):
        mapping = ActorExecutorMapping(
            actor_uri="rac://cri.hace.fdi/hace/text-ractor",
            actor_name="text-ractor",
            executor_uri="rac://cri.hace.fdi/hace/executor-py/core",
            executor_name="executor-py",
            modules=[
                "rac://cri.hace.fdi/hace/executor-py/io/rac/cri/fdi",
                "rac://cri.hace.fpi/hace/executor-py/io/rac/cri/fpi",
            ],
            mode="mcv",
        )
        assert len(mapping.modules) == 2
        assert "fdi" in mapping.modules[0]


class TestFESDNARegistry:
    """Test global FES DNA registry."""
    
    def test_registry_singleton(self):
        registry1 = get_dna_registry()
        registry2 = get_dna_registry()
        assert registry1 is registry2
    
    def test_register_and_get_dna(self):
        registry = get_dna_registry()
        dna = ExecutorDNA(
            trait="TestTrait",
            struct="TestStruct",
            features=["test"],
            bindings={},
        )
        registry.register_dna("test-key", dna)
        
        retrieved = registry.get_dna("test-key")
        assert retrieved is not None
        assert retrieved.trait == "TestTrait"
    
    def test_register_and_get_mapping(self):
        registry = get_dna_registry()
        mapping = ActorExecutorMapping(
            actor_uri="rac://test/actor",
            actor_name="test-actor",
            executor_uri="rac://test/executor",
            executor_name="test-executor",
        )
        registry.register_mapping(mapping)
        
        retrieved = registry.get_mapping("test-actor")
        assert retrieved is not None
        assert retrieved.actor_name == "test-actor"
    
    def test_get_executor_for_fan(self):
        registry = get_dna_registry()
        dna = ExecutorDNA(
            trait="TestTrait",
            struct="TestStruct",
            features=["test"],
            bindings={"fan_ids": ["test-fan"]},
        )
        registry.register_dna("test-executor", dna)
        
        executor_dna = registry.get_executor_for_fan("test-fan")
        assert executor_dna is not None
        assert executor_dna.trait == "TestTrait"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])