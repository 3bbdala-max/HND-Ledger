"""Isolated RFC 8785 compatibility spike; not a production VSP parser.

This module deliberately does not import or replace HND canonical_json.
"""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

import rfc8785


ROOT = Path(__file__).resolve().parents[1]
NODE_CROSSCHECK = ROOT / "scripts" / "vsp_jcs_crosscheck.cjs"


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-JSON numeric constant: {value}")


def parse_strict(raw: bytes):
    if type(raw) is not bytes:
        raise TypeError("input must be bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is forbidden")
    text = raw.decode("utf-8", errors="strict")
    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_constant,
    )

    def reject_surrogates(item):
        if isinstance(item, str):
            if any(0xD800 <= ord(char) <= 0xDFFF for char in item):
                raise ValueError("unpaired surrogate is forbidden")
        elif isinstance(item, list):
            for child in item:
                reject_surrogates(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                reject_surrogates(key)
                reject_surrogates(child)

    reject_surrogates(value)
    return value


class VSPJCSCompatibilitySpikeTests(unittest.TestCase):
    def test_python_candidate_known_canonical_bytes(self):
        raw = b'{"z":1,"a":4.50,"negativeZero":-0,"tiny":1e-7}'
        value = parse_strict(raw)
        self.assertEqual(
            rfc8785.dumps(value),
            b'{"a":4.5,"negativeZero":0,"tiny":1e-7,"z":1}',
        )

    def test_utf16_property_order_differs_from_python_codepoint_order(self):
        value = {"\ue000": 1, "\U00010000": 2}
        # JCS sorts property names by UTF-16 code units: D800 precedes E000.
        self.assertEqual(rfc8785.dumps(value), '{"\U00010000":2,"\ue000":1}'.encode())

    def test_reject_duplicate_members_at_every_depth(self):
        for raw in (
            b'{"a":1,"a":2}',
            b'{"outer":{"a":1,"a":2}}',
        ):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "duplicate"):
                parse_strict(raw)

    def test_reject_bom_invalid_utf8_nonstandard_constants_and_surrogates(self):
        invalid = (
            b"\xef\xbb\xbf{}",
            b'{"x":"\xff"}',
            b'{"x":NaN}',
            b'{"x":Infinity}',
            b'{"x":"\\ud800"}',
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises((ValueError, UnicodeDecodeError)):
                parse_strict(raw)

    def test_cross_language_canonical_bytes_match(self):
        if not os.environ.get("HND_JCS_NODE_MODULES"):
            self.skipTest("HND_JCS_NODE_MODULES is not configured")
        raw_inputs = [
            '{"z":1,"a":4.50,"negativeZero":-0,"tiny":1e-7}',
            '{"\ue000":1,"\U00010000":2}',
            '{"numbers":[333333333.33333329,1e30,4.50,2e-3,1e-27]}',
            '{"unicode":"\\u20ac\\ud83d\\ude00","control":"\\b\\t\\n"}',
            '{"nested":{"b":true,"a":null},"array":[0,false,"x"]}',
        ]
        python_outputs = [rfc8785.dumps(parse_strict(raw.encode())).decode("utf-8") for raw in raw_inputs]
        env = os.environ.copy()
        env["NODE_PATH"] = os.environ["HND_JCS_NODE_MODULES"]
        proc = subprocess.run(
            ["node", str(NODE_CROSSCHECK)],
            input=json.dumps(raw_inputs, ensure_ascii=True),
            text=True,
            capture_output=True,
            check=True,
            timeout=15,
            env=env,
        )
        javascript_outputs = json.loads(proc.stdout)
        self.assertEqual(javascript_outputs, python_outputs)


if __name__ == "__main__":
    unittest.main()
