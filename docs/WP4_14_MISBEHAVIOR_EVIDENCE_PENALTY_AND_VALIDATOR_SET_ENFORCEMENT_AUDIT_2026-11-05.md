# HND v0.2 — misbehavior evidence, penalties, and validator-set enforcement audit

**Workstream:** WP4.14 — evidence integrity and validator consequence boundary  
**Branch:** `phase-0.2-planning`  
**Review date:** 2026-11-05  
**Review type:** static source/design/test-evidence review; documentation-only change  
**Scope:** CometBFT v0.40.0 evidence delivery, HND evidence normalization and persistence, duplicate handling, query exposure, validator-set updates, and penalty semantics.

## 1. Executive finding

HND currently implements a deterministic, append-only **audit journal** for CometBFT-supplied misbehavior summaries. The journal is committed with HND application state, included in the application hash, exposed through a read-only `/evidence` query, and restored from the durable application store.

The pinned CometBFT evidence pipeline is separately exercised by a four-live-HND-application P2P equivocation integration design/report. That integration reports that conflicting signed prevotes were injected through the real P2P VoteChannel, CometBFT formed and committed duplicate-vote evidence, and the corresponding ABCI summary reached all four HND applications with matching journals and application hashes.

**No automatic penalty or validator removal is implemented.** The HND adapter returns `ResponseFinalizeBlock` with transaction results and app hash only; it does not emit `validator_updates` or any other sanction instruction. The HND v0.2 design has no bonded stake, delegation, unbonding, slashing, appeal, or governance mechanism. An evidence record therefore documents a CometBFT-detected event; it does not by itself reduce a balance, freeze an account, slash stake, or remove a validator.

This is consistent with the existing WP4.10/WP4.11 design boundary: evidence accounting is audit-only, and no economic consequence may be inferred without a separately approved protocol and legal/security review.

## 2. Evidence path and what is actually verified

### 2.1 CometBFT consensus layer

The WP4.10 design identifies the pinned CometBFT v0.40.0 path:
- conflicting signed votes are observed by the consensus/evidence machinery;
- CometBFT forms and validates duplicate-vote evidence;
- the ABCI `RequestFinalizeBlock.misbehavior` field carries a compact `Misbehavior` summary to the application;
- the ABCI summary does **not** carry the full pair of signed votes.

The HND application must therefore not claim that it independently verifies the original signed vote pair. That verification belongs to the CometBFT evidence/consensus layer.

### 2.2 Actual P2P integration evidence

The repository's WP4.11 report records a passing disposable integration against pinned CometBFT v0.40.0:
- a faulty validator sends two conflicting signed prevotes through the actual P2P VoteChannel;
- CometBFT detects the conflict and commits the evidence-bearing block;
- the HND applications receive the corresponding ABCI misbehavior summary;
- four replicas expose the same canonical evidence journal and application hash;
- an HND ABCI application process is restarted and its evidence journal, committed height, and app hash are restored.

The WP4.11 report records marker `HND_WP4_11_P2P_EVIDENCE_REPLICAS_OK`, four replicas, one evidence record, infraction height 2, commit height 3, unchanged balances, and restart verification. It explicitly limits the result: disposable local identities and loopback services; not a general Byzantine-fault proof, production key-custody proof, or independent HND verification of signed votes. It restarts the HND application process, not the corresponding CometBFT consensus process.

This audit relies on that repository-recorded CI/integration evidence; it did not rerun the integration.

## 3. HND normalization and journal checks

Source reviewed:
- `hnd_v02/cometbft_v040_server.py`
- `hnd_v02/abci_app.py`

The ABCI adapter normalizes each protobuf misbehavior item into:
- evidence type;
- validator consensus address;
- validator voting power;
- infraction height;
- canonical Unix timestamp;
- total voting power.

The application `_merge_evidence` path then:
1. accepts only the expected record schema (with optional supplied evidence ID);
2. accepts evidence types 1 and 2 only;
3. requires a 40-character lowercase hexadecimal validator address;
4. requires positive validator and total voting power, with validator power not greater than total power;
5. requires a positive infraction height strictly before the block currently being finalized;
6. requires a canonical seconds/nanoseconds timestamp;
7. derives a deterministic evidence ID from canonicalized `type`, `validator_address`, and infraction `height`;
8. rejects a supplied evidence ID that does not match the derived ID;
9. treats an identical repeat as idempotent and rejects conflicting metadata for an existing ID;
10. returns records in deterministic evidence-ID order.

The journal is included in `_calculate_app_hash`, committed with the pending block, persisted in the application store, revalidated during store load, and exposed by the read-only `/evidence` query.

### 3.1 Important trust boundary

These HND checks validate the **shape, canonical representation, and deterministic identity** of the ABCI summary. They do not reconstruct or cryptographically verify the two signed votes, and they do not independently prove that the address/power tuple belongs to the currently approved validator set.

That is acceptable only while the application treats the CometBFT process as the trusted evidence verifier and the ABCI endpoint remains a protected local interface. The earlier P0 loopback-listener closure limits remote network exposure, but loopback binding is not process authentication: another process with local access to the listener may still be able to submit ABCI requests. Production host isolation and process-level access controls remain necessary.

## 4. Penalty and validator-set enforcement

Reviewed:
- `HNDABCIApplication.finalize_block`
- `HNDCometBFTv040Servicer.FinalizeBlock`
- the current HND v0.2 architecture/evidence design documents.

The adapter's `ResponseFinalizeBlock` populates `tx_results` and `app_hash`; it does not populate `validator_updates` or `consensus_param_updates`. The application has no slashing, stake-locking, validator-jailing, ban, appeal, or governance state transition.

Consequences:
- a CometBFT evidence record does not automatically remove or reduce the voting power of the offending validator;
- the HND application does not impose a balance penalty on the validator's HND account;
- validator membership and consensus voting power remain governed by the CometBFT validator-set configuration and its update mechanism, not by the HND evidence journal;
- the evidence journal is an audit record, not an enforcement engine.

This is **not classified as an implementation defect** under the current transfer-only v0.2 protocol scope, because no staking or slashing policy has been specified. It is a release-scope limitation that must be made explicit in operator and user documentation.

## 5. Existing test coverage and its limits

Repository test evidence reviewed:
- `tests/test_v02_abci_app.py`: evidence journal starts empty; evidence is committed and survives restart; duplicate evidence is idempotent.
- `tests/test_v02_cometbft_v040_adapter.py`: adapter passes a protobuf misbehavior summary into the persisted HND journal and exposes it through `/evidence`.
- `tests/test_v02_four_abci_replica_evidence.py`: four independent ABCI replicas commit identical evidence and application hashes, including a restart leg.
- `scripts/cometbft_v040_hnd_p2p_evidence_integration.py` and WP4.11 report: actual P2P equivocation path into four live HND applications.

The WP4.11 report records the actual P2P integration as passed in its CI evidence. This review did not rerun tests.

Not established by these tests:
- cryptographic verification of original signed votes by HND itself (not possible from the ABCI summary alone);
- rejection of fabricated ABCI evidence from an unauthorized local process;
- a production validator onboarding/key-approval ceremony;
- automatic validator removal, jailing, slashing, or appeals;
- production custody, revocation, or rotation of validator consensus keys;
- a complete Byzantine security proof or production network security certification.

## 6. Risk classification and release requirements

| Area | Current disposition | Required treatment |
|---|---|---|
| CometBFT equivocation detection | Covered by pinned upstream path and repository-recorded P2P integration | Keep CometBFT version pinned; retain the real P2P integration in CI |
| ABCI summary normalization | Implemented with strict schema/canonical checks | Keep negative tests for malformed fields and unsupported types |
| Duplicate evidence | Deterministic ID, idempotent repeat, conflicting metadata rejected | Preserve regression tests |
| Journal persistence/convergence | Included in app hash and durable state; replica integration reported | Preserve restart and four-replica convergence tests |
| Independent HND vote verification | Not implemented; ABCI summary lacks signed vote pair | Do not claim HND independently verifies the vote signatures |
| Unauthorized local evidence injection | Not authenticated at the application layer | Harden host/process isolation; consider authenticated local transport or a trusted private socket boundary before production |
| Economic penalties | Not implemented and not specified | Do not slash, burn, freeze, confiscate, or transfer balances under v0.2 |
| Validator removal/jailing | No HND validator updates emitted | State clearly that evidence logging does not automatically remove a validator |

## 7. Recommended acceptance tests (not run in this review)

1. `EVD-001`: unsupported evidence type is rejected.
2. `EVD-002`: malformed address, zero/negative power, power greater than total, invalid height, and noncanonical timestamp are rejected.
3. `EVD-003`: duplicate evidence in one block yields exactly one journal entry.
4. `EVD-004`: same evidence ID with conflicting metadata fails closed.
5. `EVD-005`: evidence order does not affect canonical journal bytes or app hash.
6. `EVD-006`: journal survives restart and recomputes the same app hash.
7. `EVD-007`: four replicas receiving the same CometBFT evidence converge on identical journal bytes and app hashes.
8. `EVD-008`: real P2P VoteChannel equivocation remains in CI; direct fabricated ABCI summaries are not accepted as a substitute for this integration.
9. `EVD-009`: verify that the ABCI listener is loopback-only and document the local-process trust assumption; test unauthorized remote connection rejection.
10. `EVD-010`: assert the v0.2 response contains no validator updates and that evidence ingestion causes no HND balance mutation, preventing accidental implicit slashing.

## 8. Final disposition

**Evidence audit journal: implemented.**  
**Deterministic duplicate handling and persistence: implemented and covered by repository tests.**  
**Actual P2P equivocation-to-ABCI integration: reported passed in WP4.11 CI evidence, not rerun here.**  
**Automatic penalties or validator removal: not implemented; intentionally outside the current transfer-only v0.2 policy.**  
**Independent cryptographic verification of signed vote pairs inside HND: not implemented and not supported by the ABCI summary payload.**

No source, test, workflow, validator-key, or protocol behavior was changed by this review. No tests were executed as part of this audit. This report is not a security certification, legal opinion, or approval to launch a public network.
