# HND Ledger — WP0 3,000-Transfer Recheck

**Date:** 2026-10-31  
**Scope:** Local reproducibility test against the recovered, integrity-fixed v0.1 implementation.  
**Status:** PASS — local test execution only; not GitHub Actions and not an independent audit.

## Source identity

- Implementation: `hnd_prototype.py`
- GitHub branch: `phase-0.2-planning`
- GitHub source blob: `0e5b702364fc6fe5376cda276b0fa993eae2eaba`
- Local source SHA-256 (file includes final newline): `e25f61aad7fe7881458b1210779c14f2cfbfb7340b9af7ca6b92b6e3ffd7d601`
- The GitHub blob was fetched from the branch and its Git blob hash was independently recomputed from the fetched content; it matches the GitHub blob SHA. The local working copy differs only by a final newline.

## Reproduction environment

- Python: `3.13.5`
- cryptography: `46.0.4`
- Test command:

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
```

## Test design

The test creates ALICE and BOB wallets, allocates 10,000 HND to each by moving the same amount out of GENESIS, then performs 3,000 sequential, signed, one-unit transfers, alternating sender between ALICE and BOB. Each transaction uses the sender's current nonce and is applied through `HNDLedger.apply()`.

Assertions verify:

- all 3,000 transfers are accepted;
- total supply remains exactly 1,000,000 HND;
- `history` and `accepted` each contain 3,000 transaction IDs;
- each wallet nonce advances to 1,500;
- state hash changes and matches a fresh recomputation.

## Results

- 3,000-transfer test: **PASS**
- 12 recovered baseline tests: **PASS**
- 2 accepted/history integrity regression tests: **PASS**
- Total test suite: **15 passed, 0 failed**
- Observed suite runtime: approximately 6.0 seconds
- Final total supply: **1,000,000 HND**
- Rejected transfers: **0**

## Evidence file hashes (SHA-256)

- `hnd_prototype.py`: `e25f61aad7fe7881458b1210779c14f2cfbfb7340b9af7ca6b92b6e3ffd7d601`
- `tests/test_hnd.py`: `b1cb58b6774e26ad0a6f52f8a74dc8258b3bf5000ed3bda390430513a4ad99ef`
- `tests/test_3000_transfers.py`: `fb854ebc5825b8e4f52fda378c1a6b630bd5938671a400d2f3ac5e21d8f2df6c`

## Interpretation and limitations

This result reproduces a sequential transfer workload in one local process. It does not test a peer-to-peer network, concurrent distributed execution, network partitions, Byzantine behavior, validator incentives, production key management, or throughput under adversarial load. It is not an independent security audit, production approval, legal authorization, or permission to issue or trade a token.
