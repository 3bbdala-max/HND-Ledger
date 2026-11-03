import pytest

from hnd_ledger import Ledger, LedgerError, Transaction, address_from_public_key, generate_keypair, sign_transaction

NETWORK = "hnd-local-testnet"


def make_tx(private_key, public_key, recipient, amount, nonce=0, network=NETWORK):
    sender = address_from_public_key(public_key)
    unsigned = Transaction(network, sender, recipient, amount, nonce, public_key.hex(), "00")
    signature = sign_transaction(private_key, unsigned.signing_bytes())
    return Transaction(**{**unsigned.__dict__, "signature": signature})


@pytest.fixture
def ledger_setup():
    key, pub = generate_keypair()
    recipient_key, recipient_pub = generate_keypair()
    sender = address_from_public_key(pub)
    recipient = address_from_public_key(recipient_pub)
    ledger = Ledger(NETWORK, {sender: 1000, recipient: 100})
    return ledger, key, pub, sender, recipient


def test_valid_transfer(ledger_setup):
    ledger, key, pub, sender, recipient = ledger_setup
    txid = ledger.submit_transaction(make_tx(key, pub, recipient, 125))
    assert len(txid) == 64
    assert ledger.balance_of(sender) == 875
    assert ledger.balance_of(recipient) == 225
    assert ledger.nonce_of(sender) == 1


def test_duplicate_rejected(ledger_setup):
    ledger, key, pub, sender, recipient = ledger_setup
    tx = make_tx(key, pub, recipient, 10)
    ledger.submit_transaction(tx)
    with pytest.raises(LedgerError, match="duplicate"):
        ledger.submit_transaction(tx)


def test_invalid_signature_is_atomic(ledger_setup):
    ledger, key, pub, sender, recipient = ledger_setup
    tx = make_tx(key, pub, recipient, 10)
    altered = Transaction(**{**tx.__dict__, "amount": 11})
    with pytest.raises(LedgerError, match="signature"):
        ledger.submit_transaction(altered)
    assert ledger.balance_of(sender) == 1000
    assert ledger.balance_of(recipient) == 100
    assert ledger.nonce_of(sender) == 0


def test_wrong_network_rejected(ledger_setup):
    ledger, key, pub, sender, recipient = ledger_setup
    tx = make_tx(key, pub, recipient, 10, network="other")
    with pytest.raises(LedgerError, match="network"):
        ledger.submit_transaction(tx)


def test_insufficient_funds_is_atomic(ledger_setup):
    ledger, key, pub, sender, recipient = ledger_setup
    with pytest.raises(LedgerError, match="insufficient"):
        ledger.submit_transaction(make_tx(key, pub, recipient, 1001))
    assert ledger.balance_of(sender) == 1000
    assert ledger.nonce_of(sender) == 0


def test_nonce_conflict_rejected(ledger_setup):
    ledger, key, pub, sender, recipient = ledger_setup
    with pytest.raises(LedgerError, match="nonce"):
        ledger.submit_transaction(make_tx(key, pub, recipient, 10, nonce=1))


def test_replay_rejected(ledger_setup):
    ledger, key, pub, sender, recipient = ledger_setup
    tx = make_tx(key, pub, recipient, 10)
    ledger.submit_transaction(tx)
    replay = make_tx(key, pub, recipient, 10)
    with pytest.raises(LedgerError, match="duplicate|nonce"):
        ledger.submit_transaction(replay)


def test_self_transfer_keeps_balance_and_increments_nonce(ledger_setup):
    ledger, key, pub, sender, recipient = ledger_setup
    ledger.submit_transaction(make_tx(key, pub, sender, 25))
    assert ledger.balance_of(sender) == 1000
    assert ledger.nonce_of(sender) == 1


def test_malformed_dict_rejected(ledger_setup):
    ledger, *_ = ledger_setup
    with pytest.raises(LedgerError, match="malformed"):
        Transaction.from_dict({"sender": "bad"})


def test_boolean_amount_rejected(ledger_setup):
    ledger, key, pub, sender, recipient = ledger_setup
    tx = make_tx(key, pub, recipient, 10)
    bad = Transaction(**{**tx.__dict__, "amount": True})
    with pytest.raises(LedgerError, match="integer"):
        ledger.submit_transaction(bad)
