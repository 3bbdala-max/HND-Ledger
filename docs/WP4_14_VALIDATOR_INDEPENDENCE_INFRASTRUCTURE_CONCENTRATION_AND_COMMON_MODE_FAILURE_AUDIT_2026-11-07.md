# WP4.14 — Validator Independence, Infrastructure Concentration and Common-Mode Failure Audit

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Review type:** Static source, CI workflow and prior audit review; documentation-only.  
**Decision:** **NOT APPROVED** for claims of production decentralization, independent validator operation, production signing or public-network launch.  
**Change boundary:** This report adds documentation only. No source, tests, workflows, validator keys, deployment configuration or runtime behavior changed.

## 1. Executive determination

The repository now demonstrates a meaningful four-validator **local integration topology**: four CometBFT node processes, four HND ABCI application processes, unique disposable consensus and P2P identities, a shared test Genesis, loopback peer relays, partition simulations, catch-up/recovery, and optional remote-signer probes.

It does **not** demonstrate four independently operated production validators.

The four-validator smoke script creates one temporary root directory, four CometBFT homes, four HND state files, and starts all node/application processes as child processes from one Python test process. All P2P, RPC and ABCI endpoints are bound to `127.0.0.1`; peer connections are routed through local TCP relays. The CI workflow runs the entire sequence on one `ubuntu-latest` GitHub Actions runner. These choices are appropriate for deterministic integration testing, but they create a shared host, kernel, runner lifecycle, filesystem, CI control plane and likely common administrative boundary.

The test's 3/1 and 2/2 network partitions prove selected consensus and liveness behaviors under controlled peer-link isolation. They do not simulate a physical host failure, cloud-region outage, independent operator compromise, shared credential compromise, shared DNS/control-plane failure, or correlated signer/key-custody loss.

The authenticated Noise remote-signer probe establishes authenticated transport and peer rejection within a disposable local test. It does not establish that validators or signers are controlled by separate organizations, accounts, hosts, regions, HSMs or administrators. Process separation is not infrastructure independence.

**Conclusion:** the evidence supports the statement “four local validator processes can participate in a controlled integration smoke test.” It does not support “four independent operators secure the network,” “the network is decentralized,” or “the network tolerates one independent infrastructure operator failure.”

## 2. Evidence inspected

### 2.1 Four-validator network smoke

File: `scripts/cometbft_v040_four_validator_network_smoke.py`

Observed implementation facts:

- The script uses `tempfile.TemporaryDirectory(prefix="hnd-four-validator-")` as a common temporary root.
- It creates four validator homes below that root and starts four HND ABCI servers and four CometBFT node processes using `subprocess.Popen` from the same Python parent process.
- Each validator receives a fresh disposable CometBFT consensus identity and P2P node identity. Uniqueness is checked.
- The four fixture validators are assigned voting power 10 each (total 40); this is test data, not a production power policy.
- P2P, RPC and ABCI endpoints are explicitly assigned `127.0.0.1` addresses. The persistent-peer mesh also uses loopback relay ports.
- Directed TCP relays allow the harness to simulate exact peer sets and 3/1 and 2/2 partitions. These are logical link partitions on one host, not independent network/provider failure domains.
- The script stops/restarts processes and checks recovery, state convergence and quorum behavior. Its own final result labels scope as a local four-validator crash-stop integration, not Byzantine-fault proof.
- The harness reports temporary keys and state only. It does not provision durable production validator identities.

### 2.2 Genesis preflight

File: `scripts/cometbft_v040_four_validator_genesis_preflight.py`

The preflight creates four independent temporary CometBFT homes and unique disposable identities, but it explicitly does not start nodes. Its four equal powers of 10 are generated test values. It proves local Genesis construction, identity uniqueness and byte equality, not independent validator ownership or deployment.

### 2.3 CI execution boundary

File: `.github/workflows/hnd-v02-tests.yml`

The job uses `runs-on: ubuntu-latest`. The four-validator network, remote signer, Noise signer, outage/recovery and partition tests are steps in the same `cometbft-single-node-smoke` job. No matrix of independently provisioned hosts, cloud accounts, regions or operators is defined in the workflow. A successful run therefore remains evidence from one CI runner environment.

### 2.4 Remote signer boundary

Files:
- `scripts/cometbft_v040_remote_signer_process_probe.go`
- `scripts/cometbft_v040_noise_remote_signer_helper.go`
- `scripts/cometbft_v040_noise_remote_signer_probe.go`

The process probe explicitly describes a child process and temporary Unix socket; it also states that the Unix socket is unencrypted and the test is about process separation/protocol behavior, not production key custody. The Noise helper explicitly labels itself test-only, loopback and ephemeral. The four-validator harness runs the signer helper as another subprocess under the same temporary root and same CI job.

Noise authentication is a transport peer-authentication property. It does not prove independent physical hosting, operator separation, independent root credentials, HSM custody, cloud-account separation or disaster-recovery independence.

### 2.5 Production operations and governance evidence

Related repository audits:
- `docs/WP4_14_PRODUCTION_OPERATIONS_AND_VALIDATOR_DEPLOYMENT_READINESS_AUDIT_2026-11-05.md`
- `docs/WP4_14_VALIDATOR_SET_GOVERNANCE_VOTING_POWER_AND_KEY_ROTATION_AUDIT_2026-11-07.md`
- `docs/WP4_14_VALIDATOR_DEVICE_LOSS_KEY_COMPROMISE_SIGNER_REPLACEMENT_AND_SAFE_RECOVERY_AUDIT_2026-11-07.md`
- `docs/WP4_14_NETWORK_BOOTSTRAP_GENESIS_CEREMONY_AND_VALIDATOR_TRUST_DISTRIBUTION_AUDIT_2026-11-07.md`
- `docs/WP4_14_COMETBFT_NETWORK_PROFILE_AND_VALIDATOR_IDENTITY_AUDIT_2026-11-05.md`
- `docs/WP4_14_COMETBFT_VALIDATOR_IDENTITY_GENESIS_PINNING_AUDIT_2026-11-05.md`

The production-operations audit records no production Docker/Compose, Kubernetes/Helm, systemd, Ansible/Terraform deployment package, production P2P topology, monitoring/alerting, or tested off-host disaster-recovery runbook. The key-recovery audit records no production HSM/KMS, independently administered durable anti-double-sign anchor, or restore quorum. These are repository evidence gaps; they do not prove that no external infrastructure exists, but no external infrastructure evidence was supplied by the reviewed repository.

## 3. Infrastructure-independence matrix

| Dimension | Evidence in repository/CI | What is not established | Status |
|---|---|---|---|
| Process identity | Four CometBFT and four HND processes; child-process lifecycle tests | Independent failure domains | Test-only |
| Host/kernel | One temporary root and one CI runner for the smoke job | Separate physical/virtual hosts, kernels and host administrators | Not established |
| Cloud account/project | Single GitHub Actions execution context | Separate cloud accounts/projects and billing/control-plane ownership | Not established |
| Region/zone | Loopback-only test endpoints | Region/zone diversity and correlated outage analysis | Not established |
| Operator/org | No signed operator roster or independent operator attestations in reviewed artifacts | Separate legal entities, personnel, approval channels and incident authority | Not established |
| Consensus keys | Fresh unique disposable consensus identities in tests | Production key enrollment, custody and independent key owners | Test-only |
| Signer processes | Local child-process and Noise integration probes | Independent HSM/KMS partitions, operator separation and signer-side fencing in production | Not established |
| P2P network | Static peer mesh via loopback relays; PEX disabled in harness | Public/private routable topology, firewalls, sentries, DDoS controls and provider diversity | Not established |
| DNS/control plane | No production deployment profile found | DNS registrar/provider separation, account controls and recovery | Not established |
| Backups | Disposable temporary test state | Encrypted off-host backups, separate administrators and tested restores | Not established |
| CI/release authority | One GitHub Actions workflow/runner job | Independent build/release approvals, credential separation and signed provenance | Not established |
| Monitoring/incident response | Test polling and temporary logs | Independent monitoring, paging, on-call and incident command | Not established |

A blank or unverified cell must not be represented as diversity. A future operator questionnaire or infrastructure diagram is not evidence until backed by independently verifiable deployment records, attestations and failure tests.

## 4. Consensus power, collusion and capture model

CometBFT consensus safety is weighted by **voting power**, not by validator process count.

For total voting power (P):

- Byzantine voting power must remain strictly below (P/3) for the usual BFT safety assumption.
- A commit requires more than (2P/3) voting power in the relevant precommit quorum.
- A partition or outage that leaves no side with more than (2P/3) may stop progress.
- A coalition's influence is the sum of its voting power. “Three of four validators” is meaningful only if the powers are equal and the exact active set is known.

For the current test fixture only, each of four validators has power 10, so (P=40). One validator represents 25% of power; two represent 50%; three represent 75%. A three-validator side can exceed the commit threshold in this equal-weight fixture, while a 2/2 split leaves each side at 50% and neither side can commit. This arithmetic is not a proposed production roster or concentration policy.

The current test fixture does not establish a production power cap, minimum independent operator count, ownership separation, stake model, or anti-capture rule. Four keys controlled by one operator, one shared cloud account or one privileged deployment credential are not four independent trust domains.

## 5. Common-mode failure and adversary scenarios

The deployment threat model must explicitly address:

1. **Shared host/root compromise:** one host administrator or kernel compromise can affect all four local processes and local signer helpers.
2. **Shared CI credential compromise:** a repository/workflow credential or privileged runner compromise can alter the same build/test/deployment control plane.
3. **Shared operator compromise:** one organization or person may control multiple nominal validators despite separate keys.
4. **Shared cloud account/control plane:** account suspension, IAM compromise, quota exhaustion or provider incident may remove several validators simultaneously.
5. **Shared region/zone/network:** power, routing, transit, firewall or regional outage can correlate failures.
6. **Shared signer custody:** common HSM/KMS tenant, recovery administrator, backup key or anti-double-sign anchor can become a common failure point.
7. **Shared DNS/domain dependency:** name-resolution or registrar compromise may disrupt discovery and operator access.
8. **Shared software supply chain:** a single compromised build, package source or release signer can distribute the same malicious binary to every validator.
9. **Coordinated collusion:** nominally separate validators may vote as one coalition; measure the coalition by voting power and control relationships.
10. **Network partition plus failover:** automatic failover may accidentally permit two signers or stale hosts to act concurrently unless signer-side fencing is enforced.
11. **Monitoring monoculture:** one compromised or unavailable monitoring plane may hide correlated failures.
12. **Backup monoculture:** copies in separate directories or processes are not independent backups if they share credentials, host, region or encryption root.

## 6. Required production architecture evidence

Before any decentralization or independent-operator claim, require an owner-approved and independently reviewed deployment package containing:

- Validator-to-operator mapping with legal/operator identities, accountable contacts and signed acceptance.
- Per-validator host, cloud account/project, region/zone, network provider and administrative boundary evidence.
- Consensus public-key fingerprints, P2P identity fingerprints, signer identity and chain/Genesis binding; never publish private keys.
- Independent signer/HSM/KMS custody, separate administrative roles, recovery quorum and signer-side fencing evidence.
- Production P2P topology, peer allowlists, sentry strategy, firewall rules, RPC isolation, DDoS/rate-limit policy and partition recovery runbooks.
- Signed software/build provenance and independently controlled release approvals.
- Off-host encrypted backups with distinct administrative credentials and witnessed restore drills.
- Independent monitoring, alert routing, incident command and audit-log retention.
- A weighted-power concentration analysis, collusion scenarios and a policy for membership/power changes.
- A failure-domain map showing that loss of one host/operator/account/region/provider does not silently remove or compromise the required quorum.

Do not expose the current loopback-only ABCI endpoint as a shortcut to remote deployment. Preserve the local trust boundary unless an authenticated, encrypted and separately reviewed transport is implemented.

## 7. Proposed acceptance tests — not executed

The following are requirements, not claims that tests already exist or passed.

| ID | Test | Required result |
|---|---|---|
| VIND-T01 | Four validators deployed on four separately attested hosts | Host/kernel identities are distinct and independently evidenced |
| VIND-T02 | Separate cloud accounts/projects | No shared privileged account can administer all validators |
| VIND-T03 | Separate regions/zones | Documented region diversity; single-region loss does not violate the approved quorum target |
| VIND-T04 | Separate legal/operator entities | Signed operator acceptance and attributable control boundaries |
| VIND-T05 | One host hard power-off | Remaining validators retain the expected weighted quorum and recover safely |
| VIND-T06 | One operator account compromise simulation | Attacker cannot administer or sign for the other operators |
| VIND-T07 | One cloud account suspension | Remaining independently hosted validators behave according to the documented liveness policy |
| VIND-T08 | One network provider/ASN outage | Remaining peer topology maintains quorum or fails safely with clear alerting |
| VIND-T09 | Shared DNS outage/poisoning | Pinned peer/bootstrap recovery works without unsafe identity substitution |
| VIND-T10 | Shared CI credential compromise simulation | Production signing and deployment require separate approvals/credentials |
| VIND-T11 | One signer/HSM tenant outage | No duplicate signer; safe fail-closed behavior and documented recovery |
| VIND-T12 | Shared backup encryption key compromise | Blast radius and revocation/re-encryption process are demonstrated |
| VIND-T13 | Operator collusion calculation with uneven power | Coalition power is calculated from the approved roster, not validator count |
| VIND-T14 | Byzantine power at exactly/above one third | Monitoring marks the safety assumption violated; no misleading green status |
| VIND-T15 | Precommit quorum under uneven power | More-than-two-thirds threshold is calculated and tested correctly |
| VIND-T16 | 3/1 partition across real hosts and network links | Liveness/safety outcomes match weighted-power expectations |
| VIND-T17 | 2/2 partition across separate failure domains | Neither 50% side commits in the equal-weight case; recovery is deterministic |
| VIND-T18 | Correlated region outage | Observed loss matches the declared fault-domain model |
| VIND-T19 | Shared administrator/root compromise tabletop | Roles, credential revocation and signer fencing prevent cross-validator takeover |
| VIND-T20 | Validator host replacement | New host cannot sign until old host is fenced and signer state is verified |
| VIND-T21 | Old host reconnects after replacement | Stale host epoch is rejected at signer boundary |
| VIND-T22 | Independent restore drill | Backup restoration preserves chain/Genesis identity and anti-double-sign state |
| VIND-T23 | Release provenance substitution | Nodes reject unapproved binary/profile identity |
| VIND-T24 | Monitoring/control-plane outage | Independent alerting and operator escalation remain available |
| VIND-T25 | End-to-end independent operator exercise | All evidence is attributable, signed, timestamped and independently reviewed |

For each test record the exact commit/build, validator roster digest, voting-power weights, host/account/region identifiers (redacted as appropriate), failure injection, observed quorum, block height/hash, signer decision, alert timeline, recovery steps and independent witness. Do not place secrets or private-key material in CI artifacts.

## 8. Findings and disposition

| ID | Severity | Finding | Required closure |
|---|---|---|---|
| VIND-01 | Critical | Four validators are co-located in one local smoke-test root and one CI runner job. | Independently provisioned hosts and evidence of distinct failure domains |
| VIND-02 | Critical | Loopback P2P/RPC/ABCI topology does not model production network diversity. | Reviewed production P2P, firewall, sentry and operator-access architecture |
| VIND-03 | Critical | No independent operator/organization ownership evidence is present. | Signed operator roster and attributable control separation |
| VIND-04 | Critical | Disposable test keys do not prove independent production consensus-key custody. | Per-validator production key enrollment and independent signer custody review |
| VIND-05 | High | Noise authentication is tested locally but does not establish infrastructure independence. | Independent signer deployment, key custody and failure-domain attestations |
| VIND-06 | High | No evidence of separate cloud accounts, regions, providers or host administrators. | Deployment attestations and cross-domain failure tests |
| VIND-07 | High | No production P2P/DDoS/firewall/monitoring/incident response package found. | Operational readiness package and witnessed exercises |
| VIND-08 | High | Test equal voting power is not an approved anti-concentration policy. | Owner-approved weighted-power policy and adversarial analysis |
| VIND-09 | High | Shared CI/release authority may be a common software-supply-chain failure domain. | Independent release approvals, immutable provenance and credential separation |
| VIND-10 | High | No demonstrated one-host/operator/account/region failure exercise on independently deployed nodes. | VIND-T01–T25 evidence, with applicable tests independently witnessed |

**Disposition: NOT APPROVED** for production decentralization claims, independent validator claims, production signing or public-network launch. This is an evidence/readiness decision, not a claim that the local four-process integration test is invalid or that CometBFT consensus is defective.

## 9. Scope and next gate

This review inspected repository source, CI configuration and prior repository audits. It did not inspect external cloud accounts, real validator machines, operator identities, production networks, HSM/KMS tenants or secret material. Absence of those records in this repository is reported as “not established by repository evidence,” not proof that external infrastructure cannot exist.

No tests were run by this documentation review. The existing CI run is tracked separately and must not be treated as a run on this report's future commit unless GitHub reports the exact commit SHA.

The next gate is to obtain an owner-approved validator operating model and independently verifiable infrastructure evidence. Until then, keep all four-validator results classified as disposable local integration evidence. Do not modify source, tests or workflows for this gate without explicit owner approval.
