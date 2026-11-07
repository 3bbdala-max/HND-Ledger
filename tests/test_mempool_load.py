import base64
from concurrent.futures import ThreadPoolExecutor

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.abci_dispatch import ABCIDispatcher, MAX_MEMPOOL_BYTES, MAX_MEMPOOL_ITEMS
from hnd_ledger.application import LedgerApplication
from hnd_ledger.chain import MAX_BLOCK_BYTES, MAX_BLOCK_TRANSACTIONS, LocalChain
from hnd_ledger.protocol import account_id, create_transaction, decode_transaction, encode_transaction
from hnd_ledger.state import LedgerState


def _account_id(key):
    return account_id(key.public_key().public_bytes_raw())


def _b64(raw):
    return base64.b64encode(raw).decode("ascii")


def test_mempool_admits_and_commits_maximum_byte_bounded_concurrent_batch(tmp_path):
    # Build the largest nonce-ordered batch that fits both block limits.
    sender = Ed25519PrivateKey.generate()
    recipient = Ed25519PrivateKey.generate()
    sender_id = _account_id(sender)
    recipient_id = _account_id(recipient)

    transactions = []
    total_bytes = 0
    for nonce in range(min(MAX_BLOCK_TRANSACTIONS, MAX_MEMPOOL_ITEMS)):
        raw = encode_transaction(create_transaction(sender, recipient_id, 1, nonce))
        if total_bytes + len(raw) > min(MAX_BLOCK_BYTES, MAX_MEMPOOL_BYTES):
            break
        transactions.append(raw)
        total_bytes += len(raw)

    count = len(transactions)
    assert count > 0
    assert count <= MAX_BLOCK_TRANSACTIONS
    assert total_bytes <= MAX_BLOCK_BYTES
    assert total_bytes <= MAX_MEMPOOL_BYTES

    chain = LocalChain(
        tmp_path / "mempool-maximum-batch.sqlite",
        LedgerState(balances={sender_id: count}, supply_cap=count),
    )
    dispatcher = ABCIDispatcher(LedgerApplication(chain))
    try:
        with ThreadPoolExecutor(max_workers=32) as pool:
            responses = list(pool.map(
                lambda raw: dispatcher("InsertTx", {"tx": _b64(raw)}),
                transactions,
            ))

        assert len(responses) == count
        assert all(response["code"] == 0 for response in responses)
        assert len(dispatcher._mempool) == count
        assert len(set(dispatcher._mempool)) == count
        assert dispatcher._mempool_bytes == total_bytes
        assert dispatcher._mempool_bytes <= MAX_MEMPOOL_BYTES

        proposal = dispatcher("PrepareProposal", {
            "max_tx_bytes": total_bytes,
            "txs": [_b64(raw) for raw in transactions],
        })
        assert len(proposal["txs"]) == count
        assert [
            decode_transaction(base64.b64decode(raw), chain.state.chain_id).nonce
            for raw in proposal["txs"]
        ] == list(range(count))

        dispatcher("FinalizeBlock", {"height": 1, "txs": proposal["txs"]})
        dispatcher("Commit", {})
        assert chain.height == 1
        assert chain.state.balances[sender_id] == 0
        assert chain.state.balances[recipient_id] == count
        assert chain.state.next_nonces[sender_id] == count
        assert len(dispatcher._mempool) == 0
        assert dispatcher._mempool_bytes == 0
    finally:
        chain.close()
