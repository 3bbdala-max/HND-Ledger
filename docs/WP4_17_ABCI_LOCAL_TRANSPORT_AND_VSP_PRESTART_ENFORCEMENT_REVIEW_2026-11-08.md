# WP4.17 — ABCI Local Transport Boundary and Mandatory VSP Pre-Start Gate Review

**Inspection date:** 2026-11-08  
**Branch:** `phase-0.2-planning`  
**Inspected HEAD:** `38770e81a41e533915a2d42a9db741b074f60e59`  
**Review type:** Static entrypoint, transport, and CI-coverage review  
**Change type:** Documentation only  
**Disposition:** Loopback restriction is a useful exposure control; local-client authorization and mandatory VSP pre-start enforcement remain open.

## 1. Exact-commit CI evidence at inspection

Run `42420807378` targets the exact inspected HEAD `38770e81a41e533915a2d42a9db741b074f60e59`.

At inspection:

- `hnd-v02-tests`: completed successfully, including JCS spike and v0.2 tests.
- `cometbft-single-node-smoke`: in progress. The CometBFT v0.40.0 binary build step was running; later signer, ABCI, and four-validator steps were pending.

The workflow is therefore **not a completed overall success** at this inspection point. This status is recorded separately from the source-review findings below.

Run link: https://github.com/3bbdala-max/HND-Ledger/actions/runs/42420807378

## 2. ABCI gRPC server findings

Inspected source: `hnd_v02/cometbft_v040_server.py`.

### 2.1 Controls already present

The adapter has meaningful network-exposure safeguards:

- Default bind is `127.0.0.1:26658`.
- `_validate_loopback_bind_address` accepts loopback IP literals only and rejects wildcard, non-loopback, and hostname binds.
- The gRPC server is started only after this bind-address validation.
- The CLI verifies the supplied manifest digest against the separately supplied `--genesis-hash`.
- The manifest network ID must match the supplied `--network-id`.
- The HND application checks the corresponding chain/network and Genesis conditions during initialization.

The loopback policy materially reduces remote-network exposure. It should be preserved.

### 2.2 Local authorization boundary remains open

The server is created with `grpc.server(...)` and bound with `add_insecure_port(...)`. No TLS credentials, mTLS client identity, authentication interceptor, or method-level authorization policy is visible in this adapter.

The test suite deliberately creates `grpc.insecure_channel` clients and verifies Echo/Info connectivity. It tests rejection of non-loopback bind addresses, but does not establish that an unauthorized local process is denied access.

This matters because the same ABCI service exposes state-transition methods including `InitChain`, `FinalizeBlock`, and `Commit`. Loopback binding constrains the network interface; it does not distinguish the legitimate CometBFT process from another process that can connect locally.

**Risk statement:** the present boundary appears to rely on host-level isolation and the assumption that only the intended CometBFT process can reach the local endpoint. That may be acceptable for a deliberately isolated development host, but it is not yet a documented production-grade local process authorization control.

Before production, choose and test a concrete boundary appropriate to the deployment model, such as a protected Unix-domain socket with strict ownership/permissions plus process isolation, or authenticated local transport. Do not add public network exposure as a workaround. Any chosen design requires hostile-local-client tests and operational ownership rules.

## 3. Mandatory VSP pre-start gate is not yet demonstrated

Inspected entrypoints:

- `hnd_v02/cometbft_v040_server.py`
- `scripts/cometbft_v040_remote_only_main.go`
- `scripts/cometbft_v040_single_node_smoke.py`
- `tests/test_v02_cometbft_v040_adapter.py`
- `.github/workflows/hnd-v02-tests.yml`

The Python ABCI server CLI currently accepts a local HND Genesis manifest, an independently supplied manifest hash, network ID, protocol version, max amount, state path, recovery flag, and listen address. It validates those HND inputs and starts the ABCI gRPC service. The inspected startup path does not accept or verify a VSP envelope, independently pinned trust manifest, CometBFT profile digest, approved binary digest, VSP sequence, or governance signatures.

The remote-only CometBFT wrapper is explicitly described in its source as intended for HND external-signer integration tests until runtime review is complete. It validates the configured remote signer endpoint and prevents fallback to a local consensus FilePV. Its inspected startup path does not call a VSP verifier or validate a governance trust root/profile.

The single-node smoke script creates disposable keys and Genesis data under a temporary directory, starts the ABCI server, probes its gRPC endpoint, and then starts the CometBFT node. That is a useful integration test, but it is not a VSP authorization test.

The current workflow runs the above integration probes; it does not contain a test that proves both ABCI and CometBFT fail closed before startup when VSP is missing, malformed, wrongly signed, stale, linked to the wrong chain/Genesis, or bound to a substituted CometBFT profile.

**Conclusion:** the inspected entrypoints do not demonstrate the previously required unavoidable VSP pre-start gate before both HND ABCI and CometBFT launch. This is an implementation/enforcement gap, not a claim that an existing VSP verifier was tested and failed. The VSP candidate contract conflict recorded in WP4.16 must be resolved before implementing this gate.

## 4. Required acceptance tests

After the VSP schema and signature contract is formally ratified, add tests for these cases in a separately reviewed implementation change:

| Test | Expected result |
|---|---|
| VSP missing | Both ABCI and CometBFT startup denied |
| Trust manifest missing/unpinned | Startup denied |
| Invalid governance threshold/signature | Startup denied |
| Duplicate signature key ID | Startup denied |
| Wrong chain ID or HND Genesis digest | Startup denied |
| Wrong CometBFT Genesis/profile digest | Startup denied |
| Wrong binary/source identity | Startup denied |
| Stale sequence or predecessor mismatch | Startup denied |
| Activation height not yet valid / expired profile | Startup denied under ratified policy |
| VSP changed between preflight and service launch | Startup denied or launch bound to the already verified immutable bytes/digest |
| ABCI local client without authorized identity | Mutating ABCI methods denied |
| Unauthorized peer or wrong socket owner | Connection or method call denied |
| Required auth material missing | Fail closed; no insecure fallback |

The verifier must validate immutable byte inputs and independently supplied expected identities. Startup should bind the actual running binary/configuration to the exact profile that was verified; a one-time check against a replaceable file path creates a time-of-check/time-of-use exposure.

## 5. Safe design sequence

1. Resolve and ratify one VSP schema/signature contract; do not implement against the conflicting proposals.
2. Define the immutable input bundle and the exact CometBFT fields/profile digest that must be pinned.
3. Design a pure verifier with no network, process, private-key, or persistence side effects.
4. Design a single fail-closed launch supervisor that verifies the profile before starting either ABCI or CometBFT, and prevents bypass through alternate CLI commands or service units.
5. Bind the verified profile digest to the actual process configuration and binary identity.
6. Select the local ABCI transport authorization boundary and document OS account, socket ownership, permissions, and isolation assumptions.
7. Add negative startup tests and hostile-local-client tests using disposable synthetic fixtures.
8. Require exact-commit CI plus independent security review before production enablement.

No real governance keys, validator keys, trust manifest, Genesis, or production profile should be generated for these tests.

## 6. Change boundary and decision

This report is documentation only. It does not change source code, tests, workflows, dependencies, Genesis, keys, validator configuration, transport binding, or runtime behavior. It does not trigger a manual CI rerun.

**Decision:** keep the ABCI endpoint loopback-only. Do not treat loopback as client authentication. Keep the remote-only CLI and single-node smoke evidence classified as integration-test evidence, not production pre-start authorization. VSP pre-start enforcement and local ABCI client authorization remain open security gates.
