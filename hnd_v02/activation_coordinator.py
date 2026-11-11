"""Crash-reconcilable Station 2 activation coordinator.

This is an orchestration layer over injected services, not a production trust
boundary. Remote intent/anchor services and the local atomic backend must each
meet their documented durability and independence contracts.
"""
from __future__ import annotations

from typing import Mapping

from hnd_v02.activation_bundle import verify_activation_bundle_with_manifest_chain
from hnd_v02.activation_transaction import (
    ActivationState, AtomicActivationBackend, activate_verified_bundle,
)
from hnd_v02.monotonic_anchor import MonotonicRecord, MonotonicStateAnchor
from hnd_v02.remote_activation_intent import (
    ActivationIntent,
)
from hnd_v02.remote_monotonic_anchor import RemoteMonotonicAnchor


class ActivationCoordinatorError(RuntimeError):
    """Activation could not be safely reconciled; startup must remain blocked."""


def _same_record(actual, expected):
    return actual is None if expected is None else (
        actual is not None and actual.sequence == expected.sequence
        and actual.digest == expected.digest
    )


def _intent_matches(intent: ActivationIntent, request: dict) -> bool:
    return (
        intent.activation_id == request["activation_id"]
        and intent.predecessor_trust_manifest == request["predecessors"]["trust_manifest"]
        and intent.predecessor_vsp_profile == request["predecessors"]["vsp_profile"]
        and intent.successor_trust_manifest == request["successors"]["trust_manifest"]
        and intent.successor_vsp_profile == request["successors"]["vsp_profile"]
        and intent.profile_digest == request["profile_digest"]
        and intent.operator_ack_digest == request["operator_ack_digest"]
    )


class ActivationCoordinator:
    """Execute one immutable activation ID in protocol order.

    Timeouts are reconciled by read-after-write using the same ID/record. The
    coordinator never clears an intent, rolls back an anchor, or starts a
    process. Callers must keep startup disabled unless this method returns.
    """

    def __init__(self, *, intent_client, anchor: MonotonicStateAnchor,
                 backend: AtomicActivationBackend):
        if not callable(getattr(intent_client, "prepare", None)) or not callable(
            getattr(intent_client, "read_intent", None)
        ) or not callable(getattr(intent_client, "finalize", None)):
            raise ActivationCoordinatorError("HND-COORD-E-INTENT-CLIENT")
        if not callable(getattr(anchor, "read_state", None)) or not callable(
            getattr(anchor, "compare_and_advance", None)
        ):
            raise ActivationCoordinatorError("HND-COORD-E-ANCHOR")
        if not callable(getattr(backend, "read_active_state", None)) or not callable(
            getattr(backend, "compare_and_activate", None)
        ):
            raise ActivationCoordinatorError("HND-COORD-E-BACKEND")
        self.intent_client, self.anchor, self.backend = intent_client, anchor, backend

    def activate(self, *, activation_id: str, vsp_raw: bytes,
                 trust_manifests: list[bytes], operator_acks_raw: bytes,
                 profile_artifact: bytes, context: Mapping,
                 trusted_witness_keys: Mapping[str, bytes],
                 expected_operator_keys: Mapping[str, bytes]) -> ActivationState:
        if type(profile_artifact) is not bytes or not profile_artifact:
            raise ActivationCoordinatorError("HND-COORD-E-PROFILE")
        try:
            evidence = verify_activation_bundle_with_manifest_chain(
                vsp_raw, trust_manifests, operator_acks_raw, context=context,
                trusted_witness_keys=trusted_witness_keys,
                expected_operator_keys=expected_operator_keys,
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
        except Exception as exc:
            raise ActivationCoordinatorError("HND-COORD-E-EVIDENCE") from exc

        predecessors = {
            "trust_manifest": None if proposed.trust_manifest_sequence == 0 else {
                "sequence": proposed.trust_manifest_sequence - 1,
                "digest": proposed.previous_trust_manifest_digest,
            },
            "vsp_profile": None if proposed.profile_sequence == 1 else {
                "sequence": proposed.profile_sequence - 1,
                "digest": proposed.previous_profile_digest,
            },
        }
        successors = {
            "trust_manifest": {"sequence": proposed.trust_manifest_sequence,
                               "digest": proposed.trust_manifest_digest},
            "vsp_profile": {"sequence": proposed.profile_sequence,
                            "digest": proposed.profile_digest},
        }
        request = {
            "activation_id": activation_id,
            "predecessors": predecessors,
            "successors": successors,
            "profile_digest": proposed.profile_digest,
            "operator_ack_digest": proposed.operator_ack_set_sha256,
        }

        # Prepare is idempotent. On unknown outcome, read this exact ID; retry
        # only if absent, and never generate another ID here.
        try:
            intent = self.intent_client.prepare(
                activation_id=activation_id,
                predecessor_trust_manifest=predecessors["trust_manifest"],
                predecessor_vsp_profile=predecessors["vsp_profile"],
                successor_trust_manifest=successors["trust_manifest"],
                successor_vsp_profile=successors["vsp_profile"],
                profile_digest=request["profile_digest"],
                operator_ack_digest=request["operator_ack_digest"],
            )
        except Exception:
            try:
                intent = self.intent_client.read_intent(activation_id)
            except Exception as exc:
                raise ActivationCoordinatorError("HND-COORD-E-PREPARE-UNKNOWN") from exc
            if intent is None:
                try:
                    intent = self.intent_client.prepare(
                        activation_id=activation_id,
                        predecessor_trust_manifest=predecessors["trust_manifest"],
                        predecessor_vsp_profile=predecessors["vsp_profile"],
                        successor_trust_manifest=successors["trust_manifest"],
                        successor_vsp_profile=successors["vsp_profile"],
                        profile_digest=request["profile_digest"],
                        operator_ack_digest=request["operator_ack_digest"],
                    )
                except Exception as exc:
                    raise ActivationCoordinatorError("HND-COORD-E-PREPARE-RETRY") from exc
        if not isinstance(intent, ActivationIntent) or not _intent_matches(intent, request):
            raise ActivationCoordinatorError("HND-COORD-E-INTENT-MISMATCH")
        if intent.state not in {"prepared", "finalized"}:
            raise ActivationCoordinatorError("HND-COORD-E-INTENT-STATE")

        # Each namespace is reconciled independently. A timeout or false CAS
        # is followed by a read; only exact predecessor/successor is accepted.
        self._advance("trust-manifest", predecessors["trust_manifest"],
                      successors["trust_manifest"])
        self._advance("vsp-profile", predecessors["vsp_profile"],
                      successors["vsp_profile"])

        # Re-run the complete cryptographic verification through the existing
        # transaction boundary. It commits only after both remote anchors match.
        try:
            local_state = self.backend.read_active_state()
            if local_state != proposed:
                result = activate_verified_bundle(
                    self.backend, vsp_raw, trust_manifests, operator_acks_raw,
                    profile_artifact, context=context,
                    trusted_witness_keys=trusted_witness_keys,
                    expected_operator_keys=expected_operator_keys,
                )
                if result != proposed:
                    raise ActivationCoordinatorError("HND-COORD-E-LOCAL-MISMATCH")
            elif local_state is None:
                raise ActivationCoordinatorError("HND-COORD-E-LOCAL-STATE")
        except ActivationCoordinatorError:
            raise
        except Exception as exc:
            # Do not finalize: retain the prepared intent for same-ID recovery.
            raise ActivationCoordinatorError("HND-COORD-E-LOCAL-COMMIT") from exc

        # Finalize only after local durable state exactly equals the proposal.
        try:
            finalized = self.intent_client.finalize(
                activation_id=activation_id,
                profile_digest=request["profile_digest"],
                operator_ack_digest=request["operator_ack_digest"],
            )
        except Exception:
            try:
                finalized = self.intent_client.read_intent(activation_id)
            except Exception as exc:
                raise ActivationCoordinatorError("HND-COORD-E-FINALIZE-UNKNOWN") from exc
            if finalized is None or not _intent_matches(finalized, request):
                raise ActivationCoordinatorError("HND-COORD-E-FINALIZE-MISMATCH")
            if finalized.state == "prepared":
                try:
                    finalized = self.intent_client.finalize(
                        activation_id=activation_id,
                        profile_digest=request["profile_digest"],
                        operator_ack_digest=request["operator_ack_digest"],
                    )
                except Exception as exc:
                    raise ActivationCoordinatorError("HND-COORD-E-FINALIZE-RETRY") from exc
        if (not isinstance(finalized, ActivationIntent)
                or not _intent_matches(finalized, request)
                or finalized.state != "finalized"):
            raise ActivationCoordinatorError("HND-COORD-E-NOT-FINALIZED")
        return proposed

    def _advance(self, namespace: str, predecessor: dict | None,
                 successor: dict) -> None:
        expected = None if predecessor is None else MonotonicRecord(
            predecessor["sequence"], predecessor["digest"]
        )
        new = MonotonicRecord(successor["sequence"], successor["digest"])
        try:
            current = self.anchor.read_state(namespace)
            if _same_record(current, new):
                return
            if not _same_record(current, expected):
                raise ActivationCoordinatorError("HND-COORD-E-ANCHOR-CONFLICT-" + namespace)
            try:
                advanced = self.anchor.compare_and_advance(namespace, expected, new)
            except Exception:
                advanced = False  # unknown outcome; reconcile below
            if advanced is True:
                return
            observed = self.anchor.read_state(namespace)
            if _same_record(observed, new):
                return
            if _same_record(observed, expected):
                # A definitive unchanged predecessor permits the exact same CAS.
                if self.anchor.compare_and_advance(namespace, expected, new) is True:
                    return
                observed = self.anchor.read_state(namespace)
                if _same_record(observed, new):
                    return
            raise ActivationCoordinatorError("HND-COORD-E-ANCHOR-UNRESOLVED-" + namespace)
        except ActivationCoordinatorError:
            raise
        except Exception as exc:
            raise ActivationCoordinatorError("HND-COORD-E-ANCHOR-UNAVAILABLE-" + namespace) from exc
