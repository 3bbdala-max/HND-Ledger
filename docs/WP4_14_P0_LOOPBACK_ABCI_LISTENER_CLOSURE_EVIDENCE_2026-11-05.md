# WP4.14 — P0 Loopback-Only ABCI Listener Closure Evidence

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Reviewed head:** `85d4f73f7ca791fd2e9730e21646ed5ab90f812e`  
**Status:** P0 code guard and CI regression evidence verified; remote transport remains unsupported.

## 1. Decision

The P0 containment item from the pre-Config-v1 security remediation plan is implemented in the reviewed branch and has passing CI evidence. The insecure ABCI gRPC listener now rejects non-loopback bind addresses before creating or binding the gRPC server.

This closes the specific application-level risk of accidentally exposing this insecure listener through the `--listen` override. It does **not** make the transport encrypted or authenticated and does not authorize remote deployment.

## 2. Source evidence

The implementation is in `hnd_v02/cometbft_v040_server.py`:

- Adds Python's `ipaddress` parser.
- `_validate_loopback_bind_address` accepts IPv4/IPv6 loopback IP literals only.
- Requires explicit address syntax; DNS names/hostnames are rejected.
- Rejects wildcard, LAN, and public addresses.
- Validates port syntax and range 0–65535; port 0 is retained for ephemeral local test servers.
- `start_grpc_server` invokes the validator before constructing the gRPC server and before `add_insecure_port`.
- The transport remains `add_insecure_port`; no TLS or client authentication is introduced.

Implementation commit: `1f655d0568df9a4717babe2f77ef5aa00b94b972`  
Source blob SHA: `f29b07f1e24bbcc6806efb068ed09e3dcac970e6`

## 3. Regression test evidence

The following tests were added in `tests/test_v02_cometbft_v040_adapter.py` by commit `85d4f73f7ca791fd2e9730e21646ed5ab90f812e`:

- `test_loopback_bind_policy_accepts_ipv4_and_ipv6_literals`
- `test_loopback_bind_policy_rejects_non_loopback_and_hostnames`
- `test_start_grpc_server_rejects_non_loopback_before_binding`

Positive cases include `127.0.0.1`, `[::1]`, and ephemeral port 0. Negative cases include `0.0.0.0`, `::`, LAN/public IPs, hostnames, malformed syntax, and out-of-range ports.

Test file blob SHA at reviewed head: `9d1bfdb98acf77db063202130d260df679ca2ae5`.

## 4. CI evidence

GitHub Actions run: `41963456729`  
Run URL: https://github.com/3bbdala-max/HND-Ledger/actions/runs/41963456729  
Head SHA: `85d4f73f7ca791fd2e9730e21646ed5ab90f812e`  
Conclusion: **success**

Both jobs completed successfully:

1. `hnd-v02-tests` — includes the isolated v0.2 test suite; the step “Run isolated v0.2 tests” succeeded.
2. `cometbft-single-node-smoke` — succeeded, including the single-node ABCI integration smoke test and the configured four-validator / remote-signer integration checks in that workflow.

This is CI evidence for this exact commit. It is not a claim of a separate local test run in this review.

## 5. Scope and residual limitations

Closed:
- The application refuses non-loopback bind addresses for the insecure ABCI gRPC server.
- Regression coverage exists for accepted and rejected address classes.
- The full configured workflow passed at the reviewed head.

Not closed:
- No TLS, mutual TLS, client certificate lifecycle, authorization, or remote transport security is implemented here.
- Loopback binding is a process-level boundary; deployment still needs host firewall, process isolation, and state-directory permissions.
- This does not address other services, CometBFT P2P, remote signer listeners, or host compromise.
- It does not prove the full system is production-ready.

## 6. Gate update

**P0 — loopback-only listener containment: CLOSED for this code path, subject to the scope above.**

**Remote ABCI transport: BLOCKED** until a separate reviewed transport design specifies TLS/mutual authentication, peer identity, authorization, certificate/key custody, rotation/revocation, and negative handshake tests.

No workflow files were modified. No Config-v1 schema or consensus rules were changed by this P0 closure.
