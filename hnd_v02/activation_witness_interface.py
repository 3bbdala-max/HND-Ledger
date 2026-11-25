"""Backend contract for the Station 2 activation witness.

The protocol is intentionally narrower than any concrete storage technology.
Capability declarations are admission checks, not cryptographic proof: the
production implementation and its deployment evidence must still be reviewed.
"""
from __future__ import annotations

from typing import Any, Protocol, TypedDict


class WitnessBackendCapabilities(TypedDict):
    backend: str
    production_capable: bool
    quorum_ready: bool
    anti_rollback_verified: bool
    protected_key_custody: bool


class ActivationWitnessStore(Protocol):
    """Minimal API consumed by the HTTPS witness service."""

    @property
    def capabilities(self) -> WitnessBackendCapabilities:
        """Return current backend identity and fail-closed readiness claims."""

    def acknowledge(
        self, activation_id: str, activation_digest: str
    ) -> dict[str, Any]:
        """Return the immutable signed receipt for this exact activation."""


def require_production_witness_backend(store: object) -> None:
    """Reject reference stores and backends without all production gates."""
    capabilities = getattr(store, "capabilities", None)
    if not isinstance(capabilities, dict):
        raise ValueError("HND-WITNESS-SERVICE-E-CAPABILITIES")
    required_true = (
        "production_capable",
        "quorum_ready",
        "anti_rollback_verified",
        "protected_key_custody",
    )
    if (
        type(capabilities.get("backend")) is not str
        or not capabilities["backend"].strip()
        or any(capabilities.get(name) is not True for name in required_true)
        or not callable(getattr(store, "acknowledge", None))
    ):
        raise ValueError("HND-WITNESS-SERVICE-E-PRODUCTION-GATE")
