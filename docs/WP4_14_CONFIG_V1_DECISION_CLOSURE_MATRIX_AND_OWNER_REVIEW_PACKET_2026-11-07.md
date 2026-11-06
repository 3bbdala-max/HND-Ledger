# WP4.14 — Config-v1 Decision Closure Matrix and Owner Review Packet — 2026-11-07

**Branch:** phase-0.2-planning  
**Baseline:** d14f2ab2ab2aecb4a450468355a016c2d49f2966  
**Artifact type:** Documentation-only decision traceability  
**Protocol status:** DESIGN ONLY — no schema freeze, implementation approval, or production authorization

## 1. Purpose and authority

This packet consolidates the existing Config-v1 decision register, candidate identity specification, implementation gates, candidate vectors, negative-vector matrix, and pre-freeze compatibility audit. It makes unresolved dependencies visible so that the designated protocol owner can review them in a controlled order.

This packet does not approve any protocol value. The existing register defines ACCEPTED as requiring explicit approval by the designated project decision owner and a recorded rationale. No such approval evidence was found in the reviewed artifacts. Therefore every decision below remains PROPOSED, PENDING, or DEFERRED as stated; none is upgraded to ACCEPTED here.

No source code, tests, workflows, dependency pins, Genesis fixtures, CometBFT settings, deployment settings, or keys were changed. No tests were run by creating this document.

## 2. Decision closure matrix

| ID | Decision area | Existing candidate direction | Current disposition | Evidence required before closure |
|---|---|---|---|---|
| DEC-01 | Exact schema and field set | Exact versioned field set; reject unknown/missing fields | PROPOSED / PENDING | Owner-approved schema, exact types, field semantics, extension policy, canonical example |
| DEC-02 | Integer semantics and numeric bounds | Exact bounded integers; reject bool/float/exponent forms; nonce U64 candidate | PROPOSED; numeric ceilings partly DEFERRED | Approved monetary units, inclusive bounds, cross-field rules, overflow behavior, cross-language boundary vectors |
| DEC-03 | Network/protocol identifier grammar | Narrow ASCII allow-list is proposed | PROPOSED; maximum length DEFERRED | Inventory of all existing IDs in fixtures/scripts/Genesis; explicit compatibility policy; accepted/rejected vectors |
| DEC-04 | Canonical JSON and wire acceptance | Strict UTF-8, duplicate-key rejection, canonical-byte equality | PROPOSED / PENDING | Normative parser behavior for BOM, duplicate keys at all depths, surrogate handling, numeric lexical forms, and byte equality |
| DEC-05 | Unicode and normalization | ASCII identifiers; no implicit normalization | PROPOSED / PENDING | Per-field character policy and explicit preserve/reject rules for non-ASCII fields |
| DEC-06 | Allocation ordering and duplicates | Deterministic order; reject duplicate account identities | PROPOSED / PENDING | Exact sort key/encoding, duplicate semantics, allocation-count bound, independent manifest vectors |
| DEC-07 | Domain separators and hash preimages | Separate domains; preserve legacy manifest hash | PROPOSED / PENDING | Exact domain bytes including NUL, exact field order/preimage bytes, legacy compatibility vectors, independent review |
| DEC-08 | HND identity vs CometBFT profile identity | Separate application identity and consensus profile identity | PROPOSED / PENDING | Exact identity envelope, profile binding artifact, trusted pin delivery, mismatch rejection before listen/sign |
| DEC-09 | CometBFT profile contents and pinning | Pin exact build and consensus-critical resolved parameters | PROPOSED / PENDING | Complete field inventory/classification, exact upstream commit/build, canonical profile digest, per-node mismatch tests |
| DEC-10 | Resource limits | Explicit deterministic bounds for parsing, transactions, blocks and arrays | PROPOSED; exact values DEFERRED | Ownership table (HND validity vs CometBFT consensus vs local operational), workload measurements, agreed numeric values and enforcement-path tests |
| DEC-11 | Stable machine-readable errors | Versioned error categories; diagnostic strings non-normative | PROPOSED / PENDING | Error-code registry, stable mapping, privacy constraints, negative-vector assertions |
| DEC-12 | Durable-store migration | Normal startup rejects legacy/mismatched stores; offline migration only | PROPOSED / PENDING | Target schema, no-rewrite guarantees, offline migration procedure, backups, crash-boundary tests and state commitments |
| DEC-13 | Upgrade activation and rollback | Coordinated activation; no unilateral rollback | PROPOSED / PENDING | Activation-height policy, validator readiness/quorum rules, mixed-version behavior, recovery and rollback threat model |
| DEC-14 | Independent vector generation/review | Independent generator and reviewer separate from implementation author | PROPOSED / PENDING | Named roles, reproducible toolchain, frozen expected literals, review record, executable negative suite and commit-bound evidence |

## 3. Critical dependency ordering

The decisions are not independent. The following order minimizes rework:

1. **Schema and semantics:** DEC-01, DEC-02, DEC-03, DEC-05 and DEC-06.
2. **Deterministic encoding:** DEC-04 and DEC-07. Do not freeze hashes before the exact schema, lexical number rules, Unicode policy and array ordering are fixed.
3. **Network identity:** DEC-08 and DEC-09. Keep HND application identity distinct from CometBFT profile identity; define the trusted artifact that binds them.
4. **Resource and error contract:** DEC-10 and DEC-11. Resource limits must be assigned to the layer that owns the validity decision.
5. **Persistence and lifecycle:** DEC-12 and DEC-13. Store migration depends on the final identity; activation depends on startup and persistence guards.
6. **Independent evidence:** DEC-14. Independent vectors and review must validate the frozen specification, not merely reproduce an implementation's assumptions.

## 4. Blocking technical questions

### 4.1 Monetary bounds

The protocol owner must distinguish:
- total supply and allocation arithmetic;
- maximum amount accepted by one transaction;
- absolute representable amount-field maximum;
- nonce maximum;
- any future issuance, burn, fee, or reward policy.

The historical one-million HND example is not evidence that one million is a hard protocol constant. No numeric maximum should be inferred from a sample Genesis.

### 4.2 Resource ownership

Every proposed limit must be classified as one of:
- **HND deterministic validity rule:** all validators enforce the same rule and it belongs in the HND application-config identity;
- **CometBFT consensus profile rule:** it belongs in the separately pinned CometBFT profile and must be checked consistently at startup;
- **local operational guard:** it may protect a node but must not cause validators to disagree on block validity.

In particular, do not treat CometBFT's proposal byte budget as proof that HND independently enforces a uniform transaction-byte limit in every ABCI acceptance path.

### 4.3 Network identifier compatibility

The current implementation accepts a broader identifier grammar than the proposed lowercase-only recommendation. The owner must choose an explicit versioned compatibility policy. Silent lowercasing, normalization, or rewriting is prohibited.

### 4.4 Identity and trust

A digest adjacent to a replaceable configuration file is not an authenticated trust anchor. The final design must specify where the expected digest comes from, who controls it, how it is distributed, and how the node fails closed before opening listeners or enabling signing.

### 4.5 Store migration

A Config-v1 startup must not silently rewrite a legacy store or accept a store missing the required identity. Migration must be a separately invoked offline operation with backup, no-mutation-on-failure, and interruption-recovery evidence.

## 5. Evidence status and CI interpretation

The latest observed workflow run for the preceding documentation commit was:

- Run: 42060219249
- Commit: d14f2ab2ab2aecb4a450468355a016c2d49f2966
- Overall result: completed / success
- Jobs: `hnd-v02-tests` — success; `cometbft-single-node-smoke` — success.

The CometBFT job included the repository's configured smoke/integration steps, including the private four-validator integration path. This is evidence that those configured jobs passed on that commit. It is not Config-v1 implementation evidence: the workflow does not establish a frozen Config-v1 schema, executable Config-v1 parser, Config-v1 store binding, or production network readiness.

The present packet is documentation-only. Any workflow run triggered by this new commit must be checked separately; the previous successful run must not be attributed to this new commit.

## 6. Owner review and approval record

For each DEC item, the owner should record:
- decision: ACCEPTED, REJECTED, or DEFERRED;
- exact adopted value or replacement proposal;
- rationale and compatibility impact;
- approver identity/role and date;
- required test/vector IDs;
- evidence commit or review reference.

Until that record exists, the decision remains unapproved. Silence, repeated review, successful CI, or a candidate vector reproduction does not constitute protocol approval.

## 7. Change gates

| Gate | Current status | Exit condition |
|---|---|---|
| Decision closure DEC-01–14 | BLOCKED | Explicit owner decisions recorded with rationale |
| Schema freeze | BLOCKED | DEC-01–07 resolved and canonical bytes fully specified |
| Executable golden/negative vectors | BLOCKED | Frozen schema/preimages plus independent expected literals |
| Config-v1 source implementation | NOT AUTHORIZED | Prior gates accepted and separate implementation authorization |
| Durable-store migration | NOT AUTHORIZED | DEC-12 accepted and migration design independently reviewed |
| Multi-validator Config-v1 acceptance | NOT RUN | Implemented Config-v1 identity/profile checks and mismatch tests |
| Public network / production signing / token issuance | NOT APPROVED | Separate security, custody, operations, governance, legal and independent-review gates closed |

## 8. Disposition

Continue specification and owner-review work only. Do not implement Config-v1 piecemeal, do not mark any DEC item accepted without explicit evidence, and do not interpret the successful legacy CI run as approval for a public network or production signing.
