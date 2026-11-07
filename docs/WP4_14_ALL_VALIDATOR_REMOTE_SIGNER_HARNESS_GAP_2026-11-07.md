# WP4.14 — All-Validator External Signer Harness Gap

**Date:** 2026-11-07  
**Branch:** `phase-0.2-planning`  
**Current status:** All-four remote-signer test harness and same-host helper lock CI-validated over Unix and authenticated Noise; production signer operations and distributed fencing remain OPEN  
**Scope:** Disposable four-validator CometBFT integration harness

## Current acceptance status (latest evidence, 2026-11-07)

This summary supersedes the earlier dated sections below, which record the
initial discovery and intermediate implementation stages.

- Four independent external signer processes for all four validators: **CI PASS**.
- Remote-only CometBFT provider used by all four nodes: **CI PASS**.
- No local consensus key/state files for all four validators after startup: **CI PASS**.
- Independent signer key/state records and Genesis public-key identity matching: **CI PASS**.
- All-four signer transport over Unix sockets: **CI PASS**.
- All-four signer transport over authenticated Noise: **CI PASS**.
- Unauthorized Noise peer rejection for every signer: **CI PASS**.
- Validator-4 signer outage/restart while the other three remain online: **CI PASS**.
- Four-validator transaction, partition, reconnection, and recovery checks in
  the all-four signer runs: **CI PASS**.
- Remote-only CLI rejects missing signer, key-generation commands, and
  unauthenticated TCP endpoints: **CI PASS**.
- Same-host advisory single-writer lock in Unix and Noise test helpers,
  including duplicate-process contention rejection and safe state-digest
  handoff: **CI PASS** (run `42336661940`).
- Post-state-save/pre-response signer crash and safe retry/rejection on
  recovery (vote path): **CI PASS** (run `42337449661`).
- Multi-host exclusive ownership, durable distributed fencing, stale-leader
  rejection, and production-grade failover: **OPEN**.
- Production key custody/HSM, operational approval, signed releases,
  independent audit, and deployment/recovery evidence: **OPEN**.

The CI evidence is a disposable integration harness using test keys and
process-local signer helpers. It is not a production deployment approval.

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


### CI binary provenance closes the runtime-path ambiguity

The workflow `.github/workflows/hnd-v02-tests.yml` builds the CometBFT executable directly from the pinned upstream checkout at `0880b4d378f347ab16e54ec677ff50d803f37d62` using `go build ./cmd/cometbft`, without applying a custom provider patch. It passes that exact binary to both the private four-validator harness and the external-signer/Noise variants. Those harnesses start nodes through the CLI `node --home` command.

This ties the static upstream call-path finding to the actual CI artifact: the tested binary is the stock CLI whose default provider calls `LoadOrGenFilePV` before remote-signer replacement. The current CI integration can therefore pass while validator 4's original key has been moved to signer ownership and a replacement local FilePV has been generated in its node home. The test currently proves remote signing is used for the active validator interface, but does not prove the absence of an additional locally generated private key.

**Next implementation constraint:** any future fix must change the actual binary/provider path used by CI, not only Python setup assertions. Prefer a small, explicit CometBFT-side provider/CLI integration change or a dedicated test executable that invokes a reviewed custom `node.Provider`; retain the stock CLI test separately as an upstream behavior regression check. Then assert before and after node startup that no local consensus key file is created for any externally signed validator, and verify remote `GetPubKey` against the Genesis identity. Do not label the existing green remote-signer tests as no-fallback coverage.


### Feasible fail-closed provider boundary confirmed in pinned upstream API

The pinned source also exposes a supported extension point that avoids modifying CometBFT internals:

- `cmd/cometbft/main.go` explicitly documents copying the CLI main and replacing `node.DefaultNewNode` for external signer use; it wires the selected provider into `commands.NewRunNodeCmd(nodeFunc)`.
- `node.Provider` is an exported function type: `func(*config.Config, log.Logger) (*node.Node, error)`.
- `commands.NewRunNodeCmd` accepts a `node.Provider` and calls it for the `start` command.
- The exported `node.NewNode` accepts any `types.PrivValidator`. In `NewNodeWithContext`, when `PrivValidatorListenAddr` is non-empty, the supplied object is replaced by the external signer client before CometBFT calls `GetPubKey()` on the selected validator.
- The `types.PrivValidator` interface consists of `GetPubKey`, `SignVote`, and `SignProposal`.

**Candidate implementation (not yet coded or approved):** build a dedicated HND remote-only CometBFT CLI from the exact pinned upstream source. Its custom provider must reject an empty/unapproved `PrivValidatorListenAddr` before constructing the node; load/generate only the P2P node key; pass a deliberately non-signing in-memory `PrivValidator` placeholder to `node.NewNode`; and rely on the already configured external signer client replacing that placeholder. The placeholder's `GetPubKey`, `SignVote`, and `SignProposal` should all return explicit errors, so an unexpected code path cannot sign. It must never call `LoadOrGenFilePV`, `GenFilePV`, or `LoadFilePV` for the node's consensus key.

The custom CLI should be a separate CI artifact used only by external-signer scenarios; keep the stock CometBFT CLI for ordinary private-FilePV regression tests. First validate the custom provider with a one-validator negative startup test (missing endpoint rejected; remote endpoint succeeds; no local key/state files appear before or after startup; remote public key equals Genesis identity). Only after that passes should the four-validator harness be parameterized to use four isolated signer records and the custom binary.

**Important caveat:** this is a viable upstream-supported design path established by static API inspection, not an implementation or executed test. The all-validator lifecycle refactor, signer-mode policy authentication, and distributed single-writer/fencing controls remain separate required work.


## Remote-only provider implementation checkpoint (2026-11-07)

A dedicated CometBFT v0.40.0 CLI entrypoint has now been added at
`scripts/cometbft_v040_remote_only_main.go`. Unlike the stock CLI provider, its
provider:

- rejects startup when `priv_validator_laddr` is empty;
- loads/generates only the P2P node identity;
- passes a deliberately non-signing `types.PrivValidator` placeholder to
  `node.NewNode`;
- relies on the pinned CometBFT `NewNodeWithContext` remote-signer replacement
  branch to install the socket client before requesting the validator public
  key; and
- has no call to `LoadOrGenFilePV`, `LoadFilePV`, or consensus-key generation.

CI now builds this dedicated binary from the exact pinned CometBFT source
revision. A negative startup check is also wired to remove the local consensus
key/state files, invoke the remote-only CLI with no signer endpoint, require
the explicit fail-closed error, and assert that neither file is regenerated.

**Status at this checkpoint:** source and CI steps are committed; the newly
triggered CI run has not yet completed. The dedicated binary has not yet been
used by the four-validator external-signer integration, and no positive
remote-signer startup/no-local-file result is claimed. The validator-4 lifecycle
test still uses the stock binary until that runtime integration is adapted and
verified. The all-four signer refactor, distributed fencing, and production
signer approval remain OPEN.


## Partition regression diagnosis and correction (2026-11-07)

A completed Unix external-signer CI run passed the signer outage/restart and
validator-4 durable ABCI/CometBFT recovery checks, then failed later in the
3/1 partition assertion. The diagnostics showed the three-node quorum at
height 76 while the isolated validator was still at height 8; its own
pre-partition baseline was height 8, whereas the assertion incorrectly
compared it with the quorum's height 9 baseline. This was a harness assertion
bug: a lagging isolated validator must remain at its own last committed
height/hash, not be required to match a faster quorum at the instant the relay
cut is observed.

Commit `08d5cfad55777e67829faf104c603d327a125e8c` changes the partition
invariant to capture and compare the isolated validator's own baseline height
and block hash, while retaining the separate quorum baseline for expected
transaction-state checks. The corrected partition test is pending fresh CI
execution. The prior run remains recorded as **FAILED**; it is not retroactively
counted as passing. This correction does not relax the safety assertion: the
isolated node's height, block hash, application hash, and account state must
remain unchanged from its own pre-partition baseline.


## Later full CI result for the existing validator-4 signer scenarios

Workflow run `42333800723` on commit
`4008ec842111f0e7d77ed1d4f7f81ffeff08279a` has now completed successfully:
both `hnd-v02-tests` and `cometbft-single-node-smoke` passed. The latter
includes the private four-validator network smoke, validator-4 Unix
external-signer outage/recovery, and authenticated Noise external-signer
outage/recovery steps. This is positive evidence for the existing
**validator-4-only** signer scenarios; it does not establish all-four
external-signer coverage or validate the newly added remote-only CLI.

Subsequent source/CI commits add the dedicated remote-only CLI build and
negative startup test, and correct the isolated-node partition baseline
assertion. Those newer changes are still awaiting their own completed CI
results at the time of this update.


## Remote-only CLI wired into validator-4 integration (2026-11-07)

The external-signer branches of the four-validator harness now accept
`--remote-only-binary` and launch validator 4 with the dedicated fail-closed
CLI instead of the stock CometBFT CLI. The stock CLI remains responsible for
disposable testnet `init` and the three local-FilePV validators; the initial
validator-4 consensus key and state are moved into the signer-owned directory
before node startup. Validator 4 is then started and restarted with the
remote-only provider.

The harness now asserts all of the following in external-signer mode:

- the external signer public key matches validator 4's Genesis public key;
- no validator-4 local `priv_validator_key.json` or
  `priv_validator_state.json` exists after the signer connection and RPC
  startup, or after restart/recovery;
- the signer-owned consensus key digest and P2P node identity remain stable.

Both Unix and authenticated Noise CI invocations pass the dedicated
`--remote-only-binary` built from pinned CometBFT v0.40.0 source. This change
is committed in the branch; the resulting new CI runs must pass before the
no-local-fallback property is considered verified. The architecture is still
validator-4-only; the other three validators intentionally remain local in
this integration stage.


## Remote-only CLI command-surface hardening (2026-11-07)

The dedicated binary's command registration has been reduced to node startup,
node-ID inspection, version, debug, and shell completion. It no longer
registers CometBFT commands that initialize, generate, reset, or replace
validator consensus keys (including `InitFilesCmd`,
`GenValidatorCmd`, `ResetPrivValidatorCmd`, and `TestnetFilesCmd`).
This narrows the remote-only executable's exposed operations in addition to
the provider's fail-closed behavior. The new command-surface change is awaiting
a fresh pinned-source CI build.


## First positive remote-only runtime result: Unix transport (2026-11-07)

Workflow run `42334495538` on commit
`61e94b5bf53a56295c2fcb63e5c96a4f179d21f5` completed the
`Run four-validator external remote-signer integration and outage recovery`
step successfully while invoking the dedicated remote-only CometBFT binary
for validator 4. The preceding pinned-source build and missing-signer
fail-closed test also passed in this run.

This is the first positive runtime CI evidence for the remote-only provider
with the Unix external signer in the four-validator harness. The harness's
post-connection and post-restart assertions check that validator 4 has no
local consensus key or state file, and that the signer-owned public key
matches Genesis. The separate authenticated Noise variant is still running
in this same workflow; no Noise remote-only result is claimed yet.


## Positive remote-only runtime results: Unix and authenticated Noise

Workflow run `42334495538` on commit
`61e94b5bf53a56295c2fcb63e5c96a4f179d21f5` has now completed with
**both** external-signer network integration steps successful:

- Unix remote signer: success, including outage/restart and durable recovery.
- Authenticated Noise remote signer: success, including outage/restart and
  durable recovery.

Both invocations use the dedicated remote-only CometBFT binary for validator
4. The harness verifies the signer public key against Genesis and checks that
validator 4 does not create local consensus key/state files after signer/RPC
startup or after recovery. The existing four-validator network and partition
checks are also included in the successful workflow.

**Scope remains limited:** this is a proven no-local-fallback runtime path for
validator 4 under both supported test transports. Validators 1–3 remain local
FilePV in these network runs; all-four external signer mode has not yet been
implemented or tested. The reduced CLI command-surface hardening committed
after this run also awaits its own fresh CI result.


## Repeated CI confirmation after readiness-bound no-local-key assertions

The later workflow runs `42334524327` and `42334548900` also completed
successfully on commits `22e90205832d93fb26dc4208be909ecf9f5ecc01` and
`da491eacb18c2602cf49932a90e1ed565786faf6`. Both include the Unix and
authenticated Noise remote-only validator-4 integration steps. These runs
therefore re-exercise the explicit post-signer-connection/RPC-startup and
post-restart no-local-key/state assertions after those assertions were added.


The remote-only CLI negative CI check has been extended to assert that the
binary does not expose `init` or `gen-validator` commands and that these
attempts cannot create validator key/state files. This verifies the narrowed
command surface behavior rather than relying on source inspection alone.
Fresh CI is pending.


## All-four independent signer mode implementation checkpoint (2026-11-07)

The four-validator harness now has an opt-in Unix-only
`--all-remote-signers` mode. It creates four distinct signer-owned
directories, moves each validator's consensus key and anti-double-sign state
into its own directory, configures four independent Unix signer endpoints,
and starts all four validators with the remote-only CometBFT binary. The mode
checks each signer public key against its Genesis validator identity and
asserts that no validator home contains a local consensus key/state file
after RPC startup. The existing validator-4 outage/restart recovery path is
retained, with the other three independent signer processes kept online.

A dedicated CI step now invokes this mode. This is a newly added test path,
not yet verified; it must pass before all-four external signing is marked
implemented. Authenticated Noise is currently tested with the validator-4
remote-only path, not yet in an all-four arrangement.


The all-four mode now emits a machine-readable
`HND_WP4_14_ALL_FOUR_REMOTE_SIGNERS_NO_LOCAL_KEYS_OK` evidence marker only
after all four signer connections, Genesis public-key matches, local-key
absence checks, and distinct signer key/state paths have been verified.
This marker is an assertion result, not a production-readiness claim.


## Remote signer transport policy hardening (2026-11-07)

The remote-only provider now accepts only:
- absolute local `unix://` socket paths; or
- authenticated `noise://peer-id@host:port` endpoints with a non-empty peer
  identity and valid numeric TCP port.

Unauthenticated `tcp://` and other endpoint schemes are rejected before node
construction. CI now includes a negative test that configures a TCP signer
endpoint, expects the explicit rejection, and verifies no local consensus
key/state files are created. The Unix and Noise positive integration tests
cover the two allowed transports. This transport policy change is awaiting
fresh pinned-source CI.


## First successful all-four independent Unix remote-signer integration

Workflow run `42335090721` on commit
`d46a327d075649a13ca6d3b6aeed2a98a7e1240b` completed the dedicated
`Run four independent external signers with no local consensus keys` step
successfully. This run exercised four distinct signer directories, four
independent Unix endpoints, four remote-only CometBFT node processes, and the
existing four-validator consensus/transaction, validator-4 signer outage and
recovery, and 3/1 plus 2/2 network partition checks. The harness verifies
Genesis signer identity matching and absence of local consensus key/state
files for all four validators after startup. The validator-4 restart path
retains its own signer-owned state while the other three signer processes
remain active.

This closes the all-four remote-signer **Unix test-harness milestone**. It
does not yet prove production deployment, multi-host fencing, signer hardware
security, or authenticated Noise for all four simultaneously. The dedicated
machine-readable all-four marker was added after this run and awaits its
next CI confirmation.


## All-four authenticated Noise signer extension (implementation pending)

The all-four signer harness has been extended to support four independent
authenticated Noise endpoints as well as Unix sockets. Each validator receives
its own Noise identity, peer ID, endpoint, signer-owned consensus key, and
anti-double-sign state. The harness checks every connection marker, matches
each signer key to Genesis, probes unauthorized peer rejection for every
signer, and retains the validator-4 outage/recovery scenario. A dedicated
all-four Noise CI step is now wired; no successful result is claimed until
that run completes.


## All-four Unix signer invariant marker confirmed by CI

Workflow run `42335234969` on commit
`a610ef9100257379da87b632ce31e40866131256` completed the
`Run four independent external signers with no local consensus keys` step
successfully after the explicit all-four evidence marker was added. This
reconfirms the four independent signer records, signer-to-Genesis identity
checks, absence of local consensus key/state files, validator-4 signer
outage/recovery, and four-node network behavior. The all-four Unix test path
is now green on two separate workflow revisions.


## All-four Unix signers and transport allowlist CI confirmation

Workflow run `42335387643` on commit
`76062ef988c5ea9f127d82bcd3841a4611945235` passed the four-independent-
signer Unix integration step with the remote-only provider's Unix/Noise
allowlist enabled. Its negative startup step also passed the checks that the
remote-only CLI does not expose `init` or `gen-validator`, rejects an
unauthenticated `tcp://` signer endpoint, and leaves no local consensus
key/state files after rejection. The authenticated Noise single-validator
variant was still running at this checkpoint; all-four Noise remains a
separate pending validation.


## Full green CI after transport allowlist and all-four Unix signer mode

Workflow run `42335387643` on commit
`76062ef988c5ea9f127d82bcd3841a4611945235` completed successfully across
both jobs. It passed the remote-only missing-signer and unauthenticated-TCP
negative checks, the four-independent-Unix-signer network/recovery step, and
the validator-4 authenticated Noise integration/recovery step. The dedicated
remote-only CLI therefore has green CI for both allowed transports, with
all-four simultaneous signing covered over Unix. All-four simultaneous Noise
is the next validation milestone.


## All-four Unix mode reconfirmed after Noise generalization

Workflow run `42335547079` on commit
`588a9465f36d431e735e7746aa09ef72e047a63b` passed the four-independent-
Unix-signer step after the harness was generalized to support both Unix and
Noise for all four validators. This confirms the shared signer-record and
startup logic did not regress the Unix path. The same workflow is continuing
through the authenticated Noise tests, including the new all-four Noise step.


## All-four authenticated Noise signer integration passed

Workflow run `42335547079` on commit
`588a9465f36d431e735e7746aa09ef72e047a63b` completed successfully across
both jobs. The dedicated step
`Run four independent authenticated Noise signers with no local consensus keys`
passed, in addition to the all-four Unix step and the validator-4 Unix/Noise
recovery integrations.

The all-four Noise mode uses four distinct signer identities, four distinct
Noise endpoints, and four signer-owned key/state records. It verifies every
signer connection, every signer public key against Genesis, absence of local
consensus key/state files for every validator, and rejection of unauthorized
peer identities for each signer. The existing validator-4 outage/recovery
path also passed while the other three signer processes remained online.

**Result:** simultaneous external signing for all four validators is now
covered by successful CI over both Unix sockets and authenticated Noise.
This closes the all-four signer-mode integration test milestone, not the
separate production operations, multi-host fencing, HSM/key custody, and
release assurance requirements.
