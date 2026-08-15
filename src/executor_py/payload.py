"""
Executor-Py SDK — IPO Payload Extraction Layer

Mirrors `hace/sdk/executor-cep/src/orch/ipo.rs` payload extraction logic.
Provides utilities to extract, validate, and normalize payloads from
canonical rac:call / rac:import / rac:instance frames before handing them
to ExecuteParticle implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class IpoPayload:
    """Extracted and normalized IPO payload.

    Canonical rac:call frame payload is {action, value, options}.
    This dataclass normalizes all three invocation forms into a flat
    payload usable by ExecuteParticle implementations.
    """

    action: str = ""
    value: Any = None
    options: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_value(self) -> bool:
        return self.value is not None

    def merge_value_into_options(self, key: str = "value") -> None:
        """Move self.value into self.options dict under `key` (if not already present)."""
        if self.value is not None and key not in self.options:
            self.options[key] = self.value


@dataclass
class ValidatedPayload:
    """Payload after IPO validation — ready for particle execution.

    Mirrors the validated_payload passed to ExecuteParticle.execute().
    """

    action: str
    payload: Dict[str, Any]
    headers: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)


def extract_payload(frame: Dict[str, Any]) -> IpoPayload:
    """Extract IPO payload from a canonical rac:call/import/instance frame.

    Args:
        frame: A dict with keys: method, actor, payload, headers, context

    Returns:
        IpoPayload with action, value, options, headers, context populated
    """
    payload = frame.get("payload", {})
    if not isinstance(payload, dict):
        payload = {"value": payload}

    return IpoPayload(
        action=payload.get("action", ""),
        value=payload.get("value"),
        options=payload.get("options", {}),
        headers=frame.get("headers", {}),
        context=frame.get("context", {}),
    )


def validate_payload(raw: IpoPayload, *, strict: bool = False) -> ValidatedPayload:
    """Validate raw IPO payload into a ValidatedPayload.

    Args:
        raw: The raw extracted payload
        strict: If True, raise on missing action

    Returns:
        ValidatedPayload ready for particle execution

    Raises:
        ValueError: If strict=True and action is empty
    """
    if strict and not raw.action:
        raise ValueError("IPO validation: action is required in strict mode")

    # Merge value into options if needed
    if raw.has_value:
        raw.merge_value_into_options()

    # Flatten payload: action + options (which includes value)
    flat_payload = {
        "action": raw.action,
        **raw.options,
    }

    return ValidatedPayload(
        action=raw.action,
        payload=flat_payload,
        headers=raw.headers,
        context=raw.context,
    )


def rac_frame_to_ipo_payload(
    rac_uri: str,
    method: str = "call",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> IpoPayload:
    """Convert rac URI + method + payload into IpoPayload.

    This is the inverse of the CanonicalActionBuilder.build_*_frame methods.
    """
    payload = payload or {}
    return IpoPayload(
        action=payload.get("action", method if method != "call" else ""),
        value=payload.get("value"),
        options=payload.get("options", {}),
        headers=headers or {},
        context=context or {},
    )


def build_payload_for_handler(
    ipo_payload: IpoPayload,
    *,
    flatten_value: bool = True,
) -> Dict[str, Any]:
    """Build the final payload dict to pass to a handler function.

    Args:
        ipo_payload: The extracted IPO payload
        flatten_value: If True, flatten value into the top-level payload dict

    Returns:
        Dict suitable for passing as **kwargs to handler functions
    """
    result: Dict[str, Any] = {
        "action": ipo_payload.action,
    }

    # Add all options
    result.update(ipo_payload.options)

    # Optionally flatten value into payload (backward compat with direct bindings)
    if flatten_value and ipo_payload.has_value and "value" not in result:
        result["value"] = ipo_payload.value

    return result


__all__ = [
    "IpoPayload",
    "ValidatedPayload",
    "extract_payload",
    "validate_payload",
    "rac_frame_to_ipo_payload",
    "build_payload_for_handler",
]
