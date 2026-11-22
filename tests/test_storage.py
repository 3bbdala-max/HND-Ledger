import sqlite3

import pytest

from hnd_ledger.canonical import LOCAL_CHAIN_ID, signing_message
from hnd_ledger.crypto import address_from_public_key, generate_keypair, sign_transaction
from hnd_ledger.ledger import Transaction
from hnd_ledger.storage import SQLiteChainStore, StorageError


@pytest.fixture
def chain_setup(tmp_path):
    sender_key, sender_pub = generate_keypair()
    _, recipient_pub = generate_keypair()
    sender = address_from_public_key(sender_pub)
    recipient = address_from_public_key(recipient_pub)
    balances = {sender: 1_000, recipient: 0}
    path = tmp_path / "hnd-chain.sqlite3"
    return path, sender_key, sender_pub, sender, recipient, balances


def make_tx(sender_key, sender_pub, sender, recipient, amount, nonce):
    message = signing_message(
        LOCAL_CHAIN_ID, bytes.fromhex(sender), bytes.fromhex(recipient), amount, nonce
    )
    return Transaction(
        LOCAL_CHAIN_ID, sender, recipient, amount, nonce,
        sender_pub.hex(), sign_transaction(sender_key, message)
    )


def test_sqlite_chain_survives_reopen_and_replays_multiple_blocks(chain_setup):
    path, key, pub, sender, recipient, balances = chain_setup
    first = SQLiteChainStore(path, LOCAL_CHAIN_ID, balances)
    block1 = first.append_block([make_tx(key, pub, sender, recipient, 40, 0)], 1)
    assert block1["height"] == 1
    assert first.verify()

    reopened = SQLiteChainStore(path, LOCAL_CHAIN_ID, balances)
    assert reopened.verify()
    state1, nonces1 = reopened.get_state()
    assert state1[sender] == 960
    assert state1[recipient] == 40
    assert nonces1[sender] == 1

    block2 = reopened.append_block([make_tx(key, pub, sender, recipient, 10, 1)], 2)
    assert block2["height"] == 2
    tip = reopened.get_tip()
    assert tip["height"] == 2
    assert tip["balances"][sender] == 950
    assert tip["balances"][recipient] == 50
    assert tip["nonces"][sender] == 2
    assert reopened.verify()


def test_rejected_block_is_not_partially_committed(chain_setup):
    path, key, pub, sender, recipient, balances = chain_setup
    store = SQLiteChainStore(path, LOCAL_CHAIN_ID, balances)
    invalid = make_tx(key, pub, sender, recipient, 10, 1)
    with pytest.raises(StorageError, match="append was rejected"):
        store.append_block([invalid], 1)
    assert store.get_tip()["height"] == 0
    assert store.get_state()[0] == balances
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0


def test_storage_rejects_different_genesis_on_reopen(chain_setup):
    path, _, _, _, _, balances = chain_setup
    SQLiteChainStore(path, LOCAL_CHAIN_ID, balances)
    changed = dict(balances)
    account = next(iter(changed))
    changed[account] -= 1
    with pytest.raises(StorageError, match="different or altered genesis"):
        SQLiteChainStore(path, LOCAL_CHAIN_ID, changed)


def test_replay_detects_tampered_persisted_block_hash(chain_setup):
    path, key, pub, sender, recipient, balances = chain_setup
    store = SQLiteChainStore(path, LOCAL_CHAIN_ID, balances)
    store.append_block([make_tx(key, pub, sender, recipient, 10, 0)], 1)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE blocks SET block_hash = ? WHERE height = 1", (bytes(32),)
        )
    assert not store.verify()
    with pytest.raises(StorageError):
        store.get_state()
