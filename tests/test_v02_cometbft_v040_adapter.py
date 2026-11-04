"""Wire-level tests for the CometBFT v0.40.0 ABCI gRPC adapter."""
import tempfile
import unittest
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import grpc
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.abci_app import HNDABCIApplication
from hnd_v02.cometbft_v040_server import (
    HNDCometBFTv040Servicer,
    start_grpc_server,
    types_pb2,
    types_pb2_grpc,
)
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import (
    ProtocolConfig,
    account_id_for_public_key,
    canonical_json,
    create_signed_transaction,
    public_key_b64,
)


class FakeContext:
    def abort(self, code, details):
        raise RuntimeError(f"{code}: {details}")


class TestCometBFTV040ABCIAdapter(unittest.TestCase):
    def setUp(self):
        self.config = ProtocolConfig("hnd-cometbft-v040-test", 2, 1_000_000)
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
        self.state_path = Path(self.temp.name) / "state.json"
        self.app = self.make_app()
        self.app.init_chain(
            chain_id=self.config.network_id,
            app_state_bytes=self.app.application_genesis_bytes(),
        )
        self.servicer = HNDCometBFTv040Servicer(self.app)
        self.context = FakeContext()

    def tearDown(self):
        self.temp.cleanup()

    def make_app(self):
        return HNDABCIApplication(
            config=self.config,
            manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
            state_path=self.state_path,
        )

    def tx_bytes(self, amount=10, nonce=0):
        tx = create_signed_transaction(
            self.alice_key,
            config=self.config,
            sender=self.alice_id,
            recipient=self.bob_id,
            amount=amount,
            nonce=nonce,
        )
        return canonical_json(tx)

    def test_echo_round_trip(self):
        response = self.servicer.Echo(types_pb2.RequestEcho(message="hello"), self.context)
        self.assertEqual(response.message, "hello")

    def test_info_maps_height_and_32_byte_app_hash(self):
        response = self.servicer.Info(types_pb2.RequestInfo(), self.context)
        self.assertEqual(response.last_block_height, 0)
        self.assertEqual(response.version, "HND-v0.2")
        self.assertEqual(len(response.last_block_app_hash), 32)

    def test_init_chain_maps_chain_id_and_app_hash(self):
        app = HNDABCIApplication(
            config=self.config,
            manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
            state_path=Path(self.temp.name) / "fresh.json",
        )
        servicer = HNDCometBFTv040Servicer(app)
        response = servicer.InitChain(
            types_pb2.RequestInitChain(
                chain_id=self.config.network_id,
                app_state_bytes=app.application_genesis_bytes(),
            ),
            self.context,
        )
        self.assertEqual(response.app_hash, bytes.fromhex(app.committed_state_hash))
        self.assertTrue(app.state_path.exists())

    def test_check_tx_accepts_valid_and_rejects_invalid(self):
        good = self.servicer.CheckTx(
            types_pb2.RequestCheckTx(tx=self.tx_bytes(), type=types_pb2.NEW),
            self.context,
        )
        bad = self.servicer.CheckTx(
            types_pb2.RequestCheckTx(tx=b"not-json", type=types_pb2.NEW),
            self.context,
        )
        self.assertEqual(good.code, 0)
        self.assertEqual(len(good.data), 32)
        self.assertNotEqual(bad.code, 0)

    def test_prepare_proposal_returns_valid_transactions_within_budget(self):
        first = self.tx_bytes(amount=10, nonce=0)
        second = self.tx_bytes(amount=15, nonce=1)
        response = self.servicer.PrepareProposal(
            types_pb2.RequestPrepareProposal(
                max_tx_bytes=len(first),
                txs=[first, second],
            ),
            self.context,
        )
        self.assertEqual(list(response.txs), [first])

    def test_process_proposal_maps_accept_and_reject(self):
        accepted = self.servicer.ProcessProposal(
            types_pb2.RequestProcessProposal(txs=[self.tx_bytes()]),
            self.context,
        )
        rejected = self.servicer.ProcessProposal(
            types_pb2.RequestProcessProposal(txs=[b"bad"]),
            self.context,
        )
        self.assertEqual(accepted.status, types_pb2.ResponseProcessProposal.ACCEPT)
        self.assertEqual(rejected.status, types_pb2.ResponseProcessProposal.REJECT)

    def test_finalize_and_commit_update_info_and_query(self):
        response = self.servicer.FinalizeBlock(
            types_pb2.RequestFinalizeBlock(height=1, txs=[self.tx_bytes(amount=125)]),
            self.context,
        )
        self.assertEqual(len(response.app_hash), 32)
        self.assertEqual(len(response.tx_results), 1)
        self.assertEqual(response.tx_results[0].code, 0)
        self.assertEqual(self.app.last_committed_height, 0)

        self.servicer.Commit(types_pb2.RequestCommit(), self.context)
        info = self.servicer.Info(types_pb2.RequestInfo(), self.context)
        self.assertEqual(info.last_block_height, 1)
        self.assertEqual(info.last_block_app_hash, response.app_hash)

        query = self.servicer.Query(
            types_pb2.RequestQuery(path="/account", data=self.alice_id.encode()),
            self.context,
        )
        self.assertEqual(query.code, 0)
        self.assertIn(b'"balance":599875', query.value)

    def test_query_height_and_unsupported_proof(self):
        height = self.servicer.Query(
            types_pb2.RequestQuery(path="/height"),
            self.context,
        )
        proof = self.servicer.Query(
            types_pb2.RequestQuery(path="/height", prove=True),
            self.context,
        )
        self.assertEqual(height.code, 0)
        self.assertEqual(height.value, b'{"height":0}')
        self.assertNotEqual(proof.code, 0)

    def test_vote_extensions_are_explicitly_disabled(self):
        extended = self.servicer.ExtendVote(types_pb2.RequestExtendVote(), self.context)
        accepted = self.servicer.VerifyVoteExtension(
            types_pb2.RequestVerifyVoteExtension(vote_extension=b""),
            self.context,
        )
        rejected = self.servicer.VerifyVoteExtension(
            types_pb2.RequestVerifyVoteExtension(vote_extension=b"unexpected"),
            self.context,
        )
        self.assertEqual(extended.vote_extension, b"")
        self.assertEqual(accepted.status, types_pb2.ResponseVerifyVoteExtension.ACCEPT)
        self.assertEqual(rejected.status, types_pb2.ResponseVerifyVoteExtension.REJECT)

    def test_snapshot_methods_are_explicitly_unsupported(self):
        self.assertEqual(
            len(self.servicer.ListSnapshots(types_pb2.RequestListSnapshots(), self.context).snapshots),
            0,
        )
        self.assertEqual(
            self.servicer.OfferSnapshot(
                types_pb2.RequestOfferSnapshot(), self.context
            ).result,
            types_pb2.ResponseOfferSnapshot.REJECT,
        )
        self.assertEqual(
            self.servicer.ApplySnapshotChunk(
                types_pb2.RequestApplySnapshotChunk(), self.context
            ).result,
            types_pb2.ResponseApplySnapshotChunk.ABORT,
        )
        self.assertEqual(
            self.servicer.LoadSnapshotChunk(
                types_pb2.RequestLoadSnapshotChunk(), self.context
            ).chunk,
            b"",
        )

    def test_app_mempool_rpc_is_not_enabled(self):
        inserted = self.servicer.InsertTx(
            types_pb2.RequestInsertTx(tx=self.tx_bytes()),
            self.context,
        )
        reaped = self.servicer.ReapTxs(types_pb2.RequestReapTxs(max_bytes=1000), self.context)
        self.assertNotEqual(inserted.code, 0)
        self.assertEqual(list(reaped.txs), [])

    def test_invalid_transaction_returns_nonzero_result_without_failing_block(self):
        response = self.servicer.FinalizeBlock(
            types_pb2.RequestFinalizeBlock(height=1, txs=[b"invalid"]),
            self.context,
        )
        self.assertEqual(len(response.tx_results), 1)
        self.assertNotEqual(response.tx_results[0].code, 0)
        self.assertEqual(response.tx_results[0].data, b"")
        self.assertEqual(len(response.app_hash), 32)
        committed = self.servicer.Commit(types_pb2.RequestCommit(), self.context)
        self.assertEqual(committed.retain_height, 0)
        self.assertEqual(self.app.last_committed_height, 1)

    def test_real_grpc_echo_and_info_with_concurrent_calls(self):
        server, port = start_grpc_server(
            self.app,
            bind_address="127.0.0.1:0",
            max_workers=8,
        )
        try:
            with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
                stub = types_pb2_grpc.ABCIStub(channel)
                self.assertEqual(stub.Echo(types_pb2.RequestEcho(message="wire")).message, "wire")

                def fetch_info(_):
                    return stub.Info(types_pb2.RequestInfo()).last_block_height

                with ThreadPoolExecutor(max_workers=4) as pool:
                    heights = list(pool.map(fetch_info, range(4)))
                self.assertEqual(heights, [0, 0, 0, 0])
        finally:
            server.stop(grace=0).wait()


    def test_init_chain_rejects_wrong_cometbft_chain_id(self):
        app = HNDABCIApplication(
            config=self.config,
            manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
            state_path=Path(self.temp.name) / "wrong-chain.json",
        )
        servicer = HNDCometBFTv040Servicer(app)
        with self.assertRaisesRegex(RuntimeError, "chain_id does not match"):
            servicer.InitChain(
                types_pb2.RequestInitChain(
                    chain_id="attacker-selected-chain",
                    app_state_bytes=app.application_genesis_bytes(),
                ),
                self.context,
            )
        self.assertFalse(app.state_path.exists())

    def test_init_chain_rejects_wrong_pinned_manifest_hash(self):
        app = HNDABCIApplication(
            config=self.config,
            manifest=self.manifest,
            expected_genesis_hash=self.genesis_hash,
            state_path=Path(self.temp.name) / "wrong-manifest-hash.json",
        )
        servicer = HNDCometBFTv040Servicer(app)
        wrong_payload = canonical_json({
            "genesis_hash": "0" * 64,
            "manifest": self.manifest,
        })
        with self.assertRaisesRegex(RuntimeError, "Genesis hash mismatch"):
            servicer.InitChain(
                types_pb2.RequestInitChain(
                    chain_id=self.config.network_id,
                    app_state_bytes=wrong_payload,
                ),
                self.context,
            )
        self.assertFalse(app.state_path.exists())

    def test_finalize_block_passes_misbehavior_into_persisted_hnd_evidence_journal(self):
        item = types_pb2.Misbehavior(
            type=types_pb2.DUPLICATE_VOTE,
            validator=types_pb2.Validator(address=b"\\xab" * 20, power=10),
            height=1,
            time=datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc),
            total_voting_power=40,
        )
        response = self.servicer.FinalizeBlock(
            types_pb2.RequestFinalizeBlock(height=2, misbehavior=[item]),
            self.context,
        )
        self.assertEqual(len(response.app_hash), 32)
        self.servicer.Commit(types_pb2.RequestCommit(), self.context)
        self.assertEqual(len(self.app.evidence_journal), 1)
        self.assertEqual(self.app.evidence_journal[0]["type"], types_pb2.DUPLICATE_VOTE)
        query = self.servicer.Query(types_pb2.RequestQuery(path="/evidence"), self.context)
        self.assertEqual(query.code, 0)
        self.assertIn(b"evidence", query.value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
