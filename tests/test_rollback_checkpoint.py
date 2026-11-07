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
                # The authority may have committed the candidate while the
                # acknowledgement was lost. An exact retry is idempotent;
                # a different candidate with stale CAS values is rejected.
                if candidate.digest == current.digest:
                    return True
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



def test_checkpoint_signature_domain_uses_a_real_zero_byte_separator():
    from hnd_ledger.rollback_checkpoint import CHECKPOINT_SIGNATURE_DOMAIN

    assert CHECKPOINT_SIGNATURE_DOMAIN.endswith(bytes([0]))
    assert b"\\\\x00" not in CHECKPOINT_SIGNATURE_DOMAIN


def test_assess_local_tip_requires_exact_checkpoint_match_for_writes():
    from hnd_ledger.rollback_checkpoint import (
        CheckpointRelation,
        assess_local_tip,
    )

    checkpoint = make_checkpoint(sequence=3, height=7)
    common = {
        "chain_id": checkpoint.chain_id,
        "genesis_hash": checkpoint.genesis_hash,
        "block_hash": checkpoint.block_hash,
        "app_hash": checkpoint.app_hash,
    }

    unanchored = assess_local_tip(None, **{**common, "height": 7})
    assert unanchored.relation is CheckpointRelation.UNANCHORED
    assert not unanchored.writes_allowed

    matched = assess_local_tip(checkpoint, **{**common, "height": 7})
    assert matched.relation is CheckpointRelation.MATCH
    assert matched.writes_allowed

    behind = assess_local_tip(checkpoint, **{**common, "height": 6})
    assert behind.relation is CheckpointRelation.LOCAL_BEHIND
    assert not behind.writes_allowed

    ahead = assess_local_tip(checkpoint, **{**common, "height": 8})
    assert ahead.relation is CheckpointRelation.LOCAL_AHEAD_UNVERIFIED
    assert not ahead.writes_allowed
    assert "explicit recovery" in ahead.reason

    diverged = assess_local_tip(
        checkpoint,
        **{**common, "height": 7, "block_hash": b"X" * 32},
    )
    assert diverged.relation is CheckpointRelation.DIVERGED
    assert not diverged.writes_allowed


def test_assess_local_tip_rejects_wrong_chain_genesis_and_malformed_local_values():
    from hnd_ledger.rollback_checkpoint import assess_local_tip

    checkpoint = make_checkpoint(height=7)
    args = {
        "chain_id": checkpoint.chain_id,
        "genesis_hash": checkpoint.genesis_hash,
        "height": 7,
        "block_hash": checkpoint.block_hash,
        "app_hash": checkpoint.app_hash,
    }
    with pytest.raises(CheckpointError, match="chain id"):
        assess_local_tip(checkpoint, **{**args, "chain_id": b"X" * 32})
    with pytest.raises(CheckpointError, match="genesis hash"):
        assess_local_tip(checkpoint, **{**args, "genesis_hash": b"X" * 32})
    with pytest.raises(CheckpointError, match="local height must be an integer"):
        assess_local_tip(checkpoint, **{**args, "height": True})



def test_ahead_local_chain_must_match_checkpoint_ancestor_before_recovery():
    from hnd_ledger.rollback_checkpoint import (
        CheckpointRelation,
        assess_local_tip,
    )

    checkpoint = make_checkpoint(sequence=4, height=9)
    args = {
        "chain_id": checkpoint.chain_id,
        "genesis_hash": checkpoint.genesis_hash,
        "height": 12,
        "block_hash": b"L" * 32,
        "app_hash": b"M" * 32,
    }

    without_ancestor = assess_local_tip(checkpoint, **args)
    assert without_ancestor.relation is CheckpointRelation.LOCAL_AHEAD_UNVERIFIED
    assert not without_ancestor.writes_allowed

    matching_ancestor = assess_local_tip(
        checkpoint,
        **args,
        checkpoint_ancestor_block_hash=checkpoint.block_hash,
        checkpoint_ancestor_app_hash=checkpoint.app_hash,
    )
    assert matching_ancestor.relation is CheckpointRelation.LOCAL_AHEAD_UNVERIFIED
    assert "ancestry matches" in matching_ancestor.reason
    assert not matching_ancestor.writes_allowed

    wrong_block_ancestor = assess_local_tip(
        checkpoint,
        **args,
        checkpoint_ancestor_block_hash=b"X" * 32,
        checkpoint_ancestor_app_hash=checkpoint.app_hash,
    )
    assert wrong_block_ancestor.relation is CheckpointRelation.DIVERGED
    assert not wrong_block_ancestor.writes_allowed

    wrong_app_ancestor = assess_local_tip(
        checkpoint,
        **args,
        checkpoint_ancestor_block_hash=checkpoint.block_hash,
        checkpoint_ancestor_app_hash=b"Y" * 32,
    )
    assert wrong_app_ancestor.relation is CheckpointRelation.DIVERGED
    assert not wrong_app_ancestor.writes_allowed


def test_checkpoint_ancestor_commitments_must_be_supplied_as_a_pair():
    from hnd_ledger.rollback_checkpoint import assess_local_tip

    checkpoint = make_checkpoint()
    with pytest.raises(CheckpointError, match="supplied together"):
        assess_local_tip(
            checkpoint,
            chain_id=checkpoint.chain_id,
            genesis_hash=checkpoint.genesis_hash,
            height=2,
            block_hash=b"B" * 32,
            app_hash=b"A" * 32,
            checkpoint_ancestor_block_hash=checkpoint.block_hash,
        )



def test_memory_authority_compare_and_swap_retry_is_idempotent_after_lost_ack():
    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    authority = MemoryAuthorityForTest(public_key)
    first = sign_checkpoint(make_checkpoint(), key).encode()
    assert authority.compare_and_swap(
        expected_sequence=None, expected_digest=None, new_checkpoint=first
    )
    first_checkpoint = SignedRollbackCheckpoint.decode(first).checkpoint
    second = sign_checkpoint(make_checkpoint(sequence=2, height=1), key).encode()

    # First request is durably accepted; imagine the response was lost.
    assert authority.compare_and_swap(
        expected_sequence=first_checkpoint.sequence,
        expected_digest=first_checkpoint.digest,
        new_checkpoint=second,
    )
    # Retrying the exact same signed checkpoint with the original CAS token
    # must report success without creating another sequence or conflicting tip.
    assert authority.compare_and_swap(
        expected_sequence=first_checkpoint.sequence,
        expected_digest=first_checkpoint.digest,
        new_checkpoint=second,
    )
    stored = SignedRollbackCheckpoint.decode(
        authority.read(b"C" * 32, b"G" * 32)
    ).checkpoint
    assert stored == SignedRollbackCheckpoint.decode(second).checkpoint
    assert stored.sequence == 2


def test_memory_authority_stale_cas_does_not_accept_different_candidate():
    key = Ed25519PrivateKey.generate()
    authority = MemoryAuthorityForTest(key.public_key().public_bytes_raw())
    first = sign_checkpoint(make_checkpoint(), key).encode()
    assert authority.compare_and_swap(
        expected_sequence=None, expected_digest=None, new_checkpoint=first
    )
    checkpoint = SignedRollbackCheckpoint.decode(first).checkpoint
    accepted = sign_checkpoint(make_checkpoint(sequence=2, height=1), key).encode()
    conflicting = sign_checkpoint(make_checkpoint(sequence=2, height=2), key).encode()
    assert authority.compare_and_swap(
        expected_sequence=checkpoint.sequence,
        expected_digest=checkpoint.digest,
        new_checkpoint=accepted,
    )
    assert not authority.compare_and_swap(
        expected_sequence=checkpoint.sequence,
        expected_digest=checkpoint.digest,
        new_checkpoint=conflicting,
    )



def test_signed_checkpoint_rejects_invalid_direct_payload_type():
    with pytest.raises(CheckpointError, match="payload has an invalid type"):
        SignedRollbackCheckpoint(
            checkpoint="not-a-checkpoint",
            public_key=b"K" * 32,
            signature=b"S" * 64,
        )



def test_read_and_assess_checkpoint_authenticates_authority_record():
    from hnd_ledger.rollback_checkpoint import (
        CheckpointRelation,
        read_and_assess_checkpoint,
    )

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    checkpoint = make_checkpoint(height=5)
    authority = MemoryAuthorityForTest(public_key)
    raw = sign_checkpoint(checkpoint, key).encode()
    assert authority.compare_and_swap(
        expected_sequence=None, expected_digest=None, new_checkpoint=raw
    )

    assessment = read_and_assess_checkpoint(
        authority,
        public_key,
        chain_id=checkpoint.chain_id,
        genesis_hash=checkpoint.genesis_hash,
        height=checkpoint.height,
        block_hash=checkpoint.block_hash,
        app_hash=checkpoint.app_hash,
    )
    assert assessment.relation is CheckpointRelation.MATCH
    assert assessment.writes_allowed


def test_read_and_assess_checkpoint_missing_record_is_unanchored_and_fails_closed():
    from hnd_ledger.rollback_checkpoint import (
        CheckpointRelation,
        read_and_assess_checkpoint,
    )

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    checkpoint = make_checkpoint(height=0)
    authority = MemoryAuthorityForTest(public_key)

    assessment = read_and_assess_checkpoint(
        authority,
        public_key,
        chain_id=checkpoint.chain_id,
        genesis_hash=checkpoint.genesis_hash,
        height=checkpoint.height,
        block_hash=checkpoint.block_hash,
        app_hash=checkpoint.app_hash,
    )
    assert assessment.relation is CheckpointRelation.UNANCHORED
    assert not assessment.writes_allowed


def test_read_and_assess_checkpoint_rejects_untrusted_authority_signature():
    from hnd_ledger.rollback_checkpoint import read_and_assess_checkpoint

    key = Ed25519PrivateKey.generate()
    wrong_key = Ed25519PrivateKey.generate()
    trusted_public_key = wrong_key.public_key().public_bytes_raw()
    authority = MemoryAuthorityForTest(
        key.public_key().public_bytes_raw()
    )
    checkpoint = make_checkpoint(height=0)
    raw = sign_checkpoint(checkpoint, key).encode()
    assert authority.compare_and_swap(
        expected_sequence=None, expected_digest=None, new_checkpoint=raw
    )

    with pytest.raises(CheckpointError, match="not trusted"):
        read_and_assess_checkpoint(
            authority,
            trusted_public_key,
            chain_id=checkpoint.chain_id,
            genesis_hash=checkpoint.genesis_hash,
            height=checkpoint.height,
            block_hash=checkpoint.block_hash,
            app_hash=checkpoint.app_hash,
        )


def test_read_and_assess_checkpoint_authority_outage_never_falls_back():
    from hnd_ledger.rollback_checkpoint import read_and_assess_checkpoint

    class UnavailableAuthority:
        def read(self, chain_id, genesis_hash):
            raise OSError("simulated authority outage")

        def compare_and_swap(self, **kwargs):
            raise AssertionError("read-only assessment must not write")

    checkpoint = make_checkpoint(height=0)
    with pytest.raises(CheckpointError, match="refusing unanchored fallback"):
        read_and_assess_checkpoint(
            UnavailableAuthority(),
            b"K" * 32,
            chain_id=checkpoint.chain_id,
            genesis_hash=checkpoint.genesis_hash,
            height=checkpoint.height,
            block_hash=checkpoint.block_hash,
            app_hash=checkpoint.app_hash,
        )


def test_read_and_assess_checkpoint_rejects_invalid_authority_record_type():
    from hnd_ledger.rollback_checkpoint import read_and_assess_checkpoint

    class InvalidRecordAuthority:
        def read(self, chain_id, genesis_hash):
            return "not-bytes"

        def compare_and_swap(self, **kwargs):
            return False

    checkpoint = make_checkpoint(height=0)
    with pytest.raises(CheckpointError, match="invalid record type"):
        read_and_assess_checkpoint(
            InvalidRecordAuthority(),
            b"K" * 32,
            chain_id=checkpoint.chain_id,
            genesis_hash=checkpoint.genesis_hash,
            height=checkpoint.height,
            block_hash=checkpoint.block_hash,
            app_hash=checkpoint.app_hash,
        )



def test_publish_checkpoint_advances_authority_with_monotonic_cas():
    from hnd_ledger.rollback_checkpoint import publish_checkpoint

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    authority = MemoryAuthorityForTest(public_key)
    first = sign_checkpoint(make_checkpoint(), key).encode()
    accepted_first = publish_checkpoint(authority, public_key, first)
    assert accepted_first.sequence == 1

    second = sign_checkpoint(make_checkpoint(sequence=2, height=1), key).encode()
    accepted_second = publish_checkpoint(authority, public_key, second)
    assert accepted_second.sequence == 2
    stored = SignedRollbackCheckpoint.decode(
        authority.read(b"C" * 32, b"G" * 32)
    ).checkpoint
    assert stored == accepted_second


def test_publish_checkpoint_exact_retry_is_idempotent():
    from hnd_ledger.rollback_checkpoint import publish_checkpoint

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    authority = MemoryAuthorityForTest(public_key)
    first = sign_checkpoint(make_checkpoint(), key).encode()
    publish_checkpoint(authority, public_key, first)
    second = sign_checkpoint(make_checkpoint(sequence=2, height=1), key).encode()

    assert publish_checkpoint(authority, public_key, second).sequence == 2
    # A lost local acknowledgement followed by the same publish call is safe.
    assert publish_checkpoint(authority, public_key, second).sequence == 2
    stored = SignedRollbackCheckpoint.decode(
        authority.read(b"C" * 32, b"G" * 32)
    ).checkpoint
    assert stored.sequence == 2


def test_publish_checkpoint_rejects_non_successor_and_conflicting_cas():
    from hnd_ledger.rollback_checkpoint import publish_checkpoint

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    authority = MemoryAuthorityForTest(public_key)
    first = sign_checkpoint(make_checkpoint(), key).encode()
    publish_checkpoint(authority, public_key, first)

    skipped = sign_checkpoint(make_checkpoint(sequence=3, height=2), key).encode()
    with pytest.raises(CheckpointError, match="next value"):
        publish_checkpoint(authority, public_key, skipped)

    class ConflictingAuthority(MemoryAuthorityForTest):
        def __init__(self, trusted_public_key):
            super().__init__(trusted_public_key)
            self.force_conflict = False

        def compare_and_swap(self, **kwargs):
            if self.force_conflict:
                return False
            return super().compare_and_swap(**kwargs)

    conflict_authority = ConflictingAuthority(public_key)
    publish_checkpoint(conflict_authority, public_key, first)
    conflict_authority.force_conflict = True
    conflicting = sign_checkpoint(make_checkpoint(sequence=2, height=2), key).encode()
    with pytest.raises(CheckpointError, match="compare-and-swap conflict"):
        publish_checkpoint(conflict_authority, public_key, conflicting)


def test_publish_checkpoint_fails_closed_when_authority_is_unavailable():
    from hnd_ledger.rollback_checkpoint import publish_checkpoint

    class UnavailableAuthority:
        def read(self, chain_id, genesis_hash):
            raise OSError("simulated outage")

        def compare_and_swap(self, **kwargs):
            raise AssertionError("must not write without a successful read")

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    candidate = sign_checkpoint(make_checkpoint(), key).encode()
    with pytest.raises(CheckpointError, match="read failed before publish"):
        publish_checkpoint(UnavailableAuthority(), public_key, candidate)



def test_publish_checkpoint_resolves_lost_ack_after_remote_commit():
    from hnd_ledger.rollback_checkpoint import publish_checkpoint

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()

    class CommitThenLoseAckAuthority(MemoryAuthorityForTest):
        def compare_and_swap(self, **kwargs):
            accepted = super().compare_and_swap(**kwargs)
            if accepted:
                raise OSError("simulated lost acknowledgement after commit")
            return accepted

    authority = CommitThenLoseAckAuthority(public_key)
    candidate = sign_checkpoint(make_checkpoint(), key).encode()
    accepted = publish_checkpoint(authority, public_key, candidate)
    assert accepted == SignedRollbackCheckpoint.decode(candidate).checkpoint
    stored = SignedRollbackCheckpoint.decode(
        authority.read(b"C" * 32, b"G" * 32)
    ).checkpoint
    assert stored == accepted


def test_publish_checkpoint_reports_unknown_outcome_if_cas_throws_without_commit():
    from hnd_ledger.rollback_checkpoint import publish_checkpoint

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()

    class FailBeforeCommitAuthority(MemoryAuthorityForTest):
        def compare_and_swap(self, **kwargs):
            raise OSError("simulated request failure before commit")

    authority = FailBeforeCommitAuthority(public_key)
    candidate = sign_checkpoint(make_checkpoint(), key).encode()
    with pytest.raises(CheckpointError, match="outcome is unknown"):
        publish_checkpoint(authority, public_key, candidate)



def test_publish_checkpoint_resolves_false_cas_when_candidate_is_already_stored():
    from hnd_ledger.rollback_checkpoint import publish_checkpoint

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()

    class CommitButReturnFalseAuthority(MemoryAuthorityForTest):
        def compare_and_swap(self, **kwargs):
            accepted = super().compare_and_swap(**kwargs)
            # Simulate an ambiguous provider response after durable acceptance.
            return False if accepted else False

    authority = CommitButReturnFalseAuthority(public_key)
    candidate = sign_checkpoint(make_checkpoint(), key).encode()
    accepted = publish_checkpoint(authority, public_key, candidate)
    assert accepted == SignedRollbackCheckpoint.decode(candidate).checkpoint
    stored = SignedRollbackCheckpoint.decode(
        authority.read(b"C" * 32, b"G" * 32)
    ).checkpoint
    assert stored == accepted



def test_assess_local_chain_accepts_exact_trusted_genesis_match(tmp_path):
    from hnd_ledger.chain import LocalChain, state_commitment
    from hnd_ledger.rollback_checkpoint import (
        CheckpointRelation,
        RollbackCheckpoint,
        assess_local_chain,
        sign_checkpoint,
    )
    from hnd_ledger.state import LedgerState

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    authority = MemoryAuthorityForTest(public_key)
    chain = LocalChain(tmp_path / "assess-local-genesis.sqlite", LedgerState(supply_cap=100))
    genesis_hash, _ = chain.checkpoint_ancestor_commitments(0)
    checkpoint = RollbackCheckpoint(
        chain_id=chain.state.chain_id,
        genesis_hash=genesis_hash,
        height=0,
        block_hash=genesis_hash,
        app_hash=state_commitment(chain.state),
        sequence=1,
    )
    raw = sign_checkpoint(checkpoint, key).encode()
    assert authority.compare_and_swap(
        expected_sequence=None, expected_digest=None, new_checkpoint=raw
    )

    assessment = assess_local_chain(authority, public_key, chain)
    assert assessment.relation is CheckpointRelation.MATCH
    assert assessment.writes_allowed
    chain.close()


def test_assess_local_chain_detects_behind_and_ahead_states(tmp_path):
    from hnd_ledger.chain import LocalChain
    from hnd_ledger.protocol import create_transaction
    from hnd_ledger.rollback_checkpoint import (
        CheckpointRelation,
        RollbackCheckpoint,
        assess_local_chain,
        sign_checkpoint,
    )
    from hnd_ledger.state import LedgerState

    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id = account_id(alice.public_key().public_bytes_raw())
    bob_id = account_id(bob.public_key().public_bytes_raw())
    initial = LedgerState(balances={alice_id: 20}, supply_cap=20)

    source_chain = LocalChain(tmp_path / "source-ahead.sqlite", initial)
    genesis_hash, _ = source_chain.checkpoint_ancestor_commitments(0)
    block = source_chain.append([create_transaction(alice, bob_id, 5, 0)])
    checkpoint = RollbackCheckpoint(
        chain_id=source_chain.state.chain_id,
        genesis_hash=genesis_hash,
        height=block.height,
        block_hash=block.block_hash,
        app_hash=block.state_root,
        sequence=1,
    )
    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    authority = MemoryAuthorityForTest(public_key)
    raw = sign_checkpoint(checkpoint, key).encode()
    assert authority.compare_and_swap(
        expected_sequence=None, expected_digest=None, new_checkpoint=raw
    )

    behind_chain = LocalChain(tmp_path / "local-behind.sqlite", initial)
    behind = assess_local_chain(authority, public_key, behind_chain)
    assert behind.relation is CheckpointRelation.LOCAL_BEHIND
    assert not behind.writes_allowed
    behind_chain.close()

    source_chain.append([create_transaction(alice, bob_id, 2, 1)])
    ahead = assess_local_chain(authority, public_key, source_chain)
    assert ahead.relation is CheckpointRelation.LOCAL_AHEAD_UNVERIFIED
    assert "ancestry matches" in ahead.reason
    assert not ahead.writes_allowed
    source_chain.close()


def test_assess_local_chain_rejects_divergent_checkpoint_ancestor(tmp_path):
    from hnd_ledger.chain import LocalChain
    from hnd_ledger.protocol import create_transaction
    from hnd_ledger.rollback_checkpoint import (
        CheckpointRelation,
        RollbackCheckpoint,
        assess_local_chain,
        sign_checkpoint,
    )
    from hnd_ledger.state import LedgerState

    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id = account_id(alice.public_key().public_bytes_raw())
    bob_id = account_id(bob.public_key().public_bytes_raw())
    initial = LedgerState(balances={alice_id: 30}, supply_cap=30)

    trusted_chain = LocalChain(tmp_path / "trusted-fork.sqlite", initial)
    genesis_hash, _ = trusted_chain.checkpoint_ancestor_commitments(0)
    trusted_block = trusted_chain.append([create_transaction(alice, bob_id, 5, 0)])
    checkpoint = RollbackCheckpoint(
        chain_id=trusted_chain.state.chain_id,
        genesis_hash=genesis_hash,
        height=1,
        block_hash=trusted_block.block_hash,
        app_hash=trusted_block.state_root,
        sequence=1,
    )
    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes_raw()
    authority = MemoryAuthorityForTest(public_key)
    raw = sign_checkpoint(checkpoint, key).encode()
    assert authority.compare_and_swap(
        expected_sequence=None, expected_digest=None, new_checkpoint=raw
    )

    divergent_chain = LocalChain(tmp_path / "divergent-fork.sqlite", initial)
    divergent_chain.append([create_transaction(alice, bob_id, 6, 0)])
    divergent_chain.append([create_transaction(alice, bob_id, 1, 1)])
    assessment = assess_local_chain(authority, public_key, divergent_chain)
    assert assessment.relation is CheckpointRelation.DIVERGED
    assert not assessment.writes_allowed
    trusted_chain.close()
    divergent_chain.close()
