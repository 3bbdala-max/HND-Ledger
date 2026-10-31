"""Tests for the HND v0.2 block and local chain reference."""
import copy
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.blocks import (
    BlockError,
    HNDChain,
    block_header_hash,
    transaction_merkle_root,
)
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import (
    ProtocolConfig,
    account_id_for_public_key,
    create_signed_transaction,
    public_key_b64,
)


class TestV02Blocks(unittest.TestCase):
    def setUp(self):
        self.config = ProtocolConfig("hnd-blocks-test", 2, 1_000_000)
        self.alice_key = Ed25519PrivateKey.generate()
        self.bob_key = Ed25519PrivateKey.generate()
        self.alice_public = public_key_b64(self.alice_key)
        self.bob_public = public_key_b64(self.bob_key)
        self.alice_id = account_id_for_public_key(self.alice_public, config=self.config)
        self.bob_id = account_id_for_public_key(self.bob_public, config=self.config)
        allocations = sorted([
            {"account_id": self.alice_id, "public_key": self.alice_public, "amount": 600_000},
            {"account_id": self.bob_id, "public_key": self.bob_public, "amount": 400_000},
        ], key=lambda item: item["account_id"])
        self.manifest = {
            "manifest_version": 1,
            "network_id": self.config.network_id,
            "protocol_version": 2,
            "total_supply": 1_000_000,
            "allocations": allocations,
        }
        self.genesis_hash = genesis_manifest_hash(self.manifest)
        self.chain = HNDChain(
            config=self.config, manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
        )

    def tx(self, amount=10, nonce=0):
        return create_signed_transaction(
            self.alice_key, config=self.config, sender=self.alice_id,
            recipient=self.bob_id, amount=amount, nonce=nonce,
        )

    def build(self, txs=None, timestamp=1):
        return self.chain.build_block(txs or [self.tx()], timestamp_ms=timestamp)

    def fresh_chain(self):
        return HNDChain(
            config=self.config, manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
        )

    def test_genesis_block_is_height_zero_and_commits_genesis_state(self):
        self.assertEqual(self.chain.height, 0)
        genesis = self.chain.blocks[0]
        self.assertEqual(genesis["header"]["previous_block_hash"], "0" * 64)
        self.assertEqual(genesis["header"]["transaction_count"], 0)
        self.assertEqual(genesis["header"]["genesis_hash"], self.genesis_hash)
        self.assertEqual(genesis["header"]["state_hash"], self.chain.ledger.snapshot()["state_hash"])

    def test_single_valid_block_updates_ledger_and_chain_head(self):
        tx = self.tx(amount=125)
        block = self.chain.build_block([tx], timestamp_ms=10)
        self.assertEqual(block["header"]["height"], 1)
        self.assertEqual(block["header"]["previous_block_hash"], self.chain.blocks[0]["block_hash"])
        self.assertEqual(self.chain.height, 1)
        self.assertEqual(self.chain.ledger.balances[self.alice_id], 599_875)
        self.assertEqual(self.chain.ledger.balances[self.bob_id], 400_125)
        self.assertEqual(self.chain.ledger.nonces[self.alice_id], 1)

    def test_block_can_contain_sequential_transactions(self):
        block = self.chain.build_block(
            [self.tx(10, 0), self.tx(20, 1)], timestamp_ms=10
        )
        self.assertEqual(block["header"]["transaction_count"], 2)
        self.assertEqual(self.chain.ledger.balances[self.alice_id], 599_970)
        self.assertEqual(self.chain.ledger.nonces[self.alice_id], 2)

    def test_invalid_transaction_rejects_entire_block_atomically(self):
        valid = self.tx(10, 0)
        invalid = self.tx(20, 0)
        before = self.chain.snapshot()
        with self.assertRaises(BlockError):
            self.chain.build_block([valid, invalid], timestamp_ms=10)
        self.assertEqual(self.chain.snapshot(), before)

    def test_duplicate_transaction_is_rejected(self):
        tx = self.tx()
        self.chain.build_block([tx], timestamp_ms=10)
        before = self.chain.snapshot()
        with self.assertRaises(BlockError):
            self.chain.build_block([tx], timestamp_ms=11)
        self.assertEqual(self.chain.snapshot(), before)

    def test_empty_and_oversized_blocks_rejected(self):
        with self.assertRaisesRegex(BlockError, "transaction count"):
            self.chain.build_block([], timestamp_ms=10)
        with self.assertRaisesRegex(BlockError, "transaction count"):
            self.chain.build_block([{}] * 1001, timestamp_ms=10)

    def test_timestamp_must_be_exact_nonnegative_integer(self):
        for value in (True, 1.0, "1", -1):
            with self.subTest(value=value):
                with self.assertRaises(BlockError):
                    self.chain.build_block([self.tx()], timestamp_ms=value)

    def test_timestamp_cannot_move_backwards(self):
        self.chain.build_block([self.tx(nonce=0)], timestamp_ms=10)
        tx = create_signed_transaction(
            self.alice_key, config=self.config, sender=self.alice_id,
            recipient=self.bob_id, amount=10, nonce=1,
        )
        before = self.chain.snapshot()
        with self.assertRaisesRegex(BlockError, "backwards"):
            self.chain.build_block([tx], timestamp_ms=9)
        self.assertEqual(self.chain.snapshot(), before)

    def test_merkle_root_commits_full_envelope_including_signature(self):
        tx_a = self.tx()
        tx_b = dict(tx_a)
        tx_b["signature"] = "A" * 88
        self.assertNotEqual(transaction_merkle_root([tx_a]), transaction_merkle_root([tx_b]))

    def test_merkle_root_empty_and_odd_leaf_count_are_deterministic(self):
        self.assertEqual(transaction_merkle_root([]), transaction_merkle_root([]))
        txs = [self.tx(1, 0), self.tx(2, 1), self.tx(3, 2)]
        self.assertEqual(transaction_merkle_root(txs), transaction_merkle_root(copy.deepcopy(txs)))

    def test_tampered_transaction_body_rejected_by_merkle_root(self):
        block = self.build()
        tampered = copy.deepcopy(block)
        tampered["transactions"][0]["amount"] = 11
        with self.assertRaisesRegex(BlockError, "transaction root mismatch"):
            self.fresh_chain().apply_block(tampered)

    def test_tampered_header_rejected_by_block_hash(self):
        block = self.build()
        tampered = copy.deepcopy(block)
        tampered["header"]["timestamp_ms"] = 2
        with self.assertRaisesRegex(BlockError, "block hash mismatch"):
            self.fresh_chain().apply_block(tampered)

    def test_wrong_parent_or_height_rejected(self):
        block = self.build()
        other_chain = HNDChain(
            config=self.config, manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
        )
        tampered = copy.deepcopy(block)
        tampered["header"]["previous_block_hash"] = "f" * 64
        tampered["block_hash"] = block_header_hash(tampered["header"])
        with self.assertRaisesRegex(BlockError, "previous block hash"):
            other_chain.apply_block(tampered)
        tampered = copy.deepcopy(block)
        tampered["header"]["height"] = 2
        tampered["block_hash"] = block_header_hash(tampered["header"])
        with self.assertRaisesRegex(BlockError, "height"):
            other_chain.apply_block(tampered)

    def test_wrong_network_version_and_genesis_rejected(self):
        block = self.build()
        for key, value, message in (
            ("network_id", "hnd-other", "network"),
            ("protocol_version", 3, "protocol version"),
            ("genesis_hash", "f" * 64, "genesis hash"),
        ):
            tampered = copy.deepcopy(block)
            tampered["header"][key] = value
            tampered["block_hash"] = block_header_hash(tampered["header"])
            with self.subTest(field=key):
                with self.assertRaisesRegex(BlockError, message):
                    self.fresh_chain().apply_block(tampered)

    def test_state_hash_mismatch_rejected(self):
        block = self.build()
        tampered = copy.deepcopy(block)
        tampered["header"]["state_hash"] = "f" * 64
        tampered["block_hash"] = block_header_hash(tampered["header"])
        with self.assertRaisesRegex(BlockError, "post-state hash"):
            self.fresh_chain().apply_block(tampered)

    def test_block_hash_format_and_schema_checked(self):
        block = self.build()
        tampered = copy.deepcopy(block)
        tampered["extra"] = True
        with self.assertRaisesRegex(BlockError, "schema"):
            self.chain.apply_block(tampered)
        tampered = copy.deepcopy(block)
        tampered["block_hash"] = "not-a-hash"
        with self.assertRaisesRegex(BlockError, "format"):
            self.fresh_chain().apply_block(tampered)

    def test_blocks_property_returns_detached_data(self):
        blocks = self.chain.blocks
        blocks[0]["header"]["height"] = 55
        self.assertEqual(self.chain.blocks[0]["header"]["height"], 0)

    def test_chain_snapshot_round_trip_replays_all_blocks(self):
        self.chain.build_block([self.tx(10, 0)], timestamp_ms=10)
        tx = self.tx(15, 1)
        self.chain.build_block([tx], timestamp_ms=20)
        snapshot = self.chain.snapshot()
        restored = HNDChain.restore(
            manifest=self.manifest, config=self.config,
            expected_genesis_hash=self.genesis_hash, snapshot=snapshot,
        )
        self.assertEqual(restored.snapshot(), snapshot)
        self.assertEqual(restored.ledger.balances, self.chain.ledger.balances)

    def test_chain_snapshot_tampering_rejected(self):
        self.build()
        snapshot = self.chain.snapshot()
        snapshot["blocks"][1]["header"]["timestamp_ms"] = 2
        with self.assertRaises(BlockError):
            HNDChain.restore(
                manifest=self.manifest, config=self.config,
                expected_genesis_hash=self.genesis_hash, snapshot=snapshot,
            )

    def test_chain_reordering_or_deletion_rejected(self):
        self.chain.build_block([self.tx(10, 0)], timestamp_ms=10)
        self.chain.build_block([self.tx(10, 1)], timestamp_ms=20)
        snapshot = self.chain.snapshot()
        snapshot["blocks"].reverse()
        with self.assertRaises(BlockError):
            HNDChain.restore(
                manifest=self.manifest, config=self.config,
                expected_genesis_hash=self.genesis_hash, snapshot=snapshot,
            )
        snapshot = self.chain.snapshot()
        del snapshot["blocks"][1]
        with self.assertRaisesRegex(BlockError, "head hash"):
            HNDChain.restore(
                manifest=self.manifest, config=self.config,
                expected_genesis_hash=self.genesis_hash, snapshot=snapshot,
            )

    def test_file_save_and_load(self):
        self.chain.build_block([self.tx(10, 0)], timestamp_ms=10)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chain.json"
            self.chain.save(path)
            restored = HNDChain.load(
                path, manifest=self.manifest, config=self.config,
                expected_genesis_hash=self.genesis_hash,
            )
        self.assertEqual(restored.snapshot(), self.chain.snapshot())

    def test_malformed_chain_file_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chain.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(BlockError, "cannot be decoded"):
                HNDChain.load(
                    path, manifest=self.manifest, config=self.config,
                    expected_genesis_hash=self.genesis_hash,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
