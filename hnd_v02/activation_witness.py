"""Cryptographic commitment and receipt verification for Station 2 witness ACKs.

This module verifies an Ed25519-signed acknowledgement over one exact activation
commitment. It does NOT implement witness storage, quorum durability, monotonic
counter allocation, or an independent failure domain; those remain mandatory
properties of the separately operated witness service.
"""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from hnd_v02.activation_transaction import ActivationState, _validate_state

_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_MAX_INTEGER = (1 << 53) - 1
_SCHEMA = "hnd.station2.witness-ack.v1"
_DOMAIN = b"HND-STATION2-WITNESS-ACK-V1\x00"


class ActivationWitnessError(RuntimeError):
    """A witness acknowledgement or activation commitment is invalid."""


@dataclass(frozen=True)
class VerifiedWitnessReceipt:
    activation_id: str
    activation_digest: str
    witness_id: str
    config_epoch: int
    counter: int


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("ascii")


def compute_activation_digest(
    activation_id: str,
    state: ActivationState,
    profile_artifact: bytes,
) -> str:
    """Hash the immutable activation ID, complete state and exact artifact bytes."""
    if type(activation_id) is not str or not _ID.fullmatch(activation_id):
        raise ActivationWitnessError("HND-WITNESS-E-ACTIVATION-ID")
    if type(profile_artifact) is not bytes or not profile_artifact:
        raise ActivationWitnessError("HND-WITNESS-E-PROFILE-ARTIFACT")
    try:
        _validate_state(state)
    except Exception as exc:
        raise ActivationWitnessError("HND-WITNESS-E-ACTIVATION-STATE") from exc
    commitment = {
        "schema": "hnd.station2.activation-commitment.v1",
        "activation_id": activation_id,
        "state": asdict(state),
        "profile_artifact_sha256": hashlib.sha256(profile_artifact).hexdigest(),
    }
    return hashlib.sha256(_DOMAIN + _canonical(commitment)).hexdigest()


def verify_witness_receipt(
    receipt: Mapping,
    *,
    trusted_witness_keys: Mapping[str, bytes],
    expected_activation_id: str,
    expected_activation_digest: str,
    expected_witness_id: str,
    expected_config_epoch: int,
) -> VerifiedWitnessReceipt:
    """Verify exact receipt shape, pinned witness identity/epoch and Ed25519 signature.

    The trusted key mapping and expected identity/epoch must come from separately
    protected deployment configuration, never from the receipt being verified.
    """
    keys = {
        "schema", "activation_id", "activation_digest", "witness_id",
        "config_epoch", "counter", "signature",
    }
    if type(receipt) is not dict or set(receipt) != keys:
        raise ActivationWitnessError("HND-WITNESS-E-RECEIPT-SHAPE")
    if receipt["schema"] != _SCHEMA:
        raise ActivationWitnessError("HND-WITNESS-E-SCHEMA")
    for value in (expected_activation_id, expected_witness_id):
        if type(value) is not str or not _ID.fullmatch(value):
            raise ActivationWitnessError("HND-WITNESS-E-EXPECTED-IDENTITY")
    if (type(expected_activation_digest) is not str
            or not _HEX64.fullmatch(expected_activation_digest)):
        raise ActivationWitnessError("HND-WITNESS-E-EXPECTED-DIGEST")
    if type(expected_config_epoch) is not int or not 1 <= expected_config_epoch <= _MAX_INTEGER:
        raise ActivationWitnessError("HND-WITNESS-E-EXPECTED-EPOCH")
    if (receipt["activation_id"] != expected_activation_id
            or receipt["activation_digest"] != expected_activation_digest):
        raise ActivationWitnessError("HND-WITNESS-E-COMMITMENT-MISMATCH")
    witness_id = receipt["witness_id"]
    if witness_id != expected_witness_id:
        raise ActivationWitnessError("HND-WITNESS-E-IDENTITY-MISMATCH")
    if type(receipt["config_epoch"]) is not int or receipt["config_epoch"] != expected_config_epoch:
        raise ActivationWitnessError("HND-WITNESS-E-CONFIG-EPOCH")
    counter = receipt["counter"]
    if type(counter) is not int or not 1 <= counter <= _MAX_INTEGER:
        raise ActivationWitnessError("HND-WITNESS-E-COUNTER")
    if not isinstance(trusted_witness_keys, Mapping):
        raise ActivationWitnessError("HND-WITNESS-E-TRUST-STORE")
    public_key = trusted_witness_keys.get(witness_id)
    if type(public_key) is not bytes or len(public_key) != 32:
        raise ActivationWitnessError("HND-WITNESS-E-UNTRUSTED-KEY")
    encoded_signature = receipt["signature"]
    if type(encoded_signature) is not str:
        raise ActivationWitnessError("HND-WITNESS-E-SIGNATURE-SHAPE")
    try:
        signature = base64.b64decode(encoded_signature.encode("ascii"), validate=True)
        if len(signature) != 64 or base64.b64encode(signature).decode("ascii") != encoded_signature:
            raise ValueError("non-canonical signature")
        signed_payload = {key: receipt[key] for key in (
            "schema", "activation_id", "activation_digest", "witness_id",
            "config_epoch", "counter",
        )}
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, _DOMAIN + _canonical(signed_payload)
        )
    except (ValueError, UnicodeError, InvalidSignature) as exc:
        raise ActivationWitnessError("HND-WITNESS-E-SIGNATURE-INVALID") from exc
    return VerifiedWitnessReceipt(
        expected_activation_id, expected_activation_digest,
        witness_id, expected_config_epoch, counter,
    )
