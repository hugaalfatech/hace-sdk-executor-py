"""
# Executor-Py SDK — Capor Router

Mirrors `hace/sdk/executor-cep/src/core/capor.rs` (CaporRouter, CaporDecision,
SecurityProfile, SecurityLevel, RuleEngine, PolicyResolver, Scorer).

Capor resolves WHAT capacity should execute — not HOW/WHERE to route.

Integration:
    - IPO Process phase calls CaporRouter.resolve() to determine capability + security
    - py-text-editor actor capabilities register under FanCapability
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from .core import FanId, ExecContext, FanCapability, FanRegistry
from .ipo import CaporDecision


# ─── Security Profile ───────────────────────────────────────────────────────────

@dataclass
class SecurityProfile:
    """Security profile for a capability — mirrors SecurityProfile in capor.rs.

    Describes the security context required to execute a capability.
    """
    level: str = "local"  # local | shared | restricted (mirrors SecurityLevel)
    capabilities: list[str] = field(default_factory=list)
    resource_limits: dict[str, Any] = field(default_factory=dict)
    allowed_actors: list[str] = field(default_factory=list)


@dataclass
class Scorer:
    """Scorer weights — mirrors Scorer in capor.rs.

    Assigns weights to different scoring dimensions for capacity resolution.
    """
    capability_relevance: float = 1.0
    security_match: float = 1.0
    resource_availability: float = 0.5
    context_proximity: float = 0.3


# ─── Capor Router Interface ─────────────────────────────────────────────────────

class CaporRouter(ABC):
    """CAPOR (Capacity Operation Router) — resolves WHAT capability.

    Mirrors CaporRouter trait in executor-cep/src/core/capor.rs.

    Capor resolves:
    - Which capability/actor should handle this request
    - Security/capacity context (context, security, capabilities, rules)
    - Scoring of alternative capabilities (when multiple match)

    Capor does NOT resolve:
    - Transport HOW (that's Racor)
    - Physical WHERE (that's Racor → LION/RION Machine)
    """

    @abstractmethod
    def resolve(self, ctx: ExecContext, fan_id: FanId) -> CaporDecision:
        """Resolve capacity for the given context + FanId.

        Args:
            ctx: Execution context (security tier, workspace, etc.)
            fan_id: The FanId requesting capacity

        Returns:
            CaporDecision with capability + security profile + scorer
        """
        ...

    @abstractmethod
    def evaluate_capability(
        self, ctx: ExecContext, cap: FanCapability
    ) -> bool:
        """Check if a capability is available in the given context.

        Args:
            ctx: Execution context
            cap: The capability to evaluate

        Returns:
            True if capability is eligible in this context
        """
        ...


class DefaultCaporRouter(CaporRouter):
    """Default Capor router implementation.

    Uses FanRegistry for capability lookup and simple
    security matching for eligibility checks.
    """

    def __init__(self, registry: Optional[FanRegistry] = None):
        self.registry = registry or FanRegistry()

    def resolve(self, ctx: ExecContext, fan_id: FanId) -> CaporDecision:
        """Resolve capacity: find matching capability + score."""
        caps = self.registry.list_by_fan(fan_id.id)

        if not caps:
            # Fallback: return restricted decision instead of raising
            return CaporDecision(
                fan_id=fan_id,
                capability="",
                security_profile=SecurityProfile(level="restricted"),
                scorer=Scorer(),
                reason="fallback_no_match",
            )

        # Find first eligible capability (in production, use Scorer for ranking)
        for cap in caps:
            if self.evaluate_capability(ctx, cap):
                return CaporDecision(
                    fan_id=fan_id,
                    capability=cap.id,
                    security_profile=SecurityProfile(level=ctx.security_tier),
                    scorer=Scorer(),
                    reason="matched",
                )

        # Fallback: return first capability with denied profile
        return CaporDecision(
            fan_id=fan_id,
            capability=caps[0].id,
            security_profile=SecurityProfile(level="restricted"),
            scorer=Scorer(),
            reason="fallback_no_match",
        )

    def evaluate_capability(
        self, ctx: ExecContext, cap: FanCapability
    ) -> bool:
        """Check capability eligibility based on context."""
        # Check actor-target match (explicit allow)
        if cap.fan_id.id == ctx.actor_target:
            return True

        # Security tier-based evaluation
        if ctx.security_tier == "local":
            # Local: all capabilities are eligible
            return True
        elif ctx.security_tier == "shared":
            # Shared: all capabilities are eligible by default
            return True
        elif ctx.security_tier == "restricted":
            # Restricted: deny by default unless explicitly allowed
            return False

        return False
