# HND v0.2 — ABCI evidence-handling boundary review and design

**Date:** 2026-11-04  
**Workstream:** WP4.10 — deterministic application handling of CometBFT misbehavior metadata  
**Pinned upstream:** CometBFT v0.40.0  
**Status:** Source review and design proposal; implementation not yet started or passed  
**Branch:** `phase-0.2-planning`

## 1. Finding

CometBFT v0.40.0 exposes validated block evidence to an ABCI++ application as `Misbehavior` summaries in `RequestFinalizeBlock.misbehavior` (and also in proposal-related requests). For duplicate-vote evidence, the summary contains the offending validator address, validator voting power, infraction height, infraction time, type, and total voting power. The full pair of signed votes is not carried in the ABCI `Misbehavior` summary.

The HND adapter currently ignores this field: `HNDCometBFTv040Servicer.FinalizeBlock` passes only height and transactions into `HNDABCIApplication.finalize_block`. The proposal adapter methods likewise pass transactions only. The HND application therefore does not currently persist or expose CometBFT misbehavior metadata.

This does not invalidate CometBFT's consensus-layer evidence tests. It is an application-boundary gap: consensus evidence detection and application-level evidence accounting are distinct responsibilities.

## 2. Pinned-source contract

The following v0.40.0 source contracts were inspected:

- `proto/tendermint/abci/types.proto`: `RequestFinalizeBlock` contains repeated `Misbehavior misbehavior`; `Misbehavior` includes type, validator address/power, infraction height/time, and total voting power.
- `proto/tendermint/types/evidence.proto`: CometBFT's internal evidence contains either `DuplicateVoteEvidence` (two signed votes, total voting power, validator power, timestamp) or `LightClientAttackEvidence`.
- `types/evidence.go`: evidence exposes `ABCI()`, which produces the summary supplied to the application.
- `consensus/byzantine_test.go:TestByzantinePrevoteEquivocation`: the pinned upstream test sends two signed conflicting votes over the ordinary P2P VoteChannel and waits for duplicate-vote evidence to be committed in blocks.

CometBFT's evidence pool buffers conflicting vote pairs before the infraction height is finalized, then forms evidence as consensus advances. The application receives the ABCI summary after CometBFT has formed and validated the evidence; it does not receive the complete signed vote pair through the `Misbehavior` field.

## 3. HND application policy recommendation

HND v0.2 currently has no defined staking, bonded-validator ownership, delegation, unbonding, slashing, appeal, or governance policy. Therefore:

1. **Do not slash, burn, freeze, confiscate, or transfer HND balances because of a misbehavior record.** No such economic policy is currently specified.
2. Add a deterministic, append-only evidence audit journal to the HND application state.
3. Record only the ABCI fields supplied by the pinned CometBFT version: evidence type, validator address, validator power, infraction height, infraction timestamp, and total voting power.
4. Derive a stable record identifier from a canonical encoding of those fields. Reject malformed records and deduplicate identical records deterministically.
5. Include the journal in the application state commitment and durable-store integrity validation so all honest replicas derive the same app hash.
6. Expose read-only query access for audit records. Do not make the journal an authorization or automatic penalty mechanism.
7. Emit deterministic application events for newly recorded evidence only if the event format is specified and tested; events must not affect state-transition results.

This is a proposed neutral audit policy, not a user-approved slashing or governance rule. Any later economic consequence requires a separate protocol specification and legal/security review.

## 4. Required validation rules

The adapter/application boundary should reject malformed ABCI misbehavior summaries, including:

- unknown or unsupported enum values;
- empty or incorrectly sized validator addresses;
- non-positive validator or total voting power;
- validator power greater than total voting power;
- non-positive infraction height or an infraction height not earlier than the block being finalized;
- missing or invalid timestamps;
- duplicate entries with conflicting metadata for the same canonical evidence identifier.

The exact validator-address length and timestamp conversion must be derived from the pinned generated protobuf types and CometBFT address contract, not guessed.

## 5. Implementation plan

1. Add typed normalization for the pinned Python protobuf `Misbehavior` values in the ABCI adapter.
2. Extend `HNDABCIApplication.finalize_block` to accept a list of normalized evidence records.
3. Define the canonical journal schema, ordering, identifier, and duplicate semantics.
4. Include the journal in snapshots, state hash, durable store schema, load validation, and read-only query.
5. Add tests for duplicate-vote metadata, unsupported evidence types, malformed addresses/power/heights/timestamps, deterministic ordering, duplicate handling, state-hash changes, persistence/reload, and no economic balance changes.
6. Add an ABCI adapter test proving `RequestFinalizeBlock.misbehavior` reaches the application and is committed.
7. Add an integration test proving CometBFT evidence in a committed block reaches the HND ABCI adapter and appears in the deterministic journal.
8. Rerun the complete existing HND and CometBFT CI workflow.

## 6. Explicit non-goals

- No slashing, burning, freezing, validator punishment, or balance modification.
- No claim that the HND application can independently verify the full signed vote pair from the ABCI summary.
- No replacement of CometBFT's evidence verification or consensus logic.
- No public network, production keys, real-value transactions, or mainnet deployment.
- No formal Byzantine fault-tolerance proof or security certification.

## 7. Acceptance criteria

WP4.10 can be marked passed only when:
- evidence summaries are deterministically normalized and validated;
- the same evidence set produces the same application hash on every replica;
- evidence is persisted and survives restart;
- identical evidence cannot inflate the journal count;
- malformed evidence fails closed;
- balances and supply remain unchanged by the neutral audit policy;
- an end-to-end CometBFT-to-HND ABCI test demonstrates the metadata flow;
- full CI completes successfully on the development branch.

---

This is a source review and design proposal, not a security certification, legal opinion, economic penalty rule, or authorization to issue or trade HND.
