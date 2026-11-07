"""Preflight four independent CometBFT v0.40.0 validator identities and shared Genesis.

This is deliberately a Genesis/schema preflight, not a running four-node testnet.
All keys and generated chain data remain inside a temporary directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import (
    ProtocolConfig,
    account_id_for_public_key,
    public_key_b64,
    canonical_json,
)

NETWORK_ID = "hnd-cometbft-v040-four-validator-preflight"
TOTAL_SUPPLY = 1_000_000
VALIDATOR_COUNT = 4
VOTING_POWER = 10


def run(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command, cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, timeout=90,
    )
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--cometbft-source", required=True)
    args = parser.parse_args()
    binary = str(Path(args.binary).resolve())
    source = Path(args.cometbft_source).resolve()
    if not Path(binary).is_file() or not (source / "go.mod").is_file():
        parser.error("binary and CometBFT v0.40.0 source tree must exist")

    config = ProtocolConfig(
        network_id=NETWORK_ID, protocol_version=2, max_amount=TOTAL_SUPPLY
    )
    alice_key = Ed25519PrivateKey.generate()
    bob_key = Ed25519PrivateKey.generate()
    alice_public = public_key_b64(alice_key)
    bob_public = public_key_b64(bob_key)
    allocations = [
        {
            "account_id": account_id_for_public_key(alice_public, config=config),
            "public_key": alice_public,
            "amount": 600_000,
        },
        {
            "account_id": account_id_for_public_key(bob_public, config=config),
            "public_key": bob_public,
            "amount": 400_000,
        },
    ]
    allocations.sort(key=lambda item: item["account_id"])
    manifest = {
        "manifest_version": 1,
        "network_id": NETWORK_ID,
        "protocol_version": 2,
        "total_supply": TOTAL_SUPPLY,
        "allocations": allocations,
    }
    manifest_hash = genesis_manifest_hash(manifest)
    app_state = {
        "genesis_hash": manifest_hash,
        "manifest": manifest,
        "protocol_config": {
            "network_id": config.network_id,
            "protocol_version": config.protocol_version,
            "max_amount": config.max_amount,
        },
    }

    with tempfile.TemporaryDirectory(prefix="hnd-cometbft-v040-4val-preflight-") as tmp:
        root = Path(tmp)
        validator_records = []
        node_ids = []
        homes = []
        for index in range(VALIDATOR_COUNT):
            home = root / f"validator-{index + 1}"
            home.mkdir()
            run([binary, "init", "--home", str(home)])
            key_path = home / "config" / "priv_validator_key.json"
            key = json.loads(key_path.read_text(encoding="utf-8"))
            if set(key.get("pub_key", {})) != {"type", "value"}:
                raise AssertionError(f"validator {index + 1}: unexpected pub_key schema")
            if not key.get("address") or not key.get("pub_key", {}).get("value"):
                raise AssertionError(f"validator {index + 1}: missing key identity")
            node_id = run([binary, "show-node-id", "--home", str(home)])
            if not node_id or any(ch.isspace() for ch in node_id):
                raise AssertionError(f"validator {index + 1}: invalid node ID")
            node_ids.append(node_id)
            homes.append(home)
            validator_records.append({
                "address": key["address"],
                "pub_key": key["pub_key"],
                "power": str(VOTING_POWER),
                "name": f"hnd-validator-{index + 1}",
            })

        if len(set(node_ids)) != VALIDATOR_COUNT:
            raise AssertionError("CometBFT P2P node IDs are not unique")
        if len({item["address"] for item in validator_records}) != VALIDATOR_COUNT:
            raise AssertionError("validator consensus addresses are not unique")

        genesis_path = homes[0] / "config" / "genesis.json"
        genesis = json.loads(genesis_path.read_text(encoding="utf-8"))
        genesis["chain_id"] = NETWORK_ID
        genesis["initial_height"] = "1"
        genesis["validators"] = validator_records
        genesis["app_hash"] = ""
        genesis["app_state"] = app_state
        common_genesis = json.dumps(genesis, sort_keys=True, indent=2) + "\n"
        common_hash = hashlib.sha256(common_genesis.encode("utf-8")).hexdigest()

        for home in homes:
            path = home / "config" / "genesis.json"
            path.write_text(common_genesis, encoding="utf-8")
            if hashlib.sha256(path.read_bytes()).hexdigest() != common_hash:
                raise AssertionError("validator homes do not contain byte-identical Genesis")

        # Parse and validate the exact Genesis document with the pinned CometBFT
        # v0.40.0 Go types, including each validator public-key/address pairing.
        go_helper = REPO_ROOT / "scripts" / "cometbft_v040_genesis_validate.go"
        run(["go", "run", str(go_helper), str(genesis_path)], cwd=source)

        print(json.dumps({
            "result": "COMETBFT_V040_FOUR_VALIDATOR_GENESIS_PREFLIGHT_OK",
            "validator_count": VALIDATOR_COUNT,
            "voting_power_each": VOTING_POWER,
            "total_voting_power": VALIDATOR_COUNT * VOTING_POWER,
            "node_ids_unique": len(set(node_ids)) == VALIDATOR_COUNT,
            "consensus_addresses_unique": len({v["address"] for v in validator_records}) == VALIDATOR_COUNT,
            "genesis_sha256": common_hash,
            "hnd_manifest_hash": manifest_hash,
            "genesis_identical_across_homes": True,
            "private_keys_in_temporary_directory": True,
            "scope": "genesis-and-identity-preflight-only; no nodes started",
        }, sort_keys=True))


if __name__ == "__main__":
    main()
