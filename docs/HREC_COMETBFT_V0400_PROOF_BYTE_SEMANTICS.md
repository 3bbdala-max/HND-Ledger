# CometBFT v0.40.0 Proof and Byte Semantics — Source Review

Status: source-grounded engineering note, not a frozen HREC wire protocol.

This note records the upstream `cometbft/cometbft` source behavior at tag `v0.40.0`. It narrows the required HREC proof verifier and artifact collector. It does not implement either component.

## 1. Block bytes, block hash, and PartSetHeader are distinct

The pinned source establishes this sequence:

1. `types.Block.ToProto()` converts the native block to `proto/tendermint/types.Block`.
2. `types.Block.MakePartSet(partSize)` serializes that protobuf using the CometBFT-imported `github.com/cosmos/gogoproto/proto.Marshal`.
3. The serialized bytes are split into parts by `NewPartSetFromData`; the resulting Merkle commitment is the PartSetHeader.
4. `types.Header.Hash()` independently computes the block hash as a Merkle hash over 14 canonical header-field encodings in fixed order.

Therefore the artifact verifier must reconstruct the complete block, reproduce the pinned serialization and part splitting, compare the complete PartSetHeader (total and hash), and independently recompute the Header hash. A block hash alone does not prove the PartSetHeader, and a protobuf byte digest is not the block hash.

The protobuf schema in `proto/tendermint/types/block.proto` defines Block fields in this order: Header=1, Data=2, EvidenceList=3, LastCommit=4.

## 2. Header hash construction

In `types/block.go`, `Header.Hash()` uses:

- consensus version's `Marshal()`;
- canonical protobuf timestamp encoding for header time;
- protobuf encoding of the complete BlockID;
- CometBFT canonical encodings for chain ID, height, hashes, and proposer address;
- `merkle.HashFromByteSlices` over the 14 field encodings in header field order.

The header hash must be recomputed by the pinned CometBFT implementation. Do not substitute SHA-256 of JSON, protobuf Header bytes, or a local re-encoding.

## 3. Validator-set commitment

`ValidatorSet.Hash()` Merkle-hashes the ordered `Validator.Bytes()` values. `Validator.Bytes()` serializes a protobuf `SimpleValidator` containing public key and voting power. It intentionally excludes the redundant validator address and proposer priority.

The proof artifact must nevertheless retain the complete validator set, including addresses, public keys, voting powers, ordering, and proposer information, so the supplied set can be reconstructed and its hash compared with the header's ValidatorsHash. The protobuf ValidatorSet is not itself the consensus hash input; its ToProto conversion also sets TotalVotingPower to zero for compatibility with hash use.

Relevant source: `types/validator.go`, `types/validator_set.go`, and `proto/tendermint/types/validator.proto`.

## 4. Commit hash versus commit signature verification

The native Commit contains height, round, BlockID, and ordered CommitSig entries.

- `Commit.Hash()` Merkle-hashes protobuf-marshaled CommitSig entries. This contributes to Header.LastCommitHash.
- `Commit.VoteSignBytes()` converts a CommitSig into its precommit Vote and delegates to `VoteSignBytes(chainID, vote)`.
- `VoteSignBytes` canonicalizes the vote and uses length-delimited protobuf serialization. The canonical vote omits validator address, validator index, and vote-extension fields.

These are different operations. A matching Commit hash is not proof that validator signatures are valid. Signature verification must use the pinned v0.40.0 canonical vote sign bytes and validator public keys, or preferably the upstream light-client verification path.

Relevant source: `types/block.go`, `types/canonical.go`, and `types/vote.go`.

## 5. Evidence bytes versus ABCI Misbehavior

The native Evidence interface exposes both `Bytes()` and `ABCI()`. They are not interchangeable.

For DuplicateVoteEvidence:

- `Bytes()` returns its protobuf encoding; the evidence hash is derived from those bytes.
- `ABCI()` maps the evidence to ABCI Misbehavior containing duplicate-vote type, validator address and power, infraction height, timestamp, and total voting power.

The HREC execution-input artifact must preserve both the exact ordered native evidence objects from the block and the exact ordered ABCI Misbehavior records passed to HND FinalizeBlock. The verifier must reproduce the conversion using the pinned CometBFT implementation, then reproduce HND's normalized journal. It must review every supported evidence type separately; this note does not assume that DuplicateVoteEvidence covers all possible evidence.

Relevant source: `types/evidence.go`, `types/block.go`, and the v0.40.0 ABCI evidence conversion code.

## 6. Sequential light-client verification

The upstream `light/verifier.go` provides adjacent and non-adjacent verification.

- Adjacent verification checks that the new header's ValidatorsHash equals the new validator-set hash, that the trusted header's NextValidatorsHash equals the new header's ValidatorsHash, and that more than two-thirds of the new validator set signed the new commit.
- Non-adjacent verification additionally requires the configured trust level of the previously trusted validator set to have signed the new header, then verifies more than two-thirds of the new validator set.
- Both paths validate the trusted header's expiry, the new header, chain identity, time constraints, and validator-set hash.

HREC v1's initial profile is sequential. It must verify every intervening adjacent header using the upstream adjacent verifier. It must not silently take the non-adjacent path as a shortcut. Trusted root, trusted time, trusting period, and maximum clock drift must be explicit authenticated configuration.

## 7. Required implementation contract

The HREC proof artifact must contain retrievable signed-header, commit, validator-set, and trust-transition material. Its verifier must:

1. Reconstruct the full native CometBFT block from the pinned block-store representation.
2. Recompute block hash and complete PartSetHeader using the exact v0.40.0 implementation.
3. Validate the commit BlockID against that complete BlockID.
4. Verify the signed header and validator-set transitions through sequential light-client verification.
5. Verify the one-block application-hash relationship: `Header[h].AppHash == A[h-1]`.
6. Independently execute HND from the authenticated predecessor snapshot and exact block inputs to derive `A[h]`.

The artifact's digest and storage URI are references to bytes, not proof of their correctness. All checks above must be performed by the verifier.

## 8. Source files reviewed

Upstream tag `v0.40.0`:

- `types/block.go`
- `types/canonical.go`
- `types/part_set.go`
- `types/validator.go`
- `types/validator_set.go`
- `types/vote.go`
- `types/evidence.go`
- `types/protobuf.go`
- `light/verifier.go`
- `proto/tendermint/types/block.proto`
- `proto/tendermint/types/types.proto`
- `proto/tendermint/types/validator.proto`

The exact dependency graph, generated protobuf code, Go toolchain, and serialization behavior must be captured in the pinned implementation build identity and exercised by executable Go fixtures. This source review is not a substitute for those tests.
