import pytest

from hnd_ledger.blocks import (
    ZERO_HASH,
    block_hash,
    canonical_block_header,
    canonical_genesis,
    create_genesis_block,
    decode_block_header,
    genesis_id,
    merkle_root,
    state_root,
    verify_block_hash,
)
from hnd_ledger.canonical import EncodingError, LOCAL_CHAIN_ID

A = "00" * 31 + "01"
B = "00" * 31 + "02"
C = "00" * 31 + "03"


def test_genesis_encoding_and_id_ignore_mapping_insertion_order():
    left = {A: 100, B: 200, C: 300}
    right = {C: 300, A: 100, B: 200}
    assert canonical_genesis(LOCAL_CHAIN_ID, left) == canonical_genesis(LOCAL_CHAIN_ID, right)
    assert genesis_id(LOCAL_CHAIN_ID, left) == genesis_id(LOCAL_CHAIN_ID, right)


def test_genesis_changes_when_allocation_changes():
    assert genesis_id(LOCAL_CHAIN_ID, {A: 100}) != genesis_id(LOCAL_CHAIN_ID, {A: 101})


def test_genesis_rejects_supply_over_cap():
    with pytest.raises(EncodingError, match="maximum supply"):
        canonical_genesis(LOCAL_CHAIN_ID, {A: 100_000_000_000_000, B: 1})


def test_genesis_rejects_boolean_balance():
    with pytest.raises(EncodingError, match="integer"):
        canonical_genesis(LOCAL_CHAIN_ID, {A: True})


def test_state_root_is_order_independent():
    assert state_root({A: 10, B: 20}) == state_root({B: 20, A: 10})


def test_state_root_commits_to_balance_and_nonce():
    baseline = state_root({A: 10, B: 20}, {A: 0, B: 0})
    assert baseline != state_root({A: 11, B: 20}, {A: 0, B: 0})
    assert baseline != state_root({A: 10, B: 20}, {A: 1, B: 0})


def test_empty_state_root_is_domain_separated_from_empty_transaction_root():
    assert state_root({}) != merkle_root([])


def test_state_root_rejects_nonce_for_unknown_account():
    with pytest.raises(EncodingError, match="absent"):
        state_root({A: 10}, {B: 1})


def test_merkle_root_empty_and_order_sensitive():
    empty = merkle_root([])
    assert len(empty) == 32
    x, y = bytes([1]) * 32, bytes([2]) * 32
    assert merkle_root([x, y]) != merkle_root([y, x])
    assert merkle_root([x]) != merkle_root([x, x])


def test_genesis_block_is_reproducible_and_self_verifying():
    first = create_genesis_block(LOCAL_CHAIN_ID, {B: 20, A: 10})
    second = create_genesis_block(LOCAL_CHAIN_ID, {A: 10, B: 20})
    assert first == second
    assert first["height"] == 0
    assert first["timestamp"] == 0
    assert first["previous_hash"] == ZERO_HASH
    assert verify_block_hash(first["header"], first["block_hash"])
    assert decode_block_header(first["header"])["state_root"] == first["state_root"]


def test_block_header_round_trip_and_hash_changes():
    header = canonical_block_header(
        LOCAL_CHAIN_ID, 1, 123, bytes([9]) * 32,
        merkle_root([]), state_root({A: 10}), 0
    )
    decoded = decode_block_header(header)
    assert decoded["height"] == 1
    digest = block_hash(header)
    assert verify_block_hash(header, digest)
    assert not verify_block_hash(header, bytes(32))


def test_block_hash_rejects_noncanonical_header():
    with pytest.raises(EncodingError):
        block_hash(b"not a canonical header")


def test_block_header_rejects_wrong_hash_width():
    with pytest.raises(EncodingError, match="32 bytes"):
        canonical_block_header(LOCAL_CHAIN_ID, 0, 0, b"bad", bytes(32), bytes(32), 0)


def test_genesis_and_block_hash_golden_vector():
    result = create_genesis_block(LOCAL_CHAIN_ID, {B: 20, A: 10})
    assert result["genesis_payload"].hex() == (
        "83025820484e442d4c4f43414c2d56320000000000000000000000000000000000000000"
        "8282582000000000000000000000000000000000000000000000000000000000000000010a"
        "825820000000000000000000000000000000000000000000000000000000000000000214"
    )
    assert result["genesis_id"].hex() == "5abf41e236488b231d109d1c0b5bddf4ae0bac2b4748e9e196cdd952d284876d"
    assert result["state_root"].hex() == "c319d4a7c593c436537410399a7a2f2b755e92ffdad4bfccb478eba5d401f92a"
    assert result["header"].hex() == (
        "88025820484e442d4c4f43414c2d563200000000000000000000000000000000"
        "0000000000005820000000000000000000000000000000000000000000000000"
        "00000000000000005820e915dc5e01273ce33c203835702fdf82ee0937b2baef"
        "7c8bd4e89dc012603eb95820c319d4a7c593c436537410399a7a2f2b755e92ff"
        "dad4bfccb478eba5d401f92a00"
    )
    assert len(result["header"]) == 141
    assert result["block_hash"].hex() == "de5c6f795a091c20b0a0f0e0ae2d73e4a0c66d3a00962deffd3dd3d7556bb3e9"


def test_transaction_merkle_root_golden_vector():
    txids = [bytes.fromhex("11" * 32), bytes.fromhex("22" * 32)]
    assert merkle_root(txids).hex() == "c1f4d8d5a11caf4898b7f48c7ccbec0e52c774ea7576cd2ef3b36d4521b40774"
