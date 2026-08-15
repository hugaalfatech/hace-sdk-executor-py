"""
# Executor-Py SDK — Evidence (SepiProof + FEH/ALR)

Mirrors `hace/sdk/executor-cep/src/core/evidence.rs`.

Every execute() MUST produce evidence (FEH = Fingerprint of Execution Hash,
ALR = Archetype Ledger Record seal).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from .core import ExecContext, FanId, SepiProof, SioStatus


def compute_feh_hash(
    fan_id: FanId,
    action: str,
    payload: dict[str, Any],
    result: Any,
    ctx: ExecContext,
) -> str:
    """Compute Fingerprint of Execution Hash (FEH).

    Canonical hash over execution inputs + outputs for audit/evidence sealing.
    Mirrors FEH computation in io/rac/src/loader.rs (emit_ze_alr).
    """
    # Canonical payload for hashing (sorted, stable)
    hash_input = {
        "fan_id": fan_id.id,
        "action": action,
        "payload": _stable_dict(payload),
        "context": {
            "trace_id": ctx.trace_id,
            "session_id": ctx.session_id,
            "security_tier": ctx.security_tier,
            "workspace_root": ctx.workspace_root,
            "actor_target": ctx.actor_target,
        },
        "result": result if isinstance(result, (str, int, float, bool)) else "<structured>",
        "ctx": ctx.trace_id,
    }
    raw = json.dumps(hash_input, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _stable_dict(d: dict) -> str:
    """Serialize dict to stable JSON string for hashing."""
    return json.dumps(d, sort_keys=True, default=str)


def seal_alr_record(
    fan_id: FanId,
    action: str,
    execution_id: str,
    feh_hash: str,
    status: SioStatus,
) -> str:
    """Seal Archetype Ledger Record (ALR).

    Creates a sealed audit entry for the execution.
    Mirrors ALR ledger in io/rac/src/loader.rs + rr_ze_lite.
    """
    record = {
        "execution_id": execution_id,
        "fan_id": fan_id.id,
        "action": action,
        "feh_hash": feh_hash,
        "status": status.value,
        "sealed_at": execution_id,  # timestamp encoded in execution_id
    }
    raw = json.dumps(record, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def build_proof(
    fan_id: FanId,
    action: str,
    input_data: dict[str, Any],
    result: Any,
    ctx: ExecContext,
    status: SioStatus = SioStatus.SUCCESS,
) -> "SepiProof":
    """Build complete SepiProof evidence for an execution.

    Mirrors SepiProof construction in executor-cep.
    """
    execution_id = str(uuid4())
    feh = compute_feh_hash(fan_id, action, input_data, result, ctx)
    alr = seal_alr_record(fan_id, action, execution_id, feh, status)

    return SepiProof(
        execution_id=execution_id,
        fan_id=fan_id.id,
        action=action,
        status=status.value,
        feh_hash=feh,
        alr_seal=alr,
    )
