import pytest

from hnd_ledger.canonical import (
    EncodingError,
    LOCAL_CHAIN_ID,
    signed_transaction,
    transaction_payload,
)
from hnd_ledger.decoder import (
    decode_signed_transaction,
    decode_transaction_payload,
)

SENDER = bytes(range(32))
RECIPIENT = bytes(range(32, 64))
PUBLIC_KEY = bytes(range(32))
SIGNATURE = bytes(range(64))


def test_unsigned_payload_round_trip():
    encoded = transaction_payload(LOCAL_CHAIN_ID, SENDER, RECIPIENT, 1000, 7)
    decoded = decode_transaction_payload(encoded)
    assert decoded == {
        "version": 2,
        "chain_id": LOCAL_CHAIN_ID,
        "sender": SENDER,
        "recipient": RECIPIENT,
        "amount": 1000,
        "nonce": 7,
    }


def test_signed_transaction_round_trip():
    encoded = signed_transaction(
        LOCAL_CHAIN_ID, SENDER, RECIPIENT, 1000, 7, PUBLIC_KEY, SIGNATURE
    )
    decoded = decode_signed_transaction(encoded)
    assert decoded["public_key"] == PUBLIC_KEY
    assert decoded["signature"] == SIGNATURE
    assert decoded["amount"] == 1000


@pytest.mark.parametrize(
    "bad",
    [
        b"",
        b"\x9f\xff",                 # indefinite array
        b"\x86\x18\x02",            # non-minimal version integer
        b"\x86\x02",                 # truncated array
        b"\x80",                      # wrong array length
        b"\xa0",                      # map not permitted
        b"\x86\x02" + b"\x00" * 5 + b"\x00",  # wrong field types/shape
    ],
)
def test_unsigned_decoder_rejects_malformed_or_noncanonical_input(bad):
    with pytest.raises(EncodingError):
        decode_transaction_payload(bad)


def test_unsigned_decoder_rejects_trailing_bytes():
    encoded = transaction_payload(LOCAL_CHAIN_ID, SENDER, RECIPIENT, 1000, 7)
    with pytest.raises(EncodingError, match="trailing"):
        decode_transaction_payload(encoded + b"\x00")


def test_signed_decoder_rejects_wrong_signature_length():
    malformed = (
        b"\x88\x02"
        + bytes([0x58, 32]) + LOCAL_CHAIN_ID
        + bytes([0x58, 32]) + SENDER
        + bytes([0x58, 32]) + RECIPIENT
        + b"\x19\x03\xe8\x07"
        + bytes([0x58, 32]) + PUBLIC_KEY
        + bytes([0x58, 63]) + SIGNATURE[:63]
    )
    with pytest.raises(EncodingError, match="signature"):
        decode_signed_transaction(malformed)


def test_decoder_rejects_non_bytes_input():
    with pytest.raises(EncodingError, match="must be bytes"):
        decode_transaction_payload("not bytes")
