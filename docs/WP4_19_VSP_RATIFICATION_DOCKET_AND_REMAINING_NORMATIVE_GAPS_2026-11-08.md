# WP4.19 — VSP Ratification Docket and Remaining Normative Gaps

**Inspection date:** 2026-11-08  
**Branch:** `phase-0.2-planning`  
**Inspected HEAD:** `4db5e5d1ebc907f7fd6d25426338f13e03b8ccf2`  
**Review type:** Cross-document VSP authority, schema, trust-root, and runtime-readiness reconciliation  
**Change type:** Documentation only  
**Disposition:** A consolidated VSP engineering candidate already exists, but it is not ratified; several cross-document and runtime-binding decisions remain open.

## 1. Correction and current authority status

The repository already contains:

- `docs/WP4_14_VSP_V1_CONSOLIDATED_NORMATIVE_CANDIDATE_2026-11-07.md`
- `docs/WP4_14_VSP_V1_SPECIFICATION_CONFLICT_RECONCILIATION_AND_FREEZE_GATE_2026-11-07.md`
- `docs/WP4_14_VSP_V1_CANONICALIZATION_SIGNATURE_AND_GOLDEN_VECTOR_CONTRACT_2026-11-07.md`
- `docs/WP4_14_VALIDATOR_SET_PROFILE_CANONICAL_SCHEMA_AND_VERIFICATION_SPEC_2026-11-07.md`
- `docs/WP4_14_VSP_TRUST_ROOT_GOVERNANCE_KEY_ENROLLMENT_AND_RECOVERY_CEREMONY_SPEC_2026-11-07.md`
- `docs/WP4_14_VSP_V1_SCHEMA_CANONICALIZATION_AND_CRYPTOGRAPHIC_TEST_VECTOR_DESIGN_2026-11-07.md`

The consolidated candidate is not absent. It already proposes a reconciliation: nested validator-set payload schema, the `HND-VSP-v1` domain-separated SHA-256 profile digest, the `HND-VSP-AUTH-v1` Ed25519 message, strict canonical envelope input, and a 2-of-3 trust policy.

However, its own status is **NOT protocol-owner approved, NOT implemented, and NOT approved for production**. The later WP4.16 conflict register explicitly preserves the two incompatible drafts as candidate proposals and says not to implement either as a normative contract until one decision is formally ratified.

**Authority rule for this report:** the consolidated candidate may be used as the single engineering review baseline, but it must not be described as the ratified network protocol, frozen specification, or approved cryptographic contract.

## 2. What the consolidated candidate already proposes

For review continuity only, the existing consolidated candidate proposes:

1. An envelope with exactly `payload` and `signatures`.
2. Strict UTF-8 JSON input, duplicate-member rejection, exact schema fields, and whole-envelope JCS byte equality.
3. A nested payload with network/Genesis identity, CometBFT software identity, monotonic profile sequence, predecessor, activation, complete validator roster, governance policy and change record.
4. Profile digest:

   `D = SHA-256(ASCII("HND-VSP-v1") || 0x00 || JCS(payload))`

5. Ed25519 signing message:

   `M = ASCII("HND-VSP-AUTH-v1") || 0x00 || D`

6. Three independently enrolled governance keys with a 2-of-3 signature threshold.
7. Ed25519 validator public key/address derivation and checked voting-power limits based on the inspected CometBFT v0.40.0 source.

These are candidate decisions, not implementation results or approval evidence. This report does not generate any digest, signature, key, trust manifest or golden vector.

## 3. Remaining normative gaps requiring explicit closure

### VSP-RAT-01 — CometBFT identity is not yet a complete consensus-profile binding

The consolidated payload's CometBFT object currently names version, source commit and binary SHA-256. The candidate itself says that this does not bind every consensus-affecting runtime configuration field and that a separately reviewed profile binding remains required.

Other repository specifications require stronger identity binding, including CometBFT Genesis/profile identity and the complete version-specific set of consensus-affecting configuration fields.

Required decision:
- define whether the VSP payload itself carries a CometBFT Genesis digest and profile digest, or whether a separately signed release/profile manifest is referenced;
- define exactly which configuration fields are consensus-critical, security-critical operational, or local-only;
- bind the actual runtime configuration and binary to the exact independently approved digests;
- define the CometBFT v0.40.0 field map and unknown/new-field behavior.

A version string, source commit or binary digest alone is not a complete runtime profile identity.

### VSP-RAT-02 — Expiry semantics conflict across documents

The consolidated candidate explicitly says expiry is **not** a v1 payload field and must not be added without a trusted-clock/offline-validation policy.

The trust-root governance ceremony specification's routine VSP authorization section says the package must bind expiry and that expired packages must be rejected. The same document lists expiry among anti-replay rejection conditions.

These statements cannot both be normative for the same v1 schema.

Required decision: choose one of the following approaches in the ratification record:
- no VSP expiry field in v1, relying on authenticated monotonic sequence/predecessor state and defined activation policy; or
- a specific expiry field with exact integer/time semantics, trusted clock assumptions, offline behavior, boundary inclusivity, and recovery behavior.

Do not add a timestamp field informally or make nodes depend on unsynchronized local clocks.

### VSP-RAT-03 — Envelope canonicality and exact signed-byte boundary

The consolidated candidate improves the earlier ambiguity by requiring the complete received envelope to equal its RFC 8785 canonical serialization, while separately computing JCS bytes for the payload.

The implementation contract must still explicitly define:
- how the parser rejects duplicate object members at every depth before ordinary object construction;
- how it validates the original integer token lexemes (rejecting `1.0`, `1e0`, booleans and strings for integer fields);
- how the exact payload source byte range is identified, or how full-envelope byte equality proves the payload member is byte-identical to JCS(payload);
- input size/depth/string limits and stable errors.

A conventional JSON parse into ordinary numbers and maps is not sufficient evidence that lexical integer and raw-byte requirements have been enforced.

### VSP-RAT-04 — Trust manifest and profile counters need an explicit namespace rule

The trust-root ceremony proposes an initial trust-manifest sequence of 0. The consolidated candidate proposes the initial validator profile sequence of 1.

These may be separate counters, but the final ratified specification must state that they are separate monotonic namespaces, each with its own predecessor, digest, bootstrap state and anti-rollback record. No implementation may accidentally compare or advance one counter using the other's value.

### VSP-RAT-05 — Governance key identity must be identical in profile and ceremony

The consolidated candidate defines a deterministic governance key ID derived from the raw Ed25519 public key using the `HND-GOV-KEY-v1` domain prefix.

The witnessed ceremony must use the same exact key-ID derivation in:
- the trust manifest;
- key proof-of-possession records;
- signature records;
- key rotation/revocation packages;
- audit records and operator acknowledgements.

The ceremony specification must also say how a public-key fingerprint and a key ID differ, if both are retained. Labels such as G1/G2/G3 are custodian roles, not substitutes for cryptographic key IDs.

### VSP-RAT-06 — Activation policy is not fully operationally specified

The candidate defines initial profile sequence 1, predecessor null, and genesis activation height 0; later profiles advance sequence by one and activate at a later height.

Still required:
- numeric lead-time rule or deterministic operator acknowledgement threshold;
- exact policy if one operator has not acknowledged the digest;
- whether activation halts if operators report different digests;
- exact handling of chain halt, height divergence, delayed profile distribution and recovery;
- how an activation record is durably committed with signer fencing and the active profile.

The existing design says a partial rollout must halt. The actual operational quorum, timing and restart behavior still need formal acceptance.

### VSP-RAT-07 — Governance trust-root catastrophic recovery remains unresolved

The trust-root ceremony correctly refuses to invent a unilateral emergency bypass. It identifies catastrophic loss/compromise of two governance keys as a blocking issue.

Before production, approve and rehearse:
- legal/organizational authority for recovery;
- independent identity verification and witness quorum;
- validator halt and notification rules;
- recovery publication channels and delay;
- new trust-root pinning and transition semantics;
- evidence retention and post-incident review.

A Git commit, validator majority or one operator instruction must not silently replace the trust root.

### VSP-RAT-08 — Operator attestation references are not a substitute for verified independence

The consolidated candidate includes unique operator IDs and controlled operator-attestation references. The ceremony and validator governance documents require independent custody and infrastructure-domain evidence.

The production acceptance package must define the private evidence register, evidence owner, verification interval, shared-control/failure-domain analysis, privacy minimization and revocation/expiry process for operator attestations. A syntactically valid reference must never be treated as proof of independent operation.

## 4. JCS and cryptographic evidence boundary

The isolated CI spike has passed its five implemented representative cross-language samples. That result is useful but limited.

Still open before a production VSP implementation:
- complete applicable RFC 8785 Appendix B number vectors;
- further Unicode and escaping vectors;
- symmetric duplicate-member rejection in every parser implementation;
- strict lexical integer-token validation;
- independent byte-for-byte expected canonical outputs;
- an independently reviewed and ratified VSP schema/signature formula;
- synthetic VSP signature golden vectors generated only after ratification, then verified by independent implementations.

Do not use the five-sample spike as proof of full RFC 8785 conformance, VSP schema correctness, signature verification, trust-root validity or runtime pre-start enforcement.

## 5. Implementation stop gates

Do not begin a production or consensus-affecting VSP implementation until all of the following exist:

1. A protocol-owner approval record identifying the exact consolidated candidate version/commit and the final schema/signing decision.
2. A completed field-level CometBFT Genesis/profile mapping and binary identity design.
3. A single expiry decision.
4. Exact envelope/payload parsing and numeric lexical rules.
5. Independent trust-manifest key-ID, bootstrap, rotation and catastrophic recovery approval.
6. Activation and operator acknowledgement policy.
7. Full JCS/negative-test corpus and independently verified synthetic golden vectors.
8. Independent security review of the ratified contract and implementation plan.

After those approvals, implement as separate narrow work packages: parser, pure verifier, Genesis/profile binding, pre-start launcher, OS/service bypass prevention, durable anti-rollback, signer integration, and audit evidence. Do not combine all of these into one large change.

## 6. Updated CI evidence

Run `42420946912` targets exact commit `fb261f02f4c421f4cff0c8e900d70447e242f42e`. At the current inspection it is **completed successfully**:
- `hnd-v02-tests`: success;
- `cometbft-single-node-smoke`: success;
- the four-independent authenticated Noise signer scenario with no local consensus keys completed successfully.

Run link: https://github.com/3bbdala-max/HND-Ledger/actions/runs/42420946912

The latest run for the then-current HEAD `4db5e5d1ebc907f7fd6d25426338f13e03b8ccf2` is `42421409769`. At inspection:
- `hnd-v02-tests`: completed successfully;
- `cometbft-single-node-smoke`: in progress at the pinned CometBFT binary build step.

Run link: https://github.com/3bbdala-max/HND-Ledger/actions/runs/42421409769

The latest run is not a completed overall success at this inspection. Results must remain attached to their exact HEAD SHAs.

## 7. Decisions and change boundary

- Keep the consolidated VSP candidate as the sole engineering review baseline, not as an approved protocol.
- Preserve the WP4.16 hold: no production parser/verifier, no authoritative golden VSP signatures, no real governance-key enrollment, and no runtime pre-start dependency on an unratified candidate.
- Close the expiry, CometBFT profile binding, parsing, activation, key-ID and catastrophic-recovery decisions in one ratification package.
- Do not create real keys or disclose any secret material.

This report is documentation only. It changes no protocol source, tests, workflow, dependencies, trust manifest, keys, Genesis, validator configuration, CometBFT profile, branch settings or runtime behavior. It does not manually rerun CI or approve production signing, token issuance or public launch.
