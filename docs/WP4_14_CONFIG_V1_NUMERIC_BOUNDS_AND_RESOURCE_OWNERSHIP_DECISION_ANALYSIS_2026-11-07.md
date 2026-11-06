# WP4.14 — Config-v1 Numeric Bounds and Resource Ownership Decision Analysis — 2026-11-07

**Branch:** phase-0.2-planning  
**Reviewed baseline:** 3ed84029466d3ab4fab6e52de52d64fdb83f32ac  
**Related decisions:** DEC-02, DEC-06, DEC-09, DEC-10, DEC-12  
**Review type:** Static source and prior-audit synthesis; documentation only  
**Status:** Decision support — no numeric protocol values approved

## 1. Executive conclusion

The current code establishes some local limits, but it does not yet define a complete, portable numeric domain or a single resource policy bound to network identity.

The correct next action is **not to guess maximum values**. First decide which layer owns each limit; then measure representative workloads and select explicit values; finally freeze those values in the appropriate identity and executable vectors.

No source, tests, workflow, Genesis fixture, CometBFT profile, dependency, key, or deployment setting was modified. No test was run for this review.

## 2. Confirmed current implementation facts

| Parameter | Current behavior observed | Config-v1 issue |
|---|---|---|
| Transaction amount | Must be an exact positive Python integer and must not exceed node-local `ProtocolConfig.max_amount` | No portable absolute `amount_max`; max_amount is not bound to the existing Genesis identity |
| Nonce | `MAX_NONCE = 2^64 - 1`; exact integer check excludes bool and values outside U64 | Candidate Config-v1 should state whether this remains fixed for v1 and encode it explicitly |
| Total supply / allocations | Manifest validates allocation sum against total_supply; no common explicit portable maximum is established by the reviewed audit | Need exact supply/allocation bounds and checked arithmetic contract across implementations |
| Block transaction count | `MAX_BLOCK_TRANSACTIONS = 1000` in ABCI application | Existing hard-coded deterministic rule is not represented in a versioned config identity |
| Transaction bytes | PrepareProposal receives CometBFT `max_tx_bytes`; the application audit found no uniform independent HND transaction-byte cap across every acceptance path | Must distinguish HND validity from CometBFT proposal/block budget |
| Store version | `APP_STORE_VERSION = 3`; existing store binds network/protocol/legacy Genesis hash, not Config-v1 digest/profile identity | A schema migration and no-rewrite failure policy are required |
| CLI manifest parsing | Server path uses ordinary `json.load` | Strict duplicate-key and bounded-input policy must be unified before freeze |

These are implementation observations, not recommendations to preserve every current behavior unchanged.

## 3. Numeric semantics: decisions required

### 3.1 Monetary domain

DEC-02 should explicitly separate four concepts:

1. **Per-transaction cap (`max_amount`):** maximum amount accepted in one transfer under the application rules.
2. **Absolute amount-field maximum (`amount_max`):** portable upper bound for any amount-like field in the v1 schema.
3. **Total supply and allocation bounds:** limits for Genesis total supply and each allocation, plus a checked sum rule.
4. **Issuance policy:** whether future mint, burn, rewards, fees, or supply changes exist. If absent from v1, say so normatively rather than leaving arithmetic semantics implicit.

The historical one-million HND candidate Genesis is a test example, not proof of a protocol maximum or an approved monetary policy.

### 3.2 Exact integer contract

Candidate normative requirements for owner review:
- integer fields are non-negative or positive as individually specified;
- booleans are not integers for protocol purposes;
- floats, exponent notation, NaN, and infinities are rejected;
- no lossy IEEE-754 conversion is permitted;
- upper bounds are explicit and inclusive/exclusive semantics are stated;
- arithmetic is checked before state mutation;
- all supported implementations must produce identical acceptance/rejection outcomes.

The nonce U64 ceiling already exists in the current transaction code. DEC-02 must record whether Config-v1 preserves that exact ceiling, rather than leaving it as an accidental implementation detail.

### 3.3 Boundary-vector minimum

For every numeric field, freeze tests for:
- minimum valid value;
- zero where zero is forbidden;
- maximum valid value;
- maximum plus one;
- negative one;
- boolean true/false;
- integer-looking float such as 1.0;
- exponent form such as 1e3;
- very large integer beyond the approved bound;
- cross-field mismatch (for example max_amount greater than amount_max);
- allocation sum overflow or mismatch.

Every rejected input must assert no state mutation.

## 4. Resource ownership model

Every limit must be assigned to exactly one authoritative layer, or explicitly documented as a derived relationship.

| Resource / parameter | Recommended owner for decision | Identity treatment | Required enforcement evidence |
|---|---|---|---|
| Per-transfer amount cap | HND application | HND application-config digest | Same config required at every validator; mismatch rejected before service start |
| Absolute amount/supply/allocation bounds | HND application and Genesis schema | HND config/Genesis identity as appropriate | Cross-language exact-integer and supply-conservation vectors |
| Maximum HND block transaction count | HND application if it changes deterministic acceptance | HND application-config digest | PrepareProposal, ProcessProposal, FinalizeBlock, and direct application tests agree |
| Maximum HND transaction bytes | HND application if it rejects transactions by size | HND application-config digest | Identical check at all consensus-relevant paths; boundary and mismatch tests |
| CometBFT block/proposal byte parameters | CometBFT consensus profile | Separate CometBFT profile digest | Exact resolved profile and build pin; per-node profile mismatch rejection |
| Parser input/depth/member/array bounds | Shared deterministic parser policy where rejection affects acceptance | Bind to HND config/schema identity if consensus-visible | Reject before expensive parsing; same behavior in all validators |
| Query response pagination / operational memory limits | Local operational/API layer unless query results affect consensus | Normally not part of HND consensus identity | Load tests, bounded responses, pagination and operational monitoring |
| Local ports, file paths, worker counts, logging | Node operations | Exclude from HND application identity unless evidence shows consensus effect | Deployment validation and least-privilege checks |

**Important:** a local safety cap must not silently reject a block that another validator accepts. If a limit changes consensus acceptance, it is not merely operational.

## 5. How to select numeric resource values without guessing

The owner should approve a measurement protocol before selecting limits:

1. Build a representative transaction corpus: minimum, typical, and maximum realistic signed transactions, including longest permitted identifiers and account strings.
2. Measure canonical encoded transaction sizes, parser cost, signature verification cost, and memory use.
3. Measure block processing at increasing transaction counts and aggregate byte sizes on the intended minimum validator hardware.
4. Measure Genesis manifest size, allocation count, JSON depth/member count, and startup validation time.
5. Record throughput, p95/p99 processing latency, peak RSS, and worst-case recovery/replay cost.
6. Choose limits with explicit headroom and a documented target hardware profile.
7. Verify the selected limits are identical across validators and included in the correct pinned identity.
8. Generate boundary vectors independently and run the same suite against every supported implementation.

Do not select a byte limit from CometBFT's current default or from a single-node smoke run alone. Do not infer a safe allocation limit from the current sample Genesis.

## 6. Required mismatch tests

At minimum, the future executable suite must prove:

- same manifest and legacy manifest hash but different `max_amount` cannot start as the same network;
- one-field changes to each HND consensus-critical config field change the HND config digest;
- a different CometBFT consensus profile fails preflight even when the HND config digest matches;
- HND transaction-byte limits are enforced consistently at every applicable ABCI boundary;
- CometBFT block/proposal byte parameters are checked against the separately pinned profile;
- normal Config-v1 startup rejects a legacy store or a store with missing/mismatched config/profile identity;
- all failures occur before listener start/signing where applicable and leave existing durable bytes unchanged.

## 7. Dependencies and decision status

| Decision | What can be settled now | What remains deferred |
|---|---|---|
| DEC-02 | Exact-integer semantics; preserve explicit U64 nonce candidate pending owner decision | Monetary ceilings, total supply/allocation ceilings, max_amount/amount_max relationship |
| DEC-06 | Reject duplicate allocation identities; require deterministic ordering | Exact ordering key and maximum allocation count |
| DEC-09 | Keep CometBFT profile separate from HND application config | Complete profile field inventory and exact pinned build/profile values |
| DEC-10 | Establish ownership categories and measurement method | All numeric resource values and final enforcement placement |
| DEC-12 | Normal startup must not silently migrate or rewrite legacy state | Final schema version and offline migration details depend on frozen identity |

No decision is accepted by this analysis. The existing decision register remains authoritative for approval status.

## 8. Gate disposition

- Numeric protocol bounds: **OPEN**
- Resource ownership: **PROPOSED FOR OWNER REVIEW**
- Config-v1 schema freeze: **BLOCKED**
- Executable Config-v1 vectors: **BLOCKED**
- Config-v1 source implementation: **NOT AUTHORIZED**
- Public network / production signing / token issuance: **NOT APPROVED**

Proceed with owner review and measurement planning only. Do not insert arbitrary constants into code or treat current local values as production-frozen protocol parameters.
