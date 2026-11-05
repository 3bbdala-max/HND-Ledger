# WP4.14 — Consolidated Security Posture and Launch Gate Assessment — 2026-11-05

**Branch:** phase-0.2-planning  
**Reviewed baseline:** 931c770ac1828a6a46140a54b7a5861c9794ed9d  
**Assessment:** Repository source, tests, CI and prior audit consolidation; not an independent penetration test.  
**Decision:** **NOT APPROVED FOR PUBLIC NETWORK, PRODUCTION SIGNING, TOKEN ISSUANCE OR EXCHANGE LAUNCH.**

## 1. Scope and method

This assessment consolidates the current HND v0.2 source, tests, workflow and previous WP4.14 audits. It distinguishes implemented controls from bounded test evidence and unresolved production requirements. No source, test, workflow, dependency, deployment setting, key or production configuration was modified. No new tests or network probes were executed.

## 2. Executive decision

HND v0.2 has a useful deterministic application core, transaction signature checks, Genesis identity checks, durable local state recovery and a disposable four-validator CometBFT integration harness. The insecure ABCI listener's non-loopback bind defect has been closed with code and CI evidence.

The current evidence does not establish a production-grade security boundary or safe public-network launch. The highest-risk open issues are:
1. Production validator key custody and anti-double-sign state protection are not implemented as a complete independently anchored production service.
2. Consensus-critical application configuration is not fully committed to authenticated network identity; max_amount remains independently supplied.
3. HND application state has no independent monotonic anti-rollback anchor.
4. Protocol upgrade activation and deterministic state migration are not implemented.
5. Production deployment, monitoring, backup, incident response and release provenance are not established.
6. Genesis CLI parsing still uses ordinary json.load without explicit duplicate-key rejection.
7. The ABCI local process trust boundary remains broad: the loopback listener is not authenticated or authorized at caller level.

**Overall gate: OPEN / NOT APPROVED.** Green CI means configured disposable test jobs passed for a tested commit; it does not close the production gates below.

## 3. Confirmed closures and bounded passes

### C-01 — Insecure ABCI listener non-loopback bind containment
**Status: CLOSED for this code path.**

The current loopback bind validator accepts loopback IP literals only and rejects hostnames and non-loopback addresses before the gRPC server is created or bound. Regression tests cover accepted IPv4/IPv6 loopback forms and rejected remote/hostname forms. The closure report records CI evidence.

**Boundary:** gRPC remains insecure and unauthenticated. Loopback binding prevents remote network binding; it does not authenticate local processes, enforce method authorization, or make remote ABCI transport safe. Do not weaken this rule as a deployment shortcut.

### C-02 — Transaction-envelope cryptographic integrity
**Status: PASS for the implemented transaction-envelope scope.**

Ed25519 signatures bind transaction fields under domain-separated signing bytes; tests cover tampering, sender/key mismatch, malformed signatures, network/version mismatch and nonce/replay behavior.

**Boundary:** this is not production wallet custody, validator consensus-key custody, HSM/KMS integration, key lifecycle management or independent signer anti-double-sign assurance.

### C-03 — Ledger accounting and replica convergence
**Status: PASS for tested application-level invariants.**

Transfer accounting preserves the tested total-supply invariant, and application-level four-replica tests establish convergence when replicas receive identical inputs and configuration.

**Boundary:** this does not prove identical production configuration, complete monetary bounds, issuance governance or real-world multi-operator network safety.

### C-04 — Local durable-store integrity and restart
**Status: PASS for bounded local recovery checks.**

The store validates schema, checksum, network/protocol/Genesis identity, height/hash fields, ledger replay and application hash. Recovery mode can refuse missing state. Existing tests cover corruption and uncommitted-state discard. A four-validator harness tests one-node outage/restart and catch-up.

**Boundary:** an unkeyed checksum is not authenticity or freshness. A valid old store can be internally consistent; no independent monotonic HND application-state anchor is established.

### C-05 — Four-validator disposable integration
**Status: PASS for the CI harness scenarios inspected.**

The harness uses temporary homes and disposable keys, tests common Genesis, P2P network formation, convergence, partitions/reconnection and signer outage/recovery.

**Boundary:** this is not production peer deployment, long-duration reliability, real key custody, independent P2P identity review, multi-validator rollback recovery or mixed-version upgrade safety.

## 4. Open findings ranked by launch risk

### BLOCKER-01 — Production validator key custody and independent anti-double-sign assurance
**Severity: Critical — launch blocker.**

The repository contains disposable CometBFT signing and remote-signer probes and a bounded synthetic anti-rollback reference model. The reference model is not a production remote signer with an independently protected monotonic trust anchor. Stage A's review register remains open and calls for independent review, provider selection, anchor compromise/outage procedures, schema migration policy, operator separation and tamper-evident audit evidence.

No production HSM/KMS/TPM/witness provider is selected or provisioned. No production key ceremony, two-person custody enforcement, revocation/rotation, witnessed recovery drill or complete independent-anchor recovery procedure is evidenced.

**Required closure:** select and independently review the trust-anchor/signer architecture; bind validator/network context, monotonic sequence, predecessor, complete state digest and signing status atomically; implement production-grade persistence and failure-domain separation; define compromise, outage, partition, migration and recovery procedures; complete the acceptance matrix and independent reviewer sign-off. Do not authorize live consensus signing before closure.

### BLOCKER-02 — Consensus-critical application configuration is not fully bound to network identity
**Severity: Critical — safety and deterministic-execution blocker.**

The same Genesis manifest/hash and protocol version can be paired with different CLI-supplied max_amount values. This setting changes transaction acceptance but is not committed by the current Genesis hash or durable-store identity. The four-validator harness passes the same value to all test nodes by construction; this does not prove a production node rejects a mismatch.

The CometBFT profile identity is also not bound to a complete authenticated application configuration digest.

**Required closure:** approve and freeze Config-v1 schema and canonical encoding; bind every consensus-critical field and the relevant CometBFT profile to a pinned identity; verify before listener startup and before signing; persist the digest in a versioned store; add one-field mutation and mixed-config negative tests across four validators. Do not implement a partial interim identity.

### BLOCKER-03 — HND application anti-rollback and cross-store recovery reconciliation are incomplete
**Severity: Critical — recovery/safety blocker.**

The durable store uses an unkeyed SHA-256 checksum and has no independently protected monotonic application-state high-water mark. A prior valid store with a matching checksum can be substituted. The HND startup path exposes its local height/app hash through ABCI Info but does not itself reconcile that tuple against an independently authenticated CometBFT checkpoint before opening the listener.

CometBFT maintains its own native block store and consensus recovery mechanisms. This report does not claim those upstream mechanisms are absent or that CometBFT will accept arbitrary stale state. The gap is that HND's application layer does not establish an independent authenticated freshness anchor and startup cross-store contract.

**Required closure:** define a separate trust domain for a monotonic anchor; fail closed if the anchor is unavailable, behind or inconsistent; bind height, app hash, network/config identity and predecessor; define safe ahead/behind recovery; test old-valid-store substitution, coordinated rollback of both data directories, app-ahead/behind, same-height hash mismatch and interrupted recovery.

### BLOCKER-04 — No network upgrade protocol or deterministic migration
**Severity: Critical — future protocol-change blocker.**

No activation-height upgrade plan, authenticated governance authorization, validator readiness barrier, upgrade handler, deterministic state migration, compatibility window or post-activation rollback policy was found. A protocol-version mismatch against a persisted store is rejected; that is a fail-closed mismatch check, not an upgrade mechanism.

**Required closure:** specify and implement a versioned upgrade state machine with authorized plan, activation height, software/config digest, deterministic migration, offline-validator rejoin behavior, pre-activation abort and post-activation recovery policy. Test mixed versions and validators returning after activation.

### BLOCKER-05 — Production operations and release governance are not established
**Severity: Critical — launch blocker.**

No complete production deployment/service package, supported host baseline, hardened peer/RPC/firewall profile, metrics/alerting contract, off-host backup and restore drill, incident-response runbook, production key custody implementation, signed release artifact, provenance attestation or SBOM pipeline is established by the inspected repository evidence.

**Required closure:** complete the production operations acceptance checklist, release governance and branch-protection evidence, signed reproducible release process, staged deployment, backup/restore drill, monitoring and incident response. Disposable test homes and temporary keys are not substitutes.

### HIGH-01 — Local ABCI caller authentication and host filesystem trust
**Severity: High.**

The ABCI gRPC endpoint is loopback-only but uses insecure transport and no caller authentication, authorization or method ACL. Any process able to connect locally may reach application methods. The state writer's checksum is not authentication, and startup does not enforce owner/mode policy for the state directory, existing state file or manifest file. Manifest provenance is content consistency, not authenticated provenance.

**Required closure:** document the trusted-host threat model; isolate service account and processes; enforce directory/file ownership and restrictive permissions; reject unsafe paths/symlinks where applicable; protect manifest/config provenance; consider local authenticated IPC or OS-level access controls and test unauthorized local-process behavior. Keep remote binding disabled until a separate authenticated transport is reviewed.

### HIGH-02 — Genesis CLI strict duplicate-key parsing remains open
**Severity: High.**

The CLI manifest path in cometbft_v040_server.py currently opens UTF-8 text and calls ordinary json.load. Duplicate JSON object members are not explicitly rejected before conversion into a Python object. The ABCI app-state decoder has a canonical-byte equality defense that rejects noncanonical duplicate-key encodings in practice, and the durable store loader uses duplicate-aware parsing, but those do not close the CLI manifest path.

**Required closure:** implement one shared strict parser with duplicate-key rejection at all object depths, strict UTF-8, explicit BOM policy, stable errors and raw-byte tests. Preserve the published Genesis hash vector exactly. This change still requires explicit authorization for source/test edits.

### HIGH-03 — Transaction/resource limits and unbounded query growth
**Severity: High.**

The prior resource audit found that the application transaction-count limit does not constitute a complete independent transaction-byte policy across all ABCI acceptance paths. PrepareProposal applies a max-byte parameter, while ProcessProposal/FinalizeBlock do not independently establish the same complete local aggregate bound and rely on CometBFT behavior. The /evidence query returns the complete evidence journal without pagination. Full transaction history is replayed from Genesis on restore, without checkpoint/pruning or long-horizon benchmark evidence.

**Required closure:** define protocol-bound per-transaction, aggregate-block, nesting, collection and query-response limits; enforce identical deterministic acceptance across CheckTx/PrepareProposal/ProcessProposal/FinalizeBlock; paginate or bound evidence queries; benchmark state growth and recovery over representative long histories; bind consensus-critical limits to Config-v1.

### HIGH-04 — Production P2P identity/topology and replay claims are bounded
**Severity: High.**

HND does not implement an independent peer-authentication protocol. Peer transport and consensus identity are CometBFT responsibilities and must be configured and audited separately. The four-ABCI fan-out tests are not P2P tests; TCP relays prove connectivity disruption, not message authentication or protocol replay rejection. Existing P2P equivocation integration is useful but does not establish a production peer allowlist, network segmentation, external address strategy or full message-replay test matrix.

**Required closure:** pin and inspect exact CometBFT source/config; document node-key and validator-key custody separately; define peer allowlists, persistent peers, seeds, firewall and RPC policy; archive connection evidence; add unexpected-peer, malformed/delayed/replayed-message, partition and reconnection tests.

### HIGH-05 — CI does not explicitly execute all recovery reference/control modules
**Severity: High for assurance.**

The current workflow's isolated v0.2 test command lists nine modules but omits tests.test_v02_anti_rollback_reference and tests.test_v02_recovery_controls. The remote-signer integration probes are separate and do not prove these Python modules ran or establish production anti-rollback implementation.

**Required closure:** include intended modules in required CI jobs or create explicit jobs; inspect logs proving execution; enforce required checks on the intended protected branch. Keep reference-model test results separate from production signer assurance.

### HIGH-06 — Software supply-chain and release integrity are incomplete
**Severity: High.**

cryptography is declared as >=41.0; no complete Python lockfile/hash set or Go module checksum manifest for the build process was found in the reviewed tree. GitHub Actions use mutable major-version tags; CometBFT is cloned by the v0.40.0 tag without a separately verified commit SHA. No SBOM, signed artifact, provenance or vulnerability-gate workflow is established.

**Required closure:** immutable action and source commit references, full dependency locking/hashes, Go module verification, SBOM, vulnerability scanning, reproducible build/provenance, signed release artifacts and independent promotion approval.

### MEDIUM-01 — Query error diagnostics disclose caller-supplied account/request data
**Severity: Medium.**

The /account query exception path appends the requested account ID and raw request bytes in hexadecimal to the returned error. These are not private keys, but reflecting arbitrary request data can expose user-supplied identifiers/content and amplify logs/responses.

**Required closure:** return stable generic error categories; bound diagnostic size; keep sensitive/raw request details out of caller-visible errors and production logs; add tests proving bounded non-reflective errors.

### MEDIUM-02 — Durable-store checksum and manifest hash are not authenticity anchors
**Severity: Medium as a standalone integrity primitive; Critical when relied upon for anti-rollback.**

SHA-256 detects accidental corruption when compared against the stored checksum, and the manifest hash provides content identity when compared with a trusted expected value. Neither is an authenticated trust anchor if the expected value and data can be replaced together by the same attacker.

**Required closure:** document threat boundaries and use an independently protected anchor for freshness/provenance. Do not describe an unkeyed checksum as authentication.

## 5. Stale-document and status reconciliation

The older SECURITY_REMEDIATION_PLAN_PRE_CONFIG_V1 report still describes the P0 listener exposure as open. The later P0_LOOPBACK_ABCI_LISTENER_CLOSURE_EVIDENCE report records the code fix and CI evidence and is the controlling status for that narrow issue.

Therefore:
- P0 non-loopback ABCI bind: CLOSED for the current server code path.
- Insecure/unauthenticated local gRPC and remote transport: still constrained/open as described above.
- P1 strict CLI Genesis duplicate parsing: OPEN.
- Config identity, application anti-rollback, upgrade, key custody and production operations: OPEN.

The older remediation plan is a historical baseline, not the current status register. No finding is closed merely because a design document or unit test exists; closure requires implementation and relevant integration evidence.

## 6. Consolidated launch acceptance matrix

| Gate | Required evidence | Current disposition |
|---|---|---|
| G1 — deterministic application core | vectors, negative validation, replica convergence | PARTIAL PASS |
| G2 — complete config identity | Config-v1 digest, startup/store binding, mismatch rejection | OPEN |
| G3 — production signer and anti-double-sign | independent anchor, custody, outage/rollback/compromise tests, independent review | OPEN |
| G4 — application anti-rollback/recovery | old-store rejection, cross-store reconciliation, backup restore | OPEN |
| G5 — upgrade protocol | activation height, migration, mixed-version and offline-node tests | OPEN |
| G6 — network transport and host trust | peer topology, local process authorization, permissions, firewall/RPC tests | OPEN |
| G7 — resource and abuse limits | uniform byte/count/query limits, stress and growth benchmarks | OPEN |
| G8 — production operations | deployment, monitoring, backup, incident response and restore drill | OPEN |
| G9 — supply chain and release | lockfiles, immutable sources, SBOM, provenance, signed artifacts and approvals | OPEN |
| G10 — independent security review | reviewer scope, report, residual risks, explicit approval | OPEN |

## 7. CI evidence boundary

The most recent workflow inspected was run 42026203133 on commit 931c770ac1828a6a46140a54b7a5861c9794ed9d. At the time of final API inspection it remained in_progress; hnd-v02-tests had completed successfully, while cometbft-single-node-smoke was still running. No final workflow conclusion is claimed here.

Earlier workflow run 42023790531 on commit 2c83ab9e99011155eb202aee2822b448d9aa3c08 completed successfully for both declared jobs. This is evidence for that commit and its configured commands only; it does not include the later documentation commit or close findings in this assessment.

No new tests were executed during this report preparation.

## 8. Claims that must not be made

Until the open gates are closed, do not claim:
- production-ready or publicly launchable blockchain;
- independent anti-double-sign or rollback-resistant production signer;
- all validators guaranteed to use identical transaction acceptance rules;
- safe protocol upgrades or automatic state migration;
- production-grade state sync or disaster recovery;
- production key custody, wallet security or HSM integration;
- complete P2P authentication/replay protection from HND itself;
- audited, signed or reproducible production release;
- independent security certification.

## 9. Final decision

**HND v0.2 is a promising reference implementation with useful deterministic logic and disposable CometBFT integration evidence. It is not approved for public-network launch, production validator signing, token issuance, sale or exchange activity.**

Recommended remediation sequence:
1. Complete independent signer/anti-double-sign architecture and trust-anchor decisions.
2. Freeze and implement Config-v1 identity before further consensus-critical configuration work.
3. Implement application-state freshness and cross-store recovery reconciliation.
4. Complete strict Genesis parsing and uniform resource limits.
5. Define and implement upgrade governance/migration.
6. Complete production host/network/operations and release controls.
7. Run the full negative acceptance matrix and obtain independent security review.

No source, test, workflow, deployment or production configuration changes were made. This report is not a substitute for an independent security audit, penetration test or legal/regulatory review.
