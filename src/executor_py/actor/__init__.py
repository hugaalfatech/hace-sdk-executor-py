# -*- coding: utf-8 -*-
"""
executor_py.actor — Actor (Engine) subpackage.

FES Layer: ENGINE — Runtime Engine with Authority + Lifecycle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..core import FanCapability, FanRegistry, FanId, ExecOutput, ExecInput, ExecContext, ExecuteError, SioStatus


@dataclass
class ActorConfig:
    """Actor configuration."""
    uri: str
    name: str
    authority: str = "local"
    capabilities: list[str] = field(default_factory=list)
    executors: list[str] = field(default_factory=list)
    transport: str = "fdi"


class Actor(ABC):
    """Base class for all Runtime Actors (Engines)."""

    def __init__(self, config: ActorConfig):
        self.config = config
        self._running = False
        self._executors: dict[str, Any] = {}
        self._modules: dict[str, Any] = {}
        self.fan_registry = FanRegistry()

    @property
    def uri(self) -> str:
        return self.config.uri

    @property
    def name(self) -> str:
        return self.config.name

    def register_executor(self, executor: "Any") -> None:
        """Register an Executor (Engine Part) under this Actor."""
        self._executors[executor.name] = executor

    def register_module(self, module: "Any") -> None:
        """Register an ExecutorModule under this Actor."""
        self._modules[module.name] = module

    def register_capability(self, cap: FanCapability) -> None:
        """Register a capability under this Actor."""
        self.fan_registry.register(cap)

    def find_executor(self, name: str) -> Optional[Any]:
        """Find a registered executor by name."""
        return self._executors.get(name)

    def find_module(self, name: str) -> Optional[Any]:
        """Find a registered module by name."""
        return self._modules.get(name)

    def list_executors(self) -> list[str]:
        """List all registered executor names."""
        return list(self._executors.keys())

    def list_modules(self) -> list[str]:
        """List all registered module names."""
        return list(self._modules.keys())

    def execute(self, rac_uri: str, action: str, payload: dict, ctx: ExecContext) -> ExecOutput:
        """Execute a capability via RAC dispatch.

        Delegates to the registered executor, falling back to
        the capability handler directly.
        """
        cap = self.fan_registry.find(action)
        if cap is None:
            # Check registered executors for this capability
            for exec_name, executor in self._executors.items():
                if hasattr(executor, "get_capabilities"):
                    for cap_candidate in executor.get_capabilities():
                        if cap_candidate.id == action:
                            cap = cap_candidate
                            break
                if cap:
                    break
        if cap is None:
            raise ExecuteError(
                code="NO_CAPABILITY",
                message=f"No capability found for action: {action}",
            )
        # Delegate to registered executor
        executor = self._executors.get(cap.executor)
        if cap.handler is not None:
            # Use the capability handler directly (MockParticle.execute or callable)
            handler = cap.handler
            if hasattr(handler, "execute") and callable(getattr(handler, "execute")):
                result = handler.execute(ExecInput(
                    rac_uri=rac_uri,
                    action=action,
                    payload=payload,
                ), ctx)
                if isinstance(result, ExecOutput):
                    return result
            if callable(handler):
                result = handler(payload)
                if isinstance(result, ExecOutput):
                    return result
        if executor and hasattr(executor, "execute") and callable(executor.execute):
            import inspect
            sig = inspect.signature(executor.execute)
            if len(sig.parameters) <= 1:
                return executor.execute(ctx)
            return executor.execute(rac_uri, action, payload, ctx)
        raise ExecuteError(
            code="NO_HANDLER",
            message=f"No handler for capability: {cap.id}",
        )

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...

    @abstractmethod
    def health(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def receipt(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def telemetry(self) -> dict[str, Any]:
        ...


@dataclass
class CompositeActorConfig(ActorConfig):
    """Configuration for Composite Actor."""
    child_actors: list[ActorConfig] = field(default_factory=list)


class CompositeActor(Actor):
    """Composite Actor — aggregates multiple Actors."""

    def __init__(self, config: CompositeActorConfig):
        super().__init__(config)
        self.children: dict[str, Actor] = {}

    def add_child(self, actor: Actor) -> None:
        self.children[actor.name] = actor

    def start(self):
        for child in self.children.values():
            child.start()
        self._running = True

    def stop(self):
        for child in self.children.values():
            child.stop()
        self._running = False

    def health(self):
        return {"status": "healthy" if self._running else "stopped", "children": {}}

    def receipt(self):
        return {"actor": self.name, "children": {}}

    def telemetry(self):
        return {"actor": self.name, "children": {}}


__all__ = ["Actor", "ActorConfig", "CompositeActor", "CompositeActorConfig"]
