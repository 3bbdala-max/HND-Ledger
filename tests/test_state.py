from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.protocol import account_id, create_transaction
from hnd_ledger.state import LedgerError, LedgerState


def identity(key):
    return account_id(key.public_key().public_bytes_raw())


def setup_state():
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = identity(alice), identity(bob)
    state = LedgerState(balances={alice_id: 100}, supply_cap=100)
    return alice, bob, alice_id, bob_id, state


def test_transfer_updates_balances_nonce_and_preserves_supply():
    alice, bob, alice_id, bob_id, state = setup_state()
    tx = create_transaction(alice, bob_id, 40, 0)
    state.apply(tx)
    assert state.balances[alice_id] == 60
    assert state.balances[bob_id] == 40
    assert state.next_nonces[alice_id] == 1
    assert state.total_supply == 100


@pytest.mark.parametrize("failure", ["replay", "wrong_nonce", "insufficient"])
def test_rejected_transaction_does_not_mutate_state(failure):
    alice, bob, alice_id, bob_id, state = setup_state()
    amount, nonce = (20, 1) if failure == "wrong_nonce" else (101, 0) if failure == "insufficient" else (20, 0)
    tx = create_transaction(alice, bob_id, amount, nonce)
    if failure == "replay":
        state.apply(tx)
    before_balances = dict(state.balances)
    before_nonces = dict(state.next_nonces)
    with pytest.raises(LedgerError):
        state.apply(tx)
    assert state.balances == before_balances
    assert state.next_nonces == before_nonces


def test_wrong_sender_key_is_rejected_without_mutation():
    alice, bob, alice_id, bob_id, state = setup_state()
    tx = create_transaction(alice, bob_id, 10, 0)
    bad = replace(tx, sender=bytes([7]) * 32)
    before = dict(state.balances)
    with pytest.raises(LedgerError):
        state.apply(bad)
    assert state.balances == before


def test_supply_cap_cannot_be_exceeded_at_initialization():
    key = Ed25519PrivateKey.generate()
    with pytest.raises(LedgerError, match="supply"):
        LedgerState(balances={identity(key): 101}, supply_cap=100)


def test_nonce_overflow_is_rejected_without_mutation():
    from hnd_ledger.protocol import MAX_U64

    alice, bob, alice_id, bob_id, state = setup_state()
    state.next_nonces[alice_id] = MAX_U64
    tx = create_transaction(alice, bob_id, 1, MAX_U64)
    before_balances = dict(state.balances)
    before_nonces = dict(state.next_nonces)

    with pytest.raises(LedgerError, match="nonce overflow"):
        state.apply(tx)

    assert state.balances == before_balances
    assert state.next_nonces == before_nonces


def test_corrupt_preexisting_supply_is_rejected_without_partial_mutation():
    alice, bob, alice_id, bob_id, state = setup_state()
    tx = create_transaction(alice, bob_id, 10, 0)

    # Simulate out-of-band corruption of the mutable in-memory balance map.
    state.balances[bob_id] = 1
    before_balances = dict(state.balances)
    before_nonces = dict(state.next_nonces)

    with pytest.raises(LedgerError, match="current state exceeds supply cap"):
        state.apply(tx)

    assert state.balances == before_balances
    assert state.next_nonces == before_nonces
