# WP4.14 — Config-v1 Decision Register and Recommended Resolutions

**Date:** 2026-11-05  
**Status:** Proposal for review — no decision is treated as approved  
**Branch:** `phase-0.2-planning`  
**Baseline commit:** `9798db9f51eb5d60776b43452685709dbfaf2998`

## 1. Purpose

This register converts the open Config-v1 design questions into explicit, reviewable proposals. Each entry includes:

- the decision that must be made;
- a recommended candidate resolution;
- the reason for the recommendation;
- the risk if left unresolved;
- the acceptance evidence required before the decision can be marked accepted.

**Important:** These are engineering recommendations, not protocol approvals. No user, maintainer, validator operator, or independent reviewer approval is inferred by this document. All 14 decisions remain **PROPOSED / PENDING REVIEW**.

## 2. Decision status vocabulary

| Status | Meaning |
|---|---|
| PROPOSED | Candidate resolution documented; no approval recorded |
| ACCEPTED | Explicitly approved by the designated project decision owner and recorded with rationale |
| REJECTED | Candidate rejected; replacement resolution and rationale recorded |
| DEFERRED | Cannot be decided yet; blocking dependency and revisit condition recorded |

No decision may be silently promoted from PROPOSED to ACCEPTED by implementation convenience or a passing test.

## 3. Decision register

### DEC-01 — Exact Config-v1 schema and field set

**Question:** What exact fields, types, and nesting are part of Application Config v1?

**Recommended candidate:**
- Freeze the existing proposed fields exactly:
  - `config_version`
  - `network_id`
  - `protocol_version`
  - `max_amount`
  - `max_block_transactions`
  - `max_transaction_bytes`
  - `amount_max`
  - `nonce_max`
  - `transaction_encoding`
  - `recipient_policy`
- Require exact field presence and exact types.
- Reject unknown fields in v1; introduce future fields only under a new explicitly versioned schema or a separately specified extension mechanism.
- Do not infer defaults for omitted consensus-critical fields.

**Why:** Exact schemas avoid different validators interpreting the same payload differently.

**Risk if unresolved:** Different nodes may accept different config shapes or silently apply different defaults.

**Acceptance evidence:** Schema table, JSON Schema or equivalent machine-readable definition, parser tests for missing/extra/wrong-type fields, and a reviewed example fixture.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-02 — Integer semantics and numeric bounds

**Question:** Which numeric types and maxima apply to monetary amounts, nonce values, transaction limits, and byte limits?

**Recommended candidate:**
- All consensus-critical numeric fields are non-negative integers with explicit per-field upper bounds.
- Reject booleans, floats, exponent notation, NaN, infinities, negative values, and overflow.
- Keep `nonce_max` at the existing unsigned 64-bit ceiling unless a protocol-version change is approved.
- Treat `max_amount` as a per-transaction limit, not total supply.
- Treat `amount_max` as the absolute protocol-level ceiling for a single amount field; require `max_amount <= amount_max`.
- Do not choose numeric ceilings for block transaction count or byte limits until they are checked against existing implementation constraints, CometBFT limits, and resource testing.
- Use exact integer representations across languages; JavaScript must use BigInt or an equivalent exact parser.

**Why:** The current source uses arbitrary-precision Python integers and a per-transaction max amount, while other runtimes can overflow or lose precision.

**Risk if unresolved:** Consensus divergence, arithmetic overflow, or a false assumption that a transaction cap is a supply cap.

**Acceptance evidence:** Frozen numeric table with inclusive/exclusive boundaries; cross-language min/max/overflow vectors; arithmetic and conservation tests.

**Status:** PROPOSED for integer semantics; numeric ceilings for transaction/byte limits DEFERRED pending compatibility and resource measurements.

### DEC-03 — Network ID and protocol string grammar

**Question:** What characters, lengths, and case rules are permitted in `network_id` and other identity strings?

**Recommended candidate:**
- Use a narrow ASCII grammar for network identifiers, for example lowercase letters, digits, and hyphen, with a required alphanumeric first and last character.
- Make case significant by allowing lowercase only; reject rather than lowercase-normalize.
- Set an explicit maximum byte length after checking existing fixture and CLI usage.
- Treat `transaction_encoding` and `recipient_policy` as enumerated ASCII tokens, not free-form descriptions.
- Do not place user-facing Unicode labels in the consensus-critical config identity.

**Why:** Narrow identifiers are easy to validate identically in all runtimes and avoid Unicode normalization ambiguity.

**Risk if unresolved:** Multiple textual identifiers may refer to what operators believe is the same network, or implementations may normalize differently.

**Acceptance evidence:** Frozen grammar and length; positive and negative string vectors; CLI/parser equivalence tests.

**Status:** PROPOSED; exact maximum length DEFERRED until compatibility scan of current fixtures and launch scripts.

### DEC-04 — Canonical JSON and wire-byte acceptance

**Question:** Are noncanonical JSON byte encodings accepted if they parse to the same object?

**Recommended candidate:**
- Require strict UTF-8.
- Reject BOM.
- Reject duplicate keys at every object depth before object construction.
- Reject floats and non-finite numbers for the protocol schema.
- Define object-key ordering, escaping, separators, and integer rendering exactly.
- At consensus-critical boundaries, require submitted bytes to equal the frozen canonical serialization bytes.
- Do not rely on language-specific default JSON encoder/decoder behavior.

**Why:** One accepted byte representation makes hashing, audit logs, and cross-language comparison deterministic.

**Risk if unresolved:** The same apparent config may have multiple accepted encodings, parser differential behavior, or digest ambiguity.

**Acceptance evidence:** Byte-level fixtures for whitespace, key order, escapes, duplicate keys, BOM, and numeric lexical forms; Python/Node.js identical canonical bytes.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-05 — Unicode and normalization

**Question:** Which Unicode forms are accepted in consensus-critical strings?

**Recommended candidate:**
- Restrict identifiers, enum tokens, and digest strings to ASCII.
- For any future field that genuinely requires Unicode, preserve exact Unicode scalar values and UTF-8 bytes without implicit NFC/NFD normalization.
- Reject invalid UTF-8 and unpaired surrogate values.
- Do not normalize existing protocol strings silently.

**Why:** Implicit normalization may differ across library versions and languages.

**Risk if unresolved:** Validators may compute different bytes or treat visually similar identifiers as distinct or equivalent inconsistently.

**Acceptance evidence:** Explicit per-field character policy; NFC/NFD, invalid scalar, escape, and UTF-8 test vectors.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-06 — Allocation array order and duplicate semantics

**Question:** Is allocation order meaningful, and how are duplicate account entries handled?

**Recommended candidate:**
- Define a deterministic ordering by canonical account identifier bytes.
- Require allocations to arrive in that order; reject unsorted arrays rather than silently sorting input.
- Reject duplicate account identifiers.
- Do not merge duplicate allocations.
- Verify the exact sum of allocations equals `total_supply` using bounded integer arithmetic.

**Why:** JSON object-key sorting does not define array ordering. Silent sorting or merging can hide malformed Genesis input.

**Risk if unresolved:** Equivalent manifests may produce different hashes, or duplicate allocations may be interpreted differently by implementations.

**Acceptance evidence:** Ordered/unordered fixtures, duplicate-account fixtures, sum-underflow/overflow fixtures, and cross-language manifest digest equality.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-07 — Domain separators and hash preimages

**Question:** What exact bytes are hashed for config, manifest, and aggregate network identity?

**Recommended candidate:**
- Freeze each domain separator as an exact byte string including its terminal NUL byte.
- Freeze field names, order, encoding, and concatenation rules for each preimage.
- Hash canonical bytes only.
- Keep config digest, manifest digest, and aggregate network identity as distinct values with distinct domains.
- Never reuse a legacy manifest-only digest as an aggregate Config-v1 identity.
- Treat any preimage change as a protocol/schema version change.

**Why:** Domain separation prevents cross-context hash reuse and ambiguous composition.

**Risk if unresolved:** Digest collisions across semantic domains, inconsistent preimages, or unsafe reinterpretation of old network identity.

**Acceptance evidence:** Byte-for-byte preimage fixtures; positive and mutation vectors; two independent generators; reviewer sign-off.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-08 — Aggregate HND identity versus CometBFT profile identity

**Question:** Is the CometBFT consensus profile included in the HND aggregate application identity or separately pinned?

**Recommended candidate:**
- Keep two explicit identities:
  1. HND application network identity, binding application config and Genesis manifest.
  2. CometBFT profile identity, binding the CometBFT version/build and consensus-critical profile.
- Require both identities to be verified by startup preflight before the node listens or enables signing.
- Require the deployment manifest to bind the pair together.
- Do not allow a node with the correct HND application identity but a mismatched CometBFT profile to join.
- Revisit combining them into one aggregate digest only if a complete upgrade/versioning model is designed.

**Why:** The application and consensus engine have different lifecycle/versioning concerns, but both affect network compatibility.

**Risk if unresolved:** A node may pass application config checks while running different validator powers, block limits, evidence parameters, or consensus-engine behavior.

**Acceptance evidence:** Separate deterministic profile digest vectors; preflight mismatch tests; four-node equality test; profile mutation rejection before startup.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-09 — CometBFT profile contents and pinning

**Question:** Which CometBFT values must be included in the separately pinned profile?

**Recommended candidate:**
- Pin exact CometBFT release and build identity.
- Include validator set identity and voting power.
- Include all consensus-critical block, evidence, and timing parameters that can change proposal acceptance, evidence handling, or commit behavior.
- Explicitly classify each setting as consensus-critical or operational.
- Operational-only settings may vary only where the protocol confirms they cannot affect state validity or consensus.
- Generate the profile from a reviewed source of truth; do not trust generated defaults without recording the resolved values.

**Why:** Generated local defaults can differ by version or deployment and are not automatically part of HND's application config.

**Risk if unresolved:** Nodes may run materially different consensus configurations while appearing to share an HND config hash.

**Acceptance evidence:** Profile schema, pinned sample, complete resolved config diff, validator-set digest, and deliberate mismatch tests.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-10 — Resource limits

**Question:** What maximum sizes and parser resource bounds are enforced?

**Recommended candidate:**
- Define explicit maximums for config bytes, Genesis envelope bytes, manifest bytes, nesting depth, object members, allocation count, string length, and transaction bytes.
- Reject over-limit data before expensive parsing, hashing, or state mutation.
- If a limit changes transaction acceptance or block validity, bind it to the appropriate consensus identity.
- Keep local operational safeguards separate only when they cannot create validator disagreement.
- Derive numeric limits from tested workload and CometBFT compatibility, not arbitrary guesses.

**Why:** Unbounded parsing and payload processing create denial-of-service exposure; inconsistent limits create consensus divergence.

**Risk if unresolved:** Resource exhaustion or different validators accepting different transactions/blocks.

**Acceptance evidence:** Frozen limit table; boundary and just-over-boundary vectors; stress tests; cross-node equality.

**Status:** PROPOSED; exact values DEFERRED pending workload and compatibility measurements.

### DEC-11 — Stable machine-readable error contract

**Question:** Which error classes are exposed to callers and tests?

**Recommended candidate:**
Define stable categories at minimum:
- `INVALID_ENCODING`
- `DUPLICATE_KEY`
- `INVALID_SCHEMA`
- `INVALID_FIELD_TYPE`
- `OUT_OF_RANGE`
- `NON_CANONICAL_BYTES`
- `INVALID_IDENTIFIER`
- `DIGEST_MISMATCH`
- `NETWORK_ID_MISMATCH`
- `PROFILE_MISMATCH`
- `LEGACY_STATE_REQUIRES_MIGRATION`
- `DURABLE_STATE_MISMATCH`
- `RESOURCE_LIMIT_EXCEEDED`

Runtime-specific parser text may be logged for diagnostics but must not be a protocol decision input. Do not include secrets in error messages.

**Why:** Tests and operators need consistent, safe failure categories across languages and versions.

**Risk if unresolved:** Different error paths may be mistaken for equivalent acceptance/rejection, and diagnostics may leak sensitive data.

**Acceptance evidence:** Error mapping table; negative vectors asserting categories; tests that verify secrets are absent from logs.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-12 — Durable-store migration policy

**Question:** How should existing v0.2 stores be handled after Config-v1?

**Recommended candidate:**
- Normal Config-v1 startup rejects a legacy store without the Config-v1 identity.
- Do not reinterpret old manifest-only hashes.
- Migration is an explicit offline operation on a verified backup/copy.
- Migration must emit a new versioned store and an auditable report.
- Do not permit in-place live migration or mixed-version validators.
- Require a fresh isolated test network for initial Config-v1 validation.
- Define rollback/recovery before any live activation.

**Why:** The store's trusted identity changes, so silently loading old state under a new identity is unsafe.

**Risk if unresolved:** State may be loaded under an identity it was never committed against, or validators may split across versions.

**Acceptance evidence:** Migration matrix; disposable-copy rehearsal; old-store rejection; no-rewrite assertions; interrupted migration recovery.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-13 — Upgrade activation and rollback

**Question:** How can a validator set move from the old protocol to Config-v1?

**Recommended candidate:**
- Do not support mixed-version participation in one active validator set.
- Require explicit target version, activation height, and all-validator readiness checks.
- Require every validator to verify identical HND and CometBFT profile identities before activation.
- Persist activation state and verify it after restart.
- Do not allow unilateral rollback after Config-v1 state commits.
- Define coordinated recovery/fork procedure before activation is considered operational.

**Why:** A config/Genesis identity change affects consensus and persistent state, not just a node-local software update.

**Risk if unresolved:** Split-brain behavior, incompatible state histories, or unsafe rollback.

**Acceptance evidence:** Multi-validator activation simulation, restart-at-boundary tests, partial-upgrade failure tests, and recovery rehearsal.

**Status:** PROPOSED / PENDING REVIEW.

### DEC-14 — Independent vector generation and review ownership

**Question:** Who validates the schema, serializer, and golden vectors independently?

**Recommended candidate:**
- The implementation author must not be the sole vector author and approver.
- Maintain at least two independent generators using different implementations/libraries where practical.
- Review exact canonical bytes and digest preimages, not just final hash strings.
- Record generator versions, commands, environment, commit SHA, and reviewer identity/approval.
- Any vector change requires a reason and regeneration of dependent fixtures.

**Why:** Two implementations that share the same mistaken assumptions do not constitute independent verification.

**Risk if unresolved:** A systematic bug may be encoded into both implementation and expected test results.

**Acceptance evidence:** Reproducible generator artifacts, independent comparison report, reviewer sign-off, and immutable vector version.

**Status:** PROPOSED / PENDING REVIEW.

## 4. Recommended resolution order

The decisions are not independent. Resolve them in this order:

1. DEC-01 schema and DEC-02 numeric semantics.
2. DEC-03 identifier grammar and DEC-05 Unicode policy.
3. DEC-04 canonical JSON and DEC-06 array ordering.
4. DEC-07 exact hash preimages.
5. DEC-08 and DEC-09 HND / CometBFT identity separation.
6. DEC-10 resource bounds.
7. DEC-11 stable error contract.
8. DEC-12 migration and DEC-13 activation/rollback.
9. DEC-14 independent vector ownership and sign-off.

DEC-10 numerical values depend on implementation and workload measurements, but the categories and measurement methodology can be agreed earlier.

## 5. Explicit blockers and non-decisions

The following are intentionally **not** decided by this register:

- Public token supply, distribution, or token economics.
- Mainnet launch, public endpoint exposure, or validator recruitment.
- Production key custody, HSM selection, or signing deployment.
- Legal/regulatory authorization.
- Whether G2, G3, or G4 may open.
- Exact transaction/block resource ceilings before measurements.
- Whether a live network upgrade is operationally permissible.

These require separate work, evidence, and authorization.

## 6. Review/approval record

| Decision ID | Proposed resolution | Status | Approver / evidence |
|---|---|---|---|
| DEC-01 | Exact v1 schema; reject unknown fields | PROPOSED | Pending |
| DEC-02 | Exact bounded integers; no float/bool; nonce U64 candidate | PROPOSED / PARTLY DEFERRED | Pending |
| DEC-03 | Narrow lowercase ASCII identifiers | PROPOSED | Pending |
| DEC-04 | Strict canonical UTF-8 bytes; reject duplicates/BOM | PROPOSED | Pending |
| DEC-05 | ASCII identifiers; no implicit Unicode normalization | PROPOSED | Pending |
| DEC-06 | Sorted allocations; reject duplicates | PROPOSED | Pending |
| DEC-07 | Freeze domain separators and exact preimages | PROPOSED | Pending |
| DEC-08 | Separate HND identity and mandatory CometBFT profile identity | PROPOSED | Pending |
| DEC-09 | Pin full consensus-critical CometBFT profile | PROPOSED | Pending |
| DEC-10 | Explicit bounded resource limits | PROPOSED / VALUES DEFERRED | Pending |
| DEC-11 | Stable machine-readable error categories | PROPOSED | Pending |
| DEC-12 | Offline explicit migration; legacy startup rejected | PROPOSED | Pending |
| DEC-13 | Coordinated activation; no unilateral rollback | PROPOSED | Pending |
| DEC-14 | Independent vector generation and review | PROPOSED | Pending |

An approval must identify the decision owner, date, exact decision IDs, and any conditions. A Git commit containing this proposal is not itself approval.

## 7. Next work after review

After the decision owner reviews this register:

1. Mark each item ACCEPTED, REJECTED, or DEFERRED with evidence.
2. Update the authoritative schema and canonical identity specification.
3. Regenerate positive and negative vectors from the accepted rules.
4. Obtain independent review of exact bytes and preimages.
5. Only then request a separate implementation authorization.

Until those steps are complete, remain in documentation/planning mode.

## 8. Verification and disposition

- This file records recommendations only.
- No application source code was modified.
- No tests were executed while preparing this register.
- No CI workflow was modified.
- No decision is marked accepted.
- Config-v1 implementation, migration, G2–G4, and public-network gates remain closed.
