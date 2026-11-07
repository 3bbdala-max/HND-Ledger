from concurrent.futures import ThreadPoolExecutor

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_ledger.abci_dispatch import ABCIDispatcher, MAX_MEMPOOL_BYTES, MAX_MEMPOOL_ITEMS
from hnd_ledger.application import LedgerApplication
from hnd_ledger.chain import LocalChain
from hnd_ledger.protocol import account_id, create_transaction, decode_transaction, encode_transaction
from hnd_ledger.state import LedgerState


def _account_id(key):
    return account_id(key.public_key().public_bytes_raw())


def _b64(raw):
    import base64
    return base64.b64encode(raw).decode("ascii")


def test_mempool_admits_and_commits_maximum_block_sized_concurrent_batch(tmp_path):
    # Exercise the full 1,000-transaction block boundary using a bounded
    # concurrent admission burst, then verify deterministic execution and
    # complete mempool accounting after Commit.
    count = 1_000
    sender = Ed25519PrivateKey.generate()
    recipient = Ed25519PrivateKey.generate()
    sender_id = _account_id(sender)
    recipient_id = _account_id(recipient)
    chain = LocalChain(
        tmp_path / "mempool-maximum-batch.sqlite",
        LedgerState(balances={sender_id: count}, supply_cap=count),
    )
    dispatcher = ABCIDispatcher(LedgerApplication(chain))
    transactions = [
        encode_transaction(create_transaction(sender, recipient_id, 1, nonce))
        for nonce in range(count)
    ]
    try:
        assert count <= MAX_MEMPOOL_ITEMS
        assert sum(map(len, transactions)) <= MAX_MEMPOOL_BYTES

        with ThreadPoolExecutor(max_workers=32) as pool:
            responses = list(pool.map(
                lambda raw: dispatcher("InsertTx", {"tx": _b64(raw)}),
                transactions,
            ))

        assert len(responses) == count
        assert all(response["code"] == 0 for response in responses)
        assert len(dispatcher._mempool) == count
        assert len(set(dispatcher._mempool)) == count
        assert dispatcher._mempool_bytes == sum(map(len, transactions))
        assert dispatcher._mempool_bytes <= MAX_MEMPOOL_BYTES

        # The application must produce the same nonce order regardless of
        # the concurrent arrival order at the mempool.
        ordered = sorted(
            transactions,
            key=lambda raw: decode_transaction(raw, chain.state.chain_id).nonce,
        )
        proposal = dispatcher("PrepareProposal", {
            "max_tx_bytes": sum(map(len, ordered)),
            "txs": [_b64(raw) for raw in ordered],
        })
        assert len(proposal["txs"]) == count
        assert [
            decode_transaction(__import__("base64").b64decode(raw), chain.state.chain_id).nonce
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
