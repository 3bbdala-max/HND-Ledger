"""Disposable one-validator CometBFT v0.40.0 integration smoke test.

This script creates all validator/account keys and chain data under a temporary
directory. No private keys or testnet state are written into the repository.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import grpc
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hnd_v02.abci_app import HNDABCIApplication
from hnd_v02.cometbft_v040_server import start_grpc_server, types_pb2, types_pb2_grpc
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import (
    ProtocolConfig,
    account_id_for_public_key,
    canonical_json,
    create_signed_transaction,
    public_key_b64,
)


RPC = "http://127.0.0.1:26657"
ABCI_LISTEN = "127.0.0.1:26658"
NETWORK_ID = "hnd-cometbft-v040-smoke"
INITIAL_ALICE_BALANCE = 600_000
TRANSFER_AMOUNT = 1_237


def rpc_get(path: str, params: dict[str, str] | None = None) -> dict:
    query = urllib.parse.urlencode(params or {})
    url = RPC + path + (("?" + query) if query else "")
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CometBFT RPC {path} returned HTTP {exc.code}: {body}") from exc


def decode_rpc_bytes(value: str | list[int] | None) -> bytes:
    if value is None or value == "":
        return b""
    if isinstance(value, list):
        return bytes(value)
    if not isinstance(value, str):
        raise TypeError("unexpected byte field from CometBFT RPC")
    if value.startswith("0x"):
        return bytes.fromhex(value[2:])
    try:
        decoded = base64.b64decode(value, validate=True)
        if decoded.startswith(b"{"):
            return decoded
    except (ValueError, base64.binascii.Error):
        pass
    if len(value) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", value):
        return bytes.fromhex(value)
    return base64.b64decode(value)


def query_account(account_id: str) -> dict:
    result = rpc_get(
        "/abci_query",
        {
            "path": "/account",
            "data": "0x" + account_id.encode("utf-8").hex(),
            "prove": "false",
        },
    )
    response = result.get("result", {}).get("response", {})
    code = int(response.get("code", 0))
    if code != 0:
        raise RuntimeError(f"ABCI account query failed: {response}")
    raw = decode_rpc_bytes(response.get("value"))
    return json.loads(raw.decode("utf-8"))


def wait_for_node(binary_process: subprocess.Popen, log_path: Path, *, timeout: int = 45) -> dict:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if binary_process.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-10000:]
            raise RuntimeError(
                f"CometBFT exited with code {binary_process.returncode}.\n{tail}"
            )
        try:
            result = rpc_get("/status")
            height = int(result["result"]["sync_info"]["latest_block_height"])
            if height >= 1:
                return result
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(0.25)
    tail = log_path.read_text(encoding="utf-8", errors="replace")[-10000:]
    raise TimeoutError(f"CometBFT did not reach height 1: {last_error}\n{tail}")


def wait_for_balance(account_id: str, expected: int, *, timeout: int = 30) -> dict:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            account = query_account(account_id)
            if account.get("balance") == expected:
                return account
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise TimeoutError(
        f"account balance did not reach {expected}; last query error: {last_error}"
    )


def stop_node(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def start_node(binary: str, home: Path, log_handle):
    env = os.environ.copy()
    env["CMTHOME"] = str(home)
    return subprocess.Popen(
        [binary, "node"],
        cwd=str(home.parent),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, help="path to pinned CometBFT v0.40.0 binary")
    parser.add_argument("--cometbft-source", required=True, help="cloned CometBFT v0.40.0 source tree")
    args = parser.parse_args()
    binary = str(Path(args.binary).resolve())
    cometbft_source = Path(args.cometbft_source).resolve()
    if not (cometbft_source / "go.mod").is_file():
        parser.error("--cometbft-source must be the v0.40.0 Go module root")
    if not Path(binary).is_file():
        parser.error("CometBFT binary does not exist")

    config = ProtocolConfig(
        network_id=NETWORK_ID,
        protocol_version=2,
        max_amount=1_000_000,
    )
    alice_key = Ed25519PrivateKey.generate()
    bob_key = Ed25519PrivateKey.generate()
    alice_public = public_key_b64(alice_key)
    bob_public = public_key_b64(bob_key)
    alice_id = account_id_for_public_key(alice_public, config=config)
    bob_id = account_id_for_public_key(bob_public, config=config)
    allocations = [
        {"account_id": alice_id, "public_key": alice_public, "amount": 600_000},
        {"account_id": bob_id, "public_key": bob_public, "amount": 400_000},
    ]
    allocations.sort(key=lambda item: item["account_id"])
    manifest = {
        "manifest_version": 1,
        "network_id": config.network_id,
        "protocol_version": config.protocol_version,
        "total_supply": 1_000_000,
        "allocations": allocations,
    }
    genesis_hash = genesis_manifest_hash(manifest)
    tx = create_signed_transaction(
        alice_key,
        config=config,
        sender=alice_id,
        recipient=bob_id,
        amount=TRANSFER_AMOUNT,
        nonce=0,
    )
    tx_bytes = canonical_json(tx)

    with tempfile.TemporaryDirectory(prefix="hnd-cometbft-v040-") as temp:
        root = Path(temp)
        home = root / "comet-home"
        home.mkdir()
        env = os.environ.copy()
        env["CMTHOME"] = str(home)

        initialized = subprocess.run(
            [binary, "init"],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if initialized.returncode != 0:
            raise RuntimeError(
                "CometBFT init failed:\n" + initialized.stdout + "\n" + initialized.stderr
            )

        genesis_path = home / "config" / "genesis.json"
        genesis = json.loads(genesis_path.read_text(encoding="utf-8"))
        genesis["chain_id"] = NETWORK_ID
        genesis["initial_height"] = "1"
        genesis["app_hash"] = ""
        genesis["app_state"] = {}
        app_state = canonical_json({
            "genesis_hash": genesis_hash,
            "manifest": manifest,
        }).decode("utf-8")
        genesis_text = json.dumps(genesis, indent=2)
        marker = '"app_state": {}'
        if marker not in genesis_text:
            raise RuntimeError("could not create exact canonical app_state in CometBFT Genesis")
        genesis_text = genesis_text.replace(marker, '"app_state": ' + app_state)
        genesis_path.write_text(genesis_text + "\n", encoding="utf-8")

        config_path = home / "config" / "config.toml"
        config_text = config_path.read_text(encoding="utf-8")
        config_text, abci_count = re.subn(
            r'(?m)^abci\s*=\s*"[^"]*"',
            'abci = "grpc"',
            config_text,
            count=1,
        )
        if abci_count != 1:
            raise RuntimeError("could not set CometBFT abci = grpc")
        config_text = re.sub(
            r'(?m)^proxy_app\s*=\s*"[^"]*"',
            'proxy_app = "127.0.0.1:26658"',
            config_text,
            count=1,
        )
        config_text = re.sub(
            r'(?m)^laddr\s*=\s*"tcp://0\.0\.0\.0:26656"',
            'laddr = "tcp://127.0.0.1:26656"',
            config_text,
            count=1,
        )
        config_path.write_text(config_text, encoding="utf-8")

        state_path = root / "hnd-application-state.json"
        app = HNDABCIApplication(
            config=config,
            manifest=manifest,
            expected_genesis_hash=genesis_hash,
            state_path=state_path,
        )
        server, _ = start_grpc_server(app, bind_address=ABCI_LISTEN, max_workers=16)
        # Prove the Python endpoint is reachable before CometBFT attempts its
        # own gRPC Echo handshake. This separates server readiness from node
        # startup/configuration failures.
        with grpc.insecure_channel(ABCI_LISTEN) as channel:
            preflight = types_pb2_grpc.ABCIStub(channel).Echo(
                types_pb2.RequestEcho(message="HND preflight"),
                timeout=5,
            )
        if preflight.message != "HND preflight":
            raise AssertionError("Python ABCI gRPC Echo preflight failed")
        print("HND_ABCI_GRPC_PREFLIGHT_OK", flush=True)

        # Probe with CometBFT's own Go gRPC stack and the same custom dialer
        # before launching the full node. This isolates protocol/transport
        # incompatibility from the node's startup and consensus lifecycle.
        probe = subprocess.run(
            [
                "go", "run",
                str(REPO_ROOT / "scripts" / "cometbft_v040_grpc_probe.go"),
                "127.0.0.1:26658",
            ],
            cwd=str(cometbft_source),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if probe.returncode != 0:
            raise RuntimeError(
                "CometBFT Go gRPC probe failed:\\n" + probe.stdout + "\\n" + probe.stderr
            )
        print(probe.stdout.strip(), flush=True)

        node_log = root / "cometbft-node.log"
        node_handle = node_log.open("w", encoding="utf-8")
        node = None
        try:
            node = start_node(binary, home, node_handle)
            status = wait_for_node(node, node_log)
            try:
                abci_info = rpc_get("/abci_info")
                print("HND_ABCI_INFO", json.dumps(abci_info, sort_keys=True), flush=True)
                before = query_account(alice_id)
            except Exception as exc:
                tail = node_log.read_text(encoding="utf-8", errors="replace")[-12000:]
                raise RuntimeError(f"ABCI query failed: {exc}\\nCometBFT node log tail:\\n{tail}") from exc
            if before["balance"] != INITIAL_ALICE_BALANCE:
                raise AssertionError(f"unexpected Genesis balance: {before}")

            broadcast = rpc_get(
                "/broadcast_tx_sync",
                {"tx": "0x" + tx_bytes.hex()},
            )
            check_tx = broadcast.get("result", {}).get("check_tx", {})
            if int(check_tx.get("code", 0)) != 0:
                raise RuntimeError(f"CometBFT rejected HND transaction: {broadcast}")

            after = wait_for_balance(alice_id, INITIAL_ALICE_BALANCE - TRANSFER_AMOUNT)
            height_after_tx = int(
                rpc_get("/status")["result"]["sync_info"]["latest_block_height"]
            )

            stop_node(node)
            node = None
            server.stop(grace=0).wait()

            # Simulate a Python application process restart from its durable state.
            restored_app = HNDABCIApplication(
                config=config,
                manifest=manifest,
                expected_genesis_hash=genesis_hash,
                state_path=state_path,
            )
            if restored_app.last_committed_height < 1:
                raise AssertionError("HND application did not restore a committed height")
            server, _ = start_grpc_server(
                restored_app, bind_address=ABCI_LISTEN, max_workers=16
            )

            node = start_node(binary, home, node_handle)
            restarted_status = wait_for_node(node, node_log)
            restored_account = wait_for_balance(
                alice_id, INITIAL_ALICE_BALANCE - TRANSFER_AMOUNT
            )
            if restored_account != after:
                raise AssertionError("account state changed across CometBFT/application restart")

            print(json.dumps({
                "result": "COMETBFT_V040_SINGLE_NODE_SMOKE_OK",
                "network_id": NETWORK_ID,
                "cometbft_initial_height": status["result"]["sync_info"]["latest_block_height"],
                "cometbft_height_after_transaction": height_after_tx,
                "cometbft_height_after_restart": restarted_status["result"]["sync_info"]["latest_block_height"],
                "hnd_committed_height_after_restart": restored_app.last_committed_height,
                "alice_balance_before": before["balance"],
                "alice_balance_after": after["balance"],
                "transfer_amount": TRANSFER_AMOUNT,
                "genesis_hash": genesis_hash,
                "application_state_hash": restored_app.committed_state_hash,
            }, sort_keys=True))
        finally:
            stop_node(node)
            server.stop(grace=0).wait()
            node_handle.close()


if __name__ == "__main__":
    main()
