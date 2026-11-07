# WP4.14 — VSP Contract Consistency and CI Evidence Reconciliation

**Inspection date:** 2026-11-08  
**Branch:** `phase-0.2-planning`  
**Inspected HEAD before this report:** `e90f7d8b804f5d955e4c02519d4b03d527c44684`  
**Review type:** Documentation and workflow reconciliation  
**Change type:** Documentation only  
**Disposition:** Several historical statements require temporal qualification; VSP remains a candidate and is not approved.

## 1. Current evidence baseline

The branch HEAD inspected for this report was `e90f7d8b804f5d955e4c02519d4b03d527c44684`.

GitHub Actions run `42417477813` references that exact SHA and completed successfully:

- `hnd-v02-tests`: success.
- `cometbft-single-node-smoke`: success.

The current workflow file `.github/workflows/hnd-v02-tests.yml` explicitly includes both `tests.test_v02_anti_rollback_reference` and `tests.test_v02_recovery_controls` in its v0.2 test command. It also runs the isolated JCS compatibility suite before the v0.2 test suite.

This updates the earlier CI coverage-gap observation that those two modules were omitted from the workflow snapshot inspected at that time. The earlier observation remains historically accurate for its inspected workflow version, but must not be repeated as a current omission without rechecking the current workflow.

## 2. Historical audit reconciliation

### 2.1 Anti-rollback and recovery test inclusion

The prior signer authorization TOCTOU audit states that the current workflow does not list the anti-rollback and recovery-control test modules. That statement is stale against the current branch workflow.

Correct current statement:

- Both modules are explicitly invoked by the current workflow.
- The latest exact-HEAD HND test job passed.
- The anti-rollback reference module is still a synthetic offline model, not an integrated production signature-release gate.
- The recovery-control tests do not establish a production backup/restore exercise or independently administered recovery anchor.

**Interpretation:** CI test inclusion is closed as a workflow-coverage omission; production anti-rollback integration and operational recovery remain open security gates.

### 2.2 JCS compatibility

The current workflow has a hash-pinned isolated Python JCS dependency and a lockfile/integrity-pinned JavaScript comparator. The exact-HEAD JCS compatibility test passed in run `42417477813`.

This supersedes older JCS spike notes that described the JavaScript comparator as not integrity locked. Those notes remain historical snapshots, not current supply-chain status.

The result remains limited to the five representative cross-language inputs implemented in the spike. It does not demonstrate the full RFC 8785 Appendix B numeric corpus, production VSP parsing, schema validation, trust-root validation, signature verification, or runtime enforcement.

### 2.3 Four-validator and remote-signer integration

The exact-HEAD CometBFT job completed successfully, including the four-replica P2P evidence integration and the listed remote-signer and four-validator probes. This resolves the latest observed CI failure on an older commit only for the tested scenarios and exact current commit.

It does not erase the older failed run, prove all deployment topologies, or establish production custody, independent-host fencing, production key protection, or disaster recovery.

## 3. Candidate VSP contract consistency gates

The existing `WP4_14_VSP_V1_CANONICALIZATION_SIGNATURE_AND_GOLDEN_VECTOR_CONTRACT_2026-11-07.md` is explicitly a proposal, not an approved protocol. Before it can serve as an implementation contract, reviewers must resolve these items:

1. **Document status language:** its title uses “contract” and its body says “candidate frozen v1”; this must not be mistaken for a ratified freeze. The authoritative status remains proposal / not approved until an explicit protocol-owner decision and review record exist.
2. **Numeric lexical enforcement:** the document requires unsigned JSON integer tokens and rejects exponent notation and floats. A conventional JSON parser may convert lexical forms before schema validation. The eventual parser must preserve or separately validate numeric token lexemes; checking only Python runtime types is insufficient to distinguish `1` from `1.0` or `1e0`.
3. **Whole-envelope versus payload byte boundary:** the candidate requires exact JCS bytes for the signed payload but also describes an envelope containing detached signatures. The production parser must state whether canonicality is checked on the complete envelope, the payload member's exact source byte slice, or both. It must not assume that reserializing a parsed nested object proves the original payload byte slice was canonical.
4. **JCS scope:** RFC 8785 canonicalization applies to JSON values under its number and Unicode constraints. The schema's stricter integer-token rules are an application-level lexical restriction layered before JCS, not a property provided by JCS itself.
5. **Signature corpus:** the existing vector table is a proposed design. No generated, independently cross-checked VSP payload digest or Ed25519 signature golden-vector set was observed in the current spike. Do not label the vector suite implemented or passed.
6. **Governance and activation semantics:** two valid signatures prove only the cryptographic threshold against a selected trust manifest. They do not prove the trust manifest was bootstrapped correctly, that sequence/predecessor rules are enforced, that activation height is safe, or that anti-rollback state is durable.
7. **CometBFT profile binding:** a passing smoke test does not prove the VSP runtime verifier binds every consensus-affecting CometBFT configuration field to the binary and runtime configuration. This remains a separate acceptance gate.

## 4. Recommended next verification work

In order:

1. Extend the isolated JCS test corpus with the complete applicable RFC 8785 Appendix B number vectors, obtaining expected bytes from two independent implementations and recording their exact package versions and integrity identities.
2. Add parser-boundary tests that preserve numeric token lexemes and test duplicate members, BOM, invalid UTF-8, trailing data, and unpaired surrogates before ordinary object construction.
3. Define the exact byte-slice extraction rule for the payload in the signed envelope and test that whitespace/key-order mutations are rejected at the intended boundary.
4. Generate a synthetic VSP payload digest and Ed25519 signature golden vector from independently reviewed tooling; record raw payload bytes, digest preimage, digest, signature message, public key, signature, and verification result. Do not use production keys.
5. Keep trust-manifest validation, anti-rollback sequence enforcement, activation checks, CometBFT profile binding, and unavoidable pre-start enforcement as separate tests and gates.

No source, test, workflow, dependency, key, Genesis, validator configuration, or protocol decision was changed by this report. No CI rerun was triggered. No production-readiness, public-launch, or token-issuance approval is granted.

## 5. Current disposition

- Exact-HEAD CI: **PASS** for the listed workflow jobs and steps on commit `e90f7d8b804f5d955e4c02519d4b03d527c44684`.
- CI coverage omission for the two named reference test modules: **CLOSED** in the current workflow.
- Isolated JCS cross-language compatibility: **PASS** for the five implemented representative inputs.
- Full RFC 8785 vector corpus: **OPEN**.
- Production VSP parser/verifier and signature golden vectors: **OPEN**.
- Durable production anti-rollback signature-release integration: **OPEN**.
- VSP normative freeze and runtime enforcement: **NOT APPROVED / OPEN**.
