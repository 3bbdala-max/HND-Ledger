import unittest

import hashlib
import json

from hnd_v02.cometbft_v040_profile import (
    COMETBFT_V040_SOURCE_COMMIT,
    CometBFTProfileError,
    FieldRule,
    ProfileSchema,
    cometbft_v040_profile_digest,
    load_cometbft_v040_profile_schema,
    parse_cometbft_v040_profile,
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
            "rpc.cors_allowed_origins": FieldRule(list, "shared", [], True, item_type=str),
            "p2p.bootstrap_peers": FieldRule(list, "node_local", [], True, item_fields={
                "id": FieldRule(str, "node_local"),
                "host": FieldRule(str, "node_local"),
            }),
        },
    )

def source_inventory_fixture(*, reviewed=True, complete_scopes=True, bind_policy=True):
    inventory = {
        "schema_version": 1,
        "source_commit": COMETBFT_V040_SOURCE_COMMIT,
        "root_type": "config.Config",
        "rendered_template_sha256": "a" * 64,
        "template_complete": True,
        "fields": [
        "fields": [
            {
                "path": "statesync.chunk_fetchers",
                "go_path": "StateSync.ChunkFetchers",
                "go_type": "int32",
                "toml_type": "string",
                "default": "4",
                "has_default": True,
            },
            {
                "path": "p2p.libp2p.bootstrap_peers",
                "go_path": "P2P.LibP2PConfig.BootstrapPeers",
                "go_type": "[]config.LibP2PBootstrapPeer",
                "toml_type": "array",
                "default": [],
                "has_default": True,
                "item_type": "table",
                "item_fields": [
                    {
                        "name": "host",
                        "go_path": "P2P.LibP2PConfig.BootstrapPeers[].Host",
                        "go_type": "string",
                        "required": True,
                    },
                    {
                        "name": "id",
                        "go_path": "P2P.LibP2PConfig.BootstrapPeers[].ID",
                        "go_type": "string",
                        "required": True,
                    },
                    {
                        "name": "private",
                        "go_path": "P2P.LibP2PConfig.BootstrapPeers[].Private",
                        "go_type": "bool",
                        "required": False,
                        "default": False,
                    },
                ],
            },
        ],
            {
                "path": "proxy_app",
                "go_path": "BaseConfig.ProxyApp",
                "go_type": "string",
                "toml_type": "string",
                "default": "tcp://127.0.0.1:26658",
                "has_default": True,
            },
        ],
        "tables": ["p2p", "p2p.libp2p", "statesync"],
        "excluded_source_fields": [],
    }
    inventory_raw = json.dumps(
        inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    scopes = {
        "proxy_app": "shared",
        "statesync.chunk_fetchers": "node_local",
    }
    if complete_scopes:
        scopes["p2p.libp2p.bootstrap_peers"] = "node_local"
    policy = {
        "schema_version": 1,
        "source_commit": COMETBFT_V040_SOURCE_COMMIT,
        "inventory_sha256": (
            hashlib.sha256(inventory_raw).hexdigest() if bind_policy else "0" * 64
        ),
        "reviewed": reviewed,
        "review_reference": "test-fixture: synthetic profile-scope review",
        "scopes": scopes,
    }
    policy_raw = json.dumps(
        policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return inventory_raw, policy_raw


class CometBFTProfileTests(unittest.TestCase):
    def test_source_inventory_loader_preserves_toml_types_and_array_table_defaults(self):
        inventory_raw, policy_raw = source_inventory_fixture()
        loaded = load_cometbft_v040_profile_schema(inventory_raw, policy_raw)
        self.assertTrue(loaded.complete)
        self.assertTrue(loaded.scope_policy_reviewed)
        self.assertEqual(loaded.inventory_sha256, hashlib.sha256(inventory_raw).hexdigest())

        normalized = parse_cometbft_v040_profile(
            b'proxy_app = "tcp://127.0.0.1:26658"\n'
            b'[statesync]\nchunk_fetchers = "9"\n'
            b'[[p2p.libp2p.bootstrap_peers]]\nhost = "node.example:26656"\nid = "peer-id"\n',
            loaded,
        )
        self.assertEqual(normalized["statesync.chunk_fetchers"], "9")
        self.assertEqual(
            normalized["p2p.libp2p.bootstrap_peers"],
            [{
                "host": "node.example:26656",
                "id": "peer-id",
                "private": False,
            }],
        )

    def test_scope_policy_must_be_reviewed_complete_and_inventory_bound(self):
        inventory_raw, unreviewed_raw = source_inventory_fixture(reviewed=False)
        unreviewed = load_cometbft_v040_profile_schema(inventory_raw, unreviewed_raw)
        self.assertFalse(unreviewed.complete)
        with self.assertRaisesRegex(CometBFTProfileError, "complete schema"):
            parse_cometbft_v040_profile(b'proxy_app = "tcp://127.0.0.1:26658"\n', unreviewed)

        inventory_raw, partial_raw = source_inventory_fixture(complete_scopes=False)
        partial = load_cometbft_v040_profile_schema(inventory_raw, partial_raw)
        self.assertFalse(partial.complete)

        inventory_raw, unbound_raw = source_inventory_fixture(bind_policy=False)
        unbound = load_cometbft_v040_profile_schema(inventory_raw, unbound_raw)
        self.assertFalse(unbound.complete)

    def test_source_inventory_rejects_wrong_source_and_duplicate_json_keys(self):
        inventory_raw, policy_raw = source_inventory_fixture()
        inventory = json.loads(inventory_raw)
        inventory["source_commit"] = "0" * 40
        wrong_source = json.dumps(inventory).encode("utf-8")
        with self.assertRaises(CometBFTProfileError):
            load_cometbft_v040_profile_schema(wrong_source, policy_raw)

        with self.assertRaises(CometBFTProfileError):
            load_cometbft_v040_profile_schema(
                b'{"schema_version":1,"schema_version":1}',
                policy_raw,
            )

    def test_defaults_are_resolved_only_from_pinned_schema(self):
        result = parse_cometbft_v040_profile(
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

    def test_unknown_empty_tables_fail_closed(self):
        with self.assertRaises(CometBFTProfileError):
            parse_cometbft_v040_profile(b'[unknown_section]\n', schema())

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

    def test_array_item_types_and_array_table_fields_are_strict(self):
        s = schema()
        with self.assertRaises(CometBFTProfileError):
            parse_cometbft_v040_profile(b'rpc.cors_allowed_origins=[1]\n', s)
        with self.assertRaises(CometBFTProfileError):
            parse_cometbft_v040_profile(b'[[p2p.bootstrap_peers]]\nid="peer"\nhost="node:26656"\nextra=true\n', s)

    def test_integer_bool_confusion_is_rejected(self):
        with self.assertRaises(CometBFTProfileError):
            parse_cometbft_v040_profile(b'p2p.max_num_inbound_peers=true\n', schema())

if __name__ == "__main__":
    unittest.main()
