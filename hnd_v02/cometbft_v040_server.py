"""CometBFT v0.40.0 ABCI gRPC transport for the HND application core.

Generate the pinned protobuf bindings first with:
    bash scripts/generate_cometbft_v040_python.sh

The server defaults to loopback. Do not expose this unauthenticated endpoint
to an untrusted network.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent import futures
from pathlib import Path
from typing import Any

_GENERATED_ROOT = str(Path(__file__).resolve().parent / "_cometbft_v040")
if _GENERATED_ROOT not in sys.path:
    sys.path.insert(0, _GENERATED_ROOT)

try:
    import grpc
    from tendermint.abci import types_pb2, types_pb2_grpc
except ImportError as exc:  # pragma: no cover - exercised by setup guidance
    raise ImportError(
        "CometBFT v0.40.0 Python bindings are missing. Run "
        "'bash scripts/generate_cometbft_v040_python.sh' and install "
        "grpcio/grpcio-tools first."
    ) from exc

from .abci_app import ABCIApplicationError, HNDABCIApplication
from .genesis import genesis_manifest_hash
from .transaction import ProtocolConfig, canonical_json

APP_VERSION = "HND-v0.2"
CODESPACE = "hnd"


class HNDCometBFTv040Servicer(types_pb2_grpc.ABCIServicer):
    """Translate CometBFT v0.40.0 protobuf requests to the tested HND core."""

    def __init__(self, application: HNDABCIApplication) -> None:
        self.application = application

    @staticmethod
    def _abort(context: Any, error: Exception, code: Any = grpc.StatusCode.INVALID_ARGUMENT) -> None:
        context.abort(code, str(error))

    def Echo(self, request, context):
        return types_pb2.ResponseEcho(message=request.message)

    def Flush(self, request, context):
        return types_pb2.ResponseFlush()

    def Info(self, request, context):
        info = self.application.info()
        return types_pb2.ResponseInfo(
            data="HND deterministic application",
            version=APP_VERSION,
            app_version=2,
            last_block_height=info["last_block_height"],
            last_block_app_hash=info["last_block_app_hash"],
        )

    def InitChain(self, request, context):
        try:
            self.application.init_chain(
                chain_id=request.chain_id,
                app_state_bytes=request.app_state_bytes,
            )
        except (ABCIApplicationError, ValueError, TypeError) as exc:
            self._abort(context, exc)
        return types_pb2.ResponseInitChain(
            app_hash=bytes.fromhex(self.application.committed_state_hash)
        )

    def CheckTx(self, request, context):
        result = self.application.check_tx(
            request.tx,
            recheck=(request.type == types_pb2.RECHECK),
        )
        return types_pb2.ResponseCheckTx(
            code=result["code"],
            data=result["data"],
            log=result["log"],
            codespace="" if result["code"] == 0 else CODESPACE,
        )

    def InsertTx(self, request, context):
        # WP4.1 pins CometBFT's normal flood mempool. App-mempool mode is not
        # enabled because the HND core intentionally has no InsertTx/ReapTxs
        # queue implementation yet.
        return types_pb2.ResponseInsertTx(code=1)

    def ReapTxs(self, request, context):
        return types_pb2.ResponseReapTxs(txs=[])

    def Query(self, request, context):
        if request.prove:
            return types_pb2.ResponseQuery(
                code=1, log="proof queries are not implemented", codespace=CODESPACE
            )
        try:
            if request.path == "/height":
                value = {"height": self.application.last_committed_height}
            elif request.path == "/account":
                account_id = request.data.decode("utf-8")
                value = self.application.account_view(account_id)
                value = {"account_id": account_id, **value}
            else:
                return types_pb2.ResponseQuery(
                    code=1,
                    log="supported query paths: /height, /account",
                    codespace=CODESPACE,
                )
            return types_pb2.ResponseQuery(
                code=0,
                value=canonical_json(value),
                height=self.application.last_committed_height,
            )
        except (UnicodeDecodeError, ABCIApplicationError, ValueError, TypeError) as exc:
            return types_pb2.ResponseQuery(
                code=1, log=str(exc), codespace=CODESPACE,
                height=self.application.last_committed_height,
            )

    def PrepareProposal(self, request, context):
        max_bytes = request.max_tx_bytes
        if max_bytes < 0:
            max_bytes = sum(len(tx) for tx in request.txs)
        try:
            txs = self.application.prepare_proposal(
                transactions=list(request.txs),
                max_tx_bytes=max_bytes,
            )
        except (ABCIApplicationError, ValueError, TypeError) as exc:
            self._abort(context, exc)
        return types_pb2.ResponsePrepareProposal(txs=txs)

    def ProcessProposal(self, request, context):
        result = self.application.process_proposal(transactions=list(request.txs))
        status = (
            types_pb2.ResponseProcessProposal.ACCEPT
            if result["accepted"]
            else types_pb2.ResponseProcessProposal.REJECT
        )
        return types_pb2.ResponseProcessProposal(status=status)

    def ExtendVote(self, request, context):
        # HND v0.2 does not define application vote extensions.
        return types_pb2.ResponseExtendVote(vote_extension=b"")

    def VerifyVoteExtension(self, request, context):
        # Empty extensions are the only valid behavior until a separately
        # specified and versioned HND extension format exists.
        status = (
            types_pb2.ResponseVerifyVoteExtension.ACCEPT
            if request.vote_extension == b""
            else types_pb2.ResponseVerifyVoteExtension.REJECT
        )
        return types_pb2.ResponseVerifyVoteExtension(status=status)

    def FinalizeBlock(self, request, context):
        try:
            result = self.application.finalize_block(
                height=request.height,
                transactions=list(request.txs),
            )
        except (ABCIApplicationError, ValueError, TypeError) as exc:
            self._abort(context, exc, grpc.StatusCode.FAILED_PRECONDITION)
        tx_results = [
            types_pb2.ExecTxResult(
                code=item["code"],
                data=bytes.fromhex(item["data"]),
                log=item["log"],
                codespace="" if item["code"] == 0 else CODESPACE,
            )
            for item in result["tx_results"]
        ]
        return types_pb2.ResponseFinalizeBlock(
            tx_results=tx_results,
            app_hash=result["app_hash"],
        )

    def Commit(self, request, context):
        try:
            self.application.commit()
        except (ABCIApplicationError, OSError, ValueError, TypeError) as exc:
            self._abort(context, exc, grpc.StatusCode.FAILED_PRECONDITION)
        return types_pb2.ResponseCommit(retain_height=0)

    def ListSnapshots(self, request, context):
        return types_pb2.ResponseListSnapshots(snapshots=[])

    def OfferSnapshot(self, request, context):
        return types_pb2.ResponseOfferSnapshot(
            result=types_pb2.ResponseOfferSnapshot.REJECT
        )

    def LoadSnapshotChunk(self, request, context):
        return types_pb2.ResponseLoadSnapshotChunk(chunk=b"")

    def ApplySnapshotChunk(self, request, context):
        return types_pb2.ResponseApplySnapshotChunk(
            result=types_pb2.ResponseApplySnapshotChunk.ABORT
        )


def start_grpc_server(
    application: HNDABCIApplication,
    *,
    bind_address: str = "127.0.0.1:26658",
    max_workers: int = 16,
):
    """Start a CometBFT-compatible ABCI gRPC server and return (server, port)."""
    if type(max_workers) is not int or max_workers < 4:
        raise ValueError("max_workers must be an integer >= 4 for ABCI concurrency")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    types_pb2_grpc.add_ABCIServicer_to_server(
        HNDCometBFTv040Servicer(application), server
    )
    port = server.add_insecure_port(bind_address)
    if port == 0:
        raise OSError(f"could not bind ABCI gRPC endpoint: {bind_address}")
    server.start()
    return server, port


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="HND CometBFT v0.40.0 ABCI gRPC server")
    parser.add_argument("--manifest", required=True, help="canonical HND Genesis manifest JSON")
    parser.add_argument("--genesis-hash", required=True, help="independently pinned Genesis manifest SHA-256")
    parser.add_argument("--network-id", required=True)
    parser.add_argument("--protocol-version", type=int, default=2)
    parser.add_argument("--max-amount", type=int, required=True)
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--listen", default="127.0.0.1:26658")
    args = parser.parse_args(argv)

    with Path(args.manifest).open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    actual_genesis_hash = genesis_manifest_hash(manifest)
    if actual_genesis_hash != args.genesis_hash:
        parser.error("manifest does not match the independently supplied --genesis-hash")

    config = ProtocolConfig(
        network_id=args.network_id,
        protocol_version=args.protocol_version,
        max_amount=args.max_amount,
    )
    if manifest.get("network_id") != config.network_id:
        parser.error("manifest network_id does not match --network-id")
    application = HNDABCIApplication(
        config=config,
        manifest=manifest,
        expected_genesis_hash=args.genesis_hash,
        state_path=args.state_path,
    )
    server, port = start_grpc_server(application, bind_address=args.listen)
    print(f"HND ABCI gRPC listening on {args.listen} (port {port})")
    server.wait_for_termination()


if __name__ == "__main__":  # pragma: no cover
    main()
