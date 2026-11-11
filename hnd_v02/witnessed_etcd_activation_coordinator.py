"""Witness-gated coordinator for the etcd Station 2 activation path.

This coordinator is the only supported orchestration path for this backend:
verify the evidence bundle, atomically write active state/profile/monotonic
records/pending intent, obtain an independent witness ACK, then CAS-finalize
that exact intent. Callers must not authorize startup unless activate() returns.
"""
from __future__ import annotations

from typing import Mapping

from hnd_v02.activation_bundle import verify_activation_bundle_with_manifest_chain
from hnd_v02.activation_transaction import ActivationState
from hnd_v02.activation_witness import compute_activation_digest
from hnd_v02.etcd_atomic_activation import EtcdAtomicActivationError


class WitnessedActivationCoordinatorError(RuntimeError):
    """Activation remains untrusted; startup must remain blocked."""


def _intent_matches(intent: dict, activation_id: str, state: ActivationState,
                    activation_digest: str) -> bool:
    return (
        type(intent) is dict
        and intent.get("activation_id") == activation_id
        and intent.get("activation_digest") == activation_digest
        and intent.get("trust_manifest_sequence") == state.trust_manifest_sequence
        and intent.get("trust_manifest_digest") == state.trust_manifest_digest
        and intent.get("profile_sequence") == state.profile_sequence
        and intent.get("profile_digest") == state.profile_digest
        and intent.get("operator_ack_digest") == state.operator_ack_set_sha256
        and intent.get("state") in {"pending_witness", "finalized"}
    )


class WitnessedEtcdActivationCoordinator:
    """Crash-reconcilable witness-gated activation using etcd as atomic backend."""

    def __init__(
        self,
        *,
        backend,
        witness_client,
        trusted_witness_keys: Mapping[str, bytes],
        expected_witness_id: str,
        expected_config_epoch: int,
    ):
        if not callable(getattr(backend, "compare_and_activate_with_intent", None)):
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-BACKEND")
        if not callable(getattr(backend, "read_activation_intent", None)):
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-INTENT-READ")
        if not callable(getattr(backend, "finalize_activation_intent", None)):
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-FINALIZER")
        if not callable(getattr(backend, "read_active_state", None)):
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-STATE-READ")
        if not callable(getattr(backend, "read_active_profile", None)):
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-PROFILE-READ")
        if not callable(getattr(witness_client, "acknowledge", None)):
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-WITNESS-CLIENT")
        if not isinstance(trusted_witness_keys, Mapping):
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-TRUST-STORE")
        if type(expected_witness_id) is not str or not expected_witness_id:
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-WITNESS-ID")
        if type(expected_config_epoch) is not int or expected_config_epoch < 1:
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-CONFIG-EPOCH")
        self.backend = backend
        self.witness_client = witness_client
        self.trusted_witness_keys = dict(trusted_witness_keys)
        self.expected_witness_id = expected_witness_id
        self.expected_config_epoch = expected_config_epoch

    def activate(
        self,
        *,
        activation_id: str,
        vsp_raw: bytes,
        trust_manifests: list[bytes],
        operator_acks_raw: bytes,
        profile_artifact: bytes,
        context: Mapping,
        trusted_operator_keys: Mapping[str, bytes],
    ) -> ActivationState:
        if type(profile_artifact) is not bytes or not profile_artifact:
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-PROFILE")
        try:
            evidence = verify_activation_bundle_with_manifest_chain(
                vsp_raw, trust_manifests, operator_acks_raw,
                context=context,
                trusted_witness_keys=self.trusted_witness_keys,
                expected_operator_keys=trusted_operator_keys,
            )
            proposed = ActivationState(
                trust_manifest_sequence=evidence["trust_manifest_sequence"],
                trust_manifest_digest=evidence["trust_manifest_digest"],
                profile_sequence=evidence["profile_sequence"],
                profile_digest=evidence["profile_digest"],
                activation_height=evidence["activation_height"],
                operator_ack_set_sha256=evidence["operator_ack_set_sha256"],
                previous_trust_manifest_digest=evidence["previous_trust_manifest_digest"],
                previous_profile_digest=evidence["previous_profile_digest"],
            )
            digest = compute_activation_digest(activation_id, proposed, profile_artifact)
        except Exception as exc:
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-EVIDENCE") from exc

        # First try the atomic etcd transaction. A lost response is reconciled
        # exclusively by reading the same activation ID; never mint a new ID.
        try:
            committed = self.backend.compare_and_activate_with_intent(
                self.backend.read_active_state(), proposed, profile_artifact,
                activation_id=activation_id,
            )
        except Exception:
            committed = None
        intent = None
        if committed is not True:
            try:
                intent = self.backend.read_activation_intent(activation_id)
            except Exception as exc:
                raise WitnessedActivationCoordinatorError(
                    "HND-WCOORD-E-ATOMIC-COMMIT-UNKNOWN"
                ) from exc
            if not _intent_matches(intent, activation_id, proposed, digest):
                raise WitnessedActivationCoordinatorError(
                    "HND-WCOORD-E-ATOMIC-COMMIT-UNRESOLVED"
                )
        else:
            try:
                intent = self.backend.read_activation_intent(activation_id)
            except Exception as exc:
                raise WitnessedActivationCoordinatorError(
                    "HND-WCOORD-E-INTENT-READ-AFTER-WRITE"
                ) from exc
            if not _intent_matches(intent, activation_id, proposed, digest):
                raise WitnessedActivationCoordinatorError("HND-WCOORD-E-INTENT-MISMATCH")

        if intent["state"] == "finalized":
            receipt = intent.get("witness_receipt")
            if type(receipt) is not dict:
                raise WitnessedActivationCoordinatorError("HND-WCOORD-E-RECEIPT-MISSING")
        else:
            # Same activation ID + digest is the only retry key. The reference
            # witness store returns the original receipt after a lost response.
            try:
                receipt = self.witness_client.acknowledge(activation_id, digest)
            except Exception:
                try:
                    receipt = self.witness_client.acknowledge(activation_id, digest)
                except Exception as exc:
                    raise WitnessedActivationCoordinatorError(
                        "HND-WCOORD-E-WITNESS-ACK-UNKNOWN"
                    ) from exc
            if type(receipt) is not dict:
                raise WitnessedActivationCoordinatorError("HND-WCOORD-E-RECEIPT-SHAPE")

        try:
            finalized = self.backend.finalize_activation_intent(
                activation_id, receipt,
                trusted_witness_keys=self.trusted_witness_keys,
                expected_witness_id=self.expected_witness_id,
                expected_config_epoch=self.expected_config_epoch,
            )
        except Exception:
            # Resolve a lost finalize response by reading the same intent and
            # retrying only with the exact same signed receipt.
            try:
                observed = self.backend.read_activation_intent(activation_id)
                if (not _intent_matches(observed, activation_id, proposed, digest)
                        or observed.get("state") != "finalized"
                        or observed.get("witness_receipt") != receipt):
                    finalized = self.backend.finalize_activation_intent(
                        activation_id, receipt,
                        trusted_witness_keys=self.trusted_witness_keys,
                        expected_witness_id=self.expected_witness_id,
                        expected_config_epoch=self.expected_config_epoch,
                    )
                else:
                    finalized = observed
            except Exception as exc:
                raise WitnessedActivationCoordinatorError(
                    "HND-WCOORD-E-FINALIZE-UNKNOWN"
                ) from exc

        if (not _intent_matches(finalized, activation_id, proposed, digest)
                or finalized.get("state") != "finalized"
                or finalized.get("witness_receipt") != receipt):
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-NOT-FINALIZED")

        # A successful return is the startup-authorization boundary for callers.
        try:
            active_state = self.backend.read_active_state()
            active_profile = self.backend.read_active_profile()
        except Exception as exc:
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-READ-BACK") from exc
        if active_state != proposed or active_profile != profile_artifact:
            raise WitnessedActivationCoordinatorError("HND-WCOORD-E-ACTIVE-MISMATCH")
        return proposed
