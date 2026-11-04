"""Deterministic four-replica HND state/app-hash convergence and divergence detection.

This is an application-layer test, not a consensus or Byzantine-fault proof.
It proves equal committed inputs yield equal application hashes and that a
same-height divergent valid transition is observable rather than hidden.
"""
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.abci_app import HNDABCIApplication
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import (
    ProtocolConfig,
    account_id_for_public_key,
    canonical_json,
    create_signed_transaction,
    public_key_b64,
)


def classify_replica_fingerprints(fingerprints):
    """Return a fail-closed classification for (height, 32-byte app_hash) pairs."""
    if not fingerprints or any(
        type(height) is not int or type(app_hash) is not bytes or len(app_hash) != 32
        for height, app_hash in fingerprints
    ):
        return "invalid_fingerprint"
    heights = {height for height, _ in fingerprints}
    if len(heights) != 1:
        return "height_mismatch"
    if len({app_hash for _, app_hash in fingerprints}) != 1:
        return "app_hash_mismatch"
    return "converged"


class TestFourReplicaStateConvergence(unittest.TestCase):
    def test_identical_inputs_converge_and_same_height_divergence_is_detected(self):
        config = ProtocolConfig("hnd-four-replica-state-test", 2, 1_000_000)
        alice_key = Ed25519PrivateKey.generate()
        bob_key = Ed25519PrivateKey.generate()
        alice_public = public_key_b64(alice_key)
        bob_public = public_key_b64(bob_key)
        alice_id = account_id_for_public_key(alice_public, config=config)
        bob_id = account_id_for_public_key(bob_public, config=config)
        allocations = sorted(
            [
                {"account_id": alice_id, "public_key": alice_public, "amount": 600_000},
                {"account_id": bob_id, "public_key": bob_public, "amount": 400_000},
            ],
            key=lambda item: item["account_id"],
        )
        manifest = {
            "manifest_version": 1,
            "network_id": config.network_id,
            "protocol_version": config.protocol_version,
            "total_supply": 1_000_000,
            "allocations": allocations,
        }
        genesis_hash = genesis_manifest_hash(manifest)
        temp = tempfile.TemporaryDirectory()
        try:
            root = Path(temp.name)
            apps = []
            for index in range(4):
                app = HNDABCIApplication(
                    config=config,
                    manifest=manifest,
                    expected_genesis_hash=genesis_hash,
                    state_path=root / f"replica-{index}.json",
                )
                app.init_chain(
                    chain_id=config.network_id,
                    app_state_bytes=app.application_genesis_bytes(),
                )
                apps.append(app)

            def signed_raw(amount, nonce):
                return canonical_json(
                    create_signed_transaction(
                        alice_key,
                        config=config,
                        sender=alice_id,
                        recipient=bob_id,
                        amount=amount,
                        nonce=nonce,
                    )
                )

            def commit_same_block(height, raw):
                results = [app.finalize_block(height=height, transactions=[raw]) for app in apps]
                self.assertEqual(len({result["app_hash"] for result in results}), 1)
                committed = [app.commit() for app in apps]
                self.assertEqual(len(set(committed)), 1)
                fingerprints = [
                    (app.info()["last_block_height"], app.info()["last_block_app_hash"])
                    for app in apps
                ]
                self.assertEqual(classify_replica_fingerprints(fingerprints), "converged")
                return fingerprints

            # Two deterministic blocks, including sequential nonce handling.
            commit_same_block(1, signed_raw(101, 0))
            commit_same_block(2, signed_raw(202, 1))

            expected_alice = 600_000 - 101 - 202
            expected_bob = 400_000 + 101 + 202
            for app in apps:
                self.assertEqual(app.account_view(alice_id)["balance"], expected_alice)
                self.assertEqual(app.account_view(bob_id)["balance"], expected_bob)
                self.assertEqual(
                    app.account_view(alice_id)["balance"] + app.account_view(bob_id)["balance"],
                    1_000_000,
                )

            # Restart an app and prove the committed fingerprint is durable.
            before_restart = (apps[1].info()["last_block_height"], apps[1].info()["last_block_app_hash"])
            restored = HNDABCIApplication(
                config=config,
                manifest=manifest,
                expected_genesis_hash=genesis_hash,
                state_path=root / "replica-1.json",
            )
            after_restart = (restored.info()["last_block_height"], restored.info()["last_block_app_hash"])
            self.assertEqual(after_restart, before_restart)

            # Deliberately valid but different transaction on replica 4 at the
            # same height/nonce. A comparator must report divergence, not pass.
            common_raw = signed_raw(5, 2)
            divergent_raw = signed_raw(6, 2)
            for app in apps[:3]:
                app.finalize_block(height=3, transactions=[common_raw])
                app.commit()
            apps[3].finalize_block(height=3, transactions=[divergent_raw])
            apps[3].commit()

            divergent_fingerprints = [
                (app.info()["last_block_height"], app.info()["last_block_app_hash"])
                for app in apps
            ]
            self.assertEqual({height for height, _ in divergent_fingerprints}, {3})
            self.assertEqual(
                classify_replica_fingerprints(divergent_fingerprints),
                "app_hash_mismatch",
            )
            self.assertEqual(len({app_hash for _, app_hash in divergent_fingerprints}), 2)
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
