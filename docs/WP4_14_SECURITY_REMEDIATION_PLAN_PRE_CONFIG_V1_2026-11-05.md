# WP4.14 — Security Remediation Plan Before Config-v1

**Date:** 2026-11-05  
**Status:** Remediation design — no code changes authorized by this document  
**Branch:** `phase-0.2-planning`  
**Baseline commit:** `fc1f7edb14840d061798843d7358dcbc1f9d63ef`

## 1. Executive decision

The current HND v0.2 implementation has useful deterministic state and validation controls, but several operational and input-boundary risks must be addressed before any non-local deployment or Config-v1 implementation.

The highest-priority issue is the ABCI gRPC listener: it uses an insecure transport and accepts a caller-provided bind address. The default is loopback, but the CLI can override it. This must be treated as a deployment blocker until non-loopback binding is either prohibited in code or protected by a separately reviewed authenticated transport.

This plan is a design and sequencing artifact only. It does not authorize source edits, public exposure, production keys, or opening G2–G4.

## 2. Severity and work classification

| Priority | Finding | Risk class | Required disposition |
|---|---|---|---|
| P0 | Insecure gRPC transport with configurable bind address | Remote unauthenticated access if exposed | Enforce loopback-only until secure transport is designed and reviewed |
| P1 | CLI Genesis manifest parsed without explicit duplicate-key rejection | Ambiguous input acceptance / parser differential | Use strict duplicate-aware parsing before object construction |
| P1 | No explicit transaction byte-size limit in the inspected ABCI validation path | Resource exhaustion / inconsistent local limits | Define bounded input policy and bind consensus-critical limits |
| P1 | No complete Config-v1 identity or CometBFT profile preflight | Cross-node configuration divergence | Design and implement only after schema/profile freeze |
| P1 | CLI consensus parameters supplied independently | Node configuration mismatch | Derive from pinned config; reject conflicting overrides |
| P2 | ABCI query error includes requested account ID and raw request bytes as hex | Excessive diagnostic disclosure/log amplification | Return stable generic error category; keep bounded diagnostics |
| P2 | Store checksum is unkeyed SHA-256 | Integrity detection is not authenticity | Document threat boundary; do not treat checksum as an authentication control |
| P2 | Stable cross-module machine-readable error contract absent | Operational ambiguity / inconsistent diagnostics | Define and test stable error codes |
| P2 | Durable store has no Config-v1 or CometBFT profile digest | Unsafe identity transition risk | Design explicit new store version and offline migration |
| P3 | Independent Config-v1 vector approval not complete | Common-mode implementation/test error | Require independent byte/preimage review before implementation gate |

Priority describes sequencing, not a claim that exploitation has occurred. The P0 exposure becomes a remote-access concern if the service is bound to a reachable interface; the default loopback setting reduces exposure but does not enforce the boundary.

## 3. P0 — Contain the ABCI gRPC listener

### 3.1 Current source behavior

The inspected `hnd_v02/cometbft_v040_server.py`:

- defaults `bind_address` to `127.0.0.1:26658`;
- calls `server.add_insecure_port(bind_address)`;
- exposes `--listen` as a CLI override;
- does not configure TLS or client authentication in this server path.

The module docstring warns against exposing the unauthenticated endpoint, but a warning is not an enforcement control.

### 3.2 Recommended containment

Until an authenticated transport design is approved:

1. Reject any bind address that is not a loopback IP literal.
2. Reject wildcard addresses such as `0.0.0.0`, `::`, and hostnames that cannot be proven loopback without DNS ambiguity.
3. Keep the default explicit loopback address.
4. Add tests proving loopback IPv4 and, if supported, loopback IPv6 behavior.
5. Add rejection tests for wildcard, LAN, public, hostname, and malformed addresses.
6. Ensure startup fails before the server begins listening when the address is not permitted.
7. Do not claim TLS protection; this containment is local-only, not a replacement for secure remote transport.

### 3.3 Acceptance tests

| ID | Scenario | Expected result |
|---|---|---|
| SEC-LISTEN-01 | Default loopback IPv4 | Server may bind locally |
| SEC-LISTEN-02 | Explicit 127.0.0.1 | Server may bind locally |
| SEC-LISTEN-03 | IPv6 loopback | Accept only if explicitly supported and tested |
| SEC-LISTEN-04 | 0.0.0.0 / wildcard IPv4 | Reject before bind |
| SEC-LISTEN-05 | :: / wildcard IPv6 | Reject before bind |
| SEC-LISTEN-06 | LAN or public IP | Reject before bind |
| SEC-LISTEN-07 | Hostname / DNS name | Reject unless a separately approved resolution policy exists |
| SEC-LISTEN-08 | Invalid address syntax | Reject deterministically |
| SEC-LISTEN-09 | Bind failure | Startup exits without claiming service readiness |
| SEC-LISTEN-10 | Regression: local CometBFT client | Existing local connection behavior remains compatible |

**Gate:** No non-loopback listener until a separate transport specification covers TLS, client identity, certificate/key lifecycle, rotation, revocation, authorization, and negative handshake tests.

## 4. P1 — Strict Genesis input parsing

### 4.1 Current behavior and precise distinction

The ABCI helper `_decode_canonical_object` parses JSON and then compares canonical re-encoding with the original bytes. This rejects noncanonical duplicate-key byte representations, but the parser does not currently pass `object_pairs_hook=_reject_duplicate_json_keys`; duplicate members are therefore materialized before the canonical-byte comparison rejects the input.

The CLI manifest path uses ordinary `json.load` and does not explicitly install the duplicate-key rejection hook. This is the more direct gap: the manifest is converted to a Python object before its hash and subsequent checks are performed.

### 4.2 Recommended remediation

1. Create one strict JSON byte/file parser for all consensus-critical Genesis inputs.
2. Reject duplicate keys at every object depth using pair-level parsing before dictionary construction.
3. Reject invalid UTF-8 and non-finite constants.
4. Define BOM behavior explicitly; recommended: reject BOM.
5. Require canonical-byte equality for consensus-critical byte payloads.
6. Validate exact schema and field types before hashing.
7. Keep parser diagnostics separate from stable protocol error categories.

### 4.3 Acceptance tests

| ID | Scenario | Expected result |
|---|---|---|
| SEC-JSON-01 | Duplicate top-level manifest key | Reject before object creation |
| SEC-JSON-02 | Duplicate nested allocation key | Reject before object creation |
| SEC-JSON-03 | Invalid UTF-8 | Reject |
| SEC-JSON-04 | NaN / Infinity | Reject |
| SEC-JSON-05 | BOM | Reject under recommended profile |
| SEC-JSON-06 | Noncanonical whitespace/key order | Reject at strict byte boundary |
| SEC-JSON-07 | Valid canonical manifest | Accept and reproduce expected digest |
| SEC-JSON-08 | Same malformed file through CLI and ABCI parser | Same rejection category |

## 5. P1 — Bound untrusted payload processing

### 5.1 Current source observations

The inspected ABCI application:

- requires non-empty transaction byte strings;
- caps a block at `MAX_BLOCK_TRANSACTIONS = 1000`;
- decodes transaction JSON canonically;
- receives the proposal byte budget from the CometBFT request;
- does not show a dedicated maximum transaction byte length in the inspected validation path.

The proposal byte budget does not by itself prove that every inbound transaction, CheckTx request, Genesis manifest, or parser allocation is bounded before decoding.

### 5.2 Recommended remediation

Define separate, explicit bounds for:

- individual transaction bytes;
- aggregate proposal bytes;
- Genesis envelope bytes;
- manifest bytes;
- allocation count;
- JSON nesting depth;
- JSON object member count;
- string length;
- evidence item count and encoded size.

Classify each limit:
- **Consensus-critical:** changes transaction/block acceptance and must be pinned in the network identity/profile.
- **Local defensive:** protects a process but must not cause validators to disagree about consensus validity. If a local limit can reject a consensus-valid block, it is not merely local.

Do not invent numeric values in code. Select them using existing fixtures, CometBFT compatibility, representative workloads, and stress tests; then freeze them in the relevant identity.

### 5.3 Acceptance tests

| ID | Scenario | Expected result |
|---|---|---|
| SEC-SIZE-01 | Transaction exactly at approved maximum | Accept if otherwise valid |
| SEC-SIZE-02 | Transaction one byte above maximum | Reject before expensive parsing |
| SEC-SIZE-03 | Proposal at approved byte budget | Deterministic selection |
| SEC-SIZE-04 | Genesis over byte maximum | Reject before object construction |
| SEC-SIZE-05 | Manifest over allocation-count maximum | Reject |
| SEC-SIZE-06 | Excessive JSON nesting | Reject without recursion failure |
| SEC-SIZE-07 | Excessive object members/string length | Reject |
| SEC-SIZE-08 | Same boundary fixtures on all validators | Identical acceptance decisions |

## 6. P1 — Bind startup to one verified identity

The current CLI accepts `--network-id`, `--protocol-version`, and `--max-amount` separately, constructs `ProtocolConfig`, and compares the manifest network ID. The current Genesis envelope contains only `genesis_hash` and `manifest`.

This is not the proposed Config-v1 model.

### Required design

1. Freeze the Config-v1 schema and exact canonical identity preimages.
2. Define the HND application identity.
3. Define the separately pinned CometBFT profile identity.
4. Verify both before opening the ABCI listener or enabling any signer path.
5. Derive consensus-critical settings from the verified identity.
6. Reject CLI overrides that conflict with the pinned configuration.
7. Persist the identity in a new durable store schema.
8. Refuse normal startup on missing, legacy, or mismatched identity.

### Acceptance tests

- Different `max_amount` on one node: startup refusal.
- Different transaction count or byte limit: startup refusal.
- Different CometBFT build/profile: startup refusal.
- Different validator-set identity or voting power: profile mismatch refusal.
- Correct HND identity but wrong CometBFT profile: startup refusal.
- Any mismatch must fail before listening and before signing is possible.

This work is blocked by the Config-v1 schema and DEC-01 through DEC-10 decisions. Do not implement an interim partial identity.

## 7. P2 — Safe diagnostics and stable error categories

### 7.1 Current concern

The `/account` query exception path appends the requested account ID and raw request bytes in hexadecimal to the returned diagnostic. These values are not private keys, but reflecting arbitrary request bytes can create unnecessary disclosure and log amplification.

Existing modules also use different error strings. Exception text should not become a protocol contract.

### 7.2 Recommended remediation

- Return stable machine-readable categories to ABCI callers.
- Keep detailed diagnostics bounded and server-side.
- Do not echo full request payloads or arbitrary raw bytes.
- Redact secrets and credentials by default.
- Apply length caps to all diagnostic fields.
- Keep operational logs separate from consensus state and app hashes.

### 7.3 Acceptance tests

- Oversized malformed account query produces bounded response.
- Error category remains stable across Python/runtime versions.
- No raw request payload is echoed.
- No private key, token, or credential fixture appears in logs.
- Query failure does not mutate application state.

## 8. P2 — Durable-store trust boundary

The current store checksum is an unkeyed SHA-256 integrity check. It can detect accidental or unsophisticated modification, but an actor who can rewrite the store can also recompute the checksum. It is not an authenticity mechanism.

Recommended actions:

1. Keep the checksum's purpose accurately documented.
2. Do not present it as protection against a hostile local writer.
3. Define the local filesystem and operator threat model.
4. Restrict state-directory ownership and permissions operationally.
5. Consider authenticated storage only after defining where its key is held and what attacker capability it is intended to resist.
6. Bind the new Config-v1 and CometBFT profile identities into the next store schema.
7. Reject identity mismatch without rewriting the existing store.
8. Keep migration offline, explicit, backed up, and auditable.

A keyed MAC stored beside the data on the same host is not independent authenticity if the same attacker can read or replace both the data and key.

## 9. Implementation order and change gates

| Phase | Work | Dependency | Exit evidence |
|---|---|---|---|
| R0 | Enforce loopback-only gRPC binding | No Config-v1 dependency | Positive/negative bind tests; local CometBFT compatibility |
| R1 | Strict duplicate-aware Genesis parser | Parser policy | CLI and ABCI parser tests; identical error categories |
| R2 | Payload/resource limits | Measurements and compatibility review | Boundary/stress tests; classification of consensus vs local limits |
| R3 | Stable errors and bounded diagnostics | Error taxonomy | No-echo, no-secret, no-mutation tests |
| R4 | Config-v1 and CometBFT identity preflight | Frozen DEC register/schema | Cross-language vectors and startup mismatch tests |
| R5 | Durable store identity and offline migration | R4 identity model | No-rewrite, migration, restart, recovery tests |
| R6 | Independent security and protocol review | R0–R5 evidence | Reviewer report and residual-risk register |

R0 and R1 can be designed independently of the Config-v1 schema. R2 requires careful classification and measurements. R4 and R5 must wait for the schema and identity model to be frozen.

## 10. Change-control and safety constraints

- Do not modify GitHub Actions workflow files.
- Do not bind the ABCI server to a non-loopback address during this phase.
- Do not add production keys, real funds, or public endpoints.
- Do not change the meaning of existing v0.2 Genesis or transaction domains.
- Fetch current SHA before editing any existing file.
- Make one small change per commit and test the exact commit.
- Never claim a test passed unless its command actually ran and its output was inspected.
- If a control prevents an edit or execution, do not bypass it; record the blocker and continue with static analysis.
- Keep G2–G4 and public-network gates closed.

## 11. Required evidence package per remediation

Each implementation change must produce:

1. Finding ID(s) addressed.
2. Threat and trust-boundary statement.
3. Exact source files and before/after blob SHAs.
4. Test IDs and exact commands.
5. Environment/runtime versions.
6. Observed test output and commit SHA.
7. Regression impact and compatibility notes.
8. Residual risks and reviewer sign-off.

A documentation update or a passing unit test alone does not close a security finding if integration behavior remains untested.

## 12. Current disposition

- This document is a remediation plan, not an implementation.
- No application source was modified.
- No test command was executed while preparing this plan.
- No CI workflow was modified.
- P0 gRPC exposure control remains open.
- P1 parser, resource-bound, and identity-binding work remains open.
- Config-v1 implementation and migration remain blocked by specification decisions.
- G2–G4 and public-network/production gates remain closed.
