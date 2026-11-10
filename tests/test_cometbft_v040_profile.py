import unittest

from hnd_v02.cometbft_v040_profile import (
    COMETBFT_V040_SOURCE_COMMIT, CometBFTProfileError, FieldRule,
    ProfileSchema, cometbft_v040_profile_digest, parse_cometbft_v040_profile,
)

def schema():
    return ProfileSchema(
        source_commit=COMETBFT_V040_SOURCE_COMMIT,
        complete=True,
        fields={
            "proxy_app": FieldRule(str, "shared", "tcp://127.0.0.1:26658", True),
            "rpc.laddr": FieldRule(str, "node_local", "tcp://127.0.0.1:26657", True),
            "consensus.timeout_commit": FieldRule(str, "shared", "1s", True),
            "p2p.max_num_inbound_peers": FieldRule(int, "shared", 40, True),
            "rpc.unsafe": FieldRule(bool, "shared", False, True),
        },
    )

class CometBFTProfileTests(unittest.TestCase):
    def test_defaults_are_resolved_only_from_pinned_schema(self):
        result = parse_cometbft_v040_profile(b"", schema()) if False else parse_cometbft_v040_profile(
            b'proxy_app = "tcp://127.0.0.1:26658"\n', schema()
        )
        self.assertEqual(result["consensus.timeout_commit"], "1s")
        self.assertEqual(result["rpc.unsafe"], False)

    def test_duplicate_keys_fail_closed(self):
        with self.assertRaises(CometBFTProfileError):
            parse_cometbft_v040_profile(b'proxy_app="a"\nproxy_app="b"\n', schema())

    def test_unknown_fields_fail_closed(self):
        with self.assertRaises(CometBFTProfileError):
            parse_cometbft_v040_profile(b'unknown_option=1\n', schema())

    def test_wrong_types_fail_closed(self):
        with self.assertRaises(CometBFTProfileError):
            parse_cometbft_v040_profile(b'proxy_app=true\n', schema())

    def test_bom_invalid_utf8_and_size_fail_closed(self):
        for raw in (b"\xef\xbb\xbfproxy_app='x'", b"\xff", b"x" * (1024 * 1024 + 1)):
            with self.subTest(raw=raw[:8]), self.assertRaises(CometBFTProfileError):
                parse_cometbft_v040_profile(raw, schema())

    def test_incomplete_or_wrong_source_schema_cannot_digest(self):
        incomplete = ProfileSchema("0" * 40, schema().fields, True)
        with self.assertRaises(CometBFTProfileError):
            parse_cometbft_v040_profile(b"", incomplete)
        not_complete = ProfileSchema(COMETBFT_V040_SOURCE_COMMIT, schema().fields, False)
        with self.assertRaises(CometBFTProfileError):
            cometbft_v040_profile_digest({}, not_complete)

    def test_node_local_fields_do_not_change_shared_digest(self):
        s = schema()
        a = parse_cometbft_v040_profile(b'rpc.laddr="tcp://127.0.0.1:26657"\n', s)
        b = parse_cometbft_v040_profile(b'rpc.laddr="tcp://127.0.0.1:36657"\n', s)
        self.assertEqual(cometbft_v040_profile_digest(a, s), cometbft_v040_profile_digest(b, s))

    def test_shared_field_changes_digest(self):
        s = schema()
        a = parse_cometbft_v040_profile(b'consensus.timeout_commit="1s"\n', s)
        b = parse_cometbft_v040_profile(b'consensus.timeout_commit="2s"\n', s)
        self.assertNotEqual(cometbft_v040_profile_digest(a, s), cometbft_v040_profile_digest(b, s))

    def test_integer_bool_confusion_is_rejected(self):
        with self.assertRaises(CometBFTProfileError):
            parse_cometbft_v040_profile(b'p2p.max_num_inbound_peers=true\n', schema())

if __name__ == "__main__":
    unittest.main()
