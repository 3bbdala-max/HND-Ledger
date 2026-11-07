import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.chain import ChainError, LocalChain, state_commitment
from hnd_ledger.protocol import account_id, create_transaction
from hnd_ledger.state import LedgerState


def account(key):
    return account_id(key.public_key().public_bytes_raw())



def test_state_commitment_covers_chain_id_and_supply_cap():
    key = Ed25519PrivateKey.generate()
    account_id_value = account(key)
    base = LedgerState(balances={account_id_value: 10}, supply_cap=20)
    different_cap = LedgerState(balances={account_id_value: 10}, supply_cap=30)
    different_chain = LedgerState(
        balances={account_id_value: 10}, supply_cap=20, chain_id=b"X" * 32
    )

    base_hash = state_commitment(base)
    assert state_commitment(different_cap) != base_hash
    assert state_commitment(different_chain) != base_hash


def test_append_and_restore_preserves_state(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "hnd.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 90}, supply_cap=90))
    tx = create_transaction(alice, bob_id, 35, 0)
    block = chain.append([tx])
    assert block.height == 1
    assert chain.state.balances[alice_id] == 55
    chain.close()

    restored = LocalChain(path)
    assert restored.height == 1
    assert restored.tip_hash == block.block_hash
    assert restored.state.balances[alice_id] == 55
    assert restored.state.balances[bob_id] == 35
    restored.close()


def test_invalid_block_is_not_persisted_or_applied(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    chain = LocalChain(tmp_path / "hnd.sqlite", LedgerState(balances={alice_id: 10}, supply_cap=10))
    bad = create_transaction(alice, bob_id, 11, 0)
    with pytest.raises(ValueError):
        chain.append([bad])
    assert chain.height == 0
    assert chain.state.balances[alice_id] == 10
    assert chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0
    chain.close()


def test_tampered_persisted_block_is_rejected_on_reopen(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "hnd.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 20}, supply_cap=20))
    chain.append([create_transaction(alice, bob_id, 5, 0)])
    chain.close()

    db = sqlite3.connect(path)
    db.execute("UPDATE blocks SET payload = ?", (b"tampered",))
    db.commit()
    db.close()
    with pytest.raises(ChainError):
        LocalChain(path)



def test_genesis_commitment_includes_supply_cap(tmp_path):
    key = Ed25519PrivateKey.generate()
    account_id_value = account(key)
    path = tmp_path / "hnd.sqlite"
    chain = LocalChain(path, LedgerState(balances={account_id_value: 10}, supply_cap=20))
    chain.close()

    db = sqlite3.connect(path)
    import cbor2
    snapshot = cbor2.loads(db.execute(
        "SELECT value FROM metadata WHERE key='genesis_state'"
    ).fetchone()[0])
    snapshot[2] = 30
    db.execute(
        "UPDATE metadata SET value=? WHERE key='genesis_state'",
        (cbor2.dumps(snapshot, canonical=True),),
    )
    db.commit()
    db.close()

    with pytest.raises(ChainError, match="genesis commitment"):
        LocalChain(path)


def test_block_table_hash_must_match_payload_commitment(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "hnd.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 20}, supply_cap=20))
    block = chain.append([create_transaction(alice, bob_id, 5, 0)])
    chain.close()

    db = sqlite3.connect(path)
    db.execute("UPDATE blocks SET block_hash=?", (bytes([9]) * 32,))
    db.commit()
    db.close()
    with pytest.raises(ChainError, match="commitment"):
        LocalChain(path)



def test_recovery_rejects_noncanonical_block_payload(tmp_path):
    import cbor2

    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "hnd.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 20}, supply_cap=20))
    chain.append([create_transaction(alice, bob_id, 5, 0)])
    chain.close()

    db = sqlite3.connect(path)
    payload = db.execute("SELECT payload FROM blocks").fetchone()[0]
    decoded = cbor2.loads(payload)
    # Encode an equivalent value with a deliberately non-canonical array header.
    noncanonical = bytes([0x98, 0x06]) + payload[1:]
    assert cbor2.loads(noncanonical) == decoded
    db.execute("UPDATE blocks SET payload=?", (noncanonical,))
    db.commit()
    db.close()

    with pytest.raises(ChainError, match="non-canonical"):
        LocalChain(path)



def test_multiple_sequential_transactions_in_one_block_survive_restore(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "multi.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 20}, supply_cap=20))
    first = create_transaction(alice, bob_id, 5, 0)
    second = create_transaction(alice, bob_id, 7, 1)
    block = chain.append([first, second])
    assert block.height == 1
    assert chain.state.balances[alice_id] == 8
    assert chain.state.balances[bob_id] == 12
    assert chain.state.next_nonces[alice_id] == 2
    chain.close()

    restored = LocalChain(path)
    assert restored.height == 1
    assert restored.tip_hash == block.block_hash
    assert restored.state.balances[alice_id] == 8
    assert restored.state.balances[bob_id] == 12
    assert restored.state.next_nonces[alice_id] == 2
    restored.close()


def test_block_transaction_count_limit_is_atomic(tmp_path):
    from hnd_ledger.chain import MAX_BLOCK_TRANSACTIONS

    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    chain = LocalChain(tmp_path / "limit.sqlite", LedgerState(balances={alice_id: 20}, supply_cap=20))
    tx = create_transaction(alice, bob_id, 1, 0)
    with pytest.raises(ChainError, match="transaction count"):
        chain.append([tx] * (MAX_BLOCK_TRANSACTIONS + 1))
    assert chain.height == 0
    assert chain.state.balances[alice_id] == 20
    assert chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0
    chain.close()



def test_block_encoded_byte_limit_is_checked_before_state_changes(tmp_path):
    from hnd_ledger.chain import MAX_BLOCK_TRANSACTIONS

    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    chain = LocalChain(tmp_path / "bytes.sqlite", LedgerState(balances={alice_id: 20}, supply_cap=20))
    tx = create_transaction(alice, bob_id, 1, 0)
    with pytest.raises(ChainError, match="byte limit"):
        chain.append([tx] * MAX_BLOCK_TRANSACTIONS)
    assert chain.height == 0
    assert chain.state.balances[alice_id] == 20
    assert chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0
    chain.close()
