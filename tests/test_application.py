import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.application import LedgerApplication
from hnd_ledger.chain import ChainError, LocalChain, state_commitment
from hnd_ledger.protocol import account_id, create_transaction, encode_transaction
from hnd_ledger.state import LedgerState


def _account(key):
    return account_id(key.public_key().public_bytes_raw())


def _app(tmp_path):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id, bob_id = _account(alice), _account(bob)
    chain = LocalChain(
        tmp_path / "application.sqlite",
        LedgerState(balances={alice_id: 100}, supply_cap=100),
    )
    return LedgerApplication(chain), alice, bob_id, alice_id


def test_finalize_does_not_persist_until_commit(tmp_path):
    app, alice, bob_id, alice_id = _app(tmp_path)
    raw = encode_transaction(create_transaction(alice, bob_id, 25, 0))
    before_hash = app.app_hash

    finalized_hash = app.finalize_block([raw])

    assert finalized_hash != before_hash
    assert app.height == 0
    assert app.app_hash == before_hash
    assert app.chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0

    block = app.commit()
    assert block.height == 1
    assert app.height == 1
    assert app.app_hash == finalized_hash
    assert app.chain.state.balances[alice_id] == 75
    app.chain.close()


def test_uncommitted_candidate_can_be_discarded_without_state_change(tmp_path):
    app, alice, bob_id, alice_id = _app(tmp_path)
    raw = encode_transaction(create_transaction(alice, bob_id, 25, 0))
    original_hash = app.app_hash

    app.finalize_block([raw])
    app._finalized = None  # Simulate process loss before Commit.

    assert app.height == 0
    assert app.app_hash == original_hash
    assert app.chain.state.balances[alice_id] == 100
    assert app.chain.db.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 0
    app.chain.close()


def test_proposal_retry_does_not_mutate_committed_state(tmp_path):
    app, alice, bob_id, alice_id = _app(tmp_path)
    first = encode_transaction(create_transaction(alice, bob_id, 25, 0))
    second = encode_transaction(create_transaction(alice, bob_id, 40, 0))
    original_hash = app.app_hash

    assert app.process_proposal([first])
    assert app.process_proposal([second])
    selected = app.prepare_proposal([first, second])

    assert selected == (first,)
    assert app.app_hash == original_hash
    assert app.height == 0
    assert app.chain.state.balances[alice_id] == 100
    app.chain.close()


def test_invalid_proposal_is_rejected_and_check_tx_is_read_only(tmp_path):
    app, alice, bob_id, alice_id = _app(tmp_path)
    invalid = encode_transaction(create_transaction(alice, bob_id, 101, 0))
    original_hash = app.app_hash

    with pytest.raises(ChainError):
        app.check_tx(invalid)
    assert not app.process_proposal([invalid])
    assert app.app_hash == original_hash
    assert app.chain.state.balances[alice_id] == 100
    app.chain.close()


def test_commit_requires_finalize_and_finalize_is_single_pending(tmp_path):
    app, alice, bob_id, _ = _app(tmp_path)
    raw = encode_transaction(create_transaction(alice, bob_id, 1, 0))

    with pytest.raises(ChainError, match="no finalized"):
        app.commit()
    app.finalize_block([raw])
    with pytest.raises(ChainError, match="already awaits"):
        app.finalize_block([raw])
    with pytest.raises(ChainError, match="awaits commit"):
        app.prepare_proposal([raw])
    app.commit()
    assert app.info()["last_block_height"] == 1
    app.chain.close()
