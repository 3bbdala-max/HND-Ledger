"""Tests for the side-effect-free VSP canonical envelope boundary."""
import base64
import hashlib
import unittest

import rfc8785

from hnd_v02.vsp_canonical import (
    VSPInputError,
    governance_signature_message,
    parse_vsp_envelope,
    profile_digest,
)


def _record(key_id: str) -> dict:
    return {
        "key_id": key_id,
        "algorithm": "ed25519",
        "signature": base64.b64encode(bytes(64)).decode("ascii"),
    }


def _valid_envelope() -> dict:
    return {
        "payload": {"schema": "hnd.validator-set-profile", "schema_version": 1},
        "signatures": [_record("gk1-" + "1" * 64), _record("gk1-" + "2" * 64)],
    }


class VSPCanonicalEnvelopeTests(unittest.TestCase):
    def test_accepts_exact_canonical_envelope(self):
        value = _valid_envelope()
        self.assertEqual(parse_vsp_envelope(rfc8785.dumps(value)), value)

    def test_rejects_duplicate_keys_before_object_construction(self):
        raw = (
            b'{"payload":{"schema":"x","schema":"y"},'
            b'"signatures":[' + rfc8785.dumps(_record("gk1-" + "1" * 64)) +
            b',' + rfc8785.dumps(_record("gk1-" + "2" * 64)) + b']}'
        )
        with self.assertRaisesRegex(VSPInputError, "VSP-E-DUPLICATE-KEY"):
            parse_vsp_envelope(raw)

    def test_rejects_noncanonical_whitespace_and_member_order(self):
        canonical = rfc8785.dumps(_valid_envelope())
        with self.assertRaisesRegex(VSPInputError, "VSP-E-NONCANONICAL-ENVELOPE"):
            parse_vsp_envelope(b" " + canonical)

    def test_rejects_bom_and_invalid_utf8(self):
        for raw, code in (
            (b"\xef\xbb\xbf{}", "VSP-E-UTF8-BOM"),
            (b'{"payload":"\xff","signatures":[]}', "VSP-E-INVALID-UTF8"),
        ):
            with self.subTest(code=code), self.assertRaisesRegex(VSPInputError, code):
                parse_vsp_envelope(raw)

    def test_rejects_float_exponent_negative_and_unsafe_integer_tokens(self):
        for token in (b"1.0", b"1e2", b"-1", b"9007199254740992"):
            raw = (
                b'{"payload":{"n":' + token + b'},"signatures":[' +
                rfc8785.dumps(_record("gk1-" + "1" * 64)) + b',' +
                rfc8785.dumps(_record("gk1-" + "2" * 64)) + b']}'
            )
            with self.subTest(token=token), self.assertRaises(VSPInputError):
                parse_vsp_envelope(raw)

    def test_rejects_duplicate_signer_and_wrong_signature_length(self):
        duplicate = _valid_envelope()
        duplicate["signatures"][1]["key_id"] = duplicate["signatures"][0]["key_id"]
        with self.assertRaisesRegex(VSPInputError, "VSP-E-DUPLICATE-SIGNER"):
            parse_vsp_envelope(rfc8785.dumps(duplicate))

        short = _valid_envelope()
        short["signatures"][1]["signature"] = base64.b64encode(bytes(63)).decode()
        with self.assertRaisesRegex(VSPInputError, "VSP-E-SIGNATURE-ENCODING"):
            parse_vsp_envelope(rfc8785.dumps(short))

    def test_rejects_signature_order_and_unknown_envelope_fields(self):
        value = _valid_envelope()
        value["signatures"].reverse()
        with self.assertRaisesRegex(VSPInputError, "VSP-E-SIGNATURE-ORDER"):
            parse_vsp_envelope(rfc8785.dumps(value))

        value = _valid_envelope()
        value["extra"] = True
        with self.assertRaisesRegex(VSPInputError, "VSP-E-ENVELOPE-SCHEMA"):
            parse_vsp_envelope(rfc8785.dumps(value))

    def test_profile_digest_and_authentication_preimage_are_domain_separated(self):
        payload = {"schema": "hnd.validator-set-profile", "schema_version": 1}
        expected = hashlib.sha256(b"HND-VSP-v1\x00" + rfc8785.dumps(payload)).digest()
        digest = profile_digest(payload)
        self.assertEqual(digest, expected)
        self.assertEqual(governance_signature_message(digest), b"HND-VSP-AUTH-v1\x00" + expected)
        with self.assertRaisesRegex(VSPInputError, "VSP-E-DIGEST-LENGTH"):
            governance_signature_message(b"short")


if __name__ == "__main__":
    unittest.main()
