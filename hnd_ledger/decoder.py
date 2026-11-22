"""Strict decoder for the HND v0.2 restricted deterministic-CBOR profile.

Only a fixed-length top-level array of unsigned integers and definite-length
byte strings is accepted. Nested containers, indefinite lengths, non-shortest
encodings, unsupported major types, and trailing bytes are rejected.
"""
from __future__ import annotations

from .canonical import (
    ACCOUNT_ID_SIZE,
    CHAIN_ID_SIZE,
    PROTOCOL_VERSION,
    PUBLIC_KEY_SIZE,
    SIGNATURE_SIZE,
    UINT64_MAX,
    EncodingError,
    signed_transaction,
    transaction_payload,
)


def _argument(data: bytes, offset: int, additional: int) -> tuple[int, int]:
    if additional < 24:
        return additional, offset
    widths = {24: 1, 25: 2, 26: 4, 27: 8}
    width = widths.get(additional)
    if width is None:
        raise EncodingError("indefinite or reserved CBOR additional information")
    end = offset + width
    if end > len(data):
        raise EncodingError("truncated CBOR argument")
    value = int.from_bytes(data[offset:end], "big")
    minimum = {1: 24, 2: 256, 4: 65536, 8: 1 << 32}[width]
    if value < minimum:
        raise EncodingError("non-minimal CBOR integer or length")
    return value, end


def _read_scalar(data: bytes, offset: int) -> tuple[int | bytes, int]:
    if offset >= len(data):
        raise EncodingError("truncated CBOR item")
    initial = data[offset]
    major, additional = initial >> 5, initial & 31
    value, cursor = _argument(data, offset + 1, additional)
    if major == 0:
        return value, cursor
    if major == 2:
        end = cursor + value
        if end > len(data):
            raise EncodingError("truncated CBOR byte string")
        return data[cursor:end], end
    if major == 4:
        raise EncodingError("nested CBOR arrays are not permitted")
    raise EncodingError("unsupported CBOR major type")


def _decode_array(encoded: bytes, expected_length: int) -> list[int | bytes]:
    if not isinstance(encoded, bytes):
        raise EncodingError("encoded CBOR value must be bytes")
    if not encoded:
        raise EncodingError("truncated CBOR array")
    initial = encoded[0]
    if initial >> 5 != 4:
        raise EncodingError("top-level CBOR value must be an array")
    count, cursor = _argument(encoded, 1, initial & 31)
    if count != expected_length:
        raise EncodingError("unexpected CBOR array length")
    fields: list[int | bytes] = []
    for _ in range(expected_length):
        item, cursor = _read_scalar(encoded, cursor)
        fields.append(item)
    if cursor != len(encoded):
        raise EncodingError("trailing bytes after CBOR value")
    return fields


def decode_transaction_payload(encoded: bytes) -> dict[str, object]:
    """Decode and validate the exact six-field unsigned transaction payload."""
    fields = _decode_array(encoded, 6)
    version, chain_id, sender, recipient, amount, nonce = fields
    if version != PROTOCOL_VERSION:
        raise EncodingError("unsupported protocol version")
    if not isinstance(chain_id, bytes) or len(chain_id) != CHAIN_ID_SIZE:
        raise EncodingError("chain_id must be exactly 32 bytes")
    if not isinstance(sender, bytes) or len(sender) != ACCOUNT_ID_SIZE:
        raise EncodingError("sender must be exactly 32 bytes")
    if not isinstance(recipient, bytes) or len(recipient) != ACCOUNT_ID_SIZE:
        raise EncodingError("recipient must be exactly 32 bytes")
    if not isinstance(amount, int) or not 1 <= amount <= UINT64_MAX:
        raise EncodingError("amount must be a positive uint64")
    if not isinstance(nonce, int) or not 0 <= nonce <= UINT64_MAX:
        raise EncodingError("nonce must be a uint64")
    if transaction_payload(chain_id, sender, recipient, amount, nonce) != encoded:
        raise EncodingError("transaction payload is not canonical")
    return {
        "version": version,
        "chain_id": chain_id,
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "nonce": nonce,
    }


def decode_signed_transaction(encoded: bytes) -> dict[str, object]:
    """Decode and validate the exact eight-field complete signed transaction."""
    fields = _decode_array(encoded, 8)
    version, chain_id, sender, recipient, amount, nonce, public_key, signature = fields
    if version != PROTOCOL_VERSION:
        raise EncodingError("unsupported protocol version")
    if not isinstance(chain_id, bytes) or len(chain_id) != CHAIN_ID_SIZE:
        raise EncodingError("chain_id must be exactly 32 bytes")
    if not isinstance(sender, bytes) or len(sender) != ACCOUNT_ID_SIZE:
        raise EncodingError("sender must be exactly 32 bytes")
    if not isinstance(recipient, bytes) or len(recipient) != ACCOUNT_ID_SIZE:
        raise EncodingError("recipient must be exactly 32 bytes")
    if not isinstance(amount, int) or not 1 <= amount <= UINT64_MAX:
        raise EncodingError("amount must be a positive uint64")
    if not isinstance(nonce, int) or not 0 <= nonce <= UINT64_MAX:
        raise EncodingError("nonce must be a uint64")
    if not isinstance(public_key, bytes) or len(public_key) != PUBLIC_KEY_SIZE:
        raise EncodingError("public_key must be exactly 32 bytes")
    if not isinstance(signature, bytes) or len(signature) != SIGNATURE_SIZE:
        raise EncodingError("signature must be exactly 64 bytes")
    if signed_transaction(
        chain_id, sender, recipient, amount, nonce, public_key, signature
    ) != encoded:
        raise EncodingError("signed transaction is not canonical")
    return {
        "version": version,
        "chain_id": chain_id,
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "nonce": nonce,
        "public_key": public_key,
        "signature": signature,
    }
