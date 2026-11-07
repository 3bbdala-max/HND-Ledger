# WP4.14 — Shared FilePV multi-process dual-sign reproduction (2026-11-07)

## Result

A disposable negative-security probe reproduced conflicting signatures from two independent CometBFT v0.40.0 remote-signer processes configured with the same validator key and FilePV state path.

- Branch: `phase-0.2-planning`
- Tested commit: `f769dcb2890085497bbd275e325e974eff793b6e`
- GitHub Actions run: `42323914517`
- Run conclusion: `success`
- Completed: `2026-11-07T01:29:06Z`

The workflow step `Reproduce shared FilePV multi-process dual-sign risk (expected unsafe behavior)` completed successfully. This step is intentionally a negative security probe: success means the unsafe behavior was reproduced, not that the signer design passed a safety check.

## Probe method

1. Create one disposable FilePV key and initial state file.
2. Start two independent operating-system signer processes with the same key and state paths.
3. Require both processes to establish their signer connections before sending either signing request. Each process has therefore loaded the same initial in-memory state.
4. Ask process 0 to sign a vote, then ask process 1 to sign a conflicting vote using its stale in-memory state.
5. Both requests return signatures; the probe verifies both signatures against the same validator public key and confirms the votes conflict at identical height, round, and vote type.

The requests are deliberately sequential after both processes load state. This isolates stale cross-process state from incidental simultaneous filesystem-write races.

## Security conclusion

The tested FilePV state path and per-process signer mutex do not establish exclusive cross-process ownership. Two independent signer processes sharing that path can emit valid conflicting signatures. A local in-process mutex cannot prevent this.

This is an observed, reproducible test-fixture result for two processes on one host. It is not a reproduced multi-host or network-partition failure, and it does not establish that a production deployment has already double-signed.

## CI scope

The same workflow run completed successfully for both jobs:

- `hnd-v02-tests`
- `cometbft-single-node-smoke`

The integration job also passed its existing process-isolated signer, anti-double-sign restart, missing/substituted state rejection, four-validator network, external signer outage/recovery, and authenticated Noise signer checks. Those passing checks do not negate the dual-writer finding: they test different properties.

## Required closure gate

Do not use multiple signer processes against one FilePV state directory as a production ownership design. Before production signing, select and prove one authoritative signing/ownership architecture with durable single-writer enforcement and fencing at the signing boundary. It must reject a stale writer after failover and cover crash/restart and backup-restore boundaries. A local mutex, PID file, atomic rename, or peer allowlist alone is insufficient evidence of distributed fencing.

No production signer, key, validator, network deployment, token issuance, protocol freeze, or release approval is authorized by this result.

## Validator topology limitation

The existing four-validator external-signer smoke script configures the external signer only for validator 4 (`i == 3`). Validators 1–3 retain their local FilePV key/state paths in this test fixture. The authenticated Noise variant has the same validator-4-only topology. Therefore these integration tests do **not** prove mandatory external signing for every validator, nor do they establish that a production launch can prevent local FilePV bypasses.

Before production approval, the topology must be redesigned and tested so every validator's consensus signing path is routed through the approved signer boundary, with startup rejection if a local key or bypass path is present. This must be verified for all four validators in the test profile and separately reviewed for production deployment.


## Addendum — same-host advisory lock mitigation added (2026-11-07)

The disposable HND Unix and Noise signer helpers have since been changed to
acquire a non-blocking OS advisory lock derived from the anti-double-sign
state path before loading FilePV state or starting a signer server. The
shared-state probe is being converted from reproducing two valid conflicting
signatures to verifying this behavior:

- owner process A acquires the lock and signs;
- process B using the same state path is rejected while A remains active;
- after A exits, B can acquire the lock only with the updated persisted-state
  digest and must reject a conflicting H/R/type request.

This is a same-host, same-local-filesystem mitigation for cooperating HND
helper processes only. It does not change the historical upstream finding:
CometBFT FilePV and its per-process mutex do not provide cross-process
ownership. It is not a distributed lease, durable host fencing, or protection
against processes that bypass the helper. The corresponding Unix and Noise
lock CI probes are pending; no safety result is claimed until they pass.
