# HND WP4.14 — InitChain and consensus-parameter update boundary audit

**Date:** 2026-11-05  
**Repository:** `3bbdala-max/HND-Ledger`  
**Branch:** `phase-0.2-planning`  
**HND baseline reviewed:** `aadf4e2f333031d02c03b98b3bff79f8bd3110a9`  
**CometBFT source:** tag `v0.40.0`  
**Status:** Static source review and protocol-boundary audit only. Documentation-only change; no code/tests/workflows changed and no runtime tests executed.

## 1. Executive conclusion

The current HND ABCI adapter does **not** emit consensus-parameter updates from either lifecycle response:

- `InitChain` returns only the initial HND `app_hash`.
- `FinalizeBlock` returns transaction results and HND `app_hash`; it leaves `consensus_param_updates` unset.

Therefore, the inspected HND implementation has no active application path that requests CometBFT consensus-parameter changes at initialization or during block execution.

However, there is a distinct validation gap: HND's `InitChain` handler checks the request's `chain_id` and HND `app_state_bytes`, but does not independently compare the request's CometBFT `consensus_params`, initial validator set, or initial height against an approved CometBFT release profile. The four-validator Genesis preflight checks validator identity/count and byte-identical Genesis copies, but not a complete approved consensus-parameter object.

This means the correct conclusion is **not** "CometBFT parameters are immutable." The accurate conclusion is: the present HND adapter does not request updates, while the application does not yet enforce the full incoming CometBFT Genesis parameter/validator profile at its ABCI boundary.

## 2. CometBFT v0.40.0 protocol evidence

### 2.1 InitChain request and response

Source: `proto/tendermint/abci/types.proto` at tag `v0.40.0`  
`https://github.com/cometbft/cometbft/blob/v0.40.0/proto/tendermint/abci/types.proto`

The request includes:
- `chain_id`
- `consensus_params`
- `validators`
- `app_state_bytes`
- `initial_height`

The response schema includes optional:
- `consensus_params`
- `validators`
- `app_hash`

The tagged ABCI++ methods specification describes the request's consensus parameters as the initial consensus-critical parameters and the response's consensus parameters as optional initial consensus-critical parameters. It also explains that the response validator list, when non-empty, can determine the initial validator set instead of the request list.

Source: `spec/abci/abci++_methods.md` at tag `v0.40.0`  
`https://github.com/cometbft/cometbft/blob/v0.40.0/spec/abci/abci++_methods.md`

### 2.2 FinalizeBlock update channel

The v0.40.0 `ResponseFinalizeBlock` protobuf contains `consensus_param_updates` (field 4), described as updates to consensus parameters, if any.

CometBFT's `state/execution.go` consumes a non-nil `abciResponse.ConsensusParamUpdates`:
1. derives `nextParams` from the existing state parameters;
2. validates the resulting parameters with `ValidateBasic()`;
3. validates the transition with `ValidateUpdate(..., header.Height)`;
4. stores the resulting parameters in the next CometBFT state;
5. marks the effective change height as `header.Height + 1`.

Source:
- `https://github.com/cometbft/cometbft/blob/v0.40.0/state/execution.go`
- `https://github.com/cometbft/cometbft/blob/v0.40.0/proto/tendermint/abci/types.proto`

This is an explicit runtime update channel. A future HND change that starts returning `consensus_param_updates` would therefore be a consensus-critical protocol change and must not be introduced as an incidental refactor or local node configuration edit.

## 3. HND implementation evidence

### 3.1 HND InitChain behavior

File: `hnd_v02/cometbft_v040_server.py`

The adapter calls:

```python
self.application.init_chain(
    chain_id=request.chain_id,
    app_state_bytes=request.app_state_bytes,
)
```

It does not pass `request.consensus_params`, `request.validators`, or `request.initial_height` into the application. It returns:

```python
ResponseInitChain(
    app_hash=bytes.fromhex(self.application.committed_state_hash)
)
```

File: `hnd_v02/abci_app.py`

The application validates:
- request chain ID equals HND `config.network_id`;
- HND application Genesis payload has exactly `genesis_hash` and `manifest`;
- the supplied HND manifest hash matches the independently supplied expected hash;
- the supplied manifest equals the configured manifest.

It then writes the initial application state at HND height zero. It does not validate CometBFT consensus parameters, initial validator records, or request initial height.

### 3.2 HND FinalizeBlock behavior

File: `hnd_v02/cometbft_v040_server.py`

The adapter maps HND's result into:
- `tx_results`
- `app_hash`

It does not set `consensus_param_updates` or `validator_updates`.

File: `hnd_v02/abci_app.py`

The application:
- requires initialization;
- requires the next sequential height;
- executes transactions deterministically against temporary candidate state;
- stages the candidate and app hash as pending;
- persists only when `Commit` is called.

There is no application method or configuration path in the inspected FinalizeBlock flow that creates a CometBFT consensus-parameter update.

### 3.3 Genesis preflight boundary

File: `scripts/cometbft_v040_four_validator_genesis_preflight.py`

The preflight sets:
- `chain_id`
- `initial_height`
- `validators`
- `app_hash`
- HND `app_state`

It then serializes one Genesis document, copies it to four homes, verifies byte identity, and invokes the CometBFT Go helper to parse/validate it and verify validator public-key/address pairings.

It does not explicitly compare every Genesis `consensus_params` field against an approved, versioned HND profile. Existing Genesis defaults are retained from the generated CometBFT home.

## 4. Risk classification

| Area | Current evidence | Disposition |
|---|---|---|
| HND requests InitChain consensus-param override | No; response only sets app_hash | No active override path observed |
| HND requests FinalizeBlock consensus-param updates | No; response only sets tx_results and app_hash | No active runtime update path observed |
| HND validates incoming InitChain consensus params | No | Profile-enforcement gap |
| HND validates incoming initial validator set at ABCI boundary | No | Profile-enforcement gap; external preflight has partial checks |
| HND binds CometBFT consensus params into HND manifest hash | No | Separate CometBFT Genesis digest/profile required |
| CometBFT supports runtime parameter updates | Yes; FinalizeBlock response field and state transition path | Any future use needs explicit protocol governance and tests |
| Local TOML timeout/mempool/P2P settings are Genesis consensus params | No | Keep service profile separate |

## 5. Required safeguards before production

1. Define an explicit CometBFT v0.40.0 profile containing the full consensus parameter object, initial validator set, chain ID, initial height, and approved binary identity.
2. Extend the ABCI adapter/application initialization boundary to receive and validate the full InitChain request fields, not only chain ID and HND app state.
3. Compare all incoming consensus parameters and validator records with the independently pinned release profile. Reject any missing, unknown, or mismatched field.
4. Keep `ResponseInitChain.consensus_params` and `ResponseInitChain.validators` unset unless an explicitly approved initialization policy requires them.
5. Add an explicit invariant test that the HND `FinalizeBlock` response has no consensus-parameter updates and no validator updates in the v0.2 transfer-only protocol.
6. Add adapter-level negative tests for altered block limits, evidence limits, validator key types, vote-extension height, authority field, initial height, and validator set.
7. Add a source-level/behavioral integration test showing that a deliberately supplied FinalizeBlock parameter update is either rejected by HND policy before response construction or is handled only by a separately approved upgrade mechanism.
8. Treat any future parameter update as a versioned protocol upgrade with a defined activation height, cross-validator agreement, recovery behavior, and release artifact—not as an operator-editable TOML setting.

## 6. Proposed acceptance tests (not run)

| ID | Scenario | Expected result |
|---|---|---|
| CMT040-INIT01 | InitChain receives the approved full consensus params | Initialization succeeds |
| CMT040-INIT02 | InitChain block max bytes differs from approved profile | Initialization fails closed |
| CMT040-INIT03 | InitChain evidence parameters differ | Initialization fails closed |
| CMT040-INIT04 | InitChain validator key types differ | Initialization fails closed |
| CMT040-INIT05 | InitChain vote-extension activation height differs | Initialization fails closed |
| CMT040-INIT06 | InitChain initial height differs from approved profile | Initialization fails closed |
| CMT040-INIT07 | InitChain validator list differs in key, address, power, or order policy | Initialization fails closed |
| CMT040-INIT08 | HND InitChain response is inspected | No unapproved consensus_params or validators override is emitted |
| CMT040-FINAL01 | Normal HND FinalizeBlock response | `consensus_param_updates` absent; `validator_updates` empty |
| CMT040-FINAL02 | Attempt to introduce an unapproved parameter update path | Rejected by policy; no block-level update emitted |
| CMT040-FINAL03 | All four validators use same approved Genesis profile | Profile digest agrees before node launch |
| CMT040-FINAL04 | One validator has a modified Genesis consensus parameter | Preflight rejects before network start |

## 7. Scope and disposition

This is a static review of the current HND Python adapter/application and the CometBFT v0.40.0 protocol/state source. No code or tests were modified or executed.

**Disposition:** no active HND-generated consensus-parameter update path was found in the inspected ABCI responses. Production remains blocked by the missing incoming InitChain profile validation and by the absence of a complete explicit CometBFT Genesis profile verifier. The next implementation change should be a separately reviewed, opt-in code/test change after explicit authorization; this report itself makes no such code change.
