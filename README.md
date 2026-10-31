# HND Ledger — recovered v0.1 baseline

This branch restores the HND v0.1 local educational prototype and its evidence.

- `hnd_prototype.py`: canonical integrity-fixed implementation.
- `archive/v0.1/hnd_prototype_pre_integrity_fix.py`: earlier implementation preserved for traceability.
- `test_hnd.py`: original 12-test suite.
- `docs/`: technical specification and security test report.

Run locally with Python 3.10+:

```bash
python -m pip install -r requirements.txt
python -m unittest -v test_hnd.py
```

The archived reports record the historical 3,000-transfer run; that run is not claimed as repeated here. HND v0.1 is a local educational prototype, not production software or an approved financial product. No public deployment, real funds, token sale, exchange listing, or payment integration is authorized.
