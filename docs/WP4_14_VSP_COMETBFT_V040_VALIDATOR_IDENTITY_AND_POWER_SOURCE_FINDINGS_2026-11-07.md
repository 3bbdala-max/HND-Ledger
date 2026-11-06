# WP4.14 — CometBFT v0.40.0 Validator Identity and Voting-Power Source Findings

**Date:** 2026-11-07  
**Repository branch:** `phase-0.2-planning`  
**External source:** `github.com/cometbft/cometbft`, tag `v0.40.0`  
**Review type:** Read-only source inspection  
**Disposition:** Source facts established; VSP wire schema still requires consolidation and approval

## 1. Executive findings

The exact CometBFT v0.40.0 source establishes the following facts relevant to VSP:

1. The consensus validator object contains an address, a CometBFT public key and an `int64` voting power.
2. A CometBFT Ed25519 public key is exactly 32 raw bytes; its signature size is 64 bytes.
3. For Ed25519, CometBFT derives the validator address as the first 20 bytes of SHA-256 over the raw public-key bytes.
4. The validator-set maximum total voting power is `math.MaxInt64 / 8`, equal to `1,152,921,504,606,846,975`.
5. The validator-set total is recomputed with overflow-aware checks; a caller-provided total is not a trustworthy substitute.
6. The Genesis validator validation path checks public-key/address correspondence and fills an omitted address from the public key. A VSP verifier should be stricter: require an explicit canonical address and compare it to the independently derived value.
7. The current HND Genesis preflight invokes the pinned CometBFT Go types to parse the generated Genesis, but its HND-side Python code does not independently implement the CometBFT consensus address derivation.

These are upstream source facts. They do not establish a production validator roster, a final VSP schema, or launch readiness.

## 2. Source locations inspected

The following files were inspected at the immutable version tag reference `v0.40.0`:

- `types/validator.go`
  - `Validator` carries `Address`, `PubKey`, and `VotingPower int64`.
  - `NewValidator` sets its address from `pubKey.Address()`.
  - `ValidateBasic` recomputes the address and rejects mismatch.
- `crypto/ed25519/ed25519.go`
  - `PubKeySize = 32`.
  - `SignatureSize = 64`.
  - `PubKey.Address()` calls `tmhash.SumTruncated(pubKey)`.
- `crypto/tmhash/hash.go`
  - `TruncatedSize = 20`.
  - `SumTruncated` returns the first 20 bytes of SHA-256.
- `types/validator_set.go`
  - `MaxTotalVotingPower = int64(math.MaxInt64) / 8`.
  - `updateTotalVotingPower` accumulates using overflow-aware addition and rejects totals above the maximum.
  - The source notes that a validator-set total supplied by another peer must not be trusted without recomputation.
- `crypto/encoding/codec.go`
  - CometBFT maps Ed25519 public keys to its protobuf public-key representation and validates the raw key length when decoding.
- `types/genesis.go`
  - Genesis validator records use an address, a CometBFT public key and an `int64` power.
  - Genesis validation checks that a supplied address corresponds to the public key and fills it if omitted.

## 3. Exact identity derivation

For a raw Ed25519 public key `K` of exactly 32 bytes:

```text
A = SHA-256(K)[0:20]
```

Here `A` is 20 raw bytes. The VSP's display encoding must be specified separately from the cryptographic derivation.

**Recommended VSP representation:** encode the 20 address bytes as exactly 40 lowercase hexadecimal characters. During verification:
1. Decode the VSP's 40-character lowercase hex string to exactly 20 bytes.
2. Decode the public key from canonical Base64 to exactly 32 bytes.
3. Calculate SHA-256 over those 32 raw key bytes.
4. Take the first 20 digest bytes.
5. Compare the resulting raw 20 bytes with the decoded VSP address.
6. Compare the same identity with the actual CometBFT Genesis validator address after decoding its source-defined textual representation.

The VSP should sort validator records by the 20 raw address bytes, not by a locale-sensitive string comparison. This yields a single bytewise order independent of uppercase/lowercase display conventions.

The CometBFT Genesis JSON representation is its own serialization contract. Do not assume its address text casing or public-key JSON type/value wrapper is identical to the VSP representation. The bridge must decode both into typed raw values and compare those values.

## 4. Voting-power constraints

The upstream maximum is:

```text
MaxTotalVotingPower = floor((2^63 - 1) / 8)
                     = 1,152,921,504,606,846,975
```

For VSP schema v1, the implementation should:
- accept only positive integral voting powers for active validator entries;
- reject booleans, floating-point tokens, exponent notation, strings and negative values;
- reject any individual power greater than `MaxTotalVotingPower`;
- sum using checked arithmetic and reject a total greater than `MaxTotalVotingPower`;
- require exact equality between the declared total and the recomputed sum;
- reject empty validator sets;
- compare every validator's public key, derived address and power against the actual CometBFT Genesis validator set.

This source limit is much lower than the VSP drafts' generic `2^53-1` JSON-safe integer ceiling. Therefore the validator power and total-power fields must use the stricter CometBFT bound. Other VSP integer fields may retain a separately justified bound, but must not inherit the voting-power bound by accident.

## 5. Important distinctions

- CometBFT's validator address is derived from the consensus public key. It is not an HND account ID or P2P node ID.
- CometBFT consensus keys are not governance signing keys.
- The VSP governance Ed25519 signature scheme may use the same algorithm family, but must use a separate keyset and domain-separated message.
- A matching key/address pair does not prove operator identity, independent custody, geographic diversity or absence of shared infrastructure.
- A valid Genesis parser result does not prove that the node is using the approved binary or the approved runtime profile.
- A correct total voting power does not prove decentralization. Coalition and operator-control analysis remains a separate governance gate.

## 6. Implications for the consolidated VSP contract

The single normative VSP v1 contract should freeze these rules:

1. Consensus key type is the exact literal `ed25519` for the initial v1 profile. Other CometBFT key families must be rejected unless separately specified and reviewed.
2. Consensus public key is canonical Base64 of exactly 32 raw bytes.
3. VSP address is 40 lowercase hexadecimal characters representing the 20 raw derived address bytes.
4. Address derivation is `SHA-256(raw_public_key)[0:20]`.
5. Validator array order is ascending bytewise order of the decoded 20-byte addresses.
6. Voting power is a positive integer no greater than the upstream maximum; total is checked and bounded by the same upstream maximum.
7. Every VSP validator entry must match one and only one Genesis validator by raw public-key bytes, derived address bytes and voting power.
8. The VSP's canonical representation and the CometBFT Genesis JSON representation remain separate formats; compare decoded typed values rather than assuming byte-identical subdocuments.

These are proposed VSP requirements based on upstream implementation facts. The complete wire schema and signature contract remain subject to consolidation and explicit approval.

## 7. HND repository gap and future acceptance tests

The existing `scripts/cometbft_v040_four_validator_genesis_preflight.py`:
- reads CometBFT-generated temporary consensus keys;
- checks that validator addresses and public keys are present and unique;
- passes the generated Genesis to the Go helper compiled against the supplied CometBFT v0.40.0 source.

The current Go helper checks that Genesis parses and contains four validators. This is useful upstream validation but does not compare the full roster to a VSP contract because no VSP verifier exists yet.

Proposed tests, not implemented or executed:

| ID | Case | Expected result |
|---|---|---|
| CMT-VSP-ID-01 | Correct 32-byte Ed25519 key and derived address | Accept identity pair |
| CMT-VSP-ID-02 | One-bit public-key substitution | Reject address mismatch |
| CMT-VSP-ID-03 | Address altered independently | Reject |
| CMT-VSP-ID-04 | 31-byte or 33-byte public key | Reject |
| CMT-VSP-ID-05 | Uppercase or malformed VSP address hex | Reject VSP canonical encoding |
| CMT-VSP-ID-06 | Two entries with same raw key | Reject duplicate key |
| CMT-VSP-ID-07 | Two entries with same derived address | Reject duplicate address |
| CMT-VSP-ID-08 | Validator array not sorted by raw address bytes | Reject noncanonical ordering |
| CMT-VSP-PWR-01 | Power zero, negative, bool, float or string | Reject |
| CMT-VSP-PWR-02 | Individual power exceeds upstream maximum | Reject |
| CMT-VSP-PWR-03 | Sum exceeds upstream maximum | Reject |
| CMT-VSP-PWR-04 | Declared total differs from checked sum | Reject |
| CMT-VSP-BIND-01 | VSP roster omits a Genesis validator | Reject |
| CMT-VSP-BIND-02 | VSP adds a validator absent from Genesis | Reject |
| CMT-VSP-BIND-03 | Same roster count but one changed key/address/power | Reject |
| CMT-VSP-BIND-04 | Same raw key/address/power in different display casing | Compare decoded values; reject noncanonical VSP spelling |

## 8. Verification limitations and disposition

This was read-only inspection of upstream source at tag `v0.40.0` and HND repository files. No HND source, tests, workflows, dependencies, Genesis, keys, profiles or runtime configuration were modified. No new Go build or test was run as part of this source review.

The CI run previously observed for commit `bf81942333dc3234774d88fe57ebf1329ec88a4b` is not a run for the current branch head and was still in progress at the last status check. It must not be described as validation of this report or the newer documentation commit.

**Disposition: SOURCE FACTS DOCUMENTED — VSP CONTRACT STILL NOT FROZEN — NO GOLDEN VECTORS GENERATED — NOT APPROVED FOR PRODUCTION.**
