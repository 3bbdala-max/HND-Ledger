"""Wire-level tests for the CometBFT v0.40.0 ABCI gRPC adapter."""
import io
import json
import tempfile
import unittest
from threading import Event
from unittest.mock import patch
from google.protobuf.timestamp_pb2 import Timestamp
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import redirect_stderr

import grpc
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import hnd_v02.abci_app as abci_app_module
from hnd_v02.abci_app import (
    HNDABCIApplication,
    ABCIApplicationError,
    MAX_BLOCK_TRANSACTIONS,
    MIN_PROTO_TIMESTAMP_SECONDS,
    MAX_PROTO_TIMESTAMP_SECONDS,
)
from hnd_v02.cometbft_v040_server import (
    HNDCometBFTv040Servicer,
    start_grpc_server,
    main,
    _build_argument_parser,
    _validate_genesis_initialization_path,
    _validate_loopback_bind_address,
    MAX_QUERY_REQUEST_BYTES,
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

    def test_prepare_proposal_rejects_over_limit_before_application_copy(self):
        request = types_pb2.RequestPrepareProposal(
            max_tx_bytes=1024,
            txs=[b"x"] * (MAX_BLOCK_TRANSACTIONS + 1),
        )
        with patch.object(self.app, "prepare_proposal") as prepare:
            with self.assertRaisesRegex(
                RuntimeError, "transaction count exceeds application limit"
            ):
                self.servicer.PrepareProposal(request, self.context)
        prepare.assert_not_called()

    def test_process_proposal_rejects_over_limit_before_application_copy(self):
        request = types_pb2.RequestProcessProposal(
            txs=[b"x"] * (MAX_BLOCK_TRANSACTIONS + 1),
        )
        with patch.object(self.app, "process_proposal") as process:
            response = self.servicer.ProcessProposal(request, self.context)
        self.assertEqual(response.status, types_pb2.ResponseProcessProposal.REJECT)
        process.assert_not_called()

    def test_finalize_block_rejects_over_limit_before_application_copy(self):
        request = types_pb2.RequestFinalizeBlock(
            height=1,
            txs=[b"x"] * (MAX_BLOCK_TRANSACTIONS + 1),
        )
        with patch.object(self.app, "finalize_block") as finalize:
            with self.assertRaisesRegex(
                RuntimeError, "transaction count exceeds application limit"
            ):
                self.servicer.FinalizeBlock(request, self.context)
        finalize.assert_not_called()
        self.assertEqual(self.app.last_committed_height, 0)
        self.assertIsNone(self.app._pending)

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

    def test_evidence_query_is_bounded_and_paginated(self):
        self.app._evidence_journal = [
            {"evidence_id": f"{index:064x}", "type": 1}
            for index in range(3)
        ]
        request = canonical_json({"offset": 0, "limit": 1})
        response = self.servicer.Query(
            types_pb2.RequestQuery(path="/evidence", data=request),
            self.context,
        )
        self.assertEqual(response.code, 0)
        value = json.loads(response.value)
        self.assertEqual(response.height, 0)
        self.assertEqual(value["height"], response.height)
        self.assertEqual(len(value["evidence"]), 1)
        self.assertEqual(value["evidence"][0]["evidence_id"], f"{0:064x}")
        self.assertEqual(value["offset"], 0)
        self.assertEqual(value["limit"], 1)
        self.assertEqual(value["total_count"], 3)
        self.assertEqual(value["next_offset"], 1)
        self.assertEqual(value["next_cursor"], {"height": 0, "offset": 1})

        cursor_request = canonical_json({
            "height": value["next_cursor"]["height"],
            "offset": value["next_cursor"]["offset"],
            "limit": 2,
        })
        next_response = self.servicer.Query(
            types_pb2.RequestQuery(path="/evidence", data=cursor_request),
            self.context,
        )
        self.assertEqual(next_response.code, 0)
        next_value = json.loads(next_response.value)
        self.assertEqual(next_response.height, 0)
        self.assertEqual(
            [item["evidence_id"] for item in next_value["evidence"]],
            [f"{1:064x}", f"{2:064x}"],
        )
        self.assertIsNone(next_value["next_cursor"])

    def test_evidence_query_rejects_stale_committed_height_cursor(self):
        self.app._evidence_journal = [
            {"evidence_id": f"{index:064x}", "type": 1}
            for index in range(2)
        ]
        first = self.servicer.Query(
            types_pb2.RequestQuery(
                path="/evidence",
                data=canonical_json({"offset": 0, "limit": 1}),
            ),
            self.context,
        )
        cursor = json.loads(first.value)["next_cursor"]
        self.app.finalize_block(height=1, transactions=[], misbehavior=[])
        self.app.commit()

        stale = self.servicer.Query(
            types_pb2.RequestQuery(
                path="/evidence",
                data=canonical_json({
                    "height": cursor["height"],
                    "offset": cursor["offset"],
                    "limit": 1,
                }),
            ),
            self.context,
        )
        self.assertNotEqual(stale.code, 0)
        self.assertIn("evidence cursor height is stale", stale.log)
        self.assertEqual(stale.height, 1)

    def test_evidence_query_rejects_nonzero_offset_without_height_cursor(self):
        response = self.servicer.Query(
            types_pb2.RequestQuery(
                path="/evidence",
                data=canonical_json({"offset": 1, "limit": 1}),
            ),
            self.context,
        )
        self.assertNotEqual(response.code, 0)
        self.assertIn("requires a committed-height cursor", response.log)

    def test_evidence_query_snapshot_height_is_atomic_with_commit(self):
        self.app._evidence_journal = [
            {"evidence_id": f"{index:064x}", "type": 1}
            for index in range(2)
        ]
        self.app.finalize_block(height=1, transactions=[], misbehavior=[])
        copy_entered = Event()
        release_copy = Event()
        commit_started = Event()
        original_copy = abci_app_module._json_copy

        def pause_snapshot_copy(value):
            if not copy_entered.is_set():
                copy_entered.set()
                if not release_copy.wait(2):
                    raise TimeoutError("test did not release evidence snapshot copy")
            return original_copy(value)

        with patch("hnd_v02.abci_app._json_copy", side_effect=pause_snapshot_copy):
            with ThreadPoolExecutor(max_workers=2) as pool:
                query_future = pool.submit(
                    self.servicer.Query,
                    types_pb2.RequestQuery(
                        path="/evidence",
                        data=canonical_json({"offset": 0, "limit": 1}),
                    ),
                    self.context,
                )
                self.assertTrue(copy_entered.wait(1))
                def commit_pending():
                    commit_started.set()
                    return self.app.commit()
                commit_future = pool.submit(commit_pending)
                self.assertTrue(commit_started.wait(1))
                self.assertFalse(commit_future.done())
                release_copy.set()
                response = query_future.result(2)
                commit_future.result(2)

        self.assertEqual(response.code, 0)
        value = json.loads(response.value)
        self.assertEqual(response.height, 0)
        self.assertEqual(value["height"], 0)
        self.assertEqual(self.app.last_committed_height, 1)

    def test_account_query_height_uses_the_same_committed_snapshot(self):
        expected_view = {"balance": 123, "nonce": 4}
        with patch.object(
            self.app,
            "account_view_snapshot",
            return_value=(expected_view, 9),
        ):
            response = self.servicer.Query(
                types_pb2.RequestQuery(path="/account", data=self.alice_id.encode()),
                self.context,
            )
        self.assertEqual(response.code, 0)
        self.assertEqual(response.height, 9)
        self.assertEqual(json.loads(response.value)["balance"], 123)

    def test_query_rejects_oversized_request_data(self):
        response = self.servicer.Query(
            types_pb2.RequestQuery(
                path="/account",
                data=b"x" * (MAX_QUERY_REQUEST_BYTES + 1),
            ),
            self.context,
        )
        self.assertNotEqual(response.code, 0)
        self.assertEqual(response.log, "account query failed")

    def test_account_query_errors_are_generic_bounded_and_non_reflective(self):
        secret_identifier = b"customer-private-account-id-7f3a"
        requests = (
            secret_identifier,
            b"\xffprivate-account-payload",
            b"x" * (MAX_QUERY_REQUEST_BYTES + 1),
        )
        for raw in requests:
            with self.subTest(request_size=len(raw)):
                response = self.servicer.Query(
                    types_pb2.RequestQuery(path="/account", data=raw),
                    self.context,
                )
                self.assertNotEqual(response.code, 0)
                self.assertEqual(response.log, "account query failed")
                self.assertLessEqual(len(response.log), 64)
                self.assertNotIn(raw.hex(), response.log)
                try:
                    decoded = raw.decode("utf-8")
                except UnicodeDecodeError:
                    decoded = None
                if decoded is not None:
                    self.assertNotIn(decoded, response.log)

    def test_evidence_query_rejects_noncanonical_or_invalid_page_requests(self):
        for raw in (
            b'{"limit": 1, "offset": 0}',
            canonical_json({"offset": True, "limit": 1}),
            canonical_json({"offset": 0, "limit": 101}),
            canonical_json({"offset": 0, "limit": 1, "extra": 1}),
        ):
            response = self.servicer.Query(
                types_pb2.RequestQuery(path="/evidence", data=raw),
                self.context,
            )
            self.assertNotEqual(response.code, 0)

    def test_evidence_query_rejects_excessive_nesting_without_uncaught_error(self):
        raw = b"[" * 2000 + b"0" + b"]" * 2000
        response = self.servicer.Query(
            types_pb2.RequestQuery(path="/evidence", data=raw),
            self.context,
        )
        # The bounded query parser must reject this deeply nested non-object
        # without leaking an exception, whether rejection occurs at parse or schema validation.
        self.assertNotEqual(response.code, 0)
        self.assertTrue(response.log)

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

    def test_loopback_bind_policy_accepts_ipv4_and_ipv6_literals(self):
        for address in ("127.0.0.1:26658", "127.0.0.1:0", "[::1]:26658", "[::1]:0"):
            with self.subTest(address=address):
                _validate_loopback_bind_address(address)

    def test_loopback_bind_policy_rejects_non_loopback_and_hostnames(self):
        rejected = (
            "0.0.0.0:26658",
            "192.168.1.10:26658",
            "8.8.8.8:26658",
            "[::]:26658",
            "[2001:4860:4860::8888]:26658",
            "localhost:26658",
            "example.com:26658",
            "127.0.0.1",
            "127.0.0.1:not-a-port",
            "127.0.0.1:65536",
        )
        for address in rejected:
            with self.subTest(address=address):
                with self.assertRaises(ValueError):
                    _validate_loopback_bind_address(address)

    def test_start_grpc_server_rejects_non_loopback_before_binding(self):
        with self.assertRaisesRegex(ValueError, "restricted to loopback"):
            start_grpc_server(self.app, bind_address="0.0.0.0:26658")
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
            "protocol_config": {
                "network_id": self.config.network_id,
                "protocol_version": self.config.protocol_version,
                "max_amount": self.config.max_amount,
                "max_block_transactions": MAX_BLOCK_TRANSACTIONS,
            },
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
            validator=types_pb2.Validator(address=bytes.fromhex("ab" * 20), power=10),
            height=1,
            time=Timestamp(seconds=1793786400, nanos=0),
            total_voting_power=40,
        )
        self.servicer.FinalizeBlock(types_pb2.RequestFinalizeBlock(height=1), self.context)
        self.servicer.Commit(types_pb2.RequestCommit(), self.context)
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

    def test_finalize_block_rejects_out_of_range_protobuf_timestamps(self):
        # The evidence height must be a valid predecessor so this test reaches
        # protobuf timestamp validation rather than failing the height guard.
        self.servicer.FinalizeBlock(
            types_pb2.RequestFinalizeBlock(height=1), self.context
        )
        self.servicer.Commit(types_pb2.RequestCommit(), self.context)
        for seconds in (
            MIN_PROTO_TIMESTAMP_SECONDS - 1,
            MAX_PROTO_TIMESTAMP_SECONDS + 1,
            9_223_372_036_854_775_807,
        ):
            with self.subTest(seconds=seconds):
                item = types_pb2.Misbehavior(
                    type=types_pb2.DUPLICATE_VOTE,
                    validator=types_pb2.Validator(address=bytes.fromhex("ab" * 20), power=10),
                    height=1,
                    time=Timestamp(seconds=seconds, nanos=0),
                    total_voting_power=40,
                )
                with self.assertRaisesRegex(RuntimeError, "invalid misbehavior timestamp"):
                    self.servicer.FinalizeBlock(
                        types_pb2.RequestFinalizeBlock(height=2, misbehavior=[item]),
                        self.context,
                    )
                self.assertEqual(self.app.last_committed_height, 1)
                self.assertIsNone(self.app._pending)

    def test_evidence_timestamp_accepts_protobuf_range_endpoints(self):
        for seconds, nanos in (
            (MIN_PROTO_TIMESTAMP_SECONDS, 0),
            (MAX_PROTO_TIMESTAMP_SECONDS, 999_999_999),
        ):
            with self.subTest(seconds=seconds, nanos=nanos):
                item = {
                    "type": types_pb2.DUPLICATE_VOTE,
                    "validator_address": "ab" * 20,
                    "validator_power": 10,
                    "height": 1,
                    "time": f"unix:{seconds}:{nanos:09d}",
                    "total_voting_power": 40,
                }
                normalized = self.app._merge_evidence([], [item], block_height=2)
                self.assertEqual(normalized[0]["time"], item["time"])

    def test_evidence_timestamp_rejects_oversized_seconds_before_integer_parse(self):
        item = {
            "type": types_pb2.DUPLICATE_VOTE,
            "validator_address": "ab" * 20,
            "validator_power": 10,
            "height": 1,
            "time": f"unix:{'9' * 10_000}:000000000",
            "total_voting_power": 40,
        }
        with self.assertRaisesRegex(ABCIApplicationError, "invalid misbehavior timestamp"):
            self.app._merge_evidence([], [item], block_height=2)

    def test_server_cli_requires_an_explicit_startup_mode(self):
        base = [
            "--manifest", "manifest.json",
            "--genesis-hash", "a" * 64,
            "--network-id", "hnd-test",
            "--max-amount", "100",
            "--state-path", "state.json",
        ]
        with self.assertRaises(SystemExit):
            _build_argument_parser().parse_args(base)
        with self.assertRaises(SystemExit):
            _build_argument_parser().parse_args(
                base + ["--initialize-genesis", "--recovery"]
            )
        self.assertTrue(
            _build_argument_parser().parse_args(
                base + ["--initialize-genesis"]
            ).initialize_genesis
        )
        self.assertTrue(
            _build_argument_parser().parse_args(
                base + ["--recovery"]
            ).recovery
        )

    def test_genesis_initialization_rejects_an_existing_state_path(self):
        state_path = Path(self.temp.name) / "already-initialized.json"
        state_path.write_bytes(b"existing state")
        with self.assertRaisesRegex(ValueError, "requires an absent state path"):
            _validate_genesis_initialization_path(state_path)

    def test_genesis_initialization_rejects_a_dangling_state_symlink(self):
        target = Path(self.temp.name) / "missing-target.json"
        link = Path(self.temp.name) / "dangling-state-link.json"
        link.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "requires an absent state path"):
            _validate_genesis_initialization_path(link)

    def test_recovery_cli_rejects_missing_state_before_opening_listener(self):
        manifest_path = Path(self.temp.name) / "cli-manifest.json"
        manifest_path.write_bytes(canonical_json(self.manifest))
        missing_state = Path(self.temp.name) / "missing-established-state.json"
        argv = [
            "--manifest", str(manifest_path),
            "--genesis-hash", self.genesis_hash,
            "--network-id", self.config.network_id,
            "--max-amount", str(self.config.max_amount),
            "--state-path", str(missing_state),
            "--recovery",
        ]
        with patch("hnd_v02.cometbft_v040_server.start_grpc_server") as start_server:
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(argv)
            self.assertEqual(raised.exception.code, 2)
            start_server.assert_not_called()
        self.assertFalse(missing_state.exists())

    def test_genesis_cli_rejects_existing_state_before_opening_listener(self):
        manifest_path = Path(self.temp.name) / "unused-manifest.json"
        existing_state = Path(self.temp.name) / "existing-state.json"
        existing_state.write_bytes(b"existing state")
        argv = [
            "--manifest", str(manifest_path),
            "--genesis-hash", self.genesis_hash,
            "--network-id", self.config.network_id,
            "--max-amount", str(self.config.max_amount),
            "--state-path", str(existing_state),
            "--initialize-genesis",
        ]
        with patch("hnd_v02.cometbft_v040_server.start_grpc_server") as start_server:
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(argv)
            self.assertEqual(raised.exception.code, 2)
            start_server.assert_not_called()
        self.assertEqual(existing_state.read_bytes(), b"existing state")


    def test_standalone_cli_is_disabled_before_opening_listener(self):
        manifest_path = Path(self.temp.name) / "standalone-cli-manifest.json"
        manifest_path.write_bytes(canonical_json(self.manifest))
        state_path = Path(self.temp.name) / "standalone-cli-state.json"
        argv = [
            "--manifest", str(manifest_path),
            "--genesis-hash", self.genesis_hash,
            "--network-id", self.config.network_id,
            "--max-amount", str(self.config.max_amount),
            "--state-path", str(state_path),
            "--initialize-genesis",
        ]
        stderr = io.StringIO()
        with patch("hnd_v02.cometbft_v040_server.start_grpc_server") as start_server:
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    main(argv)
            self.assertEqual(raised.exception.code, 2)
            start_server.assert_not_called()
        self.assertIn("standalone ABCI startup is disabled", stderr.getvalue())
        self.assertFalse(state_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
