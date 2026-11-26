"""Explicitly disposable ABCI server for the four-validator integration harness.

This script is not a production entrypoint. It is intentionally kept under
scripts/, requires an opt-in environment marker set only by the disposable
smoke harness, and binds only through start_grpc_server's loopback validator.
Production startup remains disabled in hnd_v02.cometbft_v040_server.main.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hnd_v02.abci_app import ABCIApplicationError, HNDABCIApplication
from hnd_v02.cometbft_v040_server import (
    _validate_genesis_initialization_path,
    start_grpc_server,
)
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.strict_json import StrictJSONError, strict_json_loads
from hnd_v02.transaction import ProtocolConfig

_TEST_ONLY_ENV = "HND_DISPOSABLE_ABCI_TEST_SERVER"


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DISPOSABLE TEST-ONLY HND CometBFT v0.40.0 ABCI server"
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--genesis-hash", required=True)
    parser.add_argument("--network-id", required=True)
    parser.add_argument("--protocol-version", type=int, default=2)
    parser.add_argument("--max-amount", type=int, required=True)
    parser.add_argument("--state-path", required=True)
    startup_mode = parser.add_mutually_exclusive_group(required=True)
    startup_mode.add_argument("--initialize-genesis", action="store_true")
    startup_mode.add_argument("--recovery", action="store_true")
    parser.add_argument("--listen", default="127.0.0.1:26658")
    return parser


def build_application(args: argparse.Namespace) -> HNDABCIApplication:
    """Build the disposable app while preserving explicit first-boot/recovery modes."""
    if args.initialize_genesis:
        _validate_genesis_initialization_path(args.state_path)

    manifest = strict_json_loads(
        Path(args.manifest).read_bytes(),
        label="manifest",
    )
    if type(manifest) is not dict:
        raise ValueError("manifest must be a JSON object")
    actual_genesis_hash = genesis_manifest_hash(manifest)
    if actual_genesis_hash != args.genesis_hash:
        raise ValueError("manifest does not match the independently supplied --genesis-hash")

    config = ProtocolConfig(
        network_id=args.network_id,
        protocol_version=args.protocol_version,
        max_amount=args.max_amount,
    )
    if manifest.get("network_id") != config.network_id:
        raise ValueError("manifest network_id does not match --network-id")

    return HNDABCIApplication(
        config=config,
        manifest=manifest,
        expected_genesis_hash=args.genesis_hash,
        state_path=args.state_path,
        require_existing_state=args.recovery,
    )


def _serve_until_terminated(server) -> None:
    stopped = threading.Event()
    previous_handlers = {}

    def request_stop(_signum, _frame) -> None:
        stopped.set()

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, request_stop)
        stopped.wait()
    finally:
        server.stop(grace=2).wait(timeout=5)
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)


def main(argv: list[str] | None = None) -> None:
    parser = _build_argument_parser()
    if os.environ.get(_TEST_ONLY_ENV) != "1":
        parser.error(
            "disposable ABCI server is test-only; "
            f"set {_TEST_ONLY_ENV}=1 from the isolated smoke harness"
        )
    args = parser.parse_args(argv)

    try:
        application = build_application(args)
    except (OSError, StrictJSONError, ABCIApplicationError, TypeError, ValueError) as exc:
        parser.error(str(exc))

    server, _port = start_grpc_server(application, bind_address=args.listen)
    _serve_until_terminated(server)


if __name__ == "__main__":  # pragma: no cover
    main()
