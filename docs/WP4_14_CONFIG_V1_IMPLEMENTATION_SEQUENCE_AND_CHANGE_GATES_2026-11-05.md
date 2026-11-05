# WP4.14 — Config-v1 Implementation Sequence, Dependency Graph, and Change Gates

**Date:** 2026-11-05  
**Status:** Planning artifact — candidate, not an implementation authorization  
**Branch:** `phase-0.2-planning`  
**Baseline commit:** `e17e7ee95388e7102f0e872edcf617056b16181d`

## 1. Decision summary

Config-v1 is a cross-cutting protocol identity change. It must not be implemented as a collection of unrelated field additions. The application config, Genesis envelope, durable store, CLI startup validation, CometBFT profile, migration behavior, and cross-language identity vectors form one dependency chain.

**Current decision: continue planning and close specification decisions first. Do not begin application-code edits in this phase.**

The design document explicitly marks the work ready for implementation planning, not implementation approval. The canonical identity specification and negative-vector matrix still contain open decisions. This plan preserves that boundary.

## 2. Dependency graph

```text
Decision register + schema freeze
              |
              v
Canonical JSON / exact numeric / string grammar
              |
              v
Config + manifest + aggregate identity preimages
              |
              v
Independent positive and negative vectors
              |
              v
Genesis envelope + InitChain validation
              |
              v
Durable store schema + startup mismatch refusal
              |
              v
CLI / four-validator harness / CometBFT profile preflight
              |
              v
Offline migration + restart + rollback policy
              |
              v
Full acceptance suite + independent review
              |
              v
Separate gate decision (no automatic production approval)
```

A downstream stage must not silently define an upstream protocol rule. If an implementation discovery requires a specification change, stop that stage, update the decision register and vectors, and obtain review before proceeding.

## 3. Pre-implementation decision register

| ID | Decision required | Candidate default for review | Must be frozen before |
|---|---|---|---|
| DEC-01 | Config-v1 exact field set and types | Exact fields from the design; reject unknown fields | Schema implementation |
| DEC-02 | Integer semantics and bounds | Unsigned bounded integers; reject booleans, floats, exponent notation, overflow | Parser and validators |
| DEC-03 | Network ID grammar | Narrow ASCII allow-list with explicit maximum length | Canonical vectors |
| DEC-04 | Canonical JSON wire rule | Strict UTF-8, no BOM, duplicate-key rejection, canonical-byte equality | Parser and hash code |
| DEC-05 | Unicode policy | ASCII-only for protocol identifiers; preserve exact Unicode only where explicitly permitted | Canonical vectors |
| DEC-06 | Allocation ordering | Stable account-ID byte/string order; reject duplicates and unsorted arrays | Manifest vectors |
| DEC-07 | Domain separators and preimage field order | Freeze exact bytes including NUL terminators and exact field sequence | Digest implementation |
| DEC-08 | Aggregate network identity | Include app-config digest and manifest digest; pin CometBFT profile separately unless governance chooses inclusion | Genesis envelope |
| DEC-09 | CometBFT profile | Pin exact CometBFT version/build and consensus-critical parameters in a separately verifiable profile | Multi-node startup |
| DEC-10 | Resource bounds | Freeze byte, depth, member, array, allocation, and transaction limits | Untrusted-input parser |
| DEC-11 | Error contract | Stable machine-readable categories; runtime-specific parser strings remain diagnostic only | Negative tests |
| DEC-12 | Durable store migration | Reject legacy stores in normal startup; explicit offline migration only | Store schema edits |
| DEC-13 | Upgrade activation | Coordinated activation height and all-validator readiness; no mixed-version live set | Upgrade implementation |
| DEC-14 | Vector ownership | Independent generator/reviewer separate from implementation author | Schema freeze sign-off |

Candidate defaults are recommendations, not adopted protocol rules. Each decision needs an owner, rationale, approval reference, and test-vector impact recorded before the schema is frozen.

## 4. Ordered implementation work packages

### WP-A — Freeze the specification

**Inputs:** Application Config-v1 design, canonical identity/preimage specification, positive golden vectors, negative vector matrix, compatibility/migration matrix.

**Work:**
1. Resolve DEC-01 through DEC-14.
2. Publish one authoritative schema and validation table.
3. Freeze exact byte preimages, domain separators, digest text grammar, and canonical JSON profile.
4. Define stable error categories and no-mutation guarantees.
5. Have a reviewer who did not author the serializer independently review the spec.

**Exit evidence:** Approved decision register; versioned schema; independently reviewed preimage specification; updated positive and negative vectors.

**Stop condition:** Any unresolved consensus-critical type, limit, field, ordering, or identity rule.

### WP-B — Pure parsing and validation layer

**Work:**
1. Implement strict byte decoding and parser behavior.
2. Detect duplicate keys before object construction.
3. Enforce exact fields, types, bounds, identifier grammar, and array rules.
4. Produce canonical bytes without depending on host-language defaults.
5. Verify component and aggregate digests.

**Exit evidence:** Unit tests for every NEG vector; cross-language byte/digest equality; malformed inputs rejected before state mutation.

**Stop condition:** Any cross-language discrepancy or ambiguous accepted representation.

### WP-C — Genesis envelope and InitChain binding

**Work:**
1. Add the versioned envelope containing application config, config digest, manifest, and required identity fields exactly as frozen.
2. Verify chain ID/network ID binding.
3. Recompute config and manifest component digests.
4. Recompute aggregate network identity.
5. Reject legacy manifest-only identity as Config-v1.
6. Ensure failed InitChain cannot leave partial initialized state.

**Exit evidence:** Positive/negative Genesis envelope tests; explicit legacy rejection; deterministic application identity across all validators.

**Stop condition:** Any validator accepts a payload another validator rejects.

### WP-D — Durable store and startup guards

**Work:**
1. Version the durable store schema.
2. Persist the verified Config-v1 identity and required profile identity.
3. Verify stored identity before loading operational state.
4. Refuse mismatched, missing, or legacy identity in normal startup.
5. Ensure refusal does not rewrite the old store.
6. Keep offline migration separate from normal startup.

**Exit evidence:** Restart tests, tampered-store tests, missing-digest tests, mismatched-config tests, byte-for-byte no-rewrite assertions.

**Stop condition:** Startup can proceed with a mismatched identity or silently mutate a legacy store.

### WP-E — CLI and CometBFT profile preflight

**Work:**
1. Remove consensus-critical CLI overrides or require exact equality with the pinned config.
2. Validate configuration before opening listener sockets or enabling signing.
3. Define a separate pinned CometBFT profile with exact version/build, validator set/power, and consensus-critical limits.
4. Reject profile mismatch before multi-validator launch.
5. Keep operational settings distinct from consensus-critical settings.

**Exit evidence:** CLI mismatch tests; profile mutation tests; all validators report identical verified identities before launch.

**Stop condition:** One node can start with different transaction acceptance, block limits, validator power, or evidence parameters.

### WP-F — Migration, upgrade, and rollback controls

**Work:**
1. Implement offline migration tooling only after the source/target formats are frozen.
2. Require explicit operator confirmation and a verified backup.
3. Never reinterpret old manifest hashes as aggregate Config-v1 identities.
4. Define coordinated activation height and all-validator readiness checks.
5. Define recovery if validators disagree or activation partially completes.
6. Prohibit unilateral rollback after Config-v1 state has committed unless a coordinated recovery/fork plan is approved.

**Exit evidence:** Migration rehearsal on disposable copies; restart after migration; interrupted-migration recovery; coordinated activation simulation; rollback boundary tests.

**Stop condition:** Migration is implicit, in-place while live, non-reproducible, or not recoverable.

### WP-G — Full integration and independent review

**Work:**
1. Run all positive and negative vectors.
2. Run existing regression suite and dedicated migration/startup suites.
3. Run multi-validator config equality and mismatch scenarios.
4. Run restart, partition/rejoin, and durable-state recovery scenarios.
5. Verify all evidence against the exact commit SHA.
6. Obtain independent code and protocol review.

**Exit evidence:** Reproducible command logs, test results, commit SHA, vector version, reviewer sign-off, and a documented residual-risk register.

**Stop condition:** Any skipped required test, unexplained mismatch, unreviewed critical finding, or missing reproducible evidence.

## 5. Source-area impact map

The following are expected impact areas based on the current design and prior source review. This is not an instruction to edit all files at once.

| Area | Expected responsibility | Required guard |
|---|---|---|
| `hnd_v02/transaction.py` | Protocol config model and transaction validation | No implicit CLI-only consensus limits |
| `hnd_v02/genesis.py` | Manifest and Config-v1 identity serialization | Legacy hash remains distinct |
| `hnd_v02/abci_app.py` | InitChain binding and durable store identity | No partial state on rejection |
| `hnd_v02/cometbft_v040_server.py` | Startup preflight and server initialization | Validate before listen/signing |
| CLI / node launch scripts | Parse and validate pinned config/profile | No silent consensus-critical overrides |
| Four-validator harness | Identical config/profile distribution | Fail before launch on any mismatch |
| Tests | Positive/negative vectors and migration scenarios | Every rejection asserts no mutation |
| Documentation | Frozen protocol, operations, migration, and recovery rules | No claim of production readiness |

No workflow file is in scope for modification under the current project constraint.

## 6. Test execution order

1. Parser byte-level tests (duplicate keys, UTF-8, BOM, canonical bytes).
2. Schema/type/range tests (exact fields, booleans, floats, overflow).
3. Positive and negative digest-vector tests.
4. Manifest ordering, duplicate allocation, and supply-conservation tests.
5. Genesis envelope and legacy rejection tests.
6. Durable-store mismatch and no-rewrite tests.
7. Startup/CLI/profile preflight tests.
8. Cross-language differential tests.
9. Single-node restart and migration tests.
10. Four-validator equality, mismatch, activation, partition/rejoin tests.
11. Full regression suite and independent review.

Do not use a passing single-node test as evidence of multi-validator identity agreement. Do not use a successful parser test as evidence that durable startup and migration are safe.

## 7. Change-control rules for the implementation phase

- Work on `phase-0.2-planning` until a separate implementation branch is explicitly approved.
- Fetch the current branch head and each target file's current SHA before modifying an existing file.
- Never run parallel writes to the same path.
- Make small, reviewable commits grouped by one work package.
- Do not modify GitHub Actions workflow files.
- Do not introduce production keys, real funds, public endpoints, or public token distribution.
- Do not open G2–G4 through documentation changes or passing partial tests.
- If a security control blocks an edit or execution, do not bypass it; record the limitation and continue with static review or test design.
- Every claimed test result must include the actual command, environment, commit SHA, and observed result.

## 8. Current gate assessment

| Gate | Status | Reason |
|---|---|---|
| Specification freeze | <b>BLOCKED</b> | DEC-01–DEC-14 require explicit resolution |
| Executable vector freeze | <b>BLOCKED</b> | Canonical and negative-vector policy depends on unresolved decisions |
| Application implementation | <b>NOT AUTHORIZED</b> | Design gate allows planning only |
| Durable migration implementation | <b>NOT AUTHORIZED</b> | Migration semantics and recovery need frozen specification |
| Multi-validator Config-v1 acceptance | <b>NOT RUN</b> | No Config-v1 implementation exists in this plan |
| Production/public-network readiness | <b>CLOSED</b> | Independent review, security, operations, governance, and legal gates remain separate |

## 9. Immediate next deliverable

The next planning artifact should be a **Config-v1 Decision Register** with each DEC item assigned one of:
- accepted with rationale and approving reviewer;
- rejected with rationale and replacement;
- deferred with an explicit blocking dependency.

Only after that register is reviewed should the schema and vectors be frozen. The implementation sequence above is not permission to begin coding.

## 10. Verification and disposition

- This file is planning documentation only.
- No source code or test files were changed.
- No CI workflow files were changed.
- No tests were executed while preparing this plan.
- The baseline branch head recorded above was checked before this document was created.
- Implementation, migration, G2–G4, and public-network gates remain closed.
