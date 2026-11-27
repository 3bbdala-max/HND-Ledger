"""Backend contract for the Station 2 activation witness.

Capability declarations are descriptive only. Production admission is enforced
by the separately pinned signed-attestation verifier.
"""
from __future__ import annotations

from typing import Any, Protocol, TypedDict


class ActivationWitnessStoreError(RuntimeError):
    """The activation witness backend rejected or could not commit an ACK."""


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

    @property
    def backend_identity(self) -> dict[str, Any]:
        """Return immutable deployment identity bound by signed attestation."""

    def acknowledge(
        self, activation_id: str, activation_digest: str
    ) -> dict[str, Any]:
        """Return the immutable signed receipt for this exact activation."""
