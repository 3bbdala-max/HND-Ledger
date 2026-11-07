import sqlite3
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.chain import ChainError, LocalChain, state_commitment
from hnd_ledger.protocol import CHAIN_ID, account_id, create_transaction, encode_transaction
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



def test_genesis_state_and_marker_persist_atomically(tmp_path):
    import sqlite3

    key = Ed25519PrivateKey.generate()
    account_id_value = account(key)
    path = tmp_path / "atomic-genesis.sqlite"
    chain = LocalChain(path, LedgerState(supply_cap=100))
    before_state = chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_state'"
    ).fetchone()[0]
    before_hash = chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_hash'"
    ).fetchone()[0]
    chain.db.execute(
        """
        CREATE TRIGGER reject_genesis_marker
        BEFORE INSERT ON metadata
        WHEN NEW.key = 'cometbft_genesis_marker'
        BEGIN
            SELECT RAISE(ABORT, 'simulated marker write failure');
        END
        """
    )
    chain.db.commit()

    with pytest.raises(sqlite3.IntegrityError, match="simulated marker"):
        chain.initialize_genesis(
            LedgerState(balances={account_id_value: 50}, supply_cap=100),
            marker=b"M" * 32,
        )

    assert chain.state.total_supply == 0
    assert chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_state'"
    ).fetchone()[0] == before_state
    assert chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_hash'"
    ).fetchone()[0] == before_hash
    assert chain.db.execute(
        "SELECT COUNT(*) FROM metadata WHERE key='cometbft_genesis_marker'"
    ).fetchone()[0] == 0
    chain.close()



def test_block_persistence_failure_rolls_back_without_state_advance(tmp_path):
    key = Ed25519PrivateKey.generate()
    recipient_key = Ed25519PrivateKey.generate()
    sender_id = account(key)
    recipient_id = account(recipient_key)
    initial = LedgerState(balances={sender_id: 100}, supply_cap=100)
    path = tmp_path / "atomic-block.sqlite"
    chain = LocalChain(path, initial)
    before_hash = chain.tip_hash
    tx = create_transaction(key, recipient_id, 40, 0)

    chain.db.execute(
        """
        CREATE TRIGGER reject_block_insert
        BEFORE INSERT ON blocks
        BEGIN
            SELECT RAISE(ABORT, 'simulated block write failure');
        END
        """
    )
    chain.db.commit()

    with pytest.raises(ChainError, match="block persistence conflict"):
        chain.append([tx])

    assert chain.height == 0
    assert chain.tip_hash == before_hash
    assert chain.state.balances == {sender_id: 100}
    assert chain.state.next_nonces == {}
    assert chain.blocks == []
    assert chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0
    chain.close()

    reopened = LocalChain(path)
    assert reopened.height == 0
    assert reopened.state.balances == {sender_id: 100}
    assert reopened.state.next_nonces == {}
    assert reopened.blocks == []
    reopened.close()



def test_process_crash_during_block_insert_recovers_genesis_state(tmp_path):
    key = Ed25519PrivateKey.generate()
    recipient_key = Ed25519PrivateKey.generate()
    sender_id = account(key)
    recipient_id = account(recipient_key)
    initial = LedgerState(balances={sender_id: 100}, supply_cap=100)
    path = tmp_path / "crash-during-block.sqlite"
    chain = LocalChain(path, initial)
    chain.close()
    raw = encode_transaction(create_transaction(key, recipient_id, 40, 0))

    child = r"""
import os
import sys
from hnd_ledger.chain import LocalChain
from hnd_ledger.protocol import CHAIN_ID, decode_transaction

chain = LocalChain(sys.argv[1])
chain.db.create_function("crash_now", 0, lambda: os._exit(73))
chain.db.execute(
    "CREATE TRIGGER crash_during_insert AFTER INSERT ON blocks "
    "BEGIN SELECT crash_now(); END"
)
chain.db.commit()
chain.append([decode_transaction(bytes.fromhex(sys.argv[2]), CHAIN_ID)])
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(path), raw.hex()],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 73, result.stderr.decode(errors="replace")

    recovered = LocalChain(path)
    assert recovered.height == 0
    assert recovered.state.balances == {sender_id: 100}
    assert recovered.state.next_nonces == {}
    assert recovered.blocks == []
    assert recovered.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0
    recovered.close()


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



def test_process_crash_during_genesis_marker_write_recovers_empty_genesis(tmp_path):
    key = Ed25519PrivateKey.generate()
    account_id_value = account(key)
    path = tmp_path / "crash-during-genesis.sqlite"
    chain = LocalChain(path, LedgerState(supply_cap=100))
    before_state = chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_state'"
    ).fetchone()[0]
    before_hash = chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_hash'"
    ).fetchone()[0]
    chain.close()

    child = r"""
import os
import sys
from hnd_ledger.chain import LocalChain
from hnd_ledger.state import LedgerState

chain = LocalChain(sys.argv[1])
chain.db.create_function("crash_now", 0, lambda: os._exit(74))
chain.db.execute(
    "CREATE TRIGGER crash_during_genesis_marker "
    "BEFORE INSERT ON metadata "
    "WHEN NEW.key = 'cometbft_genesis_marker' "
    "BEGIN SELECT crash_now(); END"
)
chain.db.commit()
chain.initialize_genesis(
    LedgerState(balances={bytes.fromhex(sys.argv[2]): 50}, supply_cap=100),
    marker=b"M" * 32,
)
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(path), account_id_value.hex()],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 74, result.stderr.decode(errors="replace")

    recovered = LocalChain(path)
    assert recovered.height == 0
    assert recovered.state.total_supply == 0
    assert recovered.state.balances == {}
    assert recovered.state.next_nonces == {}
    assert recovered.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_state'"
    ).fetchone()[0] == before_state
    assert recovered.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_hash'"
    ).fetchone()[0] == before_hash
    assert recovered.db.execute(
        "SELECT COUNT(*) FROM metadata WHERE key='cometbft_genesis_marker'"
    ).fetchone()[0] == 0
    recovered.close()


def test_process_crash_after_genesis_marker_insert_rolls_back_all_genesis_writes(tmp_path):
    key = Ed25519PrivateKey.generate()
    account_id_value = account(key)
    path = tmp_path / "crash-after-genesis-marker.sqlite"
    chain = LocalChain(path, LedgerState(supply_cap=100))
    before_state = chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_state'"
    ).fetchone()[0]
    before_hash = chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_hash'"
    ).fetchone()[0]
    chain.close()

    child = r"""
import os
import sys
from hnd_ledger.chain import LocalChain
from hnd_ledger.state import LedgerState

chain = LocalChain(sys.argv[1])
chain.db.create_function("crash_now", 0, lambda: os._exit(75))
chain.db.execute(
    "CREATE TRIGGER crash_after_genesis_marker "
    "AFTER INSERT ON metadata "
    "WHEN NEW.key = 'cometbft_genesis_marker' "
    "BEGIN SELECT crash_now(); END"
)
chain.db.commit()
chain.initialize_genesis(
    LedgerState(balances={bytes.fromhex(sys.argv[2]): 50}, supply_cap=100),
    marker=b"N" * 32,
)
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(path), account_id_value.hex()],
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 75, result.stderr.decode(errors="replace")

    recovered = LocalChain(path)
    assert recovered.height == 0
    assert recovered.state.total_supply == 0
    assert recovered.state.balances == {}
    assert recovered.state.next_nonces == {}
    assert recovered.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_state'"
    ).fetchone()[0] == before_state
    assert recovered.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_hash'"
    ).fetchone()[0] == before_hash
    assert recovered.db.execute(
        "SELECT COUNT(*) FROM metadata WHERE key='cometbft_genesis_marker'"
    ).fetchone()[0] == 0
    recovered.close()


def test_failed_reopen_closes_sqlite_connection(tmp_path, monkeypatch):
    import hnd_ledger.chain as chain_module

    key = Ed25519PrivateKey.generate()
    account_id_value = account(key)
    path = tmp_path / "failed-reopen.sqlite"
    chain = LocalChain(
        path, LedgerState(balances={account_id_value: 10}, supply_cap=10)
    )
    chain.close()

    real_connect = sqlite3.connect
    tamper = real_connect(path)
    tamper.execute(
        "UPDATE metadata SET value=? WHERE key='genesis_hash'", (b"X" * 32,)
    )
    tamper.commit()
    tamper.close()

    tracked = {"closed": False}

    class TrackedConnection:
        def __init__(self, connection):
            self._connection = connection

        def __getattr__(self, name):
            return getattr(self._connection, name)

        def close(self):
            tracked["closed"] = True
            return self._connection.close()

    monkeypatch.setattr(
        chain_module.sqlite3, "connect",
        lambda *args, **kwargs: TrackedConnection(real_connect(*args, **kwargs)),
    )
    with pytest.raises(ChainError, match="genesis commitment"):
        LocalChain(path)
    assert tracked["closed"] is True


def test_sqlite_backup_restores_verified_independent_chain(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    carol = Ed25519PrivateKey.generate()
    alice_id, bob_id, carol_id = account(alice), account(bob), account(carol)
    source_path = tmp_path / "source.sqlite"
    backup_path = tmp_path / "backup.sqlite"

    source = LocalChain(
        source_path, LedgerState(balances={alice_id: 90}, supply_cap=90)
    )
    source.append([create_transaction(alice, bob_id, 35, 0)])
    source_height = source.height
    source_tip = source.tip_hash
    source_commitment = state_commitment(source.state)
    source_balances = dict(source.state.balances)
    source_nonces = dict(source.state.next_nonces)

    destination = sqlite3.connect(backup_path)
    try:
        source.db.backup(destination)
    finally:
        destination.close()

    check = sqlite3.connect(backup_path)
    try:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        check.close()

    restored = LocalChain(backup_path)
    assert restored.height == source_height
    assert restored.tip_hash == source_tip
    assert state_commitment(restored.state) == source_commitment
    assert restored.state.balances == source_balances
    assert restored.state.next_nonces == source_nonces
    assert restored.state.supply_cap == source.state.supply_cap
    assert restored.state.chain_id == source.state.chain_id

    restored.append([create_transaction(alice, carol_id, 10, 1)])
    assert restored.height == source_height + 1
    assert restored.state.balances[alice_id] == 45
    assert restored.state.balances[carol_id] == 10

    assert source.height == source_height
    assert source.tip_hash == source_tip
    assert state_commitment(source.state) == source_commitment
    assert source.state.balances == source_balances
    assert source.state.next_nonces == source_nonces
    restored.close()
    source.close()

def test_duplicate_signed_transaction_is_rejected_within_and_across_blocks(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "duplicate-replay.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 20}, supply_cap=20))
    transaction = create_transaction(alice, bob_id, 5, 0)

    # A duplicate in one candidate block must reject the entire append.
    with pytest.raises(ValueError):
        chain.append([transaction, transaction])
    assert chain.height == 0
    assert chain.state.balances == {alice_id: 20}
    assert chain.state.next_nonces == {}
    assert chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0

    # The transaction can then be committed once, but never replayed in a
    # later block with the already-consumed account nonce.
    first_block = chain.append([transaction])
    committed_state = dict(chain.state.balances)
    committed_nonces = dict(chain.state.next_nonces)
    with pytest.raises(ValueError):
        chain.append([transaction])
    assert chain.height == 1
    assert chain.tip_hash == first_block.block_hash
    assert chain.state.balances == committed_state
    assert chain.state.next_nonces == committed_nonces
    assert chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 1
    chain.close()

    restored = LocalChain(path)
    assert restored.height == 1
    assert restored.tip_hash == first_block.block_hash
    assert restored.state.balances == committed_state
    assert restored.state.next_nonces == committed_nonces
    restored.close()

@pytest.mark.parametrize("tamper", ["stored_height", "previous_hash"])
def test_recovery_rejects_tampered_block_position_or_parent(tmp_path, tamper):
    import cbor2

    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / f"tampered-{tamper}.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 20}, supply_cap=20))
    chain.append([create_transaction(alice, bob_id, 5, 0)])
    chain.close()

    db = sqlite3.connect(path)
    if tamper == "stored_height":
        db.execute("UPDATE blocks SET height=2 WHERE height=1")
    else:
        payload = db.execute(
            "SELECT payload FROM blocks WHERE height=1"
        ).fetchone()[0]
        decoded = cbor2.loads(payload)
        decoded[2] = bytes([7]) * 32
        db.execute(
            "UPDATE blocks SET payload=? WHERE height=1",
            (cbor2.dumps(decoded, canonical=True),),
        )
    db.commit()
    db.close()

    with pytest.raises(ChainError):
        LocalChain(path)

def test_recovery_rejects_missing_middle_block(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "missing-middle-block.sqlite"
    chain = LocalChain(
        path, LedgerState(balances={alice_id: 30}, supply_cap=30)
    )
    chain.append([create_transaction(alice, bob_id, 5, 0)])
    chain.append([create_transaction(alice, bob_id, 7, 1)])
    assert chain.height == 2
    chain.close()

    db = sqlite3.connect(path)
    db.execute("DELETE FROM blocks WHERE height=1")
    db.commit()
    db.close()

    with pytest.raises(ChainError, match="height sequence"):
        LocalChain(path)


def test_recovery_rejects_deleted_final_block_using_persisted_tip(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "missing-final-block.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 30}, supply_cap=30))
    chain.append([create_transaction(alice, bob_id, 5, 0)])
    chain.append([create_transaction(alice, bob_id, 7, 1)])
    assert chain.height == 2
    chain.close()

    db = sqlite3.connect(path)
    db.execute("DELETE FROM blocks WHERE height=2")
    db.commit()
    db.close()

    with pytest.raises(ChainError, match="tip commitment"):
        LocalChain(path)


def test_chain_tip_anchor_advances_atomically_with_each_block(tmp_path):
    import cbor2

    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "tip-anchor.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 30}, supply_cap=30))
    genesis_hash = chain.tip_hash
    anchor = cbor2.loads(chain.db.execute(
        "SELECT value FROM metadata WHERE key='chain_tip'"
    ).fetchone()[0])
    assert anchor == [1, 0, genesis_hash]

    block = chain.append([create_transaction(alice, bob_id, 5, 0)])
    anchor = cbor2.loads(chain.db.execute(
        "SELECT value FROM metadata WHERE key='chain_tip'"
    ).fetchone()[0])
    assert anchor == [1, 1, block.block_hash]
    chain.close()

    restored = LocalChain(path)
    assert restored.height == 1
    assert restored.tip_hash == block.block_hash
    restored.close()


def test_recovery_rejects_missing_chain_tip_anchor(tmp_path):
    alice = Ed25519PrivateKey.generate()
    alice_id = account(alice)
    path = tmp_path / "missing-chain-tip-anchor.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 30}, supply_cap=30))
    chain.append([])
    chain.close()

    db = sqlite3.connect(path)
    db.execute("DELETE FROM metadata WHERE key='chain_tip'")
    db.commit()
    db.close()

    with pytest.raises(ChainError, match="tip commitment is missing"):
        LocalChain(path)


def test_legacy_chain_tip_metadata_migrates_once(tmp_path):
    import cbor2

    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    path = tmp_path / "legacy-tip-migration.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 30}, supply_cap=30))
    block = chain.append([create_transaction(alice, bob_id, 5, 0)])
    chain.close()

    db = sqlite3.connect(path)
    db.execute("DELETE FROM metadata WHERE key IN ('chain_tip', 'chain_tip_version')")
    db.commit()
    db.close()

    migrated = LocalChain(path)
    assert migrated.height == 1
    assert migrated.tip_hash == block.block_hash
    anchor_raw = migrated.db.execute(
        "SELECT value FROM metadata WHERE key='chain_tip'"
    ).fetchone()[0]
    version_raw = migrated.db.execute(
        "SELECT value FROM metadata WHERE key='chain_tip_version'"
    ).fetchone()[0]
    assert cbor2.loads(anchor_raw) == [1, 1, block.block_hash]
    assert cbor2.loads(version_raw) == 1
    migrated.close()


@pytest.mark.parametrize("key", ["chain_tip", "chain_tip_version"])
def test_recovery_rejects_malformed_chain_tip_metadata(tmp_path, key):
    alice = Ed25519PrivateKey.generate()
    alice_id = account(alice)
    path = tmp_path / f"malformed-{key}.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 10}, supply_cap=10))
    chain.append([])
    chain.close()

    db = sqlite3.connect(path)
    db.execute("UPDATE metadata SET value=? WHERE key=?", (b"\\xff", key))
    db.commit()
    db.close()

    with pytest.raises(ChainError):
        LocalChain(path)


def test_append_fails_closed_if_tip_anchor_is_removed_while_open(tmp_path):
    alice = Ed25519PrivateKey.generate()
    alice_id = account(alice)
    path = tmp_path / "removed-tip-while-open.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 10}, supply_cap=10))

    external = sqlite3.connect(path)
    external.execute("DELETE FROM metadata WHERE key='chain_tip'")
    external.commit()
    external.close()

    with pytest.raises(ChainError, match="tip commitment is missing"):
        chain.append([])
    assert chain.height == 0
    assert chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0
    chain.close()


def test_append_fails_closed_if_tip_version_is_removed_while_open(tmp_path):
    alice = Ed25519PrivateKey.generate()
    alice_id = account(alice)
    path = tmp_path / "removed-tip-version-while-open.sqlite"
    chain = LocalChain(path, LedgerState(balances={alice_id: 10}, supply_cap=10))

    external = sqlite3.connect(path)
    external.execute("DELETE FROM metadata WHERE key='chain_tip_version'")
    external.commit()
    external.close()

    with pytest.raises(ChainError, match="metadata version is missing"):
        chain.append([])
    assert chain.height == 0
    assert chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0
    chain.close()


@pytest.mark.parametrize("missing_key", ["chain_tip", "chain_tip_version"])
def test_initialize_genesis_fails_closed_if_tip_metadata_is_removed_while_open(
    tmp_path, missing_key
):
    alice = Ed25519PrivateKey.generate()
    alice_id = account(alice)
    path = tmp_path / f"genesis-missing-{missing_key}.sqlite"
    chain = LocalChain(path, LedgerState(supply_cap=100))
    before_genesis = chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_state'"
    ).fetchone()[0]
    before_hash = chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_hash'"
    ).fetchone()[0]

    external = sqlite3.connect(path)
    external.execute("DELETE FROM metadata WHERE key=?", (missing_key,))
    external.commit()
    external.close()

    with pytest.raises(ChainError):
        chain.initialize_genesis(
            LedgerState(balances={alice_id: 50}, supply_cap=100),
            marker=b"G" * 32,
        )

    assert chain.state.total_supply == 0
    assert chain.state.balances == {}
    assert chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_state'"
    ).fetchone()[0] == before_genesis
    assert chain.db.execute(
        "SELECT value FROM metadata WHERE key='genesis_hash'"
    ).fetchone()[0] == before_hash
    assert chain.db.execute(
        "SELECT COUNT(*) FROM metadata WHERE key='cometbft_genesis_marker'"
    ).fetchone()[0] == 0
    assert chain.db.execute(
        "SELECT COUNT(*) FROM metadata WHERE key=?", (missing_key,)
    ).fetchone()[0] == 0
    chain.close()



def test_checkpoint_ancestor_commitments_match_genesis_and_replayed_blocks(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = account(alice), account(bob)
    initial = LedgerState(balances={alice_id: 20}, supply_cap=20)
    chain = LocalChain(tmp_path / "checkpoint-ancestors.sqlite", initial)

    genesis_hash, genesis_app_hash = chain.checkpoint_ancestor_commitments(0)
    assert genesis_hash == chain.tip_hash
    assert genesis_app_hash == state_commitment(initial)

    block = chain.append([create_transaction(alice, bob_id, 5, 0)])
    block_hash, app_hash = chain.checkpoint_ancestor_commitments(1)
    assert block_hash == block.block_hash
    assert app_hash == block.state_root
    chain.close()


def test_checkpoint_ancestor_commitments_reject_invalid_or_future_heights(tmp_path):
    chain = LocalChain(
        tmp_path / "checkpoint-ancestor-bounds.sqlite",
        LedgerState(supply_cap=100),
    )
    with pytest.raises(ChainError, match="non-negative integer"):
        chain.checkpoint_ancestor_commitments(True)
    with pytest.raises(ChainError, match="non-negative integer"):
        chain.checkpoint_ancestor_commitments(-1)
    with pytest.raises(ChainError, match="exceeds local chain height"):
        chain.checkpoint_ancestor_commitments(1)
    chain.close()



def test_local_chain_ancestor_commitments_feed_checkpoint_assessment(tmp_path):
    from hnd_ledger.rollback_checkpoint import (
        CheckpointRelation,
        RollbackCheckpoint,
        assess_local_tip,
    )

    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    carol = Ed25519PrivateKey.generate()
    alice_id, bob_id, carol_id = account(alice), account(bob), account(carol)
    chain = LocalChain(
        tmp_path / "checkpoint-assessment-integration.sqlite",
        LedgerState(balances={alice_id: 30}, supply_cap=30),
    )
    genesis_hash, _ = chain.checkpoint_ancestor_commitments(0)
    checkpoint_block = chain.append([create_transaction(alice, bob_id, 10, 0)])
    checkpoint = RollbackCheckpoint(
        chain_id=chain.state.chain_id,
        genesis_hash=genesis_hash,
        height=checkpoint_block.height,
        block_hash=checkpoint_block.block_hash,
        app_hash=checkpoint_block.state_root,
        sequence=1,
    )

    chain.append([create_transaction(bob, carol_id, 4, 0)])
    ancestor_block_hash, ancestor_app_hash = chain.checkpoint_ancestor_commitments(
        checkpoint.height
    )
    assessment = assess_local_tip(
        checkpoint,
        chain_id=chain.state.chain_id,
        genesis_hash=genesis_hash,
        height=chain.height,
        block_hash=chain.tip_hash,
        app_hash=state_commitment(chain.state),
        checkpoint_ancestor_block_hash=ancestor_block_hash,
        checkpoint_ancestor_app_hash=ancestor_app_hash,
    )

    assert assessment.relation is CheckpointRelation.LOCAL_AHEAD_UNVERIFIED
    assert "ancestry matches" in assessment.reason
    assert not assessment.writes_allowed
    chain.close()
