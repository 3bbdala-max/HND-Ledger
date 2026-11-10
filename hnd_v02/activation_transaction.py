"""Atomic activation boundary for verified HND profile bundles.

This is an integration contract, not a production backend. A conforming backend
must atomically install the validated profile artifact and advance BOTH
anti-rollback namespaces. A filesystem-only or sequential two-write backend is
not conforming.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol
import re

from hnd_v02.activation_bundle import verify_activation_bundle_with_manifest_chain

_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_MAX_SEQUENCE = (1 << 53) - 1


class ActivationTransactionError(RuntimeError):
    """Activation was rejected or could not be committed safely."""


class ActivationTransactionUnavailable(ActivationTransactionError):
    """No trusted atomic activation backend is available."""


class ActivationTransactionConflict(ActivationTransactionError):
    """The active state changed or the proposed state is not its successor."""


@dataclass(frozen=True)
class ActivationState:
    trust_manifest_sequence: int
    trust_manifest_digest: str
    profile_sequence: int
    profile_digest: str
    activation_height: int
    operator_ack_set_sha256: str


class AtomicActivationBackend(Protocol):
    """Independent backend with one durable, linearizable activation operation.

    compare_and_activate MUST, as one indivisible transaction:
      1. compare the complete current state with expected_current;
      2. validate the supplied profile artifact against profile_digest using
         the pinned CometBFT v0.40.0 schema;
      3. install the new profile and advance both monotonic namespaces;
      4. make the new active state durable before returning True.

    It MUST NOT return True if only a subset of those effects was committed.
    A backend unable to provide this guarantee is not suitable for production.
    """

    def read_active_state(self) -> ActivationState | None: ...

    def compare_and_activate(
        self,
        expected_current: ActivationState | None,
        new_state: ActivationState,
        profile_artifact: bytes,
    ) -> bool: ...


def _validate_state(state: ActivationState) -> None:
    if type(state) is not ActivationState:
        raise ActivationTransactionUnavailable("HND-ACT-E-STATE-TYPE")
    for value in (state.trust_manifest_sequence, state.profile_sequence,
                  state.activation_height):
        if type(value) is not int or not 0 <= value <= _MAX_SEQUENCE:
            raise ActivationTransactionUnavailable("HND-ACT-E-STATE-INTEGER")
    for value in (state.trust_manifest_digest, state.profile_digest,
                  state.operator_ack_set_sha256):
        if type(value) is not str or not _HEX64.fullmatch(value):
            raise ActivationTransactionUnavailable("HND-ACT-E-STATE-DIGEST")


def activate_verified_bundle(
    backend: AtomicActivationBackend,
    vsp_raw: bytes,
    trust_manifests: list[bytes],
    operator_acks_raw: bytes,
    profile_artifact: bytes,
    *,
    context: Mapping,
    trusted_witness_keys: Mapping[str, bytes],
    expected_operator_keys: Mapping[str, bytes],
) -> ActivationState:
    """Verify all evidence, then request one atomic activation transaction.

    The cryptographic preflight runs before the backend is called. The backend
    remains responsible for pinned-schema profile verification and atomic
    installation/anti-rollback persistence. This module ships no production
    backend and therefore cannot itself activate a live network.
    """
    if type(profile_artifact) is not bytes or not profile_artifact:
        raise ActivationTransactionError("HND-ACT-E-PROFILE-ARTIFACT")
    try:
        evidence = verify_activation_bundle_with_manifest_chain(
            vsp_raw, trust_manifests, operator_acks_raw,
            context=context, trusted_witness_keys=trusted_witness_keys,
            expected_operator_keys=expected_operator_keys,
        )
    except Exception as exc:
        raise ActivationTransactionError("HND-ACT-E-PREFLIGHT") from exc

    proposed = ActivationState(
        trust_manifest_sequence=evidence["trust_manifest_sequence"],
        trust_manifest_digest=evidence["trust_manifest_digest"],
        profile_sequence=evidence["profile_sequence"],
        profile_digest=evidence["profile_digest"],
        activation_height=evidence["activation_height"],
        operator_ack_set_sha256=evidence["operator_ack_set_sha256"],
    )
    _validate_state(proposed)

    try:
        current = backend.read_active_state()
    except Exception as exc:
        raise ActivationTransactionUnavailable("HND-ACT-E-READ") from exc
    if current is not None:
        _validate_state(current)
        if proposed.trust_manifest_sequence != current.trust_manifest_sequence + 1:
            raise ActivationTransactionConflict("HND-ACT-E-MANIFEST-SEQUENCE")
        if proposed.profile_sequence != current.profile_sequence + 1:
            raise ActivationTransactionConflict("HND-ACT-E-PROFILE-SEQUENCE")
        if proposed.activation_height <= current.activation_height:
            raise ActivationTransactionConflict("HND-ACT-E-ACTIVATION-HEIGHT")
    elif (proposed.trust_manifest_sequence != 0
          or proposed.profile_sequence != 1):
        raise ActivationTransactionConflict("HND-ACT-E-BOOTSTRAP-SEQUENCE")

    try:
        committed = backend.compare_and_activate(
            current, proposed, profile_artifact
        )
    except Exception as exc:
        raise ActivationTransactionUnavailable("HND-ACT-E-COMMIT") from exc
    if committed is not True:
        raise ActivationTransactionConflict("HND-ACT-E-CAS")
    return proposed
