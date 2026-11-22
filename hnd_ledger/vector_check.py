"""Command-line reproduction of the committed HND v0.2 golden vectors.

Run from the repository root with:
    python -m hnd_ledger.vector_check
"""
from __future__ import annotations

import json
import sys

from .blocks import create_genesis_block, merkle_root
from .canonical import LOCAL_CHAIN_ID

ACCOUNT_A = "00" * 31 + "01"
ACCOUNT_B = "00" * 31 + "02"

EXPECTED = {
    "genesis_payload": (
        "83025820484e442d4c4f43414c2d56320000000000000000000000000000000000000000"
        "8282582000000000000000000000000000000000000000000000000000000000000000010a"
        "825820000000000000000000000000000000000000000000000000000000000000000214"
    ),
    "genesis_id": "5abf41e236488b231d109d1c0b5bddf4ae0bac2b4748e9e196cdd952d284876d",
    "state_root": "c319d4a7c593c436537410399a7a2f2b755e92ffdad4bfccb478eba5d401f92a",
    "genesis_header": (
        "88025820484e442d4c4f43414c2d563200000000000000000000000000000000"
        "0000000000005820000000000000000000000000000000000000000000000000"
        "00000000000000005820e915dc5e01273ce33c203835702fdf82ee0937b2baef"
        "7c8bd4e89dc012603eb95820c319d4a7c593c436537410399a7a2f2b755e92ff"
        "dad4bfccb478eba5d401f92a00"
    ),
    "genesis_header_length": "141",
    "genesis_block_hash": "de5c6f795a091c20b0a0f0e0ae2d73e4a0c66d3a00962deffd3dd3d7556bb3e9",
    "two_transaction_merkle_root": "c1f4d8d5a11caf4898b7f48c7ccbec0e52c774ea7576cd2ef3b36d4521b40774",
}


def collect_vectors() -> dict[str, str]:
    genesis = create_genesis_block(LOCAL_CHAIN_ID, {ACCOUNT_B: 20, ACCOUNT_A: 10})
    tx_root = merkle_root([
        bytes.fromhex("11" * 32),
        bytes.fromhex("22" * 32),
    ])
    return {
        "genesis_payload": genesis["genesis_payload"].hex(),
        "genesis_id": genesis["genesis_id"].hex(),
        "state_root": genesis["state_root"].hex(),
        "genesis_header": genesis["header"].hex(),
        "genesis_header_length": str(len(genesis["header"])),
        "genesis_block_hash": genesis["block_hash"].hex(),
        "two_transaction_merkle_root": tx_root.hex(),
    }


def main() -> int:
    actual = collect_vectors()
    result = {
        "profile": "HND local v0.2 test profile",
        "expected": EXPECTED,
        "actual": actual,
        "passed": actual == EXPECTED,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if actual == EXPECTED else 1


if __name__ == "__main__":
    raise SystemExit(main())
