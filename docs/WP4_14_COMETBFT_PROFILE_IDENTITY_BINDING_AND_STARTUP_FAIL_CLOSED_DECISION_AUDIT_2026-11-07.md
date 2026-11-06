# WP4.14 — CometBFT Profile Identity Binding and Fail-Closed Startup Decision Audit

**Date:** 2026-11-07  
**Branch reviewed:** `phase-0.2-planning`  
**Review type:** Static source and workflow review; documentation only.  
**Change boundary:** No HND source, tests, CometBFT configuration, CI workflow, keys, or production settings changed.

## 1. Executive determination

The repository currently pins a CometBFT release tag (`v0.40.0`) for the test/build path and validates useful disposable Genesis and validator-identity properties. It does **not** yet establish a release-grade, independently trusted CometBFT consensus-profile identity or enforce that identity at every validator's startup.

Three identities must remain distinct:

1. **HND application configuration identity** — parameters that change deterministic HND transaction acceptance or state transition.
2. **CometBFT consensus-profile identity** — the exact CometBFT implementation/build and the complete consensus-affecting network policy.
3. **Local operational configuration** — endpoints, filesystem paths, log levels, local worker counts and peer routing, which must be hardened but should not accidentally become HND application consensus identity.

The current HND Genesis payload contains only `genesis_hash` and `manifest`. The application store records schema version, network ID, protocol version, Genesis hash, height, ledger snapshot, evidence journal and hashes; it does not record HND Config-v1 digest or CometBFT profile digest. The server's CLI independently accepts `--network-id`, `--protocol-version`, and `--max-amount`; only the manifest's network ID is compared in the shown startup path. Consequently, the runtime cannot currently fail closed on a mismatch of a complete application-config/profile identity.

**Decision status:** This report recommends a design and verification sequence. It does not approve any profile values, validator set, network parameters, upgrade policy, or public launch.

## 2. Direct source observations

### 2.1 CometBFT release selection is tag-pinned, not commit-pinned

- `scripts/generate_cometbft_v040_python.sh` clones CometBFT using `--depth 1 --branch v0.40.0` and similarly clones gogoproto tag `v1.7.2`.
- The script prints the resolved tag commit SHA after generation, but does not compare it with a repository-maintained expected commit SHA.
- `.github/workflows/hnd-v02-tests.yml` builds CometBFT by cloning `--depth 1 --branch v0.40.0`, then `go build`s the binary. It does not record or verify a trusted expected source commit, Go module graph lock/checksum manifest for the build, or resulting binary SHA-256 against an approved pin.
- A version tag is useful version selection, but it is not equivalent to an independently trusted immutable commit and artifact pin.

**Finding CPROF-01 — High:** the tested CometBFT source is selected by mutable tag reference and its resolved commit is logged, not enforced against a reviewed expected SHA. No expected binary digest is verified at node startup.

### 2.2 Test Genesis and validator identity checks are useful but narrower than a profile guard

- `scripts/cometbft_v040_four_validator_genesis_preflight.py` creates four temporary homes using the supplied binary's `init`, verifies unique P2P node IDs and consensus addresses, creates a four-validator set with fixture voting power 10 each, and writes byte-identical Genesis files to the homes.
- It validates the Genesis with the pinned CometBFT v0.40.0 Go types. Its own output explicitly scopes this to Genesis-and-identity preflight and states that no nodes are started.
- `scripts/cometbft_v040_four_validator_network_smoke.py` also initializes temporary homes from binary defaults and edits selected TOML networking fields. It checks validator identity and network convergence/recovery in a disposable test network.
- These harnesses do not define and compare a complete approved CometBFT consensus profile for every validator. Fixture values (including four validators and voting power 10) are test data, not proposed public-network values.

**Finding CPROF-02 — High:** common Genesis bytes and unique validator identities do not prove that each validator runs the same complete consensus configuration or exact CometBFT build.

### 2.3 HND startup and Genesis binding

- `hnd_v02/cometbft_v040_server.py` parses the manifest with `json.load`, computes the manifest hash, compares it with the independently supplied `--genesis-hash`, constructs `ProtocolConfig` from CLI arguments, and checks `manifest.network_id == config.network_id`.
- The startup path does not require a canonical Config-v1 document or a pinned Config-v1 digest. It does not compare `max_amount` with a value authenticated by Genesis.
- The server starts the ABCI gRPC listener after constructing the application. The listener is currently restricted to loopback because transport is insecure; that control does not provide consensus-profile authentication.
- `HNDABCIApplication.application_genesis_bytes()` emits `genesis_hash` and `manifest`. `init_chain()` checks chain ID and the pinned HND Genesis payload, but the payload has no CometBFT profile identity.
- `APP_STORE_VERSION = 3`. The persisted store includes `network_id`, `protocol_version`, and `genesis_hash`, but no application-config digest, CometBFT profile digest, binary build identity, or profile schema version.
- The store's SHA-256 checksum is an integrity check, not an authenticated external trust anchor.

**Finding CPROF-03 — Critical:** the current runtime has no fail-closed binding between a trusted HND application-config identity, a trusted CometBFT profile/build identity, Genesis and durable application state.

## 3. Recommended identity model (proposal only)

Do not collapse all configuration into one digest. Maintain at least two separately versioned canonical identities:

### A. HND application-config digest

This identity covers only HND deterministic rules, including (after explicit owner approval and implementation):

- HND protocol/config schema version;
- network ID and protocol version;
- transaction amount and nonce bounds;
- per-block transaction-count and any HND-enforced transaction/aggregate byte limits;
- deterministic transaction/proposal acceptance rules and relevant feature flags;
- any application rule that can cause validators to accept different transactions or state transitions.

The digest must be authenticated by the HND network Genesis and bound into the HND store. The exact schema, numeric bounds, canonicalization rules and hash preimage remain pending owner review; do not infer them from current test constants.

### B. CometBFT consensus-profile digest

This identity should cover the complete, version-specific set of CometBFT settings that can change consensus validity, evidence processing, validator voting power, or consensus liveness/safety. The final field list must be derived from the exact pinned CometBFT v0.40.0 source/config schema and reviewed field-by-field.

Candidate classes requiring explicit classification include:

- exact CometBFT source commit, build inputs and binary artifact digest;
- consensus protocol/version identity where exposed by the implementation;
- block maximum bytes and gas;
- evidence maximum age, duration/height and byte limits;
- validator set, consensus public-key identities, voting power and activation policy;
- consensus timeouts and related timing parameters where they affect consensus operation;
- any other version-specific consensus parameters that can change block validity, evidence acceptance or consensus behavior.

Do not include secret key material. Validator public identities and voting power are public consensus inputs, but should have their own versioned artifact/activation semantics rather than being conflated with HND account allocations.

### C. Local operational profile (separate)

Keep local-only deployment values outside the two consensus identities unless source-level analysis proves otherwise. Typical examples:

- RPC, P2P and ABCI bind addresses and ports;
- persistent peer endpoints and local routing;
- home/data/log paths;
- log level and local observability settings;
- local worker/thread counts and resource tuning.

These settings still need secure deployment policy and allowlists. A value should not be classified as local-only merely because it appears in TOML; confirm its semantics against the exact pinned CometBFT version.

## 4. Trusted pin distribution

A profile digest file located beside the configuration it is meant to authenticate is not an independent trust anchor: an attacker or accidental deployment edit could replace both.

Recommended trust-source options, in order of operational suitability to evaluate:

1. **Signed release manifest:** owner-approved release manifest containing exact CometBFT source commit, build recipe identity, binary SHA-256, HND config digest, CometBFT profile digest, Genesis digest, validator-set artifact digest, activation height/version and signer identity. Verify its signature using a trust root provisioned out-of-band.
2. **Offline-provisioned pin:** independently delivered expected digests/config identity in protected node provisioning, with authenticated change control and a documented rotation process.
3. **Hardware-backed trust root:** where available, pin verification key or measured-boot policy in a protected signing/verification environment.

Do not treat an unsigned local JSON file, a digest computed from the same untrusted config at startup, a tag name, or a store checksum as an independent trust anchor.

## 5. Required fail-closed startup order

The future startup design should reject a node before opening network listeners or permitting consensus signing if any required identity cannot be verified.

1. Load the trust root and verify the signed release/pin manifest.
2. Verify exact CometBFT binary digest and expected source/build identity.
3. Strictly parse the HND application config, CometBFT consensus profile, validator-set artifact and Genesis; reject duplicate JSON/TOML keys, unknown fields where schema requires, invalid types and non-canonical encodings.
4. Compute the HND application-config digest and CometBFT profile digest using separately versioned canonicalization/domain separation.
5. Compare both computed digests and Genesis/validator-set identities with independently trusted pins and activation metadata.
6. Load durable HND store and compare schema, Genesis, application-config digest, CometBFT profile digest and committed height with the expected network identity.
7. Verify consensus key identity, remote-signer identity and durable anti-double-sign state using the independent signer trust/recovery procedure.
8. Only after all checks pass, initialize ABCI transport and CometBFT listeners and enable signing. Any missing pin, unknown schema, digest mismatch, stale/unsupported profile, absent required state or ambiguous upgrade state must terminate startup.

This ordering is a design target, not a claim about the current startup implementation.

## 6. Ownership boundaries

| Responsibility | HND application | CometBFT | Deployment / signer |
|---|---|---|---|
| HND transaction schema, signatures, balances, amount/nonce bounds | Owns deterministic validation and state transition | Consumes application decisions through ABCI | Supplies trusted approved HND config |
| HND app-config digest and store binding | Owns canonical digest, Genesis/store enforcement, migration semantics | Not the authority for HND schema | Provisions independently trusted release pins |
| Block consensus, voting, proposal rounds and consensus state | Must behave deterministically for ABCI calls | Owns protocol and consensus implementation | Pins exact build and consensus profile |
| Block/evidence consensus limits and validator power | Must not silently reinterpret CometBFT policy | Owns native enforcement and semantics | Approves, distributes and monitors profile |
| RPC/P2P/ABCI endpoint exposure, filesystem permissions, monitoring | Exposes only defined app interfaces | Provides node services | Owns network hardening and operations |
| Private keys, remote signer and anti-double-sign durable anchor | HND account keys are separate from validator consensus keys | Defines validator signer integration | Owns custody, protected trust roots, backup and recovery |

## 7. Required negative and integration tests before implementation closure

Tests should prove rejection, not merely successful startup:

- Alter one HND deterministic parameter on one validator while keeping Genesis unchanged; startup must reject before listener bind.
- Alter each consensus-profile field independently; every validator must reject a mismatch against the trusted profile pin.
- Substitute a different CometBFT binary with the same reported version but a different digest; startup must reject.
- Change the CometBFT source commit/build inputs while retaining the release tag; release verification must reject.
- Replace or alter the signed release manifest, trust root, validator-set artifact or Genesis pin; verification must fail closed.
- Restart with an application store bound to another HND config/profile digest; reject without rewriting or silently migrating it.
- Exercise approved profile/config upgrade activation at the exact declared height; reject early, late, mixed-version and rollback cases.
- Verify that changing local-only endpoints/logging does not alter consensus identity, while unauthorized listener exposure is independently rejected by deployment policy.
- Run at least four independent validators with deliberately divergent HND config, CometBFT profile, binary digest and validator-set inputs; prove each mismatch is rejected before signing and that matching nodes converge.
- Preserve signer anti-double-sign and recovery tests, but do not treat their success as proof of HND config/profile binding.

## 8. Decision register and open owner approvals

| Decision | Recommendation | Status |
|---|---|---|
| Separate HND app-config digest from CometBFT profile digest | Required | Proposed; owner approval pending |
| Pin exact CometBFT source commit and binary digest | Required | Proposed; expected commit/artifact not yet approved |
| Define complete v0.40.0 consensus-profile field classification | Required before profile freeze | Pending source-schema review |
| Define validator-set artifact and activation semantics | Required before public network | Pending governance decision |
| Bind both digests into HND Genesis and durable store | Required | Proposed; source implementation not authorized |
| Signed release manifest / offline trust root | Select and document one trust model | Pending owner decision |
| Choose numeric limits, timeouts, block/evidence values or validator power | No values selected by this audit | Deferred; evidence and owner decision required |

## 9. Release gate

Until the above controls are implemented, tested across independent validators, reviewed, and approved, the project must not claim a fully pinned consensus profile or fail-closed production startup. Existing disposable CI integration evidence is meaningful engineering progress, but it does not establish production key custody, trusted artifact provenance, complete profile identity, or public-network readiness.

**No source or test changes were made by this audit. No launch, issuance, production-signing, or exchange-readiness approval is granted.**
