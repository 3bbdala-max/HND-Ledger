# WP4.14 — CometBFT Validator Identity and Genesis Pinning Audit

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Baseline head:** `ed7e350b977f3d23c15e2a393cfbc7f6add074d3`  
**Status:** Static source audit only. Documentation-only change. No source, test, or workflow files changed; no tests or nodes were run.

## 1. Executive finding

The repository distinguishes CometBFT consensus-signing identity from P2P node identity in its disposable four-validator smoke harness and checks that each generated identity is unique. It also creates a shared Genesis validator set from those generated consensus keys. These are useful test-harness controls, but they do **not** pin a production validator set to an approved, independently authenticated release manifest.

The HND Genesis manifest authenticates HND account allocations and protocol identity; it does not contain the CometBFT validator set. The four-validator preflight and network smoke generate fresh CometBFT homes and keys at runtime. Consequently, their validator identities are fixture identities, not stable network identities.

The ABCI adapter currently ignores CometBFT InitChain validator inputs and emits no validator updates from FinalizeBlock. That means validator membership/power is effectively established outside the HND application in the CometBFT Genesis document and is not changed by HND's current ABCI responses.

## 2. Identity domains — keep these separate

1. **CometBFT consensus key** — `config/priv_validator_key.json`; signs consensus votes/proposals and determines the validator address/public key represented in the Genesis validator set.
2. **CometBFT P2P node key** — `config/node_key.json`; determines the node ID used for peer identity and networking. It is not the consensus signing key.
3. **HND account signing key** — Ed25519 public key carried in HND account allocations/transactions; `account_id_for_public_key` derives the HND account identifier. It is not a CometBFT validator identity.

The smoke harness reads the consensus public key from `priv_validator_key.json` and obtains the P2P node ID separately through `show-node-id`. This is a positive separation in the test code. The HND account keys are generated independently for Alice/Bob and used to construct the HND allocation manifest.

## 3. Source findings

### 3.1 HND manifest does not pin validators

`docs/WP1_V02_GENESIS_MANIFEST_2026-10-31.md` defines the HND manifest as:
- manifest version, network ID, protocol version, total supply;
- sorted account allocations containing account ID, Ed25519 public key, and amount;
- a domain-separated canonical manifest hash, with the expected hash supplied through a separate trusted channel.

There is no CometBFT validator identity, consensus public key, validator address, voting power, or P2P node ID in this manifest schema. This is a distinct domain, not a defect in the account-allocation hash itself. However, a production network still needs a separately authenticated CometBFT Genesis/profile artifact or a deliberately extended release manifest that binds the validator set.

### 3.2 Four-validator preflight generates temporary identities

`scripts/cometbft_v040_four_validator_genesis_preflight.py`:
- generates Alice/Bob HND account keys in-process;
- runs CometBFT `init --home` once for each of four temporary homes;
- reads each `priv_validator_key.json`, checks that `pub_key` has `type` and `value`, and that address/value are non-empty;
- calls `show-node-id` and checks P2P node-ID uniqueness;
- checks consensus-address uniqueness;
- constructs four Genesis validator records with power 10 each from the generated keys;
- creates one shared Genesis document and copies identical bytes to all four homes;
- invokes the Go Genesis helper and reports that private keys were kept inside a temporary directory, with no nodes started.

The generated identities are intentionally disposable. The preflight does not compare the resulting validator keys against a stable, approved expected-key list. Its Python checks do not independently recompute each consensus public-key/address pair, enforce an explicit allowed consensus key type/value encoding, or compare the complete validator records to a signed/pinned validator-set profile. The Go helper loads CometBFT Genesis types and checks that there are four validators; it prints chain ID and initial height but contains no repository-defined expected profile comparison.

### 3.3 Four-validator running smoke adds local identity substitution checks

`scripts/cometbft_v040_four_validator_network_smoke.py` also:
- runs `init` for each temporary home and builds the Genesis validator list from those homes' generated consensus keys;
- checks unique P2P node IDs and unique consensus addresses;
- writes the same Genesis bytes to the homes;
- defines `validator_identity()` as the consensus public key from `priv_validator_key.json` plus the node ID from `show-node-id`;
- captures validator 4's identity before a restart, verifies its key files remain unchanged across recovery, and checks that replacing its consensus-key file or P2P node-key file with validator 1's file is rejected by comparison with the captured identity.

These are meaningful restart/identity-substitution regression checks. They do not prove that a fresh production process starts with an approved identity: the expected identity is captured from the same disposable test home during that run. The checks are not a signed identity registry, a Genesis-to-local-key startup gate, or a production key-rotation protocol.

### 3.4 InitChain validator inputs are not passed into HND

`hnd_v02/cometbft_v040_server.py` implements `InitChain` by passing only:
- `request.chain_id`;
- `request.app_state_bytes`.

It does not pass `request.validators`, `request.consensus_params`, or `request.initial_height` into `HNDABCIApplication.init_chain()`. The application validates the chain ID and the independently pinned HND manifest payload/hash, but it does not validate the CometBFT validator set or its relationship to local consensus key material.

This means HND's own InitChain validation does not currently establish that the CometBFT Genesis validator set is the approved set. The CometBFT Genesis file is the authority for the active validator set in this deployment shape.

### 3.5 Current FinalizeBlock path does not change validator membership

The adapter's `FinalizeBlock` converts HND transaction results and returns only `tx_results` and `app_hash`. It does not populate `validator_updates` or `consensus_param_updates`.

HND's `_merge_evidence()` validates and journals CometBFT misbehavior metadata (type, validator address, voting power, height, timestamp, and total voting power). The journal is incorporated into the HND application hash and durable state. It does not itself verify original signed votes, slash funds, or remove/reduce a validator's power. No validator update is emitted as a consequence of recorded evidence.

Therefore, under the current adapter behavior, the application records evidence but does not implement application-driven validator punishment or membership changes. Do not describe evidence journaling as slashing or validator-set enforcement.

### 3.6 Validator and node keys have different lifecycles

The disposable harness creates both key files under each temporary CometBFT home. In the remote-signer path, it moves validator 4's `priv_validator_key.json` and `priv_validator_state.json` into a signer-owned temporary directory and applies mode `0600`; the node's `node_key.json` remains under the node home. This correctly separates consensus signing custody from P2P identity in that test path.

This is test-fixture handling only. It does not define production key custody, hardware protection, identity enrollment, rotation, revocation, backup, or compromise response for all validators.

## 4. Control assessment

| Control | Current evidence | Assessment |
|---|---|---|
| Four validators exist in disposable Genesis | Python preflight and Go schema helper check count | Present for fixture |
| Consensus addresses unique | Python preflight and smoke | Present for fixture |
| P2P node IDs unique | Python preflight and smoke | Present for fixture |
| Consensus and P2P identities distinguished | Separate key file and `show-node-id` reads | Present in harness |
| Genesis byte-identical across four homes | SHA-256/byte checks | Present for fixture |
| Local key substitution detected after restart | Captured-identity comparison in smoke | Present for tested recovery path |
| Stable approved consensus keys pinned | No fixed expected-key manifest found in the reviewed path | Gap |
| Validator set authenticated independently of HND account manifest | No release-grade signed/pinned binding found | Gap |
| Full Genesis validator profile checked against approved values | Helper checks schema/count; no expected-set comparison | Gap |
| InitChain validates incoming validator set and local key membership | Adapter does not forward validator list | Gap |
| Evidence causes verified validator update/slashing | Evidence is journaled; no update emitted | Not implemented |
| Production key custody/rotation/revocation policy | Disposable temp-home/signer fixture only | Not established |

## 5. Recommended production binding

Before public-network approval, define a separately versioned and authenticated validator-set profile. At minimum, it should bind:

- chain ID and Genesis initial height;
- exact CometBFT version/build identity and Genesis schema/profile version;
- ordered or canonically sorted validator entries;
- each validator's consensus public-key type and canonical key bytes;
- the consensus address recomputed from each public key, not trusted as an independent input;
- positive voting power and the exact expected total voting power;
- uniqueness of public keys and addresses;
- explicit allowed key algorithms;
- an independently pinned profile digest or authenticated release signature;
- a policy for identity enrollment, rotation, removal, and emergency compromise response.

P2P node IDs should be recorded in a separate node-enrollment profile or deployment inventory. Do not treat a P2P node ID as a consensus validator key, and do not include private key material in a public manifest. Local startup should fail closed if the local consensus public key does not match exactly one authorized validator entry and if the actual Genesis validator set does not match the authenticated profile.

If the intended design is that HND does not govern validator membership, state that explicitly: CometBFT Genesis and an operator-controlled authenticated release process govern membership, while HND only records evidence. If HND is intended to govern membership, implement and test the corresponding authenticated InitChain validation and validator-update policy before launch.

## 6. Proposed regression tests (not run)

- **VID-GEN01** — Reject Genesis with validator count different from the approved profile.
- **VID-GEN02** — Reject an unknown consensus public key even when the count and total power are correct.
- **VID-GEN03** — Reject duplicate consensus public keys and duplicate derived addresses.
- **VID-GEN04** — Reject a validator address that does not equal the address derived from its public key.
- **VID-GEN05** — Reject unsupported key type, malformed key encoding, and invalid key length.
- **VID-GEN06** — Reject zero/negative power and a total-power mismatch.
- **VID-GEN07** — Reject a Genesis whose chain ID or initial height differs from the authenticated profile.
- **VID-GEN08** — Reject a validator-set/profile digest mismatch even if the HND account manifest hash matches.
- **VID-START01** — Reject startup when local `priv_validator_key.json` public key is not the authorized key for that validator slot.
- **VID-START02** — Reject startup when local P2P node identity is not the separately enrolled node identity, without confusing it with the consensus key.
- **VID-INIT01** — Verify that InitChain request validator records are checked against the authenticated profile if HND is designated to enforce them.
- **VID-UPDATE01** — Verify that evidence journaling does not imply a validator update; if governance/punishment is added, test exact update contents and activation height.
- **VID-ROT01** — Test authorized key rotation, revocation, and rejection of stale/revoked keys.
- **VID-REPRO01** — Verify that a production release reproduces the same authenticated validator profile while disposable test harnesses are explicitly allowed to generate ephemeral identities.

These are test proposals, not test results.

## 7. Disposition

**Status: production validator identity pinning is not demonstrated.** The existing four-validator harness provides valuable disposable identity uniqueness, restart continuity, and substitution checks, but it does not pin the network's validator set to an approved authenticated profile. The HND account Genesis hash must not be presented as authenticating the CometBFT validator set.

This audit is source-based and limited to the files named above and the HND manifest reference. No source or test code was changed, and no test command or live node was executed.
