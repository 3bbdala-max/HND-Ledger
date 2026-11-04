"""Tests for the HND v0.2 application lifecycle used by the ABCI adapter."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.abci_app import ABCIApplicationError, HNDABCIApplication
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import (
    ProtocolConfig,
    account_id_for_public_key,
    canonical_json,
    create_signed_transaction,
    public_key_b64,
)


class TestV02ABCIApplication(unittest.TestCase):
    def setUp(self):
        self.config = ProtocolConfig("hnd-abci-test", 2, 1_000_000)
        self.alice_key = Ed25519PrivateKey.generate()
        self.bob_key = Ed25519PrivateKey.generate()
        self.alice_public = public_key_b64(self.alice_key)
        self.bob_public = public_key_b64(self.bob_key)
        self.alice_id = account_id_for_public_key(self.alice_public, config=self.config)
        self.bob_id = account_id_for_public_key(self.bob_public, config=self.config)
        allocations = [
            {"account_id": self.alice_id, "public_key": self.alice_public, "amount": 600_000},
            {"account_id": self.bob_id, "public_key": self.bob_public, "amount": 400_000},
        ]
        allocations.sort(key=lambda item: item["account_id"])
        self.manifest = {
            "manifest_version": 1,
            "network_id": self.config.network_id,
            "protocol_version": self.config.protocol_version,
            "total_supply": 1_000_000,
            "allocations": allocations,
        }
        self.genesis_hash = genesis_manifest_hash(self.manifest)
        self.temp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp.name) / "hnd-app-state.json"
        self.app = self.make_app()
        self.app.init_chain(
            chain_id=self.config.network_id,
            app_state_bytes=self.app.application_genesis_bytes(),
        )

    def tearDown(self):
        self.temp.cleanup()

    def make_app(self):
        return HNDABCIApplication(
            config=self.config,
            manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
            state_path=self.state_path,
        )

    @staticmethod
    def reseal_store(payload):
        import hashlib
        unsigned = {key: value for key, value in payload.items() if key != "store_hash"}
        payload["store_hash"] = hashlib.sha256(
            b"HND-ABCI-STORE-V2" + bytes((92, 48)) + canonical_json(unsigned)
        ).hexdigest()

    def signed(self, amount=25, nonce=0):
        return create_signed_transaction(
            self.alice_key,
            config=self.config,
            sender=self.alice_id,
            recipient=self.bob_id,
            amount=amount,
            nonce=nonce,
        )

    def raw(self, tx=None, amount=25, nonce=0):
        return canonical_json(self.signed(amount=amount, nonce=nonce) if tx is None else tx)

    def test_init_chain_sets_genesis_height_and_app_hash(self):
        info = self.app.info()
        self.assertEqual(info["last_block_height"], 0)
        self.assertEqual(info["last_block_app_hash"], bytes.fromhex(self.app.committed_state_hash))
        self.assertTrue(self.state_path.exists())

    def test_init_chain_rejects_wrong_comet_chain_id(self):
        app = HNDABCIApplication(
            config=self.config, manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
            state_path=Path(self.temp.name) / "other.json",
        )
        with self.assertRaisesRegex(ABCIApplicationError, "chain_id"):
            app.init_chain(
                chain_id="other-network",
                app_state_bytes=app.application_genesis_bytes(),
            )

    def test_init_chain_rejects_unpinned_genesis_hash(self):
        payload = {
            "genesis_hash": "0" * 64,
            "manifest": self.manifest,
        }
        with self.assertRaisesRegex(ABCIApplicationError, "Genesis hash mismatch"):
            app = HNDABCIApplication(
                config=self.config, manifest=self.manifest,
                expected_genesis_hash=self.genesis_hash,
                state_path=Path(self.temp.name) / "bad-genesis.json",
            )
            app.init_chain(
                chain_id=self.config.network_id,
                app_state_bytes=canonical_json(payload),
            )

    def test_init_chain_is_idempotent_for_same_empty_genesis(self):
        before = self.state_path.read_bytes()
        self.app.init_chain(
            chain_id=self.config.network_id,
            app_state_bytes=self.app.application_genesis_bytes(),
        )
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_init_chain_rejects_noncanonical_app_state_bytes(self):
        raw = json.dumps(
            {"genesis_hash": self.genesis_hash, "manifest": self.manifest},
            sort_keys=True,
        ).encode("utf-8")
        with self.assertRaisesRegex(ABCIApplicationError, "non-canonical"):
            app = HNDABCIApplication(
                config=self.config, manifest=self.manifest,
                expected_genesis_hash=self.genesis_hash,
                state_path=Path(self.temp.name) / "noncanonical.json",
            )
            app.init_chain(chain_id=self.config.network_id, app_state_bytes=raw)

    def test_check_tx_updates_only_the_mempool_view(self):
        before = self.app.account_view(self.alice_id)
        response = self.app.check_tx(self.raw(amount=100, nonce=0))
        self.assertEqual(response["code"], 0)
        self.assertEqual(self.app.account_view(self.alice_id), before)
        self.assertEqual(self.app._mempool_ledger.account_view(self.alice_id)["next_nonce"], 1)
        self.assertEqual(self.app.last_committed_height, 0)

    def test_check_tx_accepts_sequential_pending_nonces(self):
        self.assertEqual(self.app.check_tx(self.raw(amount=10, nonce=0))["code"], 0)
        self.assertEqual(self.app.check_tx(self.raw(amount=20, nonce=1))["code"], 0)
        self.assertEqual(self.app._mempool_ledger.account_view(self.alice_id)["next_nonce"], 2)
        self.assertEqual(self.app.account_view(self.alice_id)["next_nonce"], 0)

    def test_failed_check_tx_does_not_change_mempool_view(self):
        before = self.app._mempool_ledger.snapshot()
        bad = self.raw(amount=10, nonce=1)
        self.assertNotEqual(self.app.check_tx(bad)["code"], 0)
        self.assertEqual(self.app._mempool_ledger.snapshot(), before)

    def test_duplicate_check_tx_is_rejected(self):
        raw = self.raw(amount=10, nonce=0)
        self.assertEqual(self.app.check_tx(raw)["code"], 0)
        self.assertNotEqual(self.app.check_tx(raw)["code"], 0)

    def test_check_tx_rejects_noncanonical_and_malformed_json(self):
        self.assertNotEqual(self.app.check_tx(b'{"amount": 1}')["code"], 0)
        self.assertNotEqual(self.app.check_tx(b'{"amount":NaN}')["code"], 0)
        self.assertNotEqual(self.app.check_tx(b'not-json')["code"], 0)

    def test_prepare_proposal_selects_sequential_valid_txs_and_skips_invalid(self):
        first = self.raw(amount=10, nonce=0)
        second = self.raw(amount=20, nonce=1)
        prepared = self.app.prepare_proposal(
            transactions=[first, b"not-json", second],
            max_tx_bytes=len(first) + len(second),
        )
        self.assertEqual(prepared, [first, second])
        self.assertEqual(self.app.account_view(self.alice_id)["next_nonce"], 0)
        self.assertEqual(self.app._mempool_ledger.account_view(self.alice_id)["next_nonce"], 0)

    def test_prepare_proposal_respects_byte_limit(self):
        first = self.raw(amount=10, nonce=0)
        second = self.raw(amount=20, nonce=1)
        prepared = self.app.prepare_proposal(
            transactions=[first, second],
            max_tx_bytes=len(first),
        )
        self.assertEqual(prepared, [first])
        self.assertEqual(self.app.prepare_proposal(transactions=[first], max_tx_bytes=0), [])

    def test_prepare_proposal_rejects_invalid_budget_and_list_types(self):
        with self.assertRaises(ABCIApplicationError):
            self.app.prepare_proposal(transactions=[], max_tx_bytes=True)
        with self.assertRaises(ABCIApplicationError):
            self.app.prepare_proposal(transactions=(), max_tx_bytes=10)

    def test_process_proposal_accepts_empty_block(self):
        self.assertEqual(
            self.app.process_proposal(transactions=[]),
            {"accepted": True, "reason": "ok"},
        )

    def test_process_proposal_accepts_valid_sequence_without_mutating_state(self):
        first = self.raw(amount=10, nonce=0)
        second = self.raw(amount=20, nonce=1)
        before = self.app._committed_ledger.snapshot()
        result = self.app.process_proposal(transactions=[first, second])
        self.assertTrue(result["accepted"])
        self.assertEqual(self.app._committed_ledger.snapshot(), before)
        self.assertEqual(self.app.last_committed_height, 0)

    def test_process_proposal_rejects_conflicting_nonce(self):
        first = self.raw(amount=10, nonce=0)
        conflicting = self.raw(amount=11, nonce=0)
        before = self.app._committed_ledger.snapshot()
        result = self.app.process_proposal(transactions=[first, conflicting])
        self.assertFalse(result["accepted"])
        self.assertEqual(self.app._committed_ledger.snapshot(), before)

    def test_process_proposal_rejects_invalid_signature_without_mutation(self):
        tx = self.signed()
        tx["signature"] = "AAAA"
        before = self.app._committed_ledger.snapshot()
        result = self.app.process_proposal(transactions=[canonical_json(tx)])
        self.assertFalse(result["accepted"])
        self.assertEqual(self.app._committed_ledger.snapshot(), before)

    def test_finalize_block_creates_pending_state_only(self):
        raw = self.raw(amount=100, nonce=0)
        before_store = self.state_path.read_bytes()
        before_info = self.app.info()
        result = self.app.finalize_block(height=1, transactions=[raw])
        self.assertEqual(result["height"], 1)
        self.assertEqual(len(result["app_hash"]), 32)
        self.assertEqual(self.app.info(), before_info)
        self.assertEqual(self.app.account_view(self.alice_id)["balance"], 600_000)
        self.assertEqual(self.state_path.read_bytes(), before_store)

    def test_finalize_block_marks_invalid_tx_and_continues_with_valid_transactions(self):
        invalid = self.raw(amount=100, nonce=5)
        valid = self.raw(amount=75, nonce=0)
        before_store = self.state_path.read_bytes()

        result = self.app.finalize_block(height=1, transactions=[invalid, valid])

        self.assertEqual([item["code"] for item in result["tx_results"]], [1, 0])
        self.assertEqual(result["tx_results"][0]["data"], "")
        self.assertIn("nonce", result["tx_results"][0]["log"])
        self.assertEqual(len(bytes.fromhex(result["tx_results"][1]["data"])), 32)
        self.assertEqual(self.app.account_view(self.alice_id)["balance"], 600_000)
        self.assertEqual(self.state_path.read_bytes(), before_store)

        self.app.commit()
        self.assertEqual(self.app.last_committed_height, 1)
        self.assertEqual(self.app.account_view(self.alice_id)["balance"], 599_925)
        self.assertEqual(self.app.account_view(self.alice_id)["next_nonce"], 1)

    def test_finalize_block_invalid_transaction_does_not_partially_change_candidate(self):
        valid = self.raw(amount=40, nonce=0)
        invalid = self.raw(amount=100, nonce=0)
        result = self.app.finalize_block(height=1, transactions=[valid, invalid])

        self.assertEqual([item["code"] for item in result["tx_results"]], [0, 1])
        self.assertIn("nonce", result["tx_results"][1]["log"])
        self.app.commit()
        self.assertEqual(self.app.account_view(self.alice_id)["balance"], 599_960)
        self.assertEqual(self.app.account_view(self.alice_id)["next_nonce"], 1)

    def test_finalize_block_requires_next_height_and_single_pending_block(self):
        with self.assertRaisesRegex(ABCIApplicationError, "height"):
            self.app.finalize_block(height=2, transactions=[])
        self.app.finalize_block(height=1, transactions=[])
        with self.assertRaisesRegex(ABCIApplicationError, "not been committed"):
            self.app.finalize_block(height=1, transactions=[])

    def test_empty_block_commits_without_changing_state_hash(self):
        before_hash = self.app.committed_state_hash
        result = self.app.finalize_block(height=1, transactions=[])
        committed_hash = self.app.commit()
        self.assertEqual(committed_hash, result["app_hash"])
        self.assertEqual(self.app.committed_state_hash, before_hash)
        self.assertEqual(self.app.last_committed_height, 1)

    def test_commit_persists_and_updates_committed_state(self):
        raw = self.raw(amount=125, nonce=0)
        result = self.app.finalize_block(height=1, transactions=[raw])
        returned_hash = self.app.commit()
        self.assertEqual(returned_hash, result["app_hash"])
        self.assertEqual(self.app.last_committed_height, 1)
        self.assertEqual(self.app.account_view(self.alice_id)["balance"], 599_875)
        restored = self.make_app()
        self.assertEqual(restored.info(), self.app.info())
        self.assertEqual(restored.account_view(self.alice_id), self.app.account_view(self.alice_id))

    def test_commit_fsyncs_state_file_and_parent_directory(self):
        self.app.finalize_block(height=1, transactions=[self.raw(amount=10, nonce=0)])
        real_fsync = __import__("os").fsync
        with patch("hnd_v02.abci_app.os.fsync", wraps=real_fsync) as fsync_spy:
            self.app.commit()
        expected_calls = 2 if __import__("os").name == "posix" else 1
        self.assertEqual(fsync_spy.call_count, expected_calls)

    def test_commit_without_finalize_is_rejected(self):
        with self.assertRaisesRegex(ABCIApplicationError, "no finalized block"):
            self.app.commit()

    def test_restart_discards_uncommitted_finalized_state(self):
        self.app.finalize_block(height=1, transactions=[self.raw(amount=25, nonce=0)])
        restarted = self.make_app()
        self.assertEqual(restarted.last_committed_height, 0)
        self.assertEqual(restarted.account_view(self.alice_id)["balance"], 600_000)
        self.assertEqual(restarted.info()["last_block_app_hash"], bytes.fromhex(restarted.committed_state_hash))

    def test_commit_storage_failure_leaves_old_committed_state(self):
        old_bytes = self.state_path.read_bytes()
        old_info = self.app.info()
        self.app.finalize_block(height=1, transactions=[self.raw(amount=50, nonce=0)])
        with patch("hnd_v02.abci_app.os.replace", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                self.app.commit()
        self.assertEqual(self.state_path.read_bytes(), old_bytes)
        self.assertEqual(self.app.info(), old_info)
        # Pending state remains available for a safe retry after the storage fault clears.
        self.assertEqual(self.app.commit(), bytes.fromhex(self.app.committed_state_hash))

    def test_restart_after_durable_replace_recovers_committed_height_and_hash(self):
        raw = self.raw(amount=60, nonce=0)
        finalized = self.app.finalize_block(height=1, transactions=[raw])
        real_replace = __import__("os").replace

        def replace_then_simulate_process_loss(source, destination):
            real_replace(source, destination)
            raise OSError("simulated process loss after durable rename")

        with patch("hnd_v02.abci_app.os.replace", side_effect=replace_then_simulate_process_loss):
            with self.assertRaisesRegex(OSError, "simulated process loss"):
                self.app.commit()

        self.assertEqual(self.app.last_committed_height, 0)
        restarted = self.make_app()
        self.assertEqual(restarted.last_committed_height, 1)
        self.assertEqual(restarted.info()["last_block_app_hash"], finalized["app_hash"])
        self.assertEqual(restarted.account_view(self.alice_id)["balance"], 599_940)
        self.assertEqual(restarted.account_view(self.alice_id)["next_nonce"], 1)

    def test_mempool_view_resets_to_committed_state_after_commit(self):
        raw = self.raw(amount=25, nonce=0)
        self.assertEqual(self.app.check_tx(raw)["code"], 0)
        self.app.finalize_block(height=1, transactions=[raw])
        self.app.commit()
        self.assertEqual(self.app._mempool_ledger.account_view(self.alice_id)["next_nonce"], 1)
        self.assertNotEqual(self.app.check_tx(raw, recheck=True)["code"], 0)

    def test_distinct_proposals_do_not_leak_candidate_state(self):
        option_a = self.raw(amount=10, nonce=0)
        option_b = self.raw(amount=20, nonce=0)
        self.assertTrue(self.app.process_proposal(transactions=[option_a])["accepted"])
        self.assertTrue(self.app.process_proposal(transactions=[option_b])["accepted"])
        self.assertEqual(self.app.account_view(self.alice_id)["next_nonce"], 0)
        self.app.finalize_block(height=1, transactions=[option_a])
        self.app.commit()
        self.assertFalse(self.app.process_proposal(transactions=[option_b])["accepted"])

    def test_corrupted_persisted_balances_are_rejected_on_restart(self):
        self.app.finalize_block(height=1, transactions=[self.raw(amount=100, nonce=0)])
        self.app.commit()
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        payload["ledger_snapshot"]["balances"][self.alice_id] -= 1
        payload["ledger_snapshot"]["balances"][self.bob_id] += 1
        self.reseal_store(payload)
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ABCIApplicationError, "snapshot failed verification"):
            self.make_app()

    def test_corrupted_application_hash_is_rejected_on_restart(self):
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        payload["app_hash"] = "0" * 64
        self.reseal_store(payload)
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ABCIApplicationError, "app hash mismatch"):
            self.make_app()

    def test_duplicate_json_keys_in_persisted_store_are_rejected(self):
        raw = self.state_path.read_text(encoding="utf-8")
        raw = raw.replace(
            '"last_committed_height": 0,',
            '"last_committed_height": 0,' + chr(10) + '  "last_committed_height": 0,',
            1,
        )
        self.state_path.write_text(raw, encoding="utf-8")
        with self.assertRaisesRegex(ABCIApplicationError, "cannot be decoded"):
            self.make_app()

    def test_recovery_metadata_tampering_is_rejected_by_store_hash(self):
        self.app.finalize_block(height=1, transactions=[self.raw(amount=40, nonce=0)])
        self.app.commit()
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        payload["last_committed_height"] = 99
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ABCIApplicationError, "store hash mismatch"):
            self.make_app()

    def test_store_hash_must_be_lowercase_sha256_hex(self):
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        payload["store_hash"] = "Z" * 64
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ABCIApplicationError, "store hash"):
            self.make_app()

    def test_transaction_count_limit_is_enforced(self):
        result = self.app.process_proposal(transactions=[b"x"] * 1001)
        self.assertFalse(result["accepted"])
        self.assertIn("count", result["reason"])

    def test_account_query_never_exposes_mempool_or_candidate_state(self):
        raw = self.raw(amount=250, nonce=0)
        self.app.check_tx(raw)
        self.app.finalize_block(height=1, transactions=[raw])
        self.assertEqual(self.app.account_view(self.alice_id)["balance"], 600_000)


    def test_evidence_journal_starts_empty(self):
        self.assertEqual(self.app.evidence_journal, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
