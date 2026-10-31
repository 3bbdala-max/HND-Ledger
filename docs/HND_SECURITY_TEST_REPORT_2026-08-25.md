# HND v0.1 — Security & Integrity Test Report
Date: 2026-08-25

## Scope
Local educational prototype only. Tests cover transaction validation, Ed25519 signatures, replay/nonce handling, state persistence, tamper detection, malformed inputs, deterministic quorum behavior, and a 3,000-transfer sequential run.

## Results
- Valid transfer: PASS
- Replay rejection: PASS
- Wrong nonce: PASS
- Insufficient balance: PASS
- Invalid signature: PASS
- Modified transaction payload: PASS
- Self-transfer: PASS
- Zero/invalid amount: PASS
- Restart/recovery: PASS
- Balance/state tamper detection: PASS
- Accepted-set tamper detection: PASS after integrity fix
- Malformed transaction fuzz set: PASS
- Consensus quorum: PASS
- No-quorum rejection: PASS
- Conflicting-quorum rejection: PASS
- 3,000 sequential transfers: PASS
- Final total supply: 1,000,000 HND
- Recovery after 3,000 transfers: PASS

## Fix applied
The state hash previously covered accounts and history but omitted the `accepted` transaction set. The implementation was corrected so the state hash includes `accepted`, and loading also verifies that `accepted` matches the transaction history.

## Gate status
Prototype security/integrity gate: PASS for the tested v0.1 scope.

This does not constitute a production security audit or Byzantine-fault-tolerant consensus validation. Public deployment, real-money use, token sale, exchange listing, or payment integration remains blocked pending independent security review, legal review in the target jurisdiction, threat modeling, and substantially more rigorous consensus work.