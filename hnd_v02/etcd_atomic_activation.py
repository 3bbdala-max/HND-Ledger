"""etcd v3 atomic activation backend for HND Station 2.

The backend stores the active state (including both anti-rollback namespaces)
and the active profile artifact in one etcd transaction. It requires an HTTPS
etcd v3 JSON gateway. The independently operated monotonic witness described
in WP4.34 remains a separate required production control; this module does not
claim to prevent rollback of an entire restored etcd cluster.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import ssl
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlsplit

from hnd_v02.activation_witness import (
    compute_activation_digest, verify_witness_receipt,
)

from hnd_v02.activation_transaction import (
    ActivationState, ActivationTransactionError, _validate_state,
)


_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_MAX_SEQUENCE = (1 << 53) - 1
def _object_without_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


_STATE_FIELDS = {
    "trust_manifest_sequence", "trust_manifest_digest",
    "profile_sequence", "profile_digest", "activation_height",
    "operator_ack_set_sha256", "previous_trust_manifest_digest",
    "previous_profile_digest",
}


class EtcdAtomicActivationError(ActivationTransactionError):
    """The etcd backend could not safely read or commit activation state."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so credentials and activation writes stay on one origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_no_redirect(request, *, timeout: float, context: ssl.SSLContext | None):
    opener = urllib.request.build_opener(
        _NoRedirectHandler,
        urllib.request.HTTPSHandler(context=context),
    )
    return opener.open(request, timeout=timeout)


class EtcdV3AtomicActivationBackend:
    """Atomic etcd v3 implementation of AtomicActivationBackend.

    A linearizable range reads the current state. compare_and_activate then
    compares that exact serialized state (or key absence) and writes the
    successor state and profile artifact in one Raft-backed etcd transaction.
    The supplied profile_validator must enforce the pinned CometBFT schema and
    shared-profile digest; no permissive default is provided.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        profile_validator: Callable[[bytes, str], bool],
        key_prefix: str = "/hnd/station2",
        timeout: float = 5.0,
        ssl_context: ssl.SSLContext | None = None,
    ):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or not parsed.netloc
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-HTTPS-ENDPOINT")
        if not callable(profile_validator):
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-VALIDATOR-REQUIRED")
        if (type(key_prefix) is not str or not key_prefix.startswith("/")
                or key_prefix == "/" or key_prefix.endswith("/")
                or any(part in {"", ".", ".."} for part in key_prefix[1:].split("/"))):
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PREFIX")
        if type(timeout) not in (int, float) or timeout <= 0:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-TIMEOUT")
        self.endpoint = endpoint.rstrip("/")
        self.prefix = key_prefix
        self.timeout = float(timeout)
        self.profile_validator = profile_validator
        self.ssl_context = ssl_context

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")

    @staticmethod
    def _unb64(value: str) -> bytes:
        if type(value) is not str:
            raise ValueError("invalid etcd base64 value")
        return base64.b64decode(value.encode("ascii"), validate=True)

    @staticmethod
    def _encode_state(state: ActivationState) -> bytes:
        _validate_state(state)
        data = {
            "trust_manifest_sequence": state.trust_manifest_sequence,
            "trust_manifest_digest": state.trust_manifest_digest,
            "profile_sequence": state.profile_sequence,
            "profile_digest": state.profile_digest,
            "activation_height": state.activation_height,
            "operator_ack_set_sha256": state.operator_ack_set_sha256,
            "previous_trust_manifest_digest": state.previous_trust_manifest_digest,
            "previous_profile_digest": state.previous_profile_digest,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _decode_state(raw: bytes) -> ActivationState:
        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys)
            if type(data) is not dict or set(data) != _STATE_FIELDS:
                raise ValueError("state shape")
            state = ActivationState(**data)
            _validate_state(state)
            return state
        except Exception as exc:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-STATE-CORRUPT") from exc

    def _key(self, name: str) -> str:
        return self._b64((self.prefix + "/" + name).encode("utf-8"))

    def _post(self, route: str, payload: dict) -> dict:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint + route, data=body, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with _open_no_redirect(
                request, timeout=self.timeout, context=self.ssl_context
            ) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("etcd response too large")
            result = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys)
            if type(result) is not dict:
                raise ValueError("invalid etcd response")
            return result
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                UnicodeError, json.JSONDecodeError) as exc:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-REQUEST") from exc

    def _range(self, key: str) -> tuple[bytes | None, str | None]:
        result = self._post("/v3/kv/range", {"key": key})
        kvs = result.get("kvs", [])
        if type(kvs) is not list or len(kvs) > 1:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-RANGE-SHAPE")
        if not kvs:
            return None, None
        row = kvs[0]
        if type(row) is not dict or "value" not in row:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-RANGE-SHAPE")
        try:
            return self._unb64(row["value"]), row.get("mod_revision")
        except Exception as exc:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-RANGE-VALUE") from exc

    def _range_pair(self) -> tuple[bytes | None, bytes | None]:
        """Read active state and profile in one linearizable etcd transaction."""
        result = self._post("/v3/kv/txn", {
            "compare": [],
            "success": [
                {"request_range": {"key": self._key("active-state")}},
                {"request_range": {"key": self._key("active-profile")}},
            ],
            "failure": [],
        })
        responses = result.get("responses")
        if type(responses) is not list or len(responses) != 2:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-RANGE-PAIR-SHAPE")

        values: list[bytes | None] = []
        for item in responses:
            if type(item) is not dict or type(item.get("response_range")) is not dict:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-RANGE-PAIR-SHAPE")
            kvs = item["response_range"].get("kvs", [])
            if type(kvs) is not list or len(kvs) > 1:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-RANGE-PAIR-SHAPE")
            if not kvs:
                values.append(None)
                continue
            row = kvs[0]
            if type(row) is not dict or "value" not in row:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-RANGE-PAIR-SHAPE")
            try:
                values.append(self._unb64(row["value"]))
            except Exception as exc:
                raise EtcdAtomicActivationError(
                    "HND-ETCD-ACT-E-RANGE-PAIR-VALUE"
                ) from exc
        return values[0], values[1]

    def read_active_state(self) -> ActivationState | None:
        raw, profile = self._range_pair()
        if raw is None:
            if profile is not None:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-ORPHAN-PROFILE")
            return None
        state = self._decode_state(raw)
        if profile is None:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-MISSING")
        try:
            valid = self.profile_validator(profile, state.profile_digest)
        except Exception as exc:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-VALIDATION") from exc
        if valid is not True:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-DIGEST")
        return state

    def read_active_profile(self) -> bytes | None:
        raw, _ = self._range(self._key("active-profile"))
        return raw

    @staticmethod
    def _validate_successor(current: ActivationState | None,
                            proposed: ActivationState) -> None:
        _validate_state(proposed)
        if current is None:
            valid = (
                proposed.trust_manifest_sequence == 0
                and proposed.profile_sequence == 1
                and proposed.previous_trust_manifest_digest is None
                and proposed.previous_profile_digest is None
            )
            if not valid:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-BOOTSTRAP")
            return
        _validate_state(current)
        if proposed.trust_manifest_sequence != current.trust_manifest_sequence + 1:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-MANIFEST-SEQUENCE")
        if proposed.profile_sequence != current.profile_sequence + 1:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-SEQUENCE")
        if proposed.activation_height <= current.activation_height:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-HEIGHT")
        if proposed.previous_trust_manifest_digest != current.trust_manifest_digest:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-MANIFEST-PREDECESSOR")
        if proposed.previous_profile_digest != current.profile_digest:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-PREDECESSOR")

    def compare_and_activate(
        self,
        expected_current: ActivationState | None,
        new_state: ActivationState,
        profile_artifact: bytes,
    ) -> bool:
        if type(profile_artifact) is not bytes or not profile_artifact:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE")
        if expected_current is not None:
            _validate_state(expected_current)
        self._validate_successor(expected_current, new_state)
        try:
            valid = self.profile_validator(profile_artifact, new_state.profile_digest)
        except Exception as exc:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-VALIDATION") from exc
        if valid is not True:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-DIGEST")

        state_key = self._key("active-state")
        profile_key = self._key("active-profile")
        current_profile, _ = self._range(profile_key)
        if expected_current is None:
            if current_profile is not None:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-ORPHAN-PROFILE")
            compare = [
                {"key": state_key, "target": "CREATE", "create_revision": "0"},
                {"key": profile_key, "target": "CREATE", "create_revision": "0"},
            ]
        else:
            if current_profile is None:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-MISSING")
            try:
                current_profile_valid = self.profile_validator(
                    current_profile, expected_current.profile_digest
                )
            except Exception as exc:
                raise EtcdAtomicActivationError(
                    "HND-ETCD-ACT-E-CURRENT-PROFILE-VALIDATION"
                ) from exc
            if current_profile_valid is not True:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-CURRENT-PROFILE-DIGEST")
            compare = [
                {
                    "key": state_key, "target": "VALUE",
                    "value": self._b64(self._encode_state(expected_current)),
                },
                {
                    "key": profile_key, "target": "VALUE",
                    "value": self._b64(current_profile),
                },
            ]
        payload = {
            "compare": compare,
            "success": [
                {"request_put": {
                    "key": state_key,
                    "value": self._b64(self._encode_state(new_state)),
                }},
                {"request_put": {
                    "key": profile_key,
                    "value": self._b64(profile_artifact),
                }},
            ],
            "failure": [],
        }
        result = self._post("/v3/kv/txn", payload)
        # etcd's protobuf JSON gateway omits default-valued false booleans
        # unless EmitUnpopulated is enabled. A valid header-only TxnResponse
        # therefore means the compare failed, not that the response is malformed.
        succeeded = result.get(
            "succeeded", False if type(result.get("header")) is dict else None
        )
        if type(succeeded) is not bool:
            shape = ",".join(
                f"{key}:{type(value).__name__}" for key, value in sorted(result.items())
            )
            raise EtcdAtomicActivationError(
                "HND-ETCD-ACT-E-TXN-SHAPE:" + (shape or "empty-response")
            )
        return succeeded

    @staticmethod
    def _encode_anchor_record(sequence: int, digest: str) -> bytes:
        if (type(sequence) is not int or not 0 <= sequence <= _MAX_SEQUENCE
                or type(digest) is not str or not _HEX64.fullmatch(digest)):
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-ANCHOR-RECORD")
        return json.dumps(
            {"sequence": sequence, "digest": digest},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _validate_activation_id(activation_id: str) -> str:
        if (type(activation_id) is not str
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
                                    activation_id, re.ASCII)):
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-ACTIVATION-ID")
        return activation_id

    def read_activation_intent(self, activation_id: str) -> dict | None:
        """Read one immutable activation intent by its validated ID."""
        activation_id = self._validate_activation_id(activation_id)
        raw, _ = self._range(self._key("activation-intents/" + activation_id))
        if raw is None:
            return None
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys)
            base_fields = {
                "activation_id", "state", "activation_digest",
                "trust_manifest_sequence", "trust_manifest_digest",
                "profile_sequence", "profile_digest", "operator_ack_digest",
            }
            if type(value) is not dict or value.get("activation_id") != activation_id:
                raise ValueError("intent shape")
            if value.get("state") == "pending_witness":
                if set(value) != base_fields:
                    raise ValueError("pending intent shape")
            elif value.get("state") == "finalized":
                if set(value) != base_fields | {"witness_receipt", "witness_counter"}:
                    raise ValueError("finalized intent shape")
                if type(value["witness_receipt"]) is not dict:
                    raise ValueError("witness receipt shape")
                if (type(value["witness_counter"]) is not int
                        or not 1 <= value["witness_counter"] <= _MAX_SEQUENCE):
                    raise ValueError("witness counter")
            else:
                raise ValueError("intent state")
            if (type(value["activation_digest"]) is not str
                    or not _HEX64.fullmatch(value["activation_digest"])
                    or type(value["trust_manifest_sequence"]) is not int
                    or not 0 <= value["trust_manifest_sequence"] <= _MAX_SEQUENCE
                    or type(value["trust_manifest_digest"]) is not str
                    or not _HEX64.fullmatch(value["trust_manifest_digest"])
                    or type(value["profile_sequence"]) is not int
                    or not 0 <= value["profile_sequence"] <= _MAX_SEQUENCE
                    or type(value["profile_digest"]) is not str
                    or not _HEX64.fullmatch(value["profile_digest"])
                    or type(value["operator_ack_digest"]) is not str
                    or not _HEX64.fullmatch(value["operator_ack_digest"])):
                raise ValueError("intent fields")
            return value
        except Exception as exc:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-INTENT-CORRUPT") from exc


    def finalize_activation_intent(
        self,
        activation_id: str,
        witness_receipt: dict,
        *,
        trusted_witness_keys: dict[str, bytes],
        expected_witness_id: str,
        expected_config_epoch: int,
    ) -> dict:
        """Finalize one pending intent only after verifying its pinned witness ACK.

        The intent update is a compare-and-swap on the exact bytes read from etcd.
        Retries with the same verified receipt are idempotent; a different receipt
        or activation commitment is rejected. The witness remains an independent
        service and its anti-rollback properties are deployment responsibilities.
        """
        activation_id = self._validate_activation_id(activation_id)
        key = self._key("activation-intents/" + activation_id)
        raw, _ = self._range(key)
        if raw is None:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-INTENT-NOT-FOUND")
        try:
            intent = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_object_without_duplicate_keys,
            )
            if type(intent) is not dict or intent.get("activation_id") != activation_id:
                raise ValueError("intent shape")
            if intent.get("state") not in {"pending_witness", "finalized"}:
                raise ValueError("intent state")
            digest = intent.get("activation_digest")
            if type(digest) is not str or not _HEX64.fullmatch(digest):
                raise ValueError("intent digest")
            verified = verify_witness_receipt(
                witness_receipt,
                trusted_witness_keys=trusted_witness_keys,
                expected_activation_id=activation_id,
                expected_activation_digest=digest,
                expected_witness_id=expected_witness_id,
                expected_config_epoch=expected_config_epoch,
            )
        except Exception as exc:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-WITNESS-RECEIPT") from exc

        if intent["state"] == "finalized":
            if intent.get("witness_receipt") != witness_receipt:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-FINALIZE-CONFLICT")
            stored_counter = intent.get("witness_counter")
            if type(stored_counter) is not int or stored_counter != verified.counter:
                raise EtcdAtomicActivationError(
                    "HND-ETCD-ACT-E-FINALIZE-COUNTER-CONFLICT"
                )
            return intent

        finalized = dict(intent)
        finalized["state"] = "finalized"
        finalized["witness_receipt"] = witness_receipt
        finalized["witness_counter"] = verified.counter
        result = self._post("/v3/kv/txn", {
            "compare": [{
                "key": key, "target": "VALUE", "value": self._b64(raw),
            }],
            "success": [{
                "request_put": {
                    "key": key,
                    "value": self._b64(json.dumps(
                        finalized, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")),
                }
            }],
            "failure": [],
        })
        if type(result.get("succeeded")) is not bool:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-FINALIZE-TXN-SHAPE")
        if result["succeeded"]:
            return finalized
        # CAS may have succeeded while its response was lost, or another writer
        # may have finalized. Re-read the same ID and accept only exact receipt.
        observed_raw, _ = self._range(key)
        if observed_raw is None:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-FINALIZE-UNKNOWN")
        try:
            observed = json.loads(
                observed_raw.decode("utf-8"),
                object_pairs_hook=_object_without_duplicate_keys,
            )
        except Exception as exc:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-FINALIZE-CORRUPT") from exc
        if (type(observed) is dict and observed.get("state") == "finalized"
                and observed.get("activation_id") == activation_id
                and observed.get("activation_digest") == digest
                and observed.get("witness_receipt") == witness_receipt):
            return observed
        raise EtcdAtomicActivationError("HND-ETCD-ACT-E-FINALIZE-CAS-CONFLICT")

    def compare_and_activate_with_intent(
        self,
        expected_current: ActivationState | None,
        new_state: ActivationState,
        profile_artifact: bytes,
        *,
        activation_id: str,
    ) -> bool:
        """Atomically commit active state/profile, both etcd anti-rollback
        records, and an immutable pending-witness intent.

        The independent witness remains a separate trust domain and must
        acknowledge this exact activation digest before startup is authorized.
        """
        activation_id = self._validate_activation_id(activation_id)
        if type(profile_artifact) is not bytes or not profile_artifact:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE")
        if expected_current is not None:
            _validate_state(expected_current)
        self._validate_successor(expected_current, new_state)
        try:
            valid = self.profile_validator(profile_artifact, new_state.profile_digest)
        except Exception as exc:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-VALIDATION") from exc
        if valid is not True:
            raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-DIGEST")

        state_key = self._key("active-state")
        profile_key = self._key("active-profile")
        trust_key = self._key("monotonic/trust-manifest")
        vsp_key = self._key("monotonic/vsp-profile")
        intent_key = self._key("activation-intents/" + activation_id)
        current_profile, _ = self._range(profile_key)

        if expected_current is None:
            if current_profile is not None:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-ORPHAN-PROFILE")
            compare = [
                {"key": key, "target": "CREATE", "create_revision": "0"}
                for key in (state_key, profile_key, trust_key, vsp_key, intent_key)
            ]
        else:
            if current_profile is None:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-PROFILE-MISSING")
            try:
                current_valid = self.profile_validator(
                    current_profile, expected_current.profile_digest
                )
            except Exception as exc:
                raise EtcdAtomicActivationError(
                    "HND-ETCD-ACT-E-CURRENT-PROFILE-VALIDATION"
                ) from exc
            if current_valid is not True:
                raise EtcdAtomicActivationError("HND-ETCD-ACT-E-CURRENT-PROFILE-DIGEST")
            expected_trust = self._encode_anchor_record(
                expected_current.trust_manifest_sequence,
                expected_current.trust_manifest_digest,
            )
            expected_vsp = self._encode_anchor_record(
                expected_current.profile_sequence,
                expected_current.profile_digest,
            )
            compare = [
                {"key": state_key, "target": "VALUE",
                 "value": self._b64(self._encode_state(expected_current))},
                {"key": profile_key, "target": "VALUE",
                 "value": self._b64(current_profile)},
                {"key": trust_key, "target": "VALUE",
                 "value": self._b64(expected_trust)},
                {"key": vsp_key, "target": "VALUE",
                 "value": self._b64(expected_vsp)},
                {"key": intent_key, "target": "CREATE", "create_revision": "0"},
            ]

        new_state_raw = self._encode_state(new_state)
        activation_digest = compute_activation_digest(
            activation_id, new_state, profile_artifact
        )
        intent = {
            "activation_id": activation_id,
            "state": "pending_witness",
            "activation_digest": activation_digest,
            "trust_manifest_sequence": new_state.trust_manifest_sequence,
            "trust_manifest_digest": new_state.trust_manifest_digest,
            "profile_sequence": new_state.profile_sequence,
            "profile_digest": new_state.profile_digest,
            "operator_ack_digest": new_state.operator_ack_set_sha256,
        }
        trust_record = self._encode_anchor_record(
            new_state.trust_manifest_sequence, new_state.trust_manifest_digest
        )
        vsp_record = self._encode_anchor_record(
            new_state.profile_sequence, new_state.profile_digest
        )
        writes = (
            (state_key, new_state_raw),
            (profile_key, profile_artifact),
            (trust_key, trust_record),
            (vsp_key, vsp_record),
            (intent_key, json.dumps(
                intent, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")),
        )
        payload = {
            "compare": compare,
            "success": [
                {"request_put": {"key": key, "value": self._b64(value)}}
                for key, value in writes
            ],
            "failure": [],
        }
        result = self._post("/v3/kv/txn", payload)
        # etcd's protobuf JSON gateway omits default-valued false booleans
        # unless EmitUnpopulated is enabled. A valid header-only TxnResponse
        # therefore means the compare failed, not that the response is malformed.
        succeeded = result.get(
            "succeeded", False if type(result.get("header")) is dict else None
        )
        if type(succeeded) is not bool:
            shape = ",".join(
                f"{key}:{type(value).__name__}" for key, value in sorted(result.items())
            )
            raise EtcdAtomicActivationError(
                "HND-ETCD-ACT-E-TXN-SHAPE:" + (shape or "empty-response")
            )
        return succeeded
