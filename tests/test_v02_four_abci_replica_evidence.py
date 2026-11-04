"""Four independent HND ABCI replicas: deterministic evidence handoff contract.

This is an ABCI fan-out test only. It deliberately does NOT claim to inject
equivocating votes through CometBFT P2P; that remains WP4.11's separate gate.
"""
import json
import tempfile
import unittest
from pathlib import Path

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.abci_app import HNDABCIApplication
from hnd_v02.cometbft_v040_server import (
    start_grpc_server,
    types_pb2,
    types_pb2_grpc,
)
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import ProtocolConfig, account_id_for_public_key, public_key_b64


class TestFourABCIReplicaEvidence(unittest.TestCase):
    def test_four_independent_grpc_replicas_commit_identical_evidence_and_hash(self):
        config = ProtocolConfig("hnd-four-abci-replica-test", 2, 1_000_000)
        keys = [Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()]
        allocations = [
            {
                "account_id": account_id_for_public_key(public_key_b64(key), config=config),
                "public_key": public_key_b64(key),
                "amount": amount,
            }
            for key, amount in zip(keys, (600_000, 400_000))
        ]
        allocations.sort(key=lambda item: item["account_id"])
        manifest = {
            "manifest_version": 1,
            "network_id": config.network_id,
            "protocol_version": config.protocol_version,
            "total_supply": 1_000_000,
            "allocations": allocations,
        }
        genesis_hash = genesis_manifest_hash(manifest)
        temp = tempfile.TemporaryDirectory()
        servers, channels, apps = [], [], []
        try:
            root = Path(temp.name)
            for index in range(4):
                app = HNDABCIApplication(
                    config=config,
                    manifest=manifest,
                    expected_genesis_hash=genesis_hash,
                    state_path=root / f"replica-{index}.json",
                )
                server, port = start_grpc_server(
                    app, bind_address="127.0.0.1:0", max_workers=8
                )
                channel = grpc.insecure_channel(f"127.0.0.1:{port}")
                grpc.channel_ready_future(channel).result(timeout=10)
                stub = types_pb2_grpc.ABCIStub(channel)
                initialized = stub.InitChain(
                    types_pb2.RequestInitChain(
                        chain_id=config.network_id,
                        app_state_bytes=app.application_genesis_bytes(),
                    ),
                    timeout=5,
                )
                self.assertEqual(initialized.app_hash, bytes.fromhex(app.committed_state_hash))
                servers.append(server)
                channels.append(channel)
                apps.append((app, stub))

            # Establish the infraction height before submitting its evidence.
            for app, stub in apps:
                stub.FinalizeBlock(types_pb2.RequestFinalizeBlock(height=1), timeout=5)
                stub.Commit(types_pb2.RequestCommit(), timeout=5)

            evidence = types_pb2.Misbehavior(
                type=types_pb2.DUPLICATE_VOTE,
                validator=types_pb2.Validator(address=bytes.fromhex("ab" * 20), power=10),
                height=1,
                time=Timestamp(seconds=1793786400, nanos=0),
                total_voting_power=40,
            )
            for app, stub in apps:
                result = stub.FinalizeBlock(
                    types_pb2.RequestFinalizeBlock(height=2, misbehavior=[evidence]),
                    timeout=5,
                )
                self.assertEqual(len(result.app_hash), 32)
                stub.Commit(types_pb2.RequestCommit(), timeout=5)

            journals, hashes, heights = [], [], []
            for app, stub in apps:
                query = stub.Query(types_pb2.RequestQuery(path="/evidence"), timeout=5)
                info = stub.Info(types_pb2.RequestInfo(), timeout=5)
                self.assertEqual(query.code, 0)
                journals.append(query.value)
                hashes.append(info.last_block_app_hash)
                heights.append(info.last_block_height)

            self.assertEqual(len(set(journals)), 1)
            self.assertEqual(len(set(hashes)), 1)
            self.assertEqual(set(heights), {2})
            decoded = json.loads(journals[0])
            self.assertEqual(len(decoded["evidence"]), 1)
            self.assertEqual(decoded["evidence"][0]["validator_address"], "ab" * 20)
            self.assertEqual(decoded["evidence"][0]["height"], 1)
            self.assertEqual(len(hashes[0]), 32)

            # Restart one application from its durable state and recheck the
            # committed evidence journal and composite application hash.
            original_hash = hashes[0]
            original_journal = journals[0]
            restarted = HNDABCIApplication(
                config=config,
                manifest=manifest,
                expected_genesis_hash=genesis_hash,
                state_path=root / "replica-0.json",
            )
            self.assertEqual(restarted.info()["last_block_height"], 2)
            self.assertEqual(restarted.info()["last_block_app_hash"], original_hash)
            self.assertEqual(
                json.dumps({"evidence": restarted.evidence_journal}, sort_keys=True, separators=(",", ":")).encode(),
                original_journal,
            )
        finally:
            for channel in channels:
                channel.close()
            for server in servers:
                server.stop(grace=0).wait()
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
