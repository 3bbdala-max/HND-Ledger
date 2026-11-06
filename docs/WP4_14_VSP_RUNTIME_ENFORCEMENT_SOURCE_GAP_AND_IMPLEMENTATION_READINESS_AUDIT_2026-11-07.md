# WP4.14 — VSP Runtime Enforcement Source Gap and Implementation Readiness Audit

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Review type:** Static inspection of current source and CI workflow; documentation only  
**Disposition:** NOT IMPLEMENTED — NOT APPROVED for production validator startup or public launch

## 1. Executive result

The VSP runtime enforcement blueprint is not present as an executable runtime gate in the inspected source. The current four-validator harness is a valuable multi-process integration test, but it runs all validator homes, HND ABCI processes and CometBFT processes inside one temporary directory on one CI runner. Its endpoints are loopback addresses. This does not demonstrate independent hosts, operators, cloud accounts, regions, signer custody domains or a production startup boundary.

The current HND ABCI server validates its HND manifest against a separately supplied manifest hash and checks the manifest network ID against a CLI-provided network ID. It does not load or verify a governance trust manifest, signed VSP, CometBFT Genesis roster digest, approved CometBFT profile digest or a durable VSP anti-rollback sequence before opening its gRPC listener.

**Conclusion:** continue with a narrowly scoped, test-first implementation design. Do not claim VSP runtime enforcement exists. No source, tests, workflows, Genesis, deployment files, keys or runtime settings were changed in this audit.

## 2. Evidence inspected

| Artifact | Direct observation | Security interpretation |
|---|---|---|
| `scripts/cometbft_v040_four_validator_network_smoke.py` | Uses one `TemporaryDirectory`, creates four homes beneath it, and launches four HND processes and four CometBFT processes using `subprocess.Popen` | Multi-process isolation on one host, not host/operator independence |
| Same harness | P2P, RPC and ABCI endpoints are generated as `127.0.0.1` addresses; peer links use in-process `DirectedTCPRelay` instances | Exercises peer topology and partition behavior locally, not production network segmentation |
| Same harness | Four temporary validator identities are generated for the run; fixture voting power is `POWER=10` for each | Test-only equal-power roster; not an approved production set |
| Same harness | Optional remote signer receives validator 4's key and state files; the other validators retain their own local FilePV arrangements | Demonstrates one remote-signer integration path, not four independently administered signer domains |
| `scripts/cometbft_v040_four_validator_genesis_preflight.py` | Explicitly reports `genesis-and-identity-preflight-only; no nodes started` | Preflight is not a running network or startup gate |
| `hnd_v02/cometbft_v040_server.py` | CLI accepts manifest, expected HND manifest hash, network ID, protocol version, max amount, state path, recovery flag and listen address | No VSP/trust-root/profile verification is wired into this server entry point |
| Same server | Validates HND manifest hash and network ID, then constructs application and starts gRPC server | HND manifest validation is narrower than signed validator-set and CometBFT profile authorization |
| `.github/workflows/hnd-v02-tests.yml` | Both jobs use `ubuntu-latest`; second job builds CometBFT and runs local four-validator/signer smoke scenarios | CI validates configured integration behavior on hosted runners; it is not a four-operator deployment |
| `docs/WP4_14_VSP_RUNTIME_ENFORCEMENT_IMPLEMENTATION_BLUEPRINT_AND_ACCEPTANCE_PLAN_2026-11-07.md` | Defines pre-start gate, OS/service bypass prevention, Genesis/profile binding and anti-rollback as future work | Architecture proposal, not implemented behavior |

## 3. Important boundary distinctions

### 3.1 What current CI can establish

Subject to a completed successful run on the exact commit, the configured workflow can provide evidence that:
- the HND v0.2 unit/integration test set passed;
- the selected CometBFT v0.40.0 build and smoke steps passed;
- the four-node local harness converged and exercised its scripted outage/recovery and signer scenarios;
- the test fixture used unique temporary validator identities and a shared Genesis.

### 3.2 What current CI cannot establish

The same run cannot prove:
- four separately administered production hosts or organizations;
- separate cloud accounts, IAM administrators, regions, network providers or physical fault domains;
- independent governance-key custody or independent signer administration;
- resistance to compromise of a shared CI runner, repository maintainer account or deployment control plane;
- production P2P firewalling, peer allowlists, sentry design, DDoS controls, monitoring or on-call response;
- VSP signature verification or fail-closed startup enforcement;
- external monotonic anti-rollback protection;
- resilience to a cloud-account, region, DNS, shared network or shared backup failure.

Noise authentication and multiple processes do not alter these conclusions.

## 4. Runtime bypass and trust-boundary findings

### Finding VSP-GAP-01 — Critical: no VSP trust verification at current HND server startup

The inspected server entry point has no trust-manifest or signed-VSP input and no 2-of-3 governance signature verification. A caller-supplied HND manifest hash is not a substitute for an independently pinned governance trust root.

### Finding VSP-GAP-02 — Critical: no complete CometBFT roster/profile binding

The HND application startup path does not verify the complete CometBFT Genesis validator roster, exact CometBFT Genesis file digest, consensus profile digest or exact binary artifact digest. HND account allocations and the CometBFT validator roster remain separate identities.

### Finding VSP-GAP-03 — Critical: no unavoidable process/service gate

The inspected repository does not provide an enforced supervisor/service boundary that prevents a routine operator from launching CometBFT directly. A wrapper is not an enforcement boundary if the same service account can invoke the binary independently.

### Finding VSP-GAP-04 — Critical: no durable VSP anti-rollback anchor

No runtime VSP sequence/digest store protected by an external monotonic trust mechanism was identified in the inspected entry point. The existing HND state integrity checksum is not, by itself, an authenticated rollback-resistant trust anchor.

### Finding VSP-GAP-05 — High: local smoke topology can be overinterpreted

Four validator processes on one runner and loopback addresses are suitable for deterministic integration testing. They must not be represented as proof of four independent validators in an operational decentralization claim.

### Finding VSP-GAP-06 — High: test signer topology is not production custody topology

The optional signer path in the four-validator harness moves validator 4's FilePV key/state into a temporary signer directory. It does not establish independently administered signer hardware, separate hosts, production HSM/KMS, independent recovery custodians or production signer fencing.

## 5. Required implementation order — decision

Choose the smallest auditable sequence, not a large all-at-once patch:

1. **Freeze a test-only VSP schema and golden vectors** without production trust claims. Define exact canonical bytes, key algorithms, chain/Genesis binding, validator roster and voting-power semantics.
2. **Implement a pure verifier module** with no network listeners, no secret-key access and no side effects. It verifies trust manifest, 2-of-3 distinct signatures, VSP canonicalization, network identity, Genesis/roster equality and local validator identity.
3. **Add exhaustive negative tests first** for duplicate JSON members, altered signatures, wrong chain, wrong Genesis, substituted validator key, wrong power, stale sequence, duplicate signer and unknown key.
4. **Add a fail-closed preflight command** that emits a redacted decision record and stable error code. It must not start HND or CometBFT.
5. **Bind the approved profile and exact software identity** only after the exact CometBFT source commit, build inputs, binary digest and version-specific config classification have been reviewed.
6. **Design and test durable anti-rollback separately.** Do not use an ordinary writable JSON file or unkeyed checksum as the production monotonic anchor.
7. **Only then design the process supervisor and OS/service restrictions** that make the gate unavoidable. Demonstrate direct-binary bypass denial by the actual service identity.
8. **Integrate signer-side independent checks** so a valid launcher result cannot be replayed as a general signing capability.
9. **Deploy to four genuinely separate disposable hosts** under distinct administrative domains before making infrastructure independence claims.
10. Obtain independent security review and explicit protocol-owner approval before production use.

No source change is authorized by this audit. A future source patch should be limited to the first approved work package and should include its negative tests in the same reviewed change.

## 6. Acceptance matrix — proposed, not executed

| ID | Test | Required result |
|---|---|---|
| VSP-GAP-T01 | VSP verifier receives no trust manifest | Reject |
| VSP-GAP-T02 | VSP has only one valid governance signature | Reject |
| VSP-GAP-T03 | Two signatures map to one governance key | Reject |
| VSP-GAP-T04 | Signed bytes differ from canonical bytes | Reject |
| VSP-GAP-T05 | Duplicate JSON keys at nested level | Reject |
| VSP-GAP-T06 | Wrong chain ID | Reject |
| VSP-GAP-T07 | Wrong HND Genesis digest | Reject |
| VSP-GAP-T08 | Wrong full CometBFT Genesis digest | Reject |
| VSP-GAP-T09 | Same validator count but one public key substituted | Reject |
| VSP-GAP-T10 | Voting power differs from signed VSP | Reject |
| VSP-GAP-T11 | Local consensus key does not map to exactly one active VSP entry | Reject |
| VSP-GAP-T12 | Old VSP sequence or predecessor digest | Reject |
| VSP-GAP-T13 | Anti-rollback state missing or corrupted | Fail closed |
| VSP-GAP-T14 | Direct CometBFT launch by routine service identity | Denied |
| VSP-GAP-T15 | VSP check fails | Neither HND nor CometBFT process starts |
| VSP-GAP-T16 | Authenticated config changes after preflight | Abort or re-verify before process start |
| VSP-GAP-T17 | Signer receives wrong chain/Genesis/validator identity | Reject signing request |
| VSP-GAP-T18 | VSP update attempts to reset H/R/S | Reject |
| VSP-GAP-T19 | Restore an older disk snapshot | Detect rollback and halt |
| VSP-GAP-T20 | One host fails in four-host deployment | Remaining behavior matches approved fault model |
| VSP-GAP-T21 | Shared cloud/IAM account compromise | Blast radius matches documented threat model; no unsupported independence claim |
| VSP-GAP-T22 | CI runner compromise | No production keys or production trust-root material exposed |
| VSP-GAP-T23 | Four operators acknowledge different VSP digests | Activation halted |
| VSP-GAP-T24 | Four independent hosts report startup evidence | All report identical authorized digest and distinct host/operator attestations |
| VSP-GAP-T25 | Independent reviewer attempts launcher bypass | Bypass denied under documented threat model |

All tests above are requirements, not test results.

## 7. Readiness decision

**Current status: NOT APPROVED** for VSP runtime enforcement, production validator onboarding, production signing, token issuance or public launch.

The four-validator local integration is useful and should be retained. Its evidence must remain scoped to a local disposable test topology. The next implementation candidate is the pure, side-effect-free VSP verifier plus negative tests. The supervisor, OS boundary and durable anti-rollback controls must follow as separate, reviewable work packages.

**Change boundary:** this audit adds documentation only. It does not alter application source, tests, workflows, dependencies, Genesis, validator keys, deployment settings or runtime behavior.

---
This report is a source-gap audit, not a security certification or launch authorization.
