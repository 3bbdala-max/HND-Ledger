# WP4.32 — Supervisor Descriptor Pinning and Remaining Launch Gate

**Date:** 2026-11-11  
**Base branch:** `phase-0.2-planning`  
**Base commit:** `5fac5a247299298913d431ae027070b87d4ba862`  
**Scope:** Post-merge source/status audit of the CometBFT executable descriptor-pinning change  
**Disposition:** The pathname TOCTOU fix is merged and CI-tested. The mandatory pre-start authorization and sole-launch-path gates remain open.

## 1. Change accepted

PR #40, “Pin CometBFT execution to the verified file descriptor”, was merged into `phase-0.2-planning`.

- PR: https://github.com/3bbdala-max/HND-Ledger/pull/40
- Tested PR head: `4055e490795651d8474b22d3b69674186709c706`
- Exact-head CI run: https://github.com/3bbdala-max/HND-Ledger/actions/runs/42979861938
- Merge commit: `5fac5a247299298913d431ae027070b87d4ba862`

The exact PR head passed both configured jobs:
- `hnd-v02-tests`: 34/34 steps, success.
- `cometbft-single-node-smoke`: 37/37 steps, success.

The CI evidence belongs to the exact PR head above. It is not represented as a separate workflow run on the squash-merge commit.

## 2. Security property now implemented

`hnd_v02/cometbft_supervisor.py` now:
1. Opens the configured executable using `O_NOFOLLOW`.
2. Checks that the opened descriptor identifies a regular executable file.
3. Hashes bytes read from that same descriptor and compares the expected SHA-256.
4. Re-hashes the same descriptor immediately before process creation.
5. Starts the child using `/proc/self/fd/<fd>`, explicitly inherits the descriptor with `pass_fds`, and uses `shell=False`.
6. Closes the parent's descriptor after process creation.

This closes the pathname replacement race between digest verification and execution for the adapter on Linux systems with `/proc/self/fd`.

It does not protect the executable inode from a privileged writer able to modify the same inode, nor does it replace OS ownership, immutable deployment, or service-account controls. Those remain deployment requirements.

## 3. Integration boundary remains open

The merged supervisor is a launch adapter, not proof that every CometBFT launch is forced through it.

The inspected `hnd_v02/startup_authorization.py` explicitly states that it is an integration seam and that deployments must remove alternate direct launch paths. The inspected ABCI server entrypoint still starts its gRPC service independently; its InitChain consistency checks occur after CometBFT has connected and submitted InitChain, not before consensus startup.

The repository's single-node and four-validator smoke scripts use direct `subprocess.Popen` calls to create disposable test processes. Those are test harnesses and should not be mechanically rewritten as if they were production service launchers. The Go remote-only CLI also describes itself as an external-signer integration-test tool pending runtime review.

Accordingly, this audit does not claim a single enforced production launch path, VSP pre-start enforcement, or production deployment.

## 4. Remaining mandatory launch gate

The next implementation must be a separately reviewed orchestration boundary that, before opening ABCI, CometBFT, RPC/P2P, or signer endpoints:

1. Consumes one immutable activation/configuration input bundle.
2. Verifies the exact HND application Genesis and a frozen, independently authenticated Config-v1 identity.
3. Verifies VSP signatures, the trust-manifest chain, and an independently provisioned trust-root pin.
4. Verifies the complete CometBFT v0.40.0 profile and exact approved binary/build identity.
5. Checks trust/VSP predecessor and successor sequences against an independent anti-rollback service.
6. Verifies the unanimous operator acknowledgement set and activation-height policy.
7. Holds verified immutable bytes/descriptors through process creation so a replaceable pathname cannot change the launched artifact.
8. Ensures alternate direct startup paths are denied by the deployment/service policy, not merely discouraged by documentation.

Any missing, malformed, stale, mismatched, unauthenticated, or unavailable required input must prevent all child processes and listeners from starting.

## 5. Dependencies that prevent claiming completion

The current source and decision records still identify these blockers:

- The CometBFT profile parser is an initial strict mechanism; the full generated recursive schema/default inventory and independent golden-vector verification are not yet frozen.
- Config-v1 and related protocol decisions remain pending owner approval; a candidate schema or successful CI run is not normative approval.
- The offline activation bundle does not itself persist an independently pinned trust root or enforce the actual CometBFT/ABCI/signer launch.
- SQLite intent/anchor services remain single-host reference implementations, not independently administered linearizable anti-rollback services.
- The ABCI gRPC endpoint is loopback-only but uses insecure local transport; loopback does not authenticate the local caller.
- Witnessed stuck-intent/key-loss recovery, production key custody, deployment/service hardening, and independent security review remain outstanding.

The earlier WP4.31 correction remains applicable: local Genesis and durable-store equality checks for `max_amount` and `max_block_transactions` are implemented, but they are not a pre-start authorization gate or an independently authenticated Config-v1 identity.

## 6. Acceptance decision

| Control | Status |
|---|---|
| Executable pathname TOCTOU mitigation in supervisor adapter | **Implemented; exact PR-head CI passed** |
| Same-descriptor digest recheck before launch | **Implemented; exact PR-head CI passed** |
| Sole enforced CometBFT/ABCI/signer startup path | **Open** |
| Complete frozen CometBFT profile identity | **Open** |
| Mandatory VSP/trust-root pre-start verification | **Open** |
| Independent multi-replica anti-rollback services | **Open** |
| Production deployment and independent security approval | **Open** |

**Disposition:** Accept PR #40 as a bounded security improvement. Keep Station 2 open. Do not describe the project as production-ready, public-network-ready, or approved for real funds or production signing.
