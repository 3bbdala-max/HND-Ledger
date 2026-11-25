import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.backup import BackupError, create_backup, verify_backup
from hnd_ledger.canonical import LOCAL_CHAIN_ID, signing_message
from hnd_ledger.crypto import address_from_public_key, generate_keypair, sign_transaction
from hnd_ledger.storage import SQLiteChainStore


def make_tx(sender_key, sender_pub, sender, recipient, amount, nonce):
    message = signing_message(
        LOCAL_CHAIN_ID, bytes.fromhex(sender), bytes.fromhex(recipient), amount, nonce
    )
    from hnd_ledger.ledger import Transaction
    return Transaction(
        LOCAL_CHAIN_ID, sender, recipient, amount, nonce,
        sender_pub.hex(), sign_transaction(sender_key, message)
    )


def _public_bytes(private_key):
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


@pytest.fixture
def backed_up_chain(tmp_path):
    sender_key, sender_pub = generate_keypair()
    _, recipient_pub = generate_keypair()
    sender = address_from_public_key(sender_pub)
    recipient = address_from_public_key(recipient_pub)
    balances = {sender: 1_000, recipient: 0}
    store = SQLiteChainStore(
        tmp_path / "live.sqlite3", LOCAL_CHAIN_ID, balances
    )
    # Keep a WAL-mode connection open so the committed block remains represented
    # in the live WAL while the online backup snapshot is taken.
    wal_keeper = store._connect()
    store.append_block([make_tx(sender_key, sender_pub, sender, recipient, 25, 0)], 1)
    signer = Ed25519PrivateKey.generate()
    destination = tmp_path / "backup-001"
    manifest = create_backup(store, destination, signer)
    wal_keeper.close()
    return destination, manifest, signer, store, balances


def _verify_args(manifest, signer, chain_id=LOCAL_CHAIN_ID):
    return {
        "trusted_public_key": _public_bytes(signer),
        "expected_chain_id": chain_id,
        "expected_genesis_hash": bytes.fromhex(manifest["genesis_hash_hex"]),
        "expected_tip_height": manifest["tip_height"],
        "expected_tip_block_hash": bytes.fromhex(manifest["tip_block_hash_hex"]),
    }


def test_signed_backup_captures_committed_wal_and_replays(backed_up_chain):
    directory, manifest, signer, store, balances = backed_up_chain
    verified = verify_backup(directory, **_verify_args(manifest, signer))
    assert verified == manifest
    assert manifest["tip_height"] == 1
    assert manifest["database_size"] > 0
    assert store.verify()


def test_backup_rejects_existing_destination(backed_up_chain):
    directory, _, _, store, _ = backed_up_chain
    with pytest.raises(BackupError, match="already exists"):
        create_backup(store, directory, Ed25519PrivateKey.generate())


def test_backup_rejects_manifest_tampering(backed_up_chain):
    directory, manifest, signer, _, _ = backed_up_chain
    path = directory / "manifest.json"
    changed = dict(manifest)
    changed["tip_height"] += 1
    path.write_text(
        json.dumps(changed, sort_keys=True, separators=(",", ":")),
        encoding="ascii",
    )
    with pytest.raises(BackupError, match="signature verification failed"):
        verify_backup(directory, **_verify_args(manifest, signer))


def test_backup_rejects_database_corruption(backed_up_chain):
    directory, manifest, signer, _, _ = backed_up_chain
    path = directory / "database.sqlite3"
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(BackupError, match="digest"):
        verify_backup(directory, **_verify_args(manifest, signer))


def test_backup_rejects_untrusted_signer(backed_up_chain):
    directory, manifest, _, _, _ = backed_up_chain
    with pytest.raises(BackupError, match="trusted key"):
        verify_backup(
            directory,
            **_verify_args(manifest, Ed25519PrivateKey.generate()),
        )


def test_backup_rejects_checkpoint_rollback_or_mismatch(backed_up_chain):
    directory, manifest, signer, _, _ = backed_up_chain
    args = _verify_args(manifest, signer)
    args["expected_tip_height"] = 0
    with pytest.raises(BackupError, match="tip height"):
        verify_backup(directory, **args)


def test_backup_rejects_unexpected_files(backed_up_chain):
    directory, manifest, signer, _, _ = backed_up_chain
    (directory / "extra.txt").write_text("unexpected")
    with pytest.raises(BackupError, match="unexpected files"):
        verify_backup(directory, **_verify_args(manifest, signer))



def test_backup_rejects_duplicate_manifest_keys(backed_up_chain):
    directory, manifest, signer, _, _ = backed_up_chain
    path = directory / "manifest.json"
    original = path.read_text(encoding="ascii")
    duplicate = original.replace(
        '"format":"HND-SQLITE-BACKUP-MANIFEST-V1",',
        '"format":"HND-SQLITE-BACKUP-MANIFEST-V1","format":"HND-SQLITE-BACKUP-MANIFEST-V1",',
        1,
    )
    path.write_text(duplicate, encoding="ascii")
    with pytest.raises(BackupError, match="duplicate JSON keys"):
        verify_backup(directory, **_verify_args(manifest, signer))


def test_backup_rejects_wrong_independent_chain_id(backed_up_chain):
    directory, manifest, signer, _, _ = backed_up_chain
    wrong_chain_id = bytes([1]) * 32
    with pytest.raises(BackupError, match="chain ID"):
        verify_backup(
            directory,
            **_verify_args(manifest, signer, chain_id=wrong_chain_id),
        )
