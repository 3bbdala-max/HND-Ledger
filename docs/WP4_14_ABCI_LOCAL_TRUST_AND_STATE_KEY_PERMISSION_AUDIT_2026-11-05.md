# HND v0.2 — ABCI local trust boundary and state/key permission audit

**Workstream:** WP4.14 — local ABCI caller trust, durable state permissions, and validator key handling  
**Review date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Review type:** static source review; documentation-only  
**Scope:** insecure loopback ABCI gRPC listener, caller authentication, HND state-file creation, manifest access, and disposable CometBFT validator key handling.

## 1. Executive disposition

The repository correctly prevents the insecure ABCI gRPC server from binding to non-loopback addresses. That closes accidental LAN/public exposure through this listener, but **loopback is not caller authentication**. Any process that can reach the local port can attempt ABCI methods, including state-transition methods. The current transport uses gRPC `add_insecure_port` and has no TLS, client identity, authorization interceptor, or per-method access policy.

The HND state writer uses `tempfile.NamedTemporaryFile` in the state directory, writes and fsyncs the temporary file, atomically replaces the state path, and fsyncs the parent directory on POSIX. The temporary file's secure default creation mode is a useful protection, but the application does not verify or enforce the parent directory's owner/mode, does not validate existing state-file permissions, and does not document an operator-enforced permission contract in the reviewed startup path.

The four-validator Genesis preflight creates disposable CometBFT homes under a temporary directory and reports that private keys remain there. It checks key schema and presence, unique P2P node IDs, unique consensus addresses, and Go-side Genesis validation. It does **not** assert filesystem permissions/ownership for `priv_validator_key.json` or `node_key.json`, nor does it create/pin production validator keys. These are disposable test identities, not production custody evidence.

## 2. ABCI listener: what is closed and what remains open

Source: `hnd_v02/cometbft_v040_server.py`.

Implemented:
- default listener is `127.0.0.1:26658`;
- `_validate_loopback_bind_address` accepts loopback IP literals only, including bracketed IPv6 syntax;
- hostnames, wildcard, LAN, and public addresses are rejected;
- validation occurs before gRPC server creation/bind;
- server binds using `add_insecure_port`.

The repository's P0 closure report records passing CI coverage for accepted and rejected bind-address classes. That evidence closes the specific non-loopback binding defect.

Not implemented:
- TLS or mutual TLS;
- client certificates or authenticated local peer identity;
- authorization interceptors or method-level ACLs;
- Unix-domain socket peer credential checks;
- authentication for `FinalizeBlock`, `Commit`, `InitChain`, or other stateful ABCI methods.

**Security consequence:** a local untrusted process with access to the loopback port can attempt to call ABCI methods. In particular, the HND application trusts the CometBFT ABCI caller to supply decided block data and validated evidence summaries. The loopback bind guard alone does not establish that the caller is the intended CometBFT process.

This is a production deployment blocker unless the host/process trust boundary is explicitly accepted and enforced, or the transport is upgraded with authenticated local IPC / mutually authenticated transport and authorization.

## 3. HND state-file permissions and integrity

Source: `hnd_v02/abci_app.py`.

Positive controls:
- the state directory must already exist and be a directory;
- recovery mode refuses to silently create a fresh state when the expected state file is absent;
- the writer creates a temporary file in the same directory, writes and flushes it, fsyncs the file, atomically replaces the destination, then fsyncs the directory on POSIX;
- the loader rejects duplicate JSON keys and non-finite constants, checks the schema and recomputes the store hash;
- the store hash is an unkeyed SHA-256 integrity checksum, not an authentication MAC.

Permission gaps:
- startup does not check the state directory's owner, group, or mode;
- startup does not reject a state directory writable by group/other users;
- startup does not reject an existing state file with overly broad permissions;
- no explicit `chmod`/permission assertion is performed after atomic replacement;
- the checksum detects accidental or unsophisticated modification but is not a secret-key MAC and cannot protect against an attacker able to rewrite the file and recompute the hash.

The use of `NamedTemporaryFile` ordinarily creates a restrictive file (commonly mode 0600 on POSIX), but this review does not treat that library default as a complete permission policy for every platform or deployment. The containing directory and any pre-existing file remain operator-controlled attack surfaces.

## 4. Manifest and configuration handling

Source: `hnd_v02/cometbft_v040_server.py`.

The CLI reads `--manifest` using ordinary file open and `json.load`, then checks the manifest hash against the separately supplied `--genesis-hash`, and checks network ID against `--network-id`.

This verifies content consistency, not provenance or filesystem access control. The startup path does not validate the manifest file owner/mode, does not obtain the expected hash from an independently authenticated trust store, and does not bind the process-supplied `--max-amount` to the manifest (a separate previously documented protocol-configuration gap).

Production requirements:
- provision manifest and pinned hash through a controlled, authenticated release process;
- make configuration files read-only to the service identity;
- protect parent directories against untrusted writes;
- ensure the service account cannot modify executable code or release artifacts.

## 5. CometBFT validator key files in preflight

Source: `scripts/cometbft_v040_four_validator_genesis_preflight.py`.

The preflight:
- creates four CometBFT homes beneath `TemporaryDirectory`;
- runs CometBFT `init` for each;
- reads `config/priv_validator_key.json`;
- checks expected public-key object schema and non-empty address/public-key value;
- obtains and checks unique P2P node IDs;
- checks unique consensus addresses;
- builds one shared Genesis and copies byte-identical Genesis content to all four homes;
- validates the Genesis with the pinned Go helper;
- reports that private keys remain inside the temporary directory and does not start nodes.

It does not:
- inspect file mode, owner, or group for validator private keys;
- inspect `node_key.json` permissions;
- assert that validator and node keys are stored separately with independent access controls;
- pin a production-approved four-key set;
- provide HSM/remote-signer custody, backup, rotation, revocation, or compromise recovery.

The temporary directory is appropriate for disposable CI/preflight identities, not a production key-management design. Temporary-directory cleanup is not equivalent to cryptographic erasure on SSDs, snapshots, CI artifacts, or host backups.

## 6. Required security controls before production

1. **ABCI caller boundary:** choose either authenticated local IPC with peer-credential verification and method authorization, or mutually authenticated TLS with certificate identity pinning and authorization. Do not expose the current insecure gRPC endpoint beyond a trusted isolated host boundary.
2. **Service isolation:** run CometBFT and HND ABCI under dedicated least-privilege identities; restrict loopback access using host policy where available; ensure unrelated local users/processes cannot access the service.
3. **State directory:** require a dedicated directory owned by the HND service identity, with no group/other write permission (recommended POSIX directory mode 0700); reject symlinks and unsafe path components where applicable.
4. **State file:** enforce owner and restrictive mode (recommended POSIX 0600) at creation and validate it on recovery; add tests for permissive file and directory modes.
5. **Manifest/config:** verify trusted owner and read-only permissions; bind the approved Genesis hash and all consensus-critical application configuration to a signed release profile.
6. **Validator consensus keys:** use a documented production custody mechanism, distinct from P2P node identity keys and HND account keys; define generation, backup, access, rotation, revocation, and compromise response.
7. **CI hygiene:** ensure temporary key homes, manifests, state files, logs, and generated secrets are not uploaded as workflow artifacts or printed in logs; retain cleanup checks on failure paths.

## 7. Recommended tests (not run in this review)

- `SEC-ABCI-001`: a non-loopback listener address is rejected before bind (existing coverage; retain).
- `SEC-ABCI-002`: verify unauthenticated local client can currently reach the listener in a controlled test, documenting the trust gap; after hardening, assert rejection.
- `SEC-ABCI-003`: unauthorized peer cannot invoke `FinalizeBlock` or `Commit` after authenticated transport is implemented.
- `SEC-STATE-001`: reject a state directory with group/other write permissions.
- `SEC-STATE-002`: reject a state file with group/other access or incorrect owner.
- `SEC-STATE-003`: verify newly created state file has restrictive mode after first Commit and after atomic replacement.
- `SEC-STATE-004`: verify recovery rejects symlinked or unsafe state paths according to the chosen platform policy.
- `SEC-CONFIG-001`: reject writable/untrusted manifest and configuration paths in production mode.
- `SEC-KEY-001`: assert disposable validator private-key and node-key files have restrictive modes on supported CI platforms.
- `SEC-KEY-002`: verify no private key material appears in logs, test output, CI artifacts, or published Genesis.
- `SEC-KEY-003`: verify production validator keys are pinned to an approved manifest without storing private keys in that manifest.

## 8. Final gate

**Closed:** insecure ABCI listener cannot bind to non-loopback addresses; regression coverage and CI closure evidence are documented.

**Not closed:** local caller authentication/authorization; state directory and existing state-file permission enforcement; production manifest provenance; production validator key custody and permission verification.

**Disposition:** production network launch remains blocked until these host/process trust and key-custody controls are implemented, tested, and documented. The current code is suitable only within its explicitly limited trusted-local test/development boundary.

No source, test, workflow, key, or runtime configuration was changed by this review. No tests were executed during this audit. This report is not a security certification or production launch approval.
