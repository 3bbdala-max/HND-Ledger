"""CometBFT v0.40.0 ABCI gRPC transport for the HND application core.

Generate the pinned protobuf bindings first with:
    bash scripts/generate_cometbft_v040_python.sh

The server defaults to loopback. Do not expose this unauthenticated endpoint
to an untrusted network.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import sys
from datetime import datetime, timezone
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
from .strict_json import StrictJSONError, strict_json_loads
from .startup_authorization import authorize_then_start_witnessed

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
        account_id = None
        try:
            if request.path == "/height":
                value = {"height": self.application.last_committed_height}
            elif request.path == "/account":
                account_id = request.data.decode("utf-8")
                value = self.application.account_view(account_id)
                value = {"account_id": account_id, **value}
            elif request.path == "/evidence":
                if request.data:
                    page_request = strict_json_loads(
                        request.data,
                        label="evidence page request",
                    )
                    if (
                        type(page_request) is not dict
                        or set(page_request) != {"offset", "limit"}
                        or canonical_json(page_request) != request.data
                    ):
                        raise ABCIApplicationError("evidence page request schema or canonical encoding")
                    offset = page_request["offset"]
                    limit = page_request["limit"]
                else:
                    offset, limit = 0, 100
                evidence, total = self.application.evidence_page(offset=offset, limit=limit)
                next_offset = offset + len(evidence) if offset + len(evidence) < total else None
                value = {
                    "evidence": evidence,
                    "offset": offset,
                    "limit": limit,
                    "total_count": total,
                    "next_offset": next_offset,
                }
            else:
                return types_pb2.ResponseQuery(
                    code=1,
                    log="supported query paths: /height, /account, /evidence",
                    codespace=CODESPACE,
                )
            return types_pb2.ResponseQuery(
                code=0,
                value=canonical_json(value),
                height=self.application.last_committed_height,
            )
        except (UnicodeDecodeError, ABCIApplicationError, ValueError, TypeError) as exc:
            detail = str(exc)
            if request.path == "/account":
                detail += f"; requested_account_id={account_id!r}; data_hex={request.data.hex()}"
            return types_pb2.ResponseQuery(
                code=1, log=detail, codespace=CODESPACE,
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

    @staticmethod
    def _normalize_misbehavior(items):
        normalized = []
        for item in items:
            stamp = item.time
            if hasattr(stamp, "seconds") and hasattr(stamp, "nanos"):
                stamp_text = f"unix:{int(stamp.seconds)}:{int(stamp.nanos):09d}"
            elif isinstance(stamp, datetime) and stamp.tzinfo is not None and stamp.utcoffset() is not None:
                delta = stamp.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
                seconds = delta.days * 86400 + delta.seconds
                stamp_text = f"unix:{seconds}:{delta.microseconds * 1000:09d}"
            else:
                raise ABCIApplicationError("misbehavior timestamp must be a protobuf Timestamp or timezone-aware datetime")
            normalized.append({
                "type": int(item.type),
                "validator_address": bytes(item.validator.address).hex(),
                "validator_power": int(item.validator.power),
                "height": int(item.height),
                "time": stamp_text,
                "total_voting_power": int(item.total_voting_power),
            })
        return normalized

    def FinalizeBlock(self, request, context):
        try:
            result = self.application.finalize_block(
                height=request.height,
                transactions=list(request.txs),
                misbehavior=self._normalize_misbehavior(request.misbehavior),
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


def _validate_loopback_bind_address(bind_address: str) -> None:
    """Reject non-loopback and hostname binds while transport remains insecure.

    Port 0 is intentionally allowed for ephemeral local test servers.
    IPv6 literals must use gRPC's bracketed form, e.g. [::1]:26658.
    """
    if type(bind_address) is not str or not bind_address:
        raise ValueError("bind_address must be a non-empty loopback IP literal")

    if bind_address.startswith("["):
        closing = bind_address.find("]")
        if closing < 0 or closing + 1 >= len(bind_address) or bind_address[closing + 1] != ":":
            raise ValueError("IPv6 bind address must use [address]:port syntax")
        host = bind_address[1:closing]
        port_text = bind_address[closing + 2:]
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("bind address must use a loopback IP literal") from exc
        if address.version != 6:
            raise ValueError("bracketed bind address must be IPv6")
    else:
        if bind_address.count(":") != 1:
            raise ValueError("bind address must use IPv4:port or [IPv6]:port syntax")
        host, port_text = bind_address.rsplit(":", 1)
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("bind address must use a loopback IP literal") from exc
        if address.version != 4:
            raise ValueError("IPv6 bind address must use [address]:port syntax")

    if not address.is_loopback:
        raise ValueError("insecure ABCI gRPC transport is restricted to loopback addresses")
    if not port_text.isascii() or not port_text.isdigit():
        raise ValueError("bind port must be an integer from 0 to 65535")
    port = int(port_text)
    if not 0 <= port <= 65535:
        raise ValueError("bind port must be an integer from 0 to 65535")

def start_grpc_server(
    application: HNDABCIApplication,
    *,
    bind_address: str = "127.0.0.1:26658",
    max_workers: int = 16,
):
    """Start a CometBFT-compatible ABCI gRPC server and return (server, port)."""
    if type(max_workers) is not int or max_workers < 4:
        raise ValueError("max_workers must be an integer >= 4 for ABCI concurrency")
    _validate_loopback_bind_address(bind_address)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    types_pb2_grpc.add_ABCIServicer_to_server(
        HNDCometBFTv040Servicer(application), server
    )
    port = server.add_insecure_port(bind_address)
    if port == 0:
        raise OSError(f"could not bind ABCI gRPC endpoint: {bind_address}")
    server.start()
    return server, port



def start_witnessed_grpc_server(
    application: HNDABCIApplication,
    *,
    backend: Any,
    witness_client: Any,
    activation_id: str,
    expected_witness_id: str,
    expected_config_epoch: int,
    vsp_raw: bytes,
    trust_manifests: list[bytes],
    operator_acks_raw: bytes,
    profile_artifact: bytes,
    context: dict,
    trusted_witness_keys: dict[str, bytes],
    expected_operator_keys: dict[str, bytes],
    application_binding_verifier,
    bind_address: str = "127.0.0.1:26658",
    max_workers: int = 16,
):
    """Authorize the exact application binding before opening the ABCI socket.

    The mandatory binding verifier must return True only when the supplied
    HNDABCIApplication instance is derived from the exact verified profile and
    Genesis/network context. It is deliberately not inferred from a local
    Genesis hash alone. The listener is created only inside the post-witness
    launch callback; failures before that point open no socket.
    """
    if not callable(application_binding_verifier):
        raise ValueError("application_binding_verifier is mandatory")

    def open_listener(state):
        try:
            bound = application_binding_verifier(application, state, profile_artifact)
        except Exception as exc:
            raise RuntimeError("HND-ABCI-E-APPLICATION-BINDING") from exc
        if bound is not True:
            raise RuntimeError("HND-ABCI-E-APPLICATION-BINDING")
        return start_grpc_server(
            application, bind_address=bind_address, max_workers=max_workers
        )

    return authorize_then_start_witnessed(
        backend=backend,
        witness_client=witness_client,
        activation_id=activation_id,
        expected_witness_id=expected_witness_id,
        expected_config_epoch=expected_config_epoch,
        vsp_raw=vsp_raw,
        trust_manifests=trust_manifests,
        operator_acks_raw=operator_acks_raw,
        profile_artifact=profile_artifact,
        context=context,
        trusted_witness_keys=trusted_witness_keys,
        expected_operator_keys=expected_operator_keys,
        launch=open_listener,
    )

def main(argv: list[str] | None = None) -> None:
    """Reject standalone startup; production must use the witnessed supervisor."""
    parser = argparse.ArgumentParser(
        description="HND CometBFT v0.40.0 ABCI gRPC server"
    )
    parser.parse_args(argv)
    parser.error(
        "HND-ABCI-E-DIRECT-START-DISABLED: standalone ABCI startup is disabled; "
        "use start_witnessed_grpc_server through the deployment supervisor "
        "with an independently authenticated witness and an exact application "
        "binding verifier"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
