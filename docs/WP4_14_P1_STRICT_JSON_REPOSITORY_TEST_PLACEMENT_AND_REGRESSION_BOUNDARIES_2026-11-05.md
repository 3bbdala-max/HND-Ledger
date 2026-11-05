# WP4.14 — P1 Strict JSON Parsing: Repository Test Placement and Regression Boundaries

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Baseline head:** `5b56c94eac6e83232e912b8d6d965839b0c70bae`  
**Status:** Repository inspection and test-placement plan only; no source/test changes; no tests run.

## 1. Repository layout confirmed

The current branch contains these relevant modules and tests:

- `hnd_v02/__init__.py`: minimal package initializer.
- `hnd_v02/cometbft_v040_server.py`: CLI entry point; currently opens the manifest as UTF-8 text and calls `json.load` at lines 319–320.
- `hnd_v02/abci_app.py`: application-state decoder and canonical-byte validation.
- `hnd_v02/genesis.py`: Genesis schema validation and manifest hashing.
- `hnd_v02/transaction.py`: canonical JSON encoding.
- `tests/test_v02_genesis_manifest.py`: published Genesis fixture and stable hash regression.
- `tests/test_v02_abci_app.py`: ABCI lifecycle, canonical application-state rejection, and malformed transaction coverage.
- `tests/test_v02_cometbft_v040_adapter.py`: adapter and gRPC listener tests.

The existing Genesis fixture test loads `vectors/v0.2-genesis-devnet-example.json`, validates the manifest, and asserts its published hash. This is the compatibility anchor; its expected hash must not be regenerated merely to satisfy a parser change.

## 2. Recommended test placement

### A. New shared-helper test module

Add `tests/test_v02_strict_json.py` for behavior that must be identical regardless of caller:

- duplicate keys at root, nested object, and deeper unrelated object;
- non-finite constants;
- strict invalid-UTF-8 rejection;
- BOM rejection;
- large integer exactness;
- ordinary valid JSON decoding.

These tests should exercise raw bytes, not only Python dictionaries. A dictionary cannot represent duplicate JSON member names and therefore cannot prove duplicate-key rejection.

### B. Genesis CLI integration tests

Extend `tests/test_v02_cometbft_v040_adapter.py` or add a dedicated CLI test module for `main(argv)`:

- valid manifest plus matching independently pinned hash proceeds past parsing;
- duplicate-key manifest fails before server startup;
- malformed UTF-8 and BOM fail with concise parser errors;
- top-level array/scalar fails as an invalid manifest object;
- captured stderr/error text does not contain the raw manifest payload.

Use a temporary manifest file and patch the server-start function so tests never bind a real socket. Assert the parser's failure path and that startup was not invoked.

### C. ABCI application-state regression tests

Extend `tests/test_v02_abci_app.py` near the existing `test_init_chain_rejects_noncanonical_app_state_bytes` test:

- canonical unique-key bytes still initialize successfully;
- duplicate-key bytes fail explicitly;
- whitespace/key-order variants remain rejected by the existing canonical-byte rule;
- NaN/Infinity and invalid UTF-8 fail;
- a malformed payload does not create or mutate the durable state file.

Keep the current canonical-byte equality check. The shared helper is an additional explicit parse-time defense, not a replacement for byte equality.

### D. Genesis hash compatibility

Keep `tests/test_v02_genesis_manifest.py` as the published-vector regression. Add a test only if needed to demonstrate that parsing the fixture bytes through the helper produces the same manifest object and exact existing hash. Do not duplicate all helper cases here.

## 3. Important distinction: raw bytes versus parsed objects

The parser-hardening tests must preserve the original JSON byte sequence until strict decoding is complete. Avoid test helpers that call `json.loads` before invoking the strict decoder; that would erase duplicate keys and make the test meaningless.

For CLI tests, write the malformed byte sequence directly with `Path.write_bytes`. For ABCI tests, pass the malformed byte sequence directly to `init_chain(app_state_bytes=...)`.

## 4. Stable failure assertions

Tests should assert stable public error categories or stable short message fragments, not the full implementation-specific Python exception text. In particular:

- do not expose raw JSON, account data, or key material in CLI errors;
- do not rely on interpreter-version-specific wording from `json.JSONDecodeError`;
- distinguish invalid UTF-8, duplicate member, invalid constant, and wrong top-level type internally if the public API can safely preserve those categories.

## 5. Change and test order

1. Confirm the package's import style and add the dependency-neutral helper.
2. Add and run helper-only tests.
3. Integrate the CLI and run CLI-specific tests.
4. Integrate ABCI and run ABCI-specific tests.
5. Run Genesis fixture/hash regression.
6. Run the full configured CI workflow and inspect every relevant job result.
7. Review the final diff for accidental schema, hash, state-envelope, network, or workflow changes.

This order localizes failures and prevents a CLI issue from being confused with an ABCI canonicalization regression.

## 6. Preconditions before implementation

- Explicit authorization for source and test edits remains required.
- Fetch the latest blob SHA for each existing path immediately before editing it.
- Create the helper as a new file only after checking the path does not already exist.
- Never update multiple copies of the same path concurrently.
- Do not modify GitHub Actions workflows.
- Do not write to `main`.

**Current result:** repository paths and regression locations have been inspected. This is not implementation evidence; no source was changed and no test was run.
