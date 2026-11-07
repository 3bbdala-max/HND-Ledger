"""Run the HND Python ABCI application over a local Unix socket."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from .abci_dispatch import ABCIDispatcher
from .application import LedgerApplication
from .chain import LocalChain
from .ipc_server import IPCServer
from .protocol import MAX_SUPPLY
from .state import LedgerState


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HND v0.2 local ABCI application")
    parser.add_argument(
        "--chain-db", default=os.environ.get("HND_CHAIN_DB"),
        help="SQLite ledger path (or HND_CHAIN_DB)",
    )
    parser.add_argument(
        "--socket", default=os.environ.get("HND_IPC_SOCKET"),
        help="private Unix socket path (or HND_IPC_SOCKET)",
    )
    parser.add_argument(
        "--init-empty-dev-genesis", action="store_true",
        help="explicitly create a new zero-allocation development genesis",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not args.chain_db or not args.socket:
        raise SystemExit("--chain-db and --socket (or their environment variables) are required")

    db_path = Path(args.chain_db)
    if db_path.exists():
        if args.init_empty_dev_genesis:
            raise SystemExit("refusing to initialize an existing database")
        chain = LocalChain(db_path)
    else:
        if not args.init_empty_dev_genesis:
            raise SystemExit(
                "new database requires explicit --init-empty-dev-genesis; "
                "no HND allocations are created automatically"
            )
        db_path.parent.mkdir(parents=True, exist_ok=True)
        chain = LocalChain(db_path, LedgerState(supply_cap=MAX_SUPPLY))
        os.chmod(db_path, 0o600)

    server = IPCServer(args.socket, ABCIDispatcher(LedgerApplication(chain)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        chain.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
