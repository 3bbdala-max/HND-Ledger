import hashlib

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.canonical import (
    EncodingError,
    LOCAL_CHAIN_ID,
    account_id,
    signing_message,
    transaction_id,
    transaction_payload,
)

SENDER = bytes(range(32))
RECIPIENT = bytes(range(32, 64))
PUBLIC_KEY = bytes(range(32))
SIGNATURE = bytes(range(64))


def test_local_chain_id_is_exactly_32_bytes():
    assert LOCAL_CHAIN_ID == b"HND-LOCAL-V2" + bytes(20)
    assert len(LOCAL_CHAIN_ID) == 32


def test_transaction_payload_matches_golden_cbor_vector():
    expected = (
        "86025820484e442d4c4f43414c2d56320000000000000000000000000000000000000000"
        "5820000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
        "5820202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f"
        "1903e807"
    )
    assert transaction_payload(LOCAL_CHAIN_ID, SENDER, RECIPIENT, 1000, 7).hex() == expected


def test_account_id_matches_domain_separated_golden_vector():
    assert account_id(PUBLIC_KEY).hex() == (
        "9399beb2cb6dc960b8e227578fe99f1b6719c522037a6b0c383fa3e21b4fe86f"
    )
    assert account_id(PUBLIC_KEY) != hashlib.sha256(PUBLIC_KEY).digest()


def test_signing_message_has_exact_domain_prefix():
    message = signing_message(LOCAL_CHAIN_ID, SENDER, RECIPIENT, 1000, 7)
    assert message.startswith(b"HND-TX-SIGN-V2\x00")
    assert message.endswith(transaction_payload(LOCAL_CHAIN_ID, SENDER, RECIPIENT, 1000, 7))


def test_ed25519_sign_and_verify_exact_message():
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    sender = account_id(public_key)
    message = signing_message(LOCAL_CHAIN_ID, sender, RECIPIENT, 1000, 7)
    signature = private_key.sign(message)
    private_key.public_key().verify(signature, message)
    with pytest.raises(InvalidSignature):
        private_key.public_key().verify(signature, message + b"!")


def test_transaction_id_commits_to_complete_signed_transaction():
    txid = transaction_id(
        LOCAL_CHAIN_ID, SENDER, RECIPIENT, 1000, 7, PUBLIC_KEY, SIGNATURE
    )
    assert txid.hex() == "164efeed621c27792f3e7727959f308605af1a49c9dc023b3ec95adee41247cc"
    changed_signature = bytes([1]) + SIGNATURE[1:]
    assert transaction_id(
        LOCAL_CHAIN_ID, SENDER, RECIPIENT, 1000, 7, PUBLIC_KEY, changed_signature
    ) != txid


@pytest.mark.parametrize("bad_amount", [0, -1, True, 1 << 64, 1.5])
def test_amount_rejects_invalid_values(bad_amount):
    with pytest.raises(EncodingError):
        transaction_payload(LOCAL_CHAIN_ID, SENDER, RECIPIENT, bad_amount, 0)


@pytest.mark.parametrize("bad_nonce", [-1, True, 1 << 64, "0"])
def test_nonce_rejects_invalid_values(bad_nonce):
    with pytest.raises(EncodingError):
        transaction_payload(LOCAL_CHAIN_ID, SENDER, RECIPIENT, 1, bad_nonce)


def test_chain_id_and_account_ids_require_exact_lengths():
    with pytest.raises(EncodingError):
        transaction_payload(b"short", SENDER, RECIPIENT, 1, 0)
    with pytest.raises(EncodingError):
        transaction_payload(LOCAL_CHAIN_ID, b"short", RECIPIENT, 1, 0)
