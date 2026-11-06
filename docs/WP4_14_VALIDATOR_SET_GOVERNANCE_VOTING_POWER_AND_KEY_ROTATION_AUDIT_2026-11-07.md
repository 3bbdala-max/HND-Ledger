# WP4.14 — Validator-Set Governance, Voting Power, Admission/Removal and Key-Rotation Audit

**Date:** 2026-11-07  
**Branch reviewed:** `phase-0.2-planning`  
**Review type:** Static source, test, Genesis-fixture and prior-evidence review; documentation-only change.  
**Decision:** **NOT APPROVED** for public validator onboarding, production signing, public-network launch or token issuance.  
**Change boundary:** This audit adds documentation only. No application source, tests, CometBFT configuration, workflow, validator key or protocol behavior is changed.

## 1. Executive determination

HND v0.2 currently has **no on-chain validator registry, staking system, governance voting, validator admission/removal transaction, slashing/jailing state, or application-defined voting-power update policy**.

The HND ABCI adapter does not pass CometBFT's InitChain validator records or consensus parameters into the HND application. Its InitChain response returns the HND application hash only. Its FinalizeBlock response returns transaction results and app hash only; it does not emit `validator_updates` or `consensus_param_updates`.

Accordingly, in the current integration shape:

- the initial consensus validator set is supplied to CometBFT through its own Genesis configuration, outside the HND account-allocation manifest;
- subsequent validator membership and power changes are not authorized by HND application state or HND on-chain governance;
- the HND evidence journal records CometBFT-supplied misbehavior metadata but does not slash, jail, remove, or reduce a validator's power;
- validator consensus-key replacement is not governed by an HND key-rotation state machine or authenticated activation process;
- voting power is CometBFT's weighted consensus input, not a count of validator processes and not an HND token-stake balance.

The repository has useful disposable four-validator integration evidence, but it is not a production validator enrollment/rotation control. The example Genesis allocation file is explicitly test-only and its two account allocations do not define a consensus validator set.

**This is a scope and launch-readiness limitation, not proof that CometBFT's own consensus engine is defective.** If the intended v0.2 design is operator-managed validator membership, that must be explicitly documented and protected by an authenticated release/governance process. If the intended design is on-chain HND governance, that capability does not yet exist in the reviewed application path.

## 2. Evidence inspected

### HND application and ABCI adapter

- `hnd_v02/abci_app.py`
  - `init_chain()` validates chain ID, canonical HND application Genesis bytes, manifest and expected HND Genesis hash. Its signature accepts only `chain_id` and `app_state_bytes`; it has no validator-set or consensus-parameter input.
  - `finalize_block()` executes HND transactions and merges the evidence journal. Its result contains `height`, `tx_results` and `app_hash`; no validator update structure is created.
  - `commit()` persists the HND ledger/evidence state. There is no validator registry or governance state in the persisted payload.
  - `_merge_evidence()` validates evidence-summary shape and voting-power metadata for journaling. It does not verify the original signed vote pair or execute a penalty.
- `hnd_v02/cometbft_v040_server.py`
  - `InitChain()` forwards only `request.chain_id` and `request.app_state_bytes`, then returns `ResponseInitChain(app_hash=...)`. It does not inspect `request.validators`, `request.consensus_params` or `request.initial_height`.
  - `FinalizeBlock()` returns `ResponseFinalizeBlock(tx_results=..., app_hash=...)`. No `validator_updates` or `consensus_param_updates` are populated.
  - `_normalize_misbehavior()` maps CometBFT evidence summary fields into HND journal records. That is an audit handoff, not validator-set enforcement.
- `hnd_v02/genesis.py`
  - the HND manifest schema contains manifest version, network ID, protocol version, total supply and account allocations. It does not define CometBFT validator identities or voting power.
- `vectors/v0.2-genesis-devnet-example.json`
  - explicitly describes itself as a test-only devnet fixture. Its two HND account allocations (600,000 and 400,000) are not validator voting power and must not be interpreted as stake or governance weight.

### Tests and previous audit evidence

- `tests/test_v02_abci_app.py` and `tests/test_v02_cometbft_v040_adapter.py` cover HND application lifecycle and adapter behavior; they do not establish an on-chain validator registry or governance lifecycle.
- `tests/test_v02_four_abci_replica_evidence.py` and the WP4.11 evidence integration cover evidence persistence/convergence, not automatic removal or slashing.
- `scripts/cometbft_v040_four_validator_genesis_preflight.py` and `scripts/cometbft_v040_four_validator_network_smoke.py` generate disposable CometBFT identities and a shared fixture Genesis. The reviewed audit records four fixture validators with voting power 10 each. Those are test values, not approved public-network parameters.
- Prior report `docs/WP4_14_INITCHAIN_AND_CONSENSUS_PARAMETER_UPDATE_BOUNDARY_AUDIT_2026-11-05.md` records the same ABCI response boundary.
- Prior report `docs/WP4_14_MISBEHAVIOR_EVIDENCE_PENALTY_AND_VALIDATOR_SET_ENFORCEMENT_AUDIT_2026-11-05.md` records that evidence is audit-only and that HND does not implement slashing, jailing, stake, or validator removal.
- Prior report `docs/WP4_14_COMETBFT_VALIDATOR_IDENTITY_GENESIS_PINNING_AUDIT_2026-11-05.md` records that disposable harness identities are generated at runtime and are not a stable, authenticated production validator set.
- Prior report `docs/WP4_14_VALIDATOR_DEVICE_LOSS_KEY_COMPROMISE_SIGNER_REPLACEMENT_AND_SAFE_RECOVERY_AUDIT_2026-11-07.md` records that production key custody, durable anti-double-sign anchoring and safe signer replacement are not established.

## 3. Findings

| ID | Severity | Finding | Consequence |
|---|---|---|---|
| VSET-01 | Critical | No HND validator registry, staking or governance state machine was found in the reviewed v0.2 application path. | HND transactions cannot authorize membership or voting-power changes. |
| VSET-02 | Critical | InitChain ignores CometBFT validator records and consensus parameters. | HND does not authenticate the initial CometBFT validator set against an HND-approved profile. |
| VSET-03 | Critical | FinalizeBlock emits no validator or consensus-parameter updates. | No on-chain HND mechanism can admit, remove, rotate or reweight validators through ABCI updates. |
| VSET-04 | High | The HND account Genesis manifest does not include consensus public keys, validator addresses or voting power. | The HND Genesis hash does not authenticate the CometBFT validator set. |
| VSET-05 | High | Disposable test harnesses generate validator keys and assign equal fixture power (10 each). | Test identity uniqueness and four-node convergence are not production enrollment or decentralization evidence. |
| VSET-06 | High | No approved production validator-set artifact, signed enrollment roster or independent expected-set pin was established. | A changed CometBFT Genesis can change the initial authority set outside HND application governance. |
| VSET-07 | High | No HND voting-power policy, per-validator cap, concentration ceiling, or approved total-power profile was found. | HND does not constrain governance capture or concentration at the application layer. |
| VSET-08 | High | No HND key-rotation state machine with authorization, delayed activation, overlap rules and revocation was found. | Consensus key replacement depends on external CometBFT/operator procedures and may cause identity mismatch or halt if validators diverge. |
| VSET-09 | High | Evidence journaling does not reduce voting power or remove a validator. | A recorded equivocation is not a penalty or automatic containment action. |
| VSET-10 | High | Prior signer review found no production-grade signer fencing, durable anti-double-sign trust anchor or complete recovery process. | Key replacement cannot be considered safe merely because a new key file is installed. |
| VSET-11 | Medium | The application does not bind a trusted CometBFT profile digest and validator-set digest into HND durable state. | Application-state identity and consensus validator-profile identity are not jointly pinned at runtime. |
| VSET-12 | High | Current evidence does not establish a production operator change-control process or independent authorization quorum for validator-set changes. | Repository access or a local configuration edit could become an operational authority path unless separately controlled. |

## 4. Voting power: correct interpretation and security boundary

CometBFT uses **weighted voting power**. Consensus thresholds are calculated from the sum of validator voting power, not from the number of running nodes.

For total voting power (P):

- a validator's share is its voting power divided by (P);
- the Byzantine fault-tolerance assumption is that Byzantine voting power remains strictly below one third of total voting power;
- committing a block requires more than two thirds of voting power in the relevant precommit quorum;
- withholding or partitioning enough voting power can prevent a quorum and halt progress, even if many low-power validator processes remain online.

Therefore, “three of four validators” is not a safe general description unless their powers are equal. A single validator with concentrated power may carry more consensus influence than several small validators. The four-validator test fixture with power 10 each is a controlled equal-weight test only.

This audit does **not** prescribe a production validator count, total voting power, minimum/maximum power, or concentration threshold. Those are protocol-owner decisions that must be explicit, analyzed against the threat model, and tested before any production profile is approved.

### Required power-policy properties

A future approved validator-set profile should define and enforce:

1. a canonical, versioned validator roster keyed by consensus public-key identity;
2. positive voting power for every member and an exact expected total;
3. uniqueness of consensus public keys and derived validator addresses;
4. an explicit maximum power per validator and an aggregate concentration policy, if adopted by the protocol owner;
5. checked arithmetic and bounds consistent with the exact CometBFT version's accepted numeric types;
6. deterministic ordering and canonical serialization of the roster;
7. an authenticated profile digest bound to chain ID, Genesis identity and activation height;
8. monitoring for power concentration, unexpected total-power changes and unauthorized profile drift.

No proposed numeric limits in this report are approved values.

## 5. Validator lifecycle and key-rotation boundary

### Current lifecycle

| Lifecycle operation | What current HND code establishes | What remains external or absent |
|---|---|---|
| Initial admission | HND validates its account-allocation manifest. CometBFT Genesis separately supplies validator records. | No HND authorization of consensus-key enrollment or validator power. |
| Add validator | No HND validator update is emitted. | Requires an external CometBFT-compatible validator-set change process or a new authenticated Genesis/release process. |
| Remove validator | Evidence is journaled, but no power-zero/removal update is emitted. | No HND removal, appeal, emergency revocation or effective-height policy. |
| Change voting power | HND does not emit validator updates. | No HND power governance, cap, delay or anti-concentration rule. |
| Rotate consensus key | No HND key-rotation state machine is present. | Requires external signer and CometBFT validator-set coordination, with anti-double-sign and activation safety. |
| Replace P2P node key | P2P identity is separate from consensus identity. | Requires peer enrollment/allowlist and operational identity change procedure. |
| Change HND account key | HND account signatures are a separate domain. | Must not be confused with consensus validator-key rotation. |

### Minimum safe operator-managed change process (proposal, not implemented)

If v0.2 remains operator-managed rather than on-chain governed, a production change should not be accepted from a single unauthenticated local edit. Define a signed change package containing:

- chain ID, Genesis hash and current validator-set/profile digest;
- monotonically increasing change sequence and target activation height;
- complete before/after validator roster, public keys, addresses and voting powers;
- explicit operation (admit, remove, power change, key rotation or emergency revocation);
- reason, change ticket and expiry;
- approvals from the protocol-defined independent authorization quorum;
- signatures bound to the exact canonical package and network identity;
- a deterministic rollout order and readiness evidence from every affected validator;
- a rollback/failure policy that does not silently re-enable a compromised key or violate anti-double-sign state.

The verifier should reject replayed sequence numbers, wrong-network packages, stale current-set digests, duplicate keys/addresses, unsupported key types, invalid power totals, insufficient approvals, conflicting activation heights and partially applied packages. Every node should fail closed if its local profile differs from the approved profile. Private keys must never be included in the change package.

### Key rotation safety requirements

A key rotation is not complete when a new private-key file is copied. At minimum:

1. authorize the new public key and its validator identity through the approved change package;
2. prove possession of the new key without exposing private material;
3. bind old key, new key, chain ID, Genesis hash, validator address, change sequence and activation height;
4. coordinate signer state and CometBFT validator-set activation so old/new keys cannot independently sign conflicting votes for the same validator identity;
5. preserve durable anti-double-sign H/R/S state and an independently protected monotonic fencing epoch;
6. reject stale signer instances and prevent automatic fallback to an unfenced local key;
7. revoke the old key only under an explicit activation/revocation rule;
8. test device loss, compromise, delayed messages, partial rollout, signer outage, restart, restore and attempted rollback.

The previous key-recovery audit found that the available synthetic anti-rollback reference is not yet a production signer-bound trust anchor. That gap blocks approval of production key rotation and failover.

## 6. Governance architecture decision required

The protocol owner must explicitly select one of these architectures before implementation work:

### Option A — Operator-managed validator set (smaller v0.2 scope)

- HND application does not claim on-chain validator governance.
- A separately authenticated validator-set/profile artifact is the sole membership/power authority.
- Changes require signed release/change packages, independent approvals, deterministic activation and per-node fail-closed checks.
- Operations, signer custody, monitoring, incident response and independent audit become mandatory release gates.

### Option B — On-chain validator governance (larger protocol scope)

- Add a versioned validator registry and deterministic governance state machine.
- Specify proposal creation, eligibility, voting power, quorum, approval threshold, timelock, activation height, cancellation, emergency pause, appeals and conflict handling.
- Define whether power comes from stake, a fixed authorized roster, or another explicit mechanism. Do not infer staking from the existing HND account balances.
- Validate governance transactions deterministically in every replica.
- Emit CometBFT validator updates only from an authenticated, finalized governance transition, with exact activation semantics.
- Define evidence verification, slashing/jailing policy and due process separately; evidence journaling alone is not enforcement.
- Add adversarial integration tests and independent review before enabling any production governance.

**No choice between Option A and Option B is made by this audit.** Option B must not be implemented by silently treating HND account balances or token holdings as validator stake.

## 7. Acceptance-test matrix (proposed; not run)

| Test ID | Scenario | Required result |
|---|---|---|
| VSET-T01 | Inspect InitChain response with a supplied validator list | HND response behavior is explicitly asserted; no claim of HND validator approval unless implemented. |
| VSET-T02 | Supply an unknown validator key in a candidate approved roster | Authenticated profile verifier rejects it. |
| VSET-T03 | Duplicate consensus public key | Reject before startup/activation. |
| VSET-T04 | Duplicate derived validator address | Reject before startup/activation. |
| VSET-T05 | Public key/address mismatch | Reject; address must be derived from canonical key bytes. |
| VSET-T06 | Unsupported key type, malformed encoding or invalid key length | Reject. |
| VSET-T07 | Zero, negative, excessive or out-of-range voting power | Reject using exact CometBFT-compatible checked bounds. |
| VSET-T08 | Sum of validator powers differs from signed profile total | Reject. |
| VSET-T09 | Concentrated voting power exceeds owner-approved cap/policy | Reject or require explicit governed exception; no implicit bypass. |
| VSET-T10 | Recompute power shares and quorum under uneven weights | Results use weighted power, not validator count. |
| VSET-T11 | Byzantine power reaches/exceeds the documented one-third safety assumption | Security monitor/test flags that BFT safety assumption is no longer satisfied. |
| VSET-T12 | Withhold enough voting power to prevent more-than-two-thirds precommit quorum | Network does not commit; liveness failure is detected and alerted. |
| VSET-T13 | Evidence journal receives an equivocation summary | Journal persists deterministically; no hidden slashing or validator removal occurs. |
| VSET-T14 | Candidate add/remove/power-change package lacks required signatures | Reject without changing active set. |
| VSET-T15 | Replay an already activated change sequence | Reject as replay. |
| VSET-T16 | Change package targets another chain ID or Genesis hash | Reject. |
| VSET-T17 | Change package current-set digest is stale | Reject rather than overwrite newer membership. |
| VSET-T18 | Validator rotation is activated at the wrong height or only on some nodes | Reject/stop signing; no mixed active set. |
| VSET-T19 | Old signer attempts signing after rotation fencing epoch advances | Reject at signer boundary. |
| VSET-T20 | Old and new signers race to sign the same H/R/S | Exactly one fenced signer can authorize; double-sign prevention state remains durable. |
| VSET-T21 | Restore signer backup with stale anti-double-sign state | Fail closed; no signing until trusted recovery is proven. |
| VSET-T22 | Compromised validator key is emergency-revoked | Revocation package is authenticated, replay-protected and activated consistently. |
| VSET-T23 | P2P node key changes while consensus key remains stable | Treat as a separate peer-identity change; do not accidentally rotate validator consensus identity. |
| VSET-T24 | HND account key changes | Must not modify CometBFT validator membership or voting power. |
| VSET-T25 | Restart each validator with altered validator-set/profile digest | Startup fails before consensus signing or network participation. |

All tests above are acceptance criteria, not executed test results.

## 8. CI and verification provenance

The current branch head at audit start was:

`bda541b7b091ab43d6f13e011b81176f91913a92`

GitHub Actions run **42305379789** (run number 395) is recorded as completed with conclusion **success** on that exact commit. It is the existing HND v0.2 reference-tests workflow. This is repository CI evidence for that commit; it does not independently prove the proposed validator-governance acceptance matrix, which has not been implemented.

This audit did not launch a new network or run tests locally. It did not modify source, tests, workflow, validator configuration or keys. The report commit itself will trigger the repository workflow; its result must be checked separately before claiming CI passed on the new documentation commit.

## 9. Final disposition

- **On-chain validator governance:** not implemented.
- **HND validator admission/removal and voting-power updates:** not implemented.
- **Validator-set authentication by HND Genesis:** not implemented; the HND account manifest is a separate identity domain.
- **CometBFT weighted consensus:** used by the consensus engine; the fixture's equal powers are test data only.
- **Evidence journal:** implemented as deterministic audit persistence; not slashing, jailing or validator removal.
- **Production validator key rotation/recovery:** not approved; production signer fencing and durable anti-double-sign trust remain open.
- **Public validator onboarding / production signing / public network / token issuance:** **NOT APPROVED**.

The next implementation decision is the protocol owner's explicit selection of operator-managed validator membership (Option A) or on-chain governance (Option B), followed by an authenticated validator-set profile and the acceptance tests above. No source changes should precede that decision and approval.

---
This document is an engineering audit and design proposal, not a security certification, legal opinion, economic-security assessment, or launch authorization.
