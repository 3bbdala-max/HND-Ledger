"""Offline end-to-end verifier for a VSP activation evidence bundle."""
from __future__ import annotations
from typing import Mapping
from hnd_v02.operator_ack import verify_unanimous_operator_acks
from hnd_v02.trust_manifest import verify_vsp_with_trust_manifest

def verify_activation_bundle(vsp_raw: bytes, trust_manifest_raw: bytes,
        operator_acks_raw: bytes, *, context: Mapping,
        trusted_witness_keys: Mapping[str, bytes],
        expected_operator_keys: Mapping[str, bytes]) -> dict:
    """Require valid trust root, VSP governance signatures and unanimous acks.

    This is a pure preflight decision. It does not persist anti-rollback state,
    activate a profile, gate process startup, or contact operators.
    """
    verified = verify_vsp_with_trust_manifest(
        vsp_raw, trust_manifest_raw, context=context,
        trusted_witness_keys=trusted_witness_keys)
    vsp = verified["vsp"]
    acknowledgements = verify_unanimous_operator_acks(
        operator_acks_raw,
        expected_chain_id=context["chain_id"],
        expected_profile_sha256=vsp["profile_digest"],
        expected_activation_height=vsp["activation_height"],
        expected_operator_keys=expected_operator_keys)
    return {
        "trust_manifest_digest": verified["trust_manifest"]["manifest_digest"],
        "profile_digest": vsp["profile_digest"],
        "profile_sequence": vsp["profile_sequence"],
        "activation_height": vsp["activation_height"],
        "validator_count": vsp["validator_count"],
        "operator_ack_set_sha256": acknowledgements["ack_set_sha256"],
        "operator_count": acknowledgements["operator_count"],
        "unanimous_operator_approval": acknowledgements["unanimous"],
        "preflight_accepted": True,
    }
