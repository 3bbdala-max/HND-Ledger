import threading

import cbor2
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.protocol import canonical_cbor
from hnd_ledger.rollback_checkpoint import (
    CHECKPOINT_DOMAIN,
    CheckpointError,
    RollbackCheckpoint,
    SignedRollbackCheckpoint,
    sign_checkpoint,
    validate_successor,
    verify_signed_checkpoint,
)


def make_checkpoint(*, sequence=1, height=0, chain_id=b"C" * 32, genesis=b"G" * 32):
    return RollbackCheckpoint(
        chain_id=chain_id,
        genesis_hash=genesis,
        height=height,
        block_hash=bytes([height % 256]) * 32,
        app_hash=b"A" * 32,
        sequence=sequence,
    )


def test_checkpoint_round_trip_is_canonical():
    checkpoint = make_checkpoint()
    encoded = checkpoint.encode()
    assert RollbackCheckpoint.decode(encoded) == checkpoint
    assert canonical_cbor(cbor2.loads(encoded)) == encoded
    assert checkpoint.digest == make_checkpoint().digest


def test_checkpoint_rejects_boolean_and_invalid_numeric_fields():
    with pytest.raises(CheckpointError, match="height must be an integer"):
        make_checkpoint(height=True)
    with pytest.raises(CheckpointError, match="sequence must be an integer"):
        make_checkpoint(sequence=True)
    with pytest.raises(CheckpointError, match="outside the uint64 range"):
        make_checkpoint(height=1 << 64)


def test_checkpoint_rejects_wrong_hash_lengths_and_version():
    with pytest.raises(CheckpointError, match="chain_id must be exactly 32 bytes"):
        RollbackCheckpoint(b"x", b"G" * 32, 0, b"B" * 32, b"A" * 32, 1)
    with pytest.raises(CheckpointError, match="unsupported checkpoint version"):
        RollbackCheckpoint(b"C" * 32, b"G" * 32, 0, b"B" * 32, b"A" * 32, 1, True)


def test_checkpoint_decode_rejects_wrong_domain_and_noncanonical_encoding():
    payload = [CHECKPOINT_DOMAIN, 1, b"C" * 32, b"G" * 32, 0, b"B" * 32, b"A" * 32, 1]
    wrong_domain = canonical_cbor(["OTHER", *payload[1:]])
    with pytest.raises(CheckpointError, match="domain mismatch"):
        RollbackCheckpoint.decode(wrong_domain)
    noncanonical = cbor2.dumps(payload, canonical=False)
    if noncanonical == canonical_cbor(payload):
        noncanonical += b"\\x00"
    with pytest.raises(CheckpointError):
        RollbackCheckpoint.decode(noncanonical)


def test_signed_checkpoint_round_trip_and_pinned_key_verification():
    key = Ed25519PrivateKey.generate()
    checkpoint = make_checkpoint()
    signed = sign_checkpoint(checkpoint, key)
    encoded = signed.encode()
    decoded = SignedRollbackCheckpoint.decode(encoded)
    assert decoded == signed
    assert verify_signed_checkpoint(encoded, signed.public_key) == checkpoint


def test_signed_checkpoint_rejects_tampering_and_untrusted_signer():
    key = Ed25519PrivateKey.generate()
    other_key = Ed25519PrivateKey.generate()
    signed = sign_checkpoint(make_checkpoint(), key)
    with pytest.raises(CheckpointError, match="not trusted"):
        verify_signed_checkpoint(signed, other_key.public_key().public_bytes_raw())
    tampered = SignedRollbackCheckpoint(
        checkpoint=make_checkpoint(height=1),
        public_key=signed.public_key,
        signature=signed.signature,
    )
    with pytest.raises(CheckpointError, match="signature verification failed"):
        verify_signed_checkpoint(tampered, signed.public_key)
    damaged_signature = signed.signature[:-1] + bytes([signed.signature[-1] ^ 1])
    damaged = SignedRollbackCheckpoint(signed.checkpoint, signed.public_key, damaged_signature)
    with pytest.raises(CheckpointError, match="signature verification failed"):
        verify_signed_checkpoint(damaged, signed.public_key)


def test_signed_checkpoint_encoding_rejects_bad_envelope():
    raw = canonical_cbor(["WRONG-ENVELOPE", 1, make_checkpoint().encode(), b"K" * 32, b"S" * 64])
    with pytest.raises(CheckpointError, match="envelope domain mismatch"):
        SignedRollbackCheckpoint.decode(raw)


def test_successor_requires_same_identity_and_monotonic_sequence_and_height():
    current = make_checkpoint(sequence=1, height=4)
    validate_successor(current, make_checkpoint(sequence=2, height=5))
    with pytest.raises(CheckpointError, match="next value"):
        validate_successor(current, make_checkpoint(sequence=3, height=5))
    with pytest.raises(CheckpointError, match="height must advance"):
        validate_successor(current, make_checkpoint(sequence=2, height=4))
    with pytest.raises(CheckpointError, match="chain id changed"):
        validate_successor(current, make_checkpoint(sequence=2, height=5, chain_id=b"X" * 32))
    with pytest.raises(CheckpointError, match="genesis hash changed"):
        validate_successor(current, make_checkpoint(sequence=2, height=5, genesis=b"X" * 32))
    with pytest.raises(CheckpointError, match="first checkpoint sequence"):
        validate_successor(None, make_checkpoint(sequence=2))


class MemoryAuthorityForTest:
    """Test double only; deliberately volatile and not a production trust anchor."""

    def __init__(self, trusted_public_key):
        self.trusted_public_key = trusted_public_key
        self.raw = None
        self.lock = threading.Lock()

    def read(self, chain_id, genesis_hash):
        with self.lock:
            if self.raw is None:
                return None
            checkpoint = verify_signed_checkpoint(self.raw, self.trusted_public_key)
            if checkpoint.chain_id != chain_id or checkpoint.genesis_hash != genesis_hash:
                raise CheckpointError("authority record belongs to another chain")
            return self.raw

    def compare_and_swap(self, *, expected_sequence, expected_digest, new_checkpoint):
        candidate = verify_signed_checkpoint(new_checkpoint, self.trusted_public_key)
        with self.lock:
            current = None if self.raw is None else verify_signed_checkpoint(
                self.raw, self.trusted_public_key
            )
            if current is None:
                if expected_sequence is not None or expected_digest is not None:
                    return False
            else:
                if expected_sequence != current.sequence or expected_digest != current.digest:
                    return False
            validate_successor(current, candidate)
            self.raw = new_checkpoint
            return True


def test_memory_authority_accepts_one_successor_and_rejects_replay_or_conflict():
    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    authority = MemoryAuthorityForTest(public_key)
    first = sign_checkpoint(make_checkpoint(), key).encode()
    assert authority.compare_and_swap(
        expected_sequence=None, expected_digest=None, new_checkpoint=first
    )
    current = RollbackCheckpoint.decode(
        SignedRollbackCheckpoint.decode(authority.read(b"C" * 32, b"G" * 32)).checkpoint.encode()
    )
    second = sign_checkpoint(make_checkpoint(sequence=2, height=1), key).encode()
    assert authority.compare_and_swap(
        expected_sequence=current.sequence,
        expected_digest=current.digest,
        new_checkpoint=second,
    )
    assert not authority.compare_and_swap(
        expected_sequence=1, expected_digest=current.digest, new_checkpoint=first
    )
    conflicting = sign_checkpoint(make_checkpoint(sequence=2, height=2), key).encode()
    assert not authority.compare_and_swap(
        expected_sequence=1, expected_digest=current.digest, new_checkpoint=conflicting
    )


def test_memory_authority_compare_and_swap_allows_only_one_concurrent_successor():
    key = Ed25519PrivateKey.generate()
    authority = MemoryAuthorityForTest(key.public_key().public_bytes_raw())
    first = sign_checkpoint(make_checkpoint(), key).encode()
    assert authority.compare_and_swap(
        expected_sequence=None, expected_digest=None, new_checkpoint=first
    )
    current = SignedRollbackCheckpoint.decode(authority.read(b"C" * 32, b"G" * 32)).checkpoint
    candidates = [
        sign_checkpoint(make_checkpoint(sequence=2, height=1), key).encode(),
        sign_checkpoint(make_checkpoint(sequence=2, height=2), key).encode(),
    ]
    results = []
    threads = [
        threading.Thread(target=lambda raw=raw: results.append(authority.compare_and_swap(
            expected_sequence=current.sequence,
            expected_digest=current.digest,
            new_checkpoint=raw,
        )))
        for raw in candidates
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [False, True]
