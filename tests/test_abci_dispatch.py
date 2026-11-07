import base64
import json

import cbor2

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.abci_dispatch import ABCIDispatcher
from hnd_ledger.application import LedgerApplication
from hnd_ledger.chain import LocalChain
from hnd_ledger.protocol import account_id, create_transaction, encode_transaction
from hnd_ledger.state import LedgerState


def _key_account(key):
    return account_id(key.public_key().public_bytes_raw())


def _dispatcher(tmp_path, *, funded=True):
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    alice_id = _key_account(alice)
    state = LedgerState(
        balances={alice_id: 100} if funded else {},
        supply_cap=100 if funded else 1_000_000 * 10**8,
    )
    chain = LocalChain(tmp_path / "abci.sqlite", state)
    return ABCIDispatcher(LedgerApplication(chain)), chain, alice, bob, alice_id


def _b64(raw):
    return base64.b64encode(raw).decode("ascii")


def _genesis_bytes(value):
    payload = cbor2.dumps(value, canonical=True)
    return json.dumps(
        {"version": 2, "payload": base64.b64encode(payload).decode("ascii")},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def test_info_and_init_chain_are_explicit(tmp_path):
    dispatcher, chain, *_ = _dispatcher(tmp_path, funded=False)
    info = dispatcher("Info", {})
    assert info["version"] == "0.2.0"
    assert info["last_block_height"] == 0
    assert base64.b64decode(info["last_block_app_hash"]) == b""

    result = dispatcher("InitChain", {"chain_id": "HND-LOCAL-V2"})
    assert result == {"validators": []}
    assert dispatcher("InitChain", {"chain_id": "HND-LOCAL-V2"}) == result
    chain.close()


def test_init_chain_rejects_wrong_chain_or_allocations(tmp_path):
    dispatcher, chain, *_ = _dispatcher(tmp_path, funded=False)
    try:
        dispatcher("InitChain", {"chain_id": "other"})
        assert False, "wrong chain id should fail"
    except ValueError:
        pass
    try:
        dispatcher("InitChain", {
            "chain_id": "HND-LOCAL-V2",
            "app_state_bytes": _b64(b'{"allocations":[]}'),
        })
        assert False, "unreviewed genesis payload should fail"
    except ValueError:
        pass
    chain.close()


def test_insert_tx_deduplicates_and_reap_respects_max_bytes(tmp_path):
    dispatcher, chain, alice, bob, _ = _dispatcher(tmp_path)
    raw = encode_transaction(create_transaction(alice, _key_account(bob), 10, 0))
    assert dispatcher("InsertTx", {"tx": _b64(raw)}) == {"code": 0}
    assert dispatcher("InsertTx", {"tx": _b64(raw)}) == {"code": 0}
    assert dispatcher("ReapTxs", {"max_bytes": len(raw) - 1}) == {"txs": []}
    assert dispatcher("ReapTxs", {"max_bytes": len(raw)}) == {"txs": [_b64(raw)]}
    chain.close()


def test_proposal_finalize_and_commit_flow(tmp_path):
    dispatcher, chain, alice, bob, alice_id = _dispatcher(tmp_path)
    raw = encode_transaction(create_transaction(alice, _key_account(bob), 25, 0))
    assert dispatcher("CheckTx", {"tx": _b64(raw)})["code"] == 0
    assert dispatcher("InsertTx", {"tx": _b64(raw)}) == {"code": 0}
    prepared = dispatcher("PrepareProposal", {
        "max_tx_bytes": 65_536, "txs": [_b64(raw)],
    })
    assert prepared == {"txs": [_b64(raw)]}
    assert dispatcher("ProcessProposal", {"txs": prepared["txs"]}) == {"status": 1}

    finalized = dispatcher("FinalizeBlock", {"height": 1, "txs": prepared["txs"]})
    assert len(base64.b64decode(finalized["app_hash"])) == 32
    assert finalized["tx_results"] == [{"code": 0}]
    assert chain.height == 0

    assert dispatcher("Commit", {}) == {"retain_height": 0}
    assert chain.height == 1
    assert chain.state.balances[alice_id] == 75
    assert dispatcher("ReapTxs", {"max_bytes": 65_536}) == {"txs": []}
    chain.close()



def test_weak_mempool_admission_filters_overspend_before_proposal(tmp_path):
    dispatcher, chain, alice, bob, alice_id = _dispatcher(tmp_path)
    bob_id = _key_account(bob)
    overspend = encode_transaction(create_transaction(alice, bob_id, 101, 0))
    valid = encode_transaction(create_transaction(alice, bob_id, 60, 0))

    assert dispatcher("CheckTx", {"tx": _b64(overspend)})["code"] == 0
    assert dispatcher("InsertTx", {"tx": _b64(overspend)})["code"] == 0
    assert dispatcher("InsertTx", {"tx": _b64(valid)})["code"] == 0

    reaped = dispatcher("ReapTxs", {"max_bytes": 65_536})["txs"]
    assert reaped == [_b64(overspend), _b64(valid)]
    prepared = dispatcher("PrepareProposal", {
        "txs": reaped, "max_tx_bytes": 65_536,
    })["txs"]
    assert prepared == [_b64(valid)]
    assert dispatcher("ProcessProposal", {"txs": prepared}) == {"status": 1}
    assert chain.state.balances[alice_id] == 100

    dispatcher("FinalizeBlock", {"height": 1, "txs": prepared})
    dispatcher("Commit", {})
    assert chain.state.balances[alice_id] == 40
    assert chain.state.balances[bob_id] == 60
    chain.close()


def test_invalid_proposal_is_rejected_and_unsupported_methods_fail_closed(tmp_path):
    dispatcher, chain, alice, bob, _ = _dispatcher(tmp_path)
    invalid = encode_transaction(create_transaction(alice, _key_account(bob), 101, 0))
    assert dispatcher("ProcessProposal", {"txs": [_b64(invalid)]}) == {"status": 2}
    try:
        dispatcher("ListSnapshots", {})
        assert False, "unsupported method should fail closed"
    except NotImplementedError:
        pass
    chain.close()



def test_query_returns_read_only_account_and_ledger_info(tmp_path):
    dispatcher, chain, alice, bob, alice_id = _dispatcher(tmp_path)
    before_hash = chain.tip_hash
    before_state = chain.state.total_supply

    account_result = dispatcher("Query", {
        "path": "/hnd/v1/account", "data": _b64(alice_id),
    })
    account_value = json.loads(base64.b64decode(account_result["value"]))
    assert account_result["code"] == 0
    assert base64.b64decode(account_result["key"]) == alice_id
    assert account_value == {
        "account_id": alice_id.hex(), "balance": 100,
        "next_nonce": 0, "height": 0,
    }

    info_result = dispatcher("Query", {"path": "/hnd/v1/info"})
    info_value = json.loads(base64.b64decode(info_result["value"]))
    assert info_result["code"] == 0
    assert info_value["chain_id"] == "HND-LOCAL-V2"
    assert info_value["height"] == 0
    assert info_value["supply_cap"] == 100
    assert info_value["total_supply"] == 100
    assert info_value["state_commitment"] == dispatcher.application.app_hash.hex()

    assert chain.tip_hash == before_hash
    assert chain.state.total_supply == before_state
    chain.close()


def test_query_rejects_proofs_historical_heights_and_bad_account_ids(tmp_path):
    dispatcher, chain, *_ = _dispatcher(tmp_path)
    assert dispatcher("Query", {
        "path": "/hnd/v1/info", "prove": True,
    })["code"] == 1
    assert dispatcher("Query", {
        "path": "/hnd/v1/info", "height": 1,
    })["code"] == 1
    assert dispatcher("Query", {
        "path": "/hnd/v1/account", "data": _b64(b"short"),
    })["code"] == 1
    assert dispatcher("Query", {"path": "/unknown"})["code"] == 1
    chain.close()


def test_check_tx_rejects_tampered_signature_and_invalid_base64(tmp_path):
    import cbor2
    from dataclasses import replace
    from hnd_ledger.protocol import transaction_array

    dispatcher, chain, alice, bob, _ = _dispatcher(tmp_path)
    tx = create_transaction(alice, _key_account(bob), 10, 0)
    tampered = replace(tx, signature=bytes([0xA5]) * 64)
    raw = cbor2.dumps(transaction_array(tampered), canonical=True)

    assert dispatcher("CheckTx", {"tx": _b64(raw)})["code"] == 1
    assert dispatcher("InsertTx", {"tx": _b64(raw)}) == {"code": 1}
    try:
        dispatcher("CheckTx", {"tx": "not base64!"})
        assert False, "invalid base64 must fail"
    except ValueError:
        pass
    assert dispatcher("ReapTxs", {"max_bytes": 65_536}) == {"txs": []}
    chain.close()


def test_init_chain_installs_canonical_genesis_allocations_once(tmp_path):
    dispatcher, chain, alice, bob, alice_id = _dispatcher(tmp_path, funded=False)
    bob_id = _key_account(bob)
    allocations = sorted([[alice_id, 700], [bob_id, 300]], key=lambda row: row[0])
    app_state = _genesis_bytes([2, 1_000, allocations])
    encoded = _b64(app_state)

    assert dispatcher("InitChain", {
        "chain_id": "HND-LOCAL-V2", "app_state_bytes": encoded,
    }) == {"validators": []}
    assert chain.state.balances == {row[0]: row[1] for row in allocations}
    assert chain.state.total_supply == 1_000
    assert chain.state.supply_cap == 1_000

    # An identical InitChain retry is idempotent; a different genesis is rejected.
    assert dispatcher("InitChain", {
        "chain_id": "HND-LOCAL-V2", "app_state_bytes": encoded,
    }) == {"validators": []}
    other_state = _b64(_genesis_bytes([2, 1_000, [[alice_id, 999]]]))
    try:
        dispatcher("InitChain", {
            "chain_id": "HND-LOCAL-V2", "app_state_bytes": other_state,
        })
        assert False, "a different genesis must be rejected"
    except ValueError:
        pass

    path = chain.path
    chain.close()
    restored = LocalChain(path)
    assert restored.state.balances == {row[0]: row[1] for row in allocations}
    assert restored.state.supply_cap == 1_000
    restored.close()


def test_init_chain_rejects_unsorted_duplicate_and_over_cap_allocations(tmp_path):
    dispatcher, chain, alice, bob, alice_id = _dispatcher(tmp_path, funded=False)
    bob_id = _key_account(bob)
    reverse_sorted = sorted([[alice_id, 1], [bob_id, 1]], key=lambda row: row[0], reverse=True)
    bad_payloads = [
        [2, 1_000, reverse_sorted],
        [2, 1_000, [[alice_id, 1], [alice_id, 2]]],
        [2, 1_000, [[alice_id, 1_001]]],
    ]
    for value in bad_payloads:
        try:
            dispatcher("InitChain", {
                "chain_id": "HND-LOCAL-V2",
                "app_state_bytes": _b64(_genesis_bytes(value)),
            })
            assert False, "invalid genesis allocations must fail"
        except ValueError:
            pass
    assert chain.state.total_supply == 0
    chain.close()
