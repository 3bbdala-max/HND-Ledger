# WP4.14 — All-Validator External Signer Harness Gap

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Status:** Engineering review; no all-validator implementation claimed  
**Scope:** Disposable four-validator CometBFT integration harness

## Finding

The existing four-validator remote-signer integration is intentionally scoped to validator 4. Validators 1–3 retain their local CometBFT FilePV. Extending the current script by merely moving all four private-key files and adding four signer processes is not a safe mechanical change.

The harness has later lifecycle checks that directly inspect validator 4's local `config/priv_validator_key.json` during identity-preservation, identity-substitution, and node-restart recovery checks. A true all-validator external-signer mode must preserve public validator identity evidence without leaving a usable local private-key fallback. It must also restore each remote signer through the same fail-closed state-digest path and prove each CometBFT node reconnects to its own signer after restart.

The current test helper has a single validator-4 signer lifecycle, single signer log, single Unix socket, and validator-4-specific recovery assertions. These are architectural assumptions in the fixture, not just a missing loop.

## Required refactor before claiming coverage

1. Model signer endpoint, process, log, key path, state path, and expected state digest as per-validator records.
2. Separate public validator identity evidence from local private-key material; prove no node can fall back to a local private signer.
3. Start all four signer processes and require a fresh authenticated/connected marker from each before consensus proceeds.
4. Verify each node is configured for its corresponding external signer endpoint and reject any local FilePV private-key fallback.
5. Exercise signer outage for one validator while the other three external signers continue to form quorum.
6. Restart each validator node and its signer in controlled cases; validate the correct validator identity and fail-closed anti-double-sign state digest.
7. Collect all signer processes in cleanup, including replacement processes after outage and node restart.
8. Run the complete four-validator network, partition, recovery, and state-convergence suite in CI.

## Security boundary

Even a passing all-four external-signer integration would establish only that this disposable test topology routes each validator through a separate signer process and survives the tested restart/outage cases. It would **not** establish multi-process or multi-host exclusive ownership, durable distributed fencing, stale-leader rejection, or production-grade failover safety. Those require a separate authoritative ownership design and adversarial crash/partition tests.

## Acceptance status

- Validator 4 external signer integration: **EXERCISED IN CURRENT CI**.
- Validators 1–3 mandatory external signer routing: **NOT YET EXERCISED**.
- Local signer fallback resistance for every validator: **NOT YET PROVEN**.
- All-validator signer restart/recovery matrix: **NOT YET IMPLEMENTED**.
- Distributed single-writer fencing: **OPEN**.
- Production signer approval: **NOT APPROVED**.

No test result is claimed by this review. The implementation must be delivered as a coherent lifecycle refactor with CI evidence, not as a flag-only change.

## CI regression evidence and correction

A short-lived all-validator experiment was pushed as commit `77def8c85b2d9b95a548d26d8d557cdb2779f978`. Its CI run `42328113608` failed in the **ordinary private four-validator smoke test**, before the external-signer scenario, with a Python `NameError: name 'all_signers_mode' is not defined` at the stale experimental process-registration line. This was a harness regression, not evidence of a consensus or signer protocol failure.

The follow-up commit `18a5b9de299b81ceb4483a027a42702672cc6052` removed the incomplete experimental workflow invocation and the stale registration line, and recorded this harness gap. CI run `42328227277` on that follow-up commit completed successfully: both `hnd-v02-tests` and `cometbft-single-node-smoke` passed. The passing run confirms the regression was removed and the existing suite is green; it does **not** add all-validator external-signer coverage.

Acceptance remains unchanged: validator 4 only is exercised through the current external-signer integration. The next implementation must be a coherent per-validator lifecycle refactor, with explicit no-local-fallback assertions and restart/outage coverage, before adding the all-validator mode back to CI.


## Concrete refactor blueprint from source-level follow-up (2026-11-07)

A second pass over the current harness confirms the refactor boundary is larger than the initial signer-start loop. The existing script has validator-4 assumptions in its identity reader, signer process variables, endpoint setup, outage/recovery path, and post-restart identity checks. The following is the implementation contract for the next source change; it is not a claim that the refactor has been implemented.

### Per-validator record

Replace the singleton values (`signer`, `signer_log`, `signer_socket`, `signer_key_path`, `signer_state_path`, `identity_path`, `noise_addr`) with one record per validator, keyed by validator index. Each record must carry: node home, expected consensus public key/address captured before key isolation, node P2P identity, transport mode, unique endpoint, signer transport identity (Noise only), signer-owned key/state paths, signer process, log handle/path, and current expected state digest. Keep signer processes and logs in arrays/maps whose cardinality is asserted to equal N.

### Required setup ordering and invariants

1. Generate all four node homes and validator-set entries first; preserve only the public consensus identity in the harness's expected-identity record.
2. For every validator, verify the initial FilePV key and state files exist, move both into a unique signer-owned directory, and set restrictive permissions. Do not copy the private key back into a node home for later identity assertions.
3. Configure `priv_validator_laddr` for every node, using a unique Unix socket or unique Noise listener address. Generate a distinct Noise transport identity per signer and pin that signer's expected node peer identity.
4. Before starting any node, assert that every node home lacks `config/priv_validator_key.json`, that each signer-owned key/state path is a regular file, that all key/state paths are distinct, and that each node's configured endpoint matches exactly one signer record.
5. Start all node-side listeners, then start all signer processes (or use a deterministic per-node handshake sequence); require a fresh successful connection marker from each signer before treating the network as initialized. A process being alive or a socket path existing is not proof of an authenticated connection.
6. Verify each node's remote public key equals its previously captured validator public key. For Noise, additionally prove each signer accepts only its pinned node peer and that cross-wiring signer i to node j is rejected.

### Lifecycle and recovery

- Replace the single validator-4 outage case with a parameterized one-validator-at-a-time outage test. The other three remote signers must remain connected and the three-node quorum must commit; the isolated validator must not advance. Restart that signer only after pinning its own state digest, then require a fresh connection marker and four-way convergence.
- Parameterize node restart/recovery over each validator. Stop that validator's signer and node-side process in a controlled order, preserve its node P2P key and HND application state, and restart using the same signer-owned consensus key/state. The signer recovery command must reject missing or substituted state and accept only the digest captured after a clean signer stop.
- Track every original and replacement signer process for cleanup. Cleanup must stop all signers even when an earlier validator's recovery assertion fails.
- Change identity assertions to compare the node's remote `GetPubKey` result against the captured public identity. The existing `validator_identity()` helper reads `config/priv_validator_key.json`; retaining that helper as-is would either fail after proper key isolation or tempt the test to restore a dangerous local private-key copy.
- Keep the existing consensus, transaction, partition, ABCI recovery, and application-hash checks, but require all four validators to satisfy the external-signer invariants throughout the run.

### Explicit non-goals

This harness refactor does not solve cross-process or cross-host signer ownership, durable fencing, stale-leader rejection, signature-release linearization, signer authorization TOCTOU, or production key custody. It must not be described as proving those properties. The existing CI invocation also needs separate private-only and all-remote-signer modes so the ordinary private smoke path remains a regression guard and the all-signer mode is independently visible in logs.

**Disposition after this review:** implementation remains OPEN. No source change was made because the lifecycle and identity refactor must be delivered atomically with its assertions and full CI execution; a partial loop conversion would create misleading coverage.


## Pinned CometBFT v0.40.0 startup-path confirmation (2026-11-07)

The exact CometBFT source revision pinned by CI, `0880b4d378f347ab16e54ec677ff50d803f37d62`, was inspected after the lifecycle blueprint was written.

- In `node/node.go`, `NewNodeWithContext` checks `config.PrivValidatorListenAddr != ""`. When set, it replaces the supplied `privValidator` with `createAndStartPrivValidatorSocketClient(...)`; an error creating the external client aborts node construction. This confirms that the remote-signer endpoint is the selected validator implementation on this path, rather than an additive second signer.
- In `config/config.go`, `BaseConfig` independently retains default local FilePV key and state paths (`priv_validator_key.json` and `priv_validator_state.json`) even when a remote listen address is configured. Therefore, an external-signer deployment must explicitly ensure local key material is not provisioned and must verify the actual startup configuration; the mere existence of the default path fields is not proof of fallback.
- In `privval/file.go`, `LoadFilePV` exits if either the key or state file cannot be read. `LoadOrGenFilePV` generates a new local FilePV if the key file is absent. This is a material reason to test the actual CLI/startup path with missing local key files, rather than assuming absence is safe or assuming it causes fallback. The node's external-listener branch and the CLI's construction of the initial validator object must be exercised together.

**Evidence boundary:** this is source inspection of the pinned revision, not an executed negative startup test. It confirms the external-client replacement branch and the dangerous local load-or-generate behavior as separate code paths. The all-validator harness must prove that the exact node command, config, and startup sequence select the external client for every validator and never create or retain a local private key. The proposed downgrade matrix remains open until executed.


## CLI default-provider local FilePV generation confirmed (2026-11-07)

A further source trace closed the ambiguity left by the previous section. In the same CI-pinned CometBFT revision `0880b4d378f347ab16e54ec677ff50d803f37d62`:

- `cmd/cometbft/main.go` assigns `nodeFunc := nm.DefaultNewNode` and passes it to `NewRunNodeCmd`.
- `cmd/cometbft/commands/run_node.go` invokes that provider directly in the `start` command: `n, err := nodeProvider(config, logger)`.
- `node/setup.go`, in `DefaultNewNode`, evaluates `privval.LoadOrGenFilePV(config.PrivValidatorKeyFile(), config.PrivValidatorStateFile())` as an argument to `NewNode(...)`.
- Only after that provider has created/loaded the local FilePV does `node/node.go`'s `NewNodeWithContext` replace the supplied `privValidator` with the external socket client when `PrivValidatorListenAddr` is non-empty.

**Conclusion:** the standard CometBFT CLI `start` path does invoke local FilePV load-or-generate before the remote-signer replacement. With a missing local key file, `LoadOrGenFilePV` generates and saves a new local consensus key/state pair, even though the subsequently constructed node uses the remote signer client. This is stronger than the prior source-level warning: it establishes a concrete local-key-provisioning hazard in the default CLI provider path.

**Required engineering response:** do not treat deletion of the local key file as a safe configuration for the stock CLI provider. The all-validator harness must either use a deliberately constructed custom `node.Provider` that supplies a non-local placeholder/appropriate validator object without invoking `LoadOrGenFilePV`, or use a patched/approved upstream startup path whose behavior is explicitly tested. Any custom provider must be reviewed against all call sites that may dereference the initially supplied validator before the remote-client substitution. Tests must assert that no local `priv_validator_key.json` is created and that the remote signer public key is the only validator identity used by consensus.

**Evidence boundary:** this conclusion is a static call-path trace across the pinned source files, not yet an executed CLI negative test. The harness refactor and negative startup test remain OPEN. It does not establish that the current HND harness invokes the stock CLI provider; that must be checked in the HND test runner itself before applying this finding to its runtime behavior.


### Applicability to the current HND four-validator smoke harness

The HND harness was then traced against the same finding. In `scripts/cometbft_v040_four_validator_network_smoke.py`:

- The harness initializes every home with `[binary, "init", "--home", ...]`, capturing the initial public validator identity from each generated `config/priv_validator_key.json`.
- For validator 4, the remote-signer setup moves the original key and state files out of the node home.
- The harness later starts every node with `[binary, "node", "--home", ...]` (line 225 in the reviewed branch version), with no custom provider injected.
- In the pinned CometBFT CLI, `node` is an alias of the standard `start` command; `cmd/cometbft/main.go` wires that command to `nm.DefaultNewNode`.

**Direct implication for this harness:** validator 4's missing local key causes the stock CLI's `DefaultNewNode` to generate a replacement local FilePV before `NewNodeWithContext` swaps in the remote signer. The remote signer still supplies the active validator identity, which explains why consensus can pass while an unwanted local private key is present. The current smoke test therefore does not prove no-local-fallback resistance; it currently permits local key regeneration for validator 4. Validators 1–3 intentionally continue using their local FilePV.

This is now a concrete, HND-harness-specific coverage gap, not merely a generic upstream concern. Before changing the test to assert absence, the harness must adopt a reviewed startup provider/path that does not call `LoadOrGenFilePV` for externally signed validators, and prove it against the exact pinned binary. Do not paper over this by deleting the regenerated key after startup: the private key has already been created and its presence would invalidate the security assertion.

**Status:** current external signer routing for validator 4 remains exercised; no-local-private-key guarantee for validator 4 is **NOT SATISFIED** by the present stock-CLI test path. All-validator remote signing remains **NOT IMPLEMENTED**.
