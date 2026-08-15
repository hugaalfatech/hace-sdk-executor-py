"""
# Executor-Py SDK — Fan & Capability Types

Mirrors `hace/sdk/executor-cep/src/core/fan.rs` (FanId, FanCapability, FanRegistry),
plus re-exports from core.

FAN = Feature ↔ Artifact ↔ Name mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .core import FanId, FanCapability, FanRegistry


__all__ = ["FanId", "FanCapability", "FanRegistry"]
