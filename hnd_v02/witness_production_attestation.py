"""Cryptographically verified production admission for Station 2 witnesses.

Backend capability flags are self-reported and are not a trust boundary. A
production deployment must pin an attestor public key outside the witness
process and provide a signed, short-lived attestation binding the concrete
backend, witness identity, quorum, anti-rollback anchor and signing-key handle.
"""
from __future__ import annotations

import base64
import json
import time
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from hnd_v02.activation_witness_interface import (
    ActivationWitnessStoreError,
    WitnessBackendCapabilities,
)

_SCHEMA = "hnd.station2.witness-production-attestation.v1"
_DOMAIN = b"HND-STATION2-WITNESS-PRODUCTION-ATTESTATION-V1\x00"
_FIELDS = frozenset({
    "schema", "backend", "witness_id", "config_epoch", "quorum_id",
    "anchor_id", "signing_key_ref", "review_reference", "issued_at",
    "expires_at",
})
_ID_FIELDS = ("backend", "witness_id", "quorum_id", "anchor_id", "signing_key_ref")
_MAX_INTEGER = (1 << 53) - 1


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("ascii")


def verify_production_attestation(
    store: object,
    attestation: Mapping[str, Any],
    trusted_attestor_public_key: bytes,
    *,
    now: int | None = None,
) -> None:
    """Verify a pinned attestor signature and exact backend identity binding.

    The trusted public key must come from deployment configuration protected
    independently of the witness service. This check does not replace external
    audit, infrastructure inspection, or proof of actual operator independence.
    """
    if type(trusted_attestor_public_key) is not bytes or len(trusted_attestor_public_key) != 32:
        raise ValueError("HND-WITNESS-SERVICE-E-ATTESTOR-KEY")
    if not isinstance(attestation, Mapping) or set(attestation) != _FIELDS | {"signature"}:
        raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-SHAPE")
    payload = {key: attestation[key] for key in _FIELDS}
    if payload.get("schema") != _SCHEMA:
        raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-SCHEMA")
    for key in _ID_FIELDS + ("review_reference",):
        value = payload.get(key)
        if type(value) is not str or not value.strip() or len(value) > 256:
            raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-FIELDS")
    for key in ("config_epoch", "issued_at", "expires_at"):
        value = payload.get(key)
        if type(value) is not int or not 0 <= value <= _MAX_INTEGER:
            raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-TIME")
    current_time = int(time.time()) if now is None else now
    if type(current_time) is not int or not 0 <= current_time <= _MAX_INTEGER:
        raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-CLOCK")
    if (payload["config_epoch"] < 1 or payload["issued_at"] > current_time + 60
            or payload["expires_at"] <= current_time
            or payload["expires_at"] <= payload["issued_at"]
            or payload["expires_at"] - payload["issued_at"] > 90 * 24 * 60 * 60):
        raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-EXPIRED")
    signature_text = attestation["signature"]
    if type(signature_text) is not str:
        raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-SIGNATURE")
    try:
        signature = base64.b64decode(signature_text.encode("ascii"), validate=True)
        if len(signature) != 64 or base64.b64encode(signature).decode("ascii") != signature_text:
            raise ValueError("non-canonical signature")
        Ed25519PublicKey.from_public_bytes(trusted_attestor_public_key).verify(
            signature, _DOMAIN + _canonical(payload)
        )
    except (ValueError, UnicodeError, InvalidSignature) as exc:
        raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-INVALID") from exc

    identity = getattr(store, "backend_identity", None)
    if not isinstance(identity, Mapping):
        raise ValueError("HND-WITNESS-SERVICE-E-BACKEND-IDENTITY")
    for key in _ID_FIELDS + ("config_epoch",):
        if identity.get(key) != payload[key]:
            raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-BINDING")


def require_production_witness_backend(
    store: object,
    *,
    attestation: Mapping[str, Any] | None = None,
    trusted_attestor_public_key: bytes | None = None,
    now: int | None = None,
) -> None:
    """Reject self-asserted capability flags unless a pinned attestation verifies."""
    capabilities = getattr(store, "capabilities", None)
    if not isinstance(capabilities, dict):
        raise ValueError("HND-WITNESS-SERVICE-E-CAPABILITIES")
    required_true = (
        "production_capable", "quorum_ready",
        "anti_rollback_verified", "protected_key_custody",
    )
    if (
        type(capabilities.get("backend")) is not str
        or not capabilities["backend"].strip()
        or any(capabilities.get(name) is not True for name in required_true)
        or not callable(getattr(store, "acknowledge", None))
    ):
        raise ValueError("HND-WITNESS-SERVICE-E-PRODUCTION-GATE")
    if attestation is None or trusted_attestor_public_key is None:
        raise ValueError("HND-WITNESS-SERVICE-E-ATTESTATION-REQUIRED")
    verify_production_attestation(
        store, attestation, trusted_attestor_public_key, now=now
    )
