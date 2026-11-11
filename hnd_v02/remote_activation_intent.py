"""Strict client for the remote activation-intent v2 protocol.

This is a transport adapter only. It does not provide a server, durable storage,
linearizability, local artifact installation, or crash-safe activation by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from hnd_v02.monotonic_anchor import MonotonicAnchorUnavailable
from hnd_v02.remote_monotonic_anchor import RemoteMonotonicAnchor

_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_STATES = frozenset({"prepared", "finalized", "conflict"})


class RemoteActivationProtocolError(RuntimeError):
    """The remote activation service response or request is not trustworthy."""


@dataclass(frozen=True)
class ActivationIntent:
    activation_id: str
    state: str
    predecessor_trust_manifest: Mapping[str, Any] | None
    predecessor_vsp_profile: Mapping[str, Any] | None
    successor_trust_manifest: Mapping[str, Any]
    successor_vsp_profile: Mapping[str, Any]
    profile_digest: str
    operator_ack_digest: str


def _record(value: Any, *, nullable: bool = False):
    if value is None and nullable:
        return None
    if type(value) is not dict or set(value) != {"sequence", "digest"}:
        raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-RECORD-SHAPE")
    if type(value["sequence"]) is not int or not 0 <= value["sequence"] <= (1 << 53) - 1:
        raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-SEQUENCE")
    if type(value["digest"]) is not str or not _HEX64.fullmatch(value["digest"]):
        raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-DIGEST")
    return {"sequence": value["sequence"], "digest": value["digest"]}


def _validate_id(value: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-ID")
    return value


class RemoteActivationIntentClient:
    """Prepare/read/finalize client layered on the existing HTTPS/mTLS channel.

    The service contract requires each operation to be linearizable and durable.
    The client treats every timeout as an unknown outcome and requires callers
    to read the same activation_id before retrying or making a new decision.
    """

    def __init__(self, anchor: RemoteMonotonicAnchor):
        if not isinstance(anchor, RemoteMonotonicAnchor):
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-CLIENT")
        self._anchor = anchor

    def prepare(
        self, *, activation_id: str,
        predecessor_trust_manifest: Mapping[str, Any] | None,
        predecessor_vsp_profile: Mapping[str, Any] | None,
        successor_trust_manifest: Mapping[str, Any],
        successor_vsp_profile: Mapping[str, Any],
        profile_digest: str, operator_ack_digest: str,
    ) -> ActivationIntent:
        activation_id = _validate_id(activation_id)
        predecessors = {
            "trust_manifest": _record(predecessor_trust_manifest, nullable=True),
            "vsp_profile": _record(predecessor_vsp_profile, nullable=True),
        }
        successors = {
            "trust_manifest": _record(successor_trust_manifest),
            "vsp_profile": _record(successor_vsp_profile),
        }
        for name, value in (("profile", profile_digest), ("operator ack", operator_ack_digest)):
            if type(value) is not str or not _HEX64.fullmatch(value):
                raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-" + name.upper().replace(" ", "-"))
        # Validate exact successor relationships before network I/O.
        for namespace, bootstrap in (("trust_manifest", 0), ("vsp_profile", 1)):
            old, new = predecessors[namespace], successors[namespace]
            expected = bootstrap if old is None else old["sequence"] + 1
            if new["sequence"] != expected:
                raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-SEQUENCE")
            if old is not None and new["sequence"] > (1 << 53) - 1:
                raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-SEQUENCE")
        payload = {
            "activation_id": activation_id,
            "predecessors": predecessors,
            "successors": successors,
            "profile_digest": profile_digest,
            "operator_ack_digest": operator_ack_digest,
        }
        response = self._request("/v2/activation/prepare", payload)
        return self._parse_intent(response, expected_id=activation_id)

    def read_intent(self, activation_id: str) -> ActivationIntent | None:
        activation_id = _validate_id(activation_id)
        response = self._request("/v2/activation/read", {"activation_id": activation_id})
        if type(response) is not dict or set(response) != {"intent"}:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-READ-SHAPE")
        if response["intent"] is None:
            return None
        return self._parse_intent(response["intent"], expected_id=activation_id)

    def finalize(self, *, activation_id: str, profile_digest: str,
                 operator_ack_digest: str) -> ActivationIntent:
        activation_id = _validate_id(activation_id)
        for value in (profile_digest, operator_ack_digest):
            if type(value) is not str or not _HEX64.fullmatch(value):
                raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-DIGEST")
        response = self._request("/v2/activation/finalize", {
            "activation_id": activation_id,
            "profile_digest": profile_digest,
            "operator_ack_digest": operator_ack_digest,
        })
        intent = self._parse_intent(response, expected_id=activation_id)
        if intent.state != "finalized":
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-NOT-FINALIZED")
        if intent.profile_digest != profile_digest or intent.operator_ack_digest != operator_ack_digest:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-FINALIZE-MISMATCH")
        return intent

    def _request(self, route: str, payload: Mapping) -> Any:
        try:
            return self._anchor._post(route, payload)
        except MonotonicAnchorUnavailable:
            # A timeout is an unknown outcome. The caller must read by the same ID.
            raise

    @staticmethod
    def _parse_intent(value: Any, *, expected_id: str) -> ActivationIntent:
        keys = {
            "activation_id", "state", "predecessors", "successors",
            "profile_digest", "operator_ack_digest",
        }
        if type(value) is not dict or set(value) != keys:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-INTENT-SHAPE")
        if _validate_id(value["activation_id"]) != expected_id:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-ID-MISMATCH")
        if type(value["state"]) is not str or value["state"] not in _STATES:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-STATE")
        predecessors, successors = value["predecessors"], value["successors"]
        if type(predecessors) is not dict or set(predecessors) != {"trust_manifest", "vsp_profile"}:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-PREDECESSORS")
        if type(successors) is not dict or set(successors) != {"trust_manifest", "vsp_profile"}:
            raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-SUCCESSORS")
        pred = {k: _record(v, nullable=True) for k, v in predecessors.items()}
        succ = {k: _record(v) for k, v in successors.items()}
        for key in ("profile_digest", "operator_ack_digest"):
            if type(value[key]) is not str or not _HEX64.fullmatch(value[key]):
                raise RemoteActivationProtocolError("HND-REMOTE-ACT-E-DIGEST")
        return ActivationIntent(
            expected_id, value["state"], pred["trust_manifest"], pred["vsp_profile"],
            succ["trust_manifest"], succ["vsp_profile"],
            value["profile_digest"], value["operator_ack_digest"],
        )
