import pytest

from hnd_ledger.blocks import create_genesis_block
from hnd_ledger.canonical import LOCAL_CHAIN_ID, signing_message
from hnd_ledger.chain import ChainError, build_block, verify_block
from hnd_ledger.crypto import address_from_public_key, generate_keypair, sign_transaction
from hnd_ledger.ledger import Ledger, Transaction

SENDER_KEY, SENDER_PUB = generate_keypair()
RECIPIENT_KEY, RECIPIENT_PUB = generate_keypair()
SENDER = address_from_public_key(SENDER_PUB)
RECIPIENT = address_from_public_key(RECIPIENT_PUB)


def make_transaction(amount, nonce):
    message = signing_message(
        LOCAL_CHAIN_ID,
        bytes.fromhex(SENDER),
        bytes.fromhex(RECIPIENT),
        amount,
        nonce,
    )
    return Transaction(
        LOCAL_CHAIN_ID,
        SENDER,
        RECIPIENT,
        amount,
        nonce,
        SENDER_PUB.hex(),
        sign_transaction(SENDER_KEY, message),
    )


@pytest.fixture
def parent():
    balances = {SENDER: 100, RECIPIENT: 0}
    nonces = {SENDER: 0, RECIPIENT: 0}
    genesis = create_genesis_block(LOCAL_CHAIN_ID, balances)
    return genesis, balances, nonces


def test_build_and_independently_verify_two_transaction_block(parent):
    genesis, balances, nonces = parent
    transactions = [make_transaction(25, 0), make_transaction(30, 1)]
    block = build_block(
        genesis["header"], genesis["block_hash"],
        balances, nonces, transactions, timestamp=1
    )
    assert block["height"] == 1
    assert block["transaction_count"] == 2
    assert block["balances"][SENDER] == 45
    assert block["balances"][RECIPIENT] == 55
    assert block["nonces"][SENDER] == 2
    assert verify_block(
        genesis["header"], genesis["block_hash"], balances, nonces,
        transactions, block["header"], block["block_hash"]
    )


def test_replay_verifier_rejects_tampered_hash(parent):
    genesis, balances, nonces = parent
    txs = [make_transaction(10, 0)]
    block = build_block(genesis["header"], genesis["block_hash"], balances, nonces, txs, 1)
    assert not verify_block(
        genesis["header"], genesis["block_hash"], balances, nonces,
        txs, block["header"], bytes(32)
    )


def test_block_rejects_wrong_parent_hash(parent):
    genesis, balances, nonces = parent
    with pytest.raises(ChainError, match="parent hash"):
        build_block(
            genesis["header"], bytes(32), balances, nonces,
            [make_transaction(1, 0)], 1
        )


def test_block_rejects_backwards_timestamp(parent):
    genesis, balances, nonces = parent
    with pytest.raises(ChainError, match="backwards"):
        build_block(
            genesis["header"], genesis["block_hash"], balances, nonces,
            [], timestamp=0
        )


def test_block_rejects_out_of_order_nonces(parent):
    genesis, balances, nonces = parent
    with pytest.raises(ChainError, match="nonce"):
        build_block(
            genesis["header"], genesis["block_hash"], balances, nonces,
            [make_transaction(10, 1), make_transaction(10, 0)], 1
        )


def test_block_execution_does_not_mutate_parent_state(parent):
    genesis, balances, nonces = parent
    original_balances, original_nonces = dict(balances), dict(nonces)
    build_block(
        genesis["header"], genesis["block_hash"], balances, nonces,
        [make_transaction(10, 0)], 1
    )
    assert balances == original_balances
    assert nonces == original_nonces


def test_ledger_can_restore_and_export_nonces(parent):
    _, balances, _ = parent
    restored = Ledger(LOCAL_CHAIN_ID, balances, {SENDER: 4})
    exported_balances, exported_nonces = restored.export_state()
    assert exported_balances == balances
    assert exported_nonces[SENDER] == 4
    exported_balances[SENDER] = 0
    assert restored.balance_of(SENDER) == 100


def test_ledger_rejects_nonce_for_missing_account(parent):
    _, balances, _ = parent
    with pytest.raises(ValueError, match="absent"):
        Ledger(LOCAL_CHAIN_ID, balances, {"ff" * 32: 1})
