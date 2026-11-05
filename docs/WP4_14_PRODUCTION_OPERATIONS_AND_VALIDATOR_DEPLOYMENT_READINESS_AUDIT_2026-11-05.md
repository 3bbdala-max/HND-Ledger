# WP4.14 — Production Operations and Validator Deployment Readiness Audit — 2026-11-05

**Branch:** `phase-0.2-planning`  
**Baseline commit reviewed:** `2c83ab9e99011155eb202aee2822b448d9aa3c08`  
**Review type:** static repository/workflow audit plus inspection of existing CI run  
**Disposition:** **NOT APPROVED FOR PRODUCTION OPERATIONS.** The repository demonstrates a useful disposable four-validator test network, but does not yet provide a production deployment, operations, monitoring, backup, or incident-response package.

## 1. Scope

Inspected:
- `hnd_v02/cometbft_v040_server.py`
- `scripts/cometbft_v040_four_validator_genesis_preflight.py`
- `scripts/cometbft_v040_four_validator_network_smoke.py`
- `scripts/hnd_peer_relay.py`
- `.github/workflows/hnd-v02-tests.yml`
- `docs/WP4_5_PRIVATE_FOUR_VALIDATOR_NETWORK_DESIGN_2026-11-01.md`
- `docs/WP4_14_KEY_CUSTODY_BACKUP_RECOVERY_DESIGN_2026-11-04.md`
- `docs/WP4_14_RELEASE_GOVERNANCE_AND_BRANCH_PROTECTION_AUDIT_2026-11-05.md`
- `docs/WP4_14_CI_COVERAGE_AND_RELEASE_GATE_AUDIT_2026-11-05.md`
- repository tree for deployment, service, monitoring, backup and release artifacts.

No production infrastructure, credentials, validator keys, deployment settings, source, tests or workflow files were changed. No new tests were executed for this audit.

## 2. Executive result

### What is demonstrated

- A local HND ABCI server can be started with explicit manifest, expected Genesis hash, network ID, protocol version, max amount and durable state path.
- The ABCI listener rejects non-loopback bind addresses while the transport is insecure.
- The disposable four-validator smoke harness generates independent temporary CometBFT homes, consensus identities and P2P node identities; creates common Genesis; starts four nodes and four HND application processes; and checks transaction/state convergence.
- The harness exercises one-validator stop/restart, signer outage/recovery, and 3/1 and 2/2 network partitions with reconnection.
- CI run **42023790531** on baseline commit **2c83ab9e99011155eb202aee2822b448d9aa3c08** completed successfully for both declared jobs.

### What is not demonstrated

- A production node installation and service lifecycle.
- A hardened, externally reachable P2P topology and a separately secured operator/RPC access path.
- Production key generation, enrollment, custody, rotation, revocation and recovery ceremony.
- Encrypted, off-host backups and tested disaster-recovery procedures.
- Monitoring, alerting, metrics export, log retention, audit event collection or on-call runbooks.
- Signed release artifacts, provenance, SBOM, vulnerability gates or deployment approval.
- Complete CI coverage of all recovery/anti-rollback tests.

**Overall production operations gate: OPEN / NOT APPROVED.**

## 3. Findings

### OPS-F1 — No production deployment or service-management artifacts found

**Severity: Critical for launch readiness.**

The repository tree contains no Dockerfile/Compose deployment, Kubernetes/Helm manifests, systemd service units, Ansible/Terraform infrastructure, production environment templates, or deployment scripts/runbooks. The Python server exposes a `main()` CLI entry point but does not define a production supervisor, service user, restart policy, resource limits, filesystem layout, or controlled shutdown procedure.

The four-validator scripts are explicitly disposable test harnesses. They create CometBFT homes under `TemporaryDirectory`, generate temporary identities, and launch subprocesses directly from the test script. The Genesis preflight explicitly states it starts no nodes.

**Impact:** successful test startup is not a repeatable, hardened production installation. Operators do not yet have an authoritative deployment contract.

**Required:** define supported host/OS/runtime versions, package and binary provenance, service account, directory ownership/modes, persistent volumes, process supervision, resource limits, restart policy, graceful shutdown, upgrade/rollback procedure and a per-validator deployment checklist. Keep secrets out of environment dumps and logs.

### OPS-F2 — Test network configuration is loopback-only and is not a production P2P deployment profile

**Severity: High.**

The ABCI gRPC server validates that its insecure listener binds only to a loopback IP literal. This is a valuable boundary for the current unauthenticated local ABCI transport, but it implies that CometBFT and its HND ABCI process must be co-located on the same host unless a separately secured transport is implemented.

The four-validator smoke harness also binds P2P and RPC endpoints to `127.0.0.1` and routes peer connections through loopback-only TCP relays. It disables P2P peer exchange and explicitly configures a private static peer mesh. These are test topology choices, not an externally routable production peer-discovery or firewall design.

**Impact:** the current harness does not establish how geographically or operationally separate production validators connect, how peer addresses are authenticated/maintained, or how RPC/operator access is exposed safely. Removing the loopback restriction or exposing the current insecure ABCI endpoint would be unsafe.

**Required:** preserve the local-only ABCI boundary unless TLS/mTLS and peer/client authorization are implemented and reviewed. Define production P2P address/peer strategy, firewall rules, RPC exposure policy, private operator access, DDoS/rate-limit posture and network segmentation. Add deployment tests that verify no administrative or ABCI endpoint is unintentionally public.

### OPS-F3 — No production monitoring, metrics, alerting or operational health contract found

**Severity: High.**

The inspected HND server starts a gRPC server and waits for termination; no HND metrics exporter, readiness/liveness endpoint, structured operational event stream, alert rules or monitoring configuration was found in the deployment tree. The smoke scripts poll CometBFT RPC endpoints and ABCI Info as test assertions and capture process logs into temporary files. That is test instrumentation, not production observability.

**Impact:** an operator has no repository-defined alerting contract for stalled height, validator voting power loss, app-hash mismatch, signer disconnection, disk pressure, state-store write failure, peer churn or abnormal restart loops.

**Required:** define a minimum observability contract and alerts for:
- committed height/block progress and validator participation;
- HND/CometBFT height and app-hash mismatch;
- peer count/connectivity and quorum loss;
- signer connectivity, signing failures and anti-double-sign state errors;
- ABCI request errors/latency and application crashes;
- disk capacity, state-file growth, fsync/write failures and host resource pressure.
Logs must be structured, timestamped, access-controlled, retained and scrubbed of secrets. Monitoring must not expose private signing material.

### OPS-F4 — Backup, restore and key custody remain design-only, not an operator procedure

**Severity: Critical for production validator continuity.**

The key custody document explicitly labels itself design-only and states that it does not provision an HSM/KMS, create production keys or authorize live signing. It recommends separate identities for consensus signing, anti-double-sign state, P2P, remote-signer transport, admin access and backup encryption.

The integration tests use temporary homes and disposable keys. The signer outage/recovery tests verify bounded test-state persistence, but do not establish an approved production ceremony, off-host encrypted backup, quorum-controlled recovery, key rotation, revocation, HSM disaster recovery or periodic restore drill.

**Impact:** test success cannot be used as evidence that production validator signing authority can be safely backed up or restored. Loss or substitution of signing/anti-double-sign state can have consensus safety consequences.

**Required:** approve a production key custody design and provider-specific runbook; require non-exportable keys or a documented offline ceremony; separate backup encryption keys from backups; require multi-person recovery authorization; define key inventory, rotation/revocation and incident response; and conduct witnessed restore drills with synthetic keys before live signing.

### OPS-F5 — Current CI omits two recovery-related Python test modules from its explicit test command

**Severity: High for assurance and regression coverage.**

The workflow's `Run isolated v0.2 tests` command lists nine modules but does not list:
- `tests.test_v02_anti_rollback_reference`
- `tests.test_v02_recovery_controls`

This omission is consistent with the earlier CI coverage audit. The current green run cannot be cited as proof that these two modules were run. The second CI job's remote-signer integration probes are separate tests and do not execute these Python modules or establish an independent HND application monotonic trust anchor.

**Impact:** recovery-related tests exist in the repository but are not proven by the current declared CI test command. A green workflow can therefore overstate the exercised regression surface if the omitted modules are described as covered.

**Required:** add the intended modules to the workflow or create separate required jobs; ensure test names and run logs prove execution; and make the required checks enforceable through branch protection/rulesets. Keep anti-rollback reference-model evidence distinct from production anti-rollback implementation evidence.

### OPS-F6 — CI is a test workflow, not a production release/deployment pipeline

**Severity: High.**

The workflow builds CometBFT from the `v0.40.0` branch tag and uses GitHub Actions references such as `actions/checkout@v4`, `actions/setup-python@v5`, and `actions/setup-go@v6`. It runs tests and integration smoke checks; it does not produce a signed release, publish a provenance attestation or SBOM, perform a production deployment approval, or verify a signed immutable deployment artifact.

The existing supply-chain and release-governance audits separately record dependency pinning, action immutability, branch protection and release approval gaps.

**Impact:** a successful CI run proves the listed test commands passed on a particular commit. It does not prove that a production binary was reproducibly built, independently reviewed, signed, promoted or deployed from that commit.

**Required:** establish immutable source/toolchain/action references, dependency lockfiles and hashes, SBOM and vulnerability scanning, reproducible build/provenance attestations, signed artifacts/tags, independent release approval and a staged promotion process. Deploy only artifacts whose source commit and configuration identities are authenticated.

### OPS-F7 — Test logs and diagnostics are temporary and do not establish production audit retention

**Severity: Medium-High.**

The four-validator harness redirects stdout/stderr to log files under a temporary directory and reads log tails for failure diagnostics. The temporary directory is removed after the test exits. This is appropriate for disposable CI fixtures but does not define production log forwarding, retention, tamper resistance, access policy or incident evidence preservation.

**Required:** define centralized log collection, retention periods, access controls, integrity protection, incident export and secret redaction. Preserve signer security events and operator actions without logging private key material.

## 4. Operational acceptance checklist

Production operations must remain blocked until all applicable items are evidenced:

- **OPS-T01:** install from a signed immutable release artifact on a clean supported host; verify binary and source provenance.
- **OPS-T02:** run the ABCI app and CometBFT under dedicated least-privilege service identities; verify directory ownership, permissions and restart/shutdown behavior.
- **OPS-T03:** prove ABCI remains loopback-only and inaccessible from remote hosts; prove RPC/admin endpoints are private and protected.
- **OPS-T04:** prove production P2P connectivity using documented firewall and peer configuration, without test-only relays.
- **OPS-T05:** configure and exercise liveness/readiness and alerting for stalled blocks, lost quorum, app-hash mismatch, signer outage and storage failures.
- **OPS-T06:** generate/enroll synthetic validator identities using the approved custody procedure; prove no private key bytes enter CI, logs or source control.
- **OPS-T07:** perform encrypted off-host backup and witnessed restore drills, including wrong-validator, stale-state, missing anti-double-sign state and key-provider outage cases.
- **OPS-T08:** execute the documented incident procedures for signer compromise, host compromise, lost peer identity, disk failure, accidental rollback and emergency validator maintenance.
- **OPS-T09:** execute the full required CI matrix, including anti-rollback and recovery-control modules, and enforce checks on the intended protected branch.
- **OPS-T10:** publish signed artifact, SBOM, provenance and independent approval record; perform staged deployment and rollback drill.
- **OPS-T11:** verify monitoring/logging retention, access policy, secret redaction and evidence preservation.
- **OPS-T12:** demonstrate a four-validator operational run with persistent non-disposable homes and identities in a controlled non-production environment, including restart, partition, recovery and key custody controls.

## 5. CI evidence inspected

Existing run:
- [GitHub Actions run 42023790531](https://github.com/3bbdala-max/HND-Ledger/actions/runs/42023790531)
- Commit: `2c83ab9e99011155eb202aee2822b448d9aa3c08`
- `hnd-v02-tests`: completed successfully.
- `cometbft-single-node-smoke`: completed successfully.

The integration job includes disposable single-node and four-validator network smoke tests, four-validator Genesis preflight, signer outage/recovery, and authenticated Noise signer recovery. This is valuable test evidence, but it does not cover production deployment artifacts or the operational acceptance tests above.

## 6. Gate disposition

| Area | Disposition |
|---|---|
| Disposable four-validator integration harness | PASS for existing CI scenario |
| HND ABCI loopback bind restriction | PASS for current insecure transport boundary |
| Production service/deployment package | NOT PRESENT |
| Production P2P/RPC/firewall profile | NOT ESTABLISHED |
| Production monitoring/alerting | NOT ESTABLISHED |
| Production key custody and backup implementation | DESIGN ONLY |
| Backup/restore operational drill | NOT ESTABLISHED |
| Recovery-related Python CI module coverage | INCOMPLETE |
| Signed release/provenance/SBOM/deployment approval | NOT ESTABLISHED |
| Production operations readiness | NOT APPROVED |

## 7. Limitations and final decision

This report is a repository and workflow audit, not a penetration test, host audit, cloud-account inspection, HSM assessment or production deployment. Absence claims are limited to the inspected repository tree and files. No external infrastructure or secret stores were inspected.

The loopback-only ABCI policy is a positive security boundary for the current unauthenticated gRPC transport; it must not be weakened merely to simplify deployment. Production topology should keep CometBFT and its HND ABCI process co-located unless a separately secured authenticated transport is implemented.

**Final decision: do not launch production validators or accept real signing authority on the basis of the current green CI.** The project has a credible disposable integration harness, but production deployment, operations, key custody, backup/restore, observability and release governance remain unapproved. Complete OPS-T01–OPS-T12 and close the related anti-rollback, configuration-identity and upgrade findings before reconsidering launch readiness.

No code, tests, workflow, deployment or production configuration was modified.
