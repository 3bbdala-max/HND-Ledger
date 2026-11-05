# WP4.14 — Strict Genesis JSON Parsing: Test Traceability and Change Sequence

**Date:** 2026-11-05  
**Branch:** `phase-0.2-planning`  
**Baseline head:** `a6785fc6734d5022a83a4a06b8974f66e99eb795`  
**Status:** Planning artifact only; no source or test files changed; no tests run.

## 1. Purpose

This note converts the P1 static review into an implementation-ready sequence and an auditable acceptance matrix. It does not authorize or perform source changes.

## 2. Proposed module contract

A dependency-neutral helper should expose one narrow operation that accepts raw bytes and returns a decoded JSON value, with caller-selected top-level type validation where appropriate.

Required behavior:

- Strict UTF-8 decoding; invalid byte sequences fail.
- UTF-8 BOM is rejected explicitly.
- Duplicate object member names fail at every nesting level.
- JSON constants `NaN`, `Infinity`, and `-Infinity` fail.
- Native integer parsing is retained; no float intermediary.
- No Unicode normalization, key rewriting, or implicit canonicalization.
- Parser exceptions are wrapped into stable, non-sensitive errors at the CLI/ABCI boundary.

The helper must not import the CLI server or ABCI application modules. This avoids a dependency cycle and permits direct unit testing.

## 3. File-by-file change sequence

1. **Add helper module** in a dependency-neutral location after checking package layout and import conventions. Define duplicate-key and non-finite-constant rejection there.
2. **Add helper unit tests** for nested duplicates, constants, UTF-8, BOM, and exact integer preservation.
3. **Update CLI manifest loading** in `hnd_v02/cometbft_v040_server.py` to read bytes, call the helper, require a top-level object, and preserve existing schema/hash validation.
4. **Update ABCI decoding** in `hnd_v02/abci_app.py` to call the helper while retaining the existing exact canonical-byte equality check and top-level object requirement.
5. **Add integration/regression tests** for CLI and ABCI behavior, including unchanged valid Genesis hash vectors.
6. Run focused tests, then the repository's configured CI workflow. Record commit SHA, workflow run ID, job conclusions, and any skipped tests.

Only one path may be updated at a time. Fetch the current blob SHA immediately before every update to an existing file. Do not modify workflow files or push to `main`.

## 4. Acceptance traceability

| ID | Input / condition | Expected result | Primary layer |
|---|---|---|---|
| GENJSON-01 | Duplicate top-level key | Reject | Shared helper / CLI |
| GENJSON-02 | Duplicate key inside allocation object | Reject | Shared helper / CLI |
| GENJSON-03 | Duplicate key in unrelated nested object | Reject | Shared helper |
| GENJSON-04 | Existing valid Genesis manifest | Accept; manifest hash unchanged | CLI + Genesis regression |
| GENJSON-05 | `NaN` | Reject | Shared helper |
| GENJSON-06 | `Infinity` and `-Infinity` | Reject | Shared helper |
| GENJSON-07 | Invalid UTF-8 byte sequence | Reject without replacement decoding | Shared helper |
| GENJSON-08 | UTF-8 BOM prefix | Reject with documented stable error | Shared helper |
| GENJSON-09 | Array or scalar where object required | Reject | CLI / ABCI boundary |
| GENJSON-10 | Canonical ABCI object bytes | Accept unchanged | ABCI |
| GENJSON-11 | Duplicate-key or non-canonical ABCI bytes | Reject | ABCI |
| GENJSON-12 | Error path with malformed manifest | Do not echo raw document or secret values | CLI |

Additional numeric regression: a large valid JSON integer must remain an exact Python integer and must not be rounded through floating-point conversion.

## 5. Resource-limit decision

The earlier review listed an input-size bound as a possible safeguard, but no defensible numeric limit has yet been established from repository fixtures, expected production Genesis size, or a consensus-level resource policy.

Therefore, **do not introduce an arbitrary byte limit in this narrow patch**. First measure the largest supported Genesis fixture and identify whether a limit is merely a local operational safeguard or a network-validity rule. If it changes which Genesis documents nodes accept, specify it through the coordinated Config-v1 process rather than silently applying node-local policy.

## 6. Compatibility invariants

- Existing valid Genesis manifests retain identical canonical hashes.
- No change to Genesis schema, domain separator, canonical JSON encoding, allocation semantics, transaction rules, or ABCI state envelope.
- Duplicate keys become explicitly invalid rather than relying on canonical-byte mismatch as an indirect defense.
- No automatic rewriting or repair of malformed Genesis files.
- No change to gRPC/P2P security scope.

## 7. Completion evidence required

The implementation may be marked complete only when all of the following are recorded:

- [ ] Shared helper and unit tests committed.
- [ ] CLI and ABCI both use the helper.
- [ ] GENJSON-01 through GENJSON-12 pass.
- [ ] Existing Genesis hash vectors remain unchanged.
- [ ] Focused test command and result recorded.
- [ ] CI workflow run ID and all relevant job conclusions recorded.
- [ ] Final source diff reviewed for scope creep and workflow changes.

**Current gate:** planning is complete enough to implement, but source/test modification remains pending explicit authorization. No tests were run for this planning note.
