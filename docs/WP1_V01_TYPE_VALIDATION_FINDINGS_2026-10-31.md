# HND v0.1 — Type-validation exposure findings

**Date:** 2026-10-31  
**Workstream:** WP1 — protocol and security design review  
**Status:** Diagnostic findings recorded; no v0.1 source changes made.

## Scope and provenance

The current `phase-0.2-planning` branch was reviewed at commit
`6148c6737de72f2ade8a69ee2b8ceb4844df8e65`. The GitHub file response for
`hnd_prototype.py` identified blob
`0e5b702364fc6fe5376cda276b0fa993eae2eaba`.

The diagnostic suite was executed locally against the recovered v0.1 source
copy (SHA-256:
`e25f61aad7fe7881458b1210779c14f2cfbfb7340b9af7ca6b92b6e3ffd7d601`).
The relevant validation expressions in that copy were compared with the
branch source retrieved for this review. This was a local run, not GitHub
Actions and not an independent security audit.

## Findings confirmed by diagnostic tests

1. **Boolean amount is accepted.** `isinstance(True, int)` is true in Python.
   A correctly signed transaction with `amount=True` passes validation and
   transfers one unit. The total supply remains unchanged, but the input type
   violates the intended integer-only transaction schema.
2. **Boolean nonce can be accepted.** When the account nonce is integer `1`,
   a transaction with `nonce=True` passes because Python equality treats
   `True == 1` as true.
3. **Floating-point nonce can be accepted.** When the account nonce is integer
   `1`, `nonce=1.0` also passes because `1.0 == 1` is true.
4. **Control cases behave as expected.** Non-integer amount values such as
   `1.0`, `"1"`, `None`, zero and negative one are rejected by the current
   amount check. A string nonce `"1"` is rejected when the account nonce is 1.

## Test results

| Suite | Result | Interpretation |
|---|---:|---|
| New v0.1 type-validation exposure suite | 5 passed / 5 | Three tests intentionally demonstrate permissive acceptance; two are control cases. |
| Existing v0.1 baseline suite | 12 passed / 12 | Existing baseline behavior remained intact on the local recovered copy. |

Run the diagnostic suite from the repository root with:

```bash
python diagnostics/test_v01_type_validation_exposure.py
```

These are **characterization/exposure tests**, not security conformance tests.
Their passing result means the known weakness is reproducible. Do not treat a
green diagnostic run as a security approval, and do not add these assertions to
a release gate as if they represented acceptable protocol behavior.

## Recommended v0.2 correction — not yet implemented

- Require `type(amount) is int`, then enforce an explicitly specified positive
  maximum amount in protocol atomic units.
- Require `type(nonce) is int`, then enforce a specified non-negative range.
- Add negative conformance tests that require bool and float values to be
  rejected before signature/state mutation.
- Keep the v0.1 source immutable; apply these rules only in the versioned v0.2
  transaction implementation after the transaction envelope and chain identity
  are decided.

## Limitations

No source-code fix, protocol decision, distributed-network test, consensus
implementation, independent audit, or production-readiness claim is included
in this work item. The v0.1 baseline remains a local educational prototype.
