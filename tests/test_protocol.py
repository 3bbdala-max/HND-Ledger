from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.protocol import (
    CHAIN_ID, ProtocolError, account_id, create_transaction,
    decode_transaction, encode_transaction, verify_transaction,
)


def keys():
    return Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()


def test_sign_verify_and_round_trip():
    sender_key, recipient_key = keys()
    recipient = account_id(recipient_key.public_key().public_bytes_raw())
    tx = create_transaction(sender_key, recipient, 25, 0)
    verify_transaction(tx)
    assert decode_transaction(encode_transaction(tx)) == tx


def test_tampered_amount_is_rejected():
    sender_key, recipient_key = keys()
    recipient = account_id(recipient_key.public_key().public_bytes_raw())
    tx = create_transaction(sender_key, recipient, 25, 0)
    with pytest.raises(ProtocolError):
        verify_transaction(replace(tx, amount=26))


def test_wrong_chain_is_rejected():
    sender_key, recipient_key = keys()
    recipient = account_id(recipient_key.public_key().public_bytes_raw())
    tx = create_transaction(sender_key, recipient, 25, 0)
    with pytest.raises(ProtocolError, match="chain"):
        verify_transaction(tx, bytes([1]) * 32)


def test_self_transfer_and_zero_amount_are_rejected():
    key = Ed25519PrivateKey.generate()
    own_id = account_id(key.public_key().public_bytes_raw())
    with pytest.raises(ProtocolError, match="self"):
        create_transaction(key, own_id, 1, 0)
    recipient_key = Ed25519PrivateKey.generate()
    recipient = account_id(recipient_key.public_key().public_bytes_raw())
    with pytest.raises(ProtocolError):
        create_transaction(key, recipient, 0, 0)


def test_noncanonical_cbor_is_rejected():
    sender_key, recipient_key = keys()
    recipient = account_id(recipient_key.public_key().public_bytes_raw())
    tx = create_transaction(sender_key, recipient, 25, 0)
    raw = encode_transaction(tx)
    # A non-minimal encoding of the outer array length is not canonical.
    noncanonical = bytes([0x98, 0x08]) + raw[1:]
    with pytest.raises(ProtocolError, match="non-canonical"):
        decode_transaction(noncanonical, CHAIN_ID)
