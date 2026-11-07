"""Run the pinned CometBFT P2P equivocation regression against four live HND ABCI apps.

The upstream consensus test is patched only in a disposable checkout for this
process. Its actual VoteChannel equivocation injection and evidence-pool path
remain intact. The source file is restored even when the test fails.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import ProtocolConfig, account_id_for_public_key, public_key_b64
from hnd_v02.cometbft_v040_server import start_grpc_server, types_pb2, types_pb2_grpc
from hnd_v02.abci_app import HNDABCIApplication
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import grpc


def reserve_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def wait_port(port, process, label, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited early with {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"{label} did not open loopback port {port}")


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def grpc_query(port, path, data=b""):
    with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
        grpc.channel_ready_future(channel).result(timeout=10)
        stub = types_pb2_grpc.ABCIStub(channel)
        response = stub.Query(types_pb2.RequestQuery(path=path, data=data), timeout=10)
        if response.code:
            raise RuntimeError(f"ABCI Query {path} failed: {response.log}")
        return response.value


def grpc_info(port):
    with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
        grpc.channel_ready_future(channel).result(timeout=10)
        return types_pb2_grpc.ABCIStub(channel).Info(types_pb2.RequestInfo(), timeout=10)


def assert_source_pin(source):
    # CI fetches the immutable commit directly with --depth 1, which does not
    # include tag refs. Verify the exact source commit rather than requiring
    # local tag metadata that is intentionally absent from a shallow fetch.
    expected = "0880b4d378f347ab16e54ec677ff50d803f37d62"
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source, check=True, capture_output=True, text=True,
    ).stdout.strip()
    if actual != expected:
        raise RuntimeError(
            f"Expected pinned CometBFT commit {expected}, found {actual}"
        )


def patch_upstream_test(source_file):
    original = source_file.read_text()
    patched = original
    anchors = [
        "appFunc := newKVStore",
        "\t\tapp := appFunc()\n\t\tvals := types.TM2PB.ValidatorUpdates(state.Validators)\n\t\t_, err := app.InitChain(context.Background(), &abci.RequestInitChain{Validators: vals})\n\t\trequire.NoError(t, err)\n",
        "\t\tmtx := new(cmtsync.Mutex)\n\t\t// one for mempool, one for consensus\n\t\tproxyAppConnCon := proxy.NewAppConnConsensus(abcicli.NewLocalClient(mtx, app), proxy.NopMetrics())\n\t\tproxyAppConnMem := proxy.NewAppConnMempool(abcicli.NewLocalClient(mtx, app), proxy.NopMetrics())\n",
        "\t\tstate, _ := stateStore.LoadFromDBOrGenesisDoc(genDoc)\n",
    ]
    for anchor in anchors:
        if patched.count(anchor) != 1:
            raise RuntimeError(f"Expected exactly one upstream source anchor, found {patched.count(anchor)}: {anchor[:90]!r}")

    patched = patched.replace("appFunc := newKVStore", "")
    unused_import = '\tcmtsync "github.com/cometbft/cometbft/libs/sync"\n'
    if patched.count(unused_import) != 1:
        raise RuntimeError("Could not uniquely locate obsolete local-client mutex import")
    patched = patched.replace(unused_import, "")
    patched = patched.replace(
        "\t\tstate, _ := stateStore.LoadFromDBOrGenesisDoc(genDoc)\n",
        "\t\tstate, _ := stateStore.LoadFromDBOrGenesisDoc(genDoc)\n",
        1,
    )
    patched = patched.replace(
        "\tappFunc := newKVStore\n",
        "\tgenDoc.ChainID = os.Getenv(\"HND_CHAIN_ID\")\n",
        1,
    )
    init_anchor = anchors[1]
    init_replacement = """\t\tvals := types.TM2PB.ValidatorUpdates(state.Validators)
\t\tappCon := abcicli.NewGRPCClient(os.Getenv(fmt.Sprintf("HND_ABCI_ADDR_%d", i)), true)
\t\tappMem := abcicli.NewGRPCClient(os.Getenv(fmt.Sprintf("HND_ABCI_ADDR_%d", i)), true)
\t\trequire.NoError(t, appCon.Start())
\t\trequire.NoError(t, appMem.Start())
\t\tdefer func() { _ = appCon.Stop(); _ = appMem.Stop() }()
\t\t_, err := appCon.InitChain(context.Background(), &abci.RequestInitChain{
\t\t\tChainId: os.Getenv("HND_CHAIN_ID"),
\t\t\tAppStateBytes: []byte(os.Getenv("HND_APP_STATE_JSON")),
\t\t\tValidators: vals,
\t\t})
\t\trequire.NoError(t, err)
"""
    patched = patched.replace(init_anchor, init_replacement, 1)
    patched = patched.replace(anchors[2], """\t\tproxyAppConnCon := proxy.NewAppConnConsensus(appCon, proxy.NopMetrics())
\t\tproxyAppConnMem := proxy.NewAppConnMempool(appMem, proxy.NopMetrics())
""", 1)

    # The upstream function's original genesis document must use the HND chain
    # identifier so signatures and ABCI requests share one chain identity.
    marker = "\tgenDoc, privVals := randGenesisDoc(nValidators, false, 30, nil)\n"
    if patched.count(marker) != 1:
        raise RuntimeError("Could not uniquely locate upstream genesis construction")
    patched = patched.replace(marker, marker + "\tgenDoc.ChainID = os.Getenv(\"HND_CHAIN_ID\")\n", 1)

    source_file.write_text(patched)
    return original


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cometbft-source", required=True)
    args = parser.parse_args()
    source = Path(args.cometbft_source).resolve()
    if not (source / "go.mod").is_file():
        parser.error("CometBFT source directory is missing go.mod")
    assert_source_pin(source)

    test_file = source / "consensus" / "byzantine_test.go"
    original = patch_upstream_test(test_file)
    cfg = ProtocolConfig("hnd-cometbft-v040-p2p-evidence", 2, 1_000_000)
    key_a, key_b = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    pub_a, pub_b = public_key_b64(key_a), public_key_b64(key_b)
    allocations = sorted([
        {"account_id": account_id_for_public_key(pub_a, config=cfg), "public_key": pub_a, "amount": 600_000},
        {"account_id": account_id_for_public_key(pub_b, config=cfg), "public_key": pub_b, "amount": 400_000},
    ], key=lambda item: item["account_id"])
    manifest = {
        "manifest_version": 1, "network_id": cfg.network_id,
        "protocol_version": 2, "total_supply": 1_000_000,
        "allocations": allocations,
    }
    genesis_hash = genesis_manifest_hash(manifest)
    app_state_json = json.dumps(
        {
            "genesis_hash": genesis_hash,
            "manifest": manifest,
            "protocol_config": {
                "network_id": cfg.network_id,
                "protocol_version": cfg.protocol_version,
                "max_amount": cfg.max_amount,
            },
        },
        sort_keys=True, separators=(",", ":"),
    )
    with tempfile.TemporaryDirectory(prefix="hnd-wp4-11-") as temp:
        root = Path(temp)
        (root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        ports = [reserve_port() for _ in range(4)]
        apps = []
        logs = []
        try:
            for i, port in enumerate(ports):
                state_path = root / f"replica-{i}.json"
                log = (root / f"app-{i}.log").open("w")
                logs.append(log)
                process = subprocess.Popen(
                    [
                        sys.executable, "-m", "hnd_v02.cometbft_v040_server",
                        "--manifest", str(root / "manifest.json"),
                        "--genesis-hash", genesis_hash,
                        "--network-id", cfg.network_id,
                        "--protocol-version", "2",
                        "--max-amount", str(cfg.max_amount),
                        "--state-path", str(state_path),
                        "--listen", f"127.0.0.1:{port}",
                    ],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                )
                apps.append((process, port, state_path, log))
                wait_port(port, process, f"HND ABCI replica {i}")
            env = os.environ.copy()
            env["HND_CHAIN_ID"] = cfg.network_id
            env["HND_APP_STATE_JSON"] = app_state_json
            for i, port in enumerate(ports):
                env[f"HND_ABCI_ADDR_{i}"] = f"127.0.0.1:{port}"
            result = subprocess.run(
                ["go", "test", "./consensus", "-run", "^TestByzantinePrevoteEquivocation$", "-count=1", "-v"],
                cwd=source, env=env, text=True, capture_output=True, timeout=180,
            )
            print(result.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            if result.returncode:
                raise RuntimeError(f"Pinned P2P Byzantine integration failed: {result.returncode}")

            journals, hashes, heights = [], [], []
            for port in ports:
                journal = grpc_query(port, "/evidence")
                info = grpc_info(port)
                journals.append(journal)
                hashes.append(info.last_block_app_hash)
                heights.append(info.last_block_height)
            if len(set(journals)) != 1:
                raise AssertionError("Four HND evidence journals differ")
            if len(set(hashes)) != 1 or any(len(value) != 32 for value in hashes):
                raise AssertionError("Four HND application hashes differ or are not 32 bytes")
            if len(set(heights)) != 1 or heights[0] < 3:
                raise AssertionError(f"Four HND apps did not converge after evidence: {heights}")
            decoded = json.loads(journals[0])
            evidence = decoded.get("evidence", [])
            if len(evidence) != 1:
                raise AssertionError(f"Expected one evidence record, found {len(evidence)}")
            if evidence[0].get("type") != 1:
                raise AssertionError(f"Expected duplicate-vote type 1, got {evidence[0].get('type')}")

            # Compare balances on every replica against the common genesis.
            for allocation in allocations:
                account_id = allocation["account_id"]
                expected = allocation["amount"]
                for port in ports:
                    value = json.loads(grpc_query(port, "/account", account_id.encode()))
                    if value.get("balance") != expected:
                        raise AssertionError(f"Evidence handling changed balance for {account_id}")

            # Restart the first HND app against its durable state and recheck.
            first, first_port, first_state, first_log = apps[0]
            stop(first)
            first_log.close()
            replacement_log = (root / "app-0-restart.log").open("w")
            logs.append(replacement_log)
            replacement = subprocess.Popen(
                [
                    sys.executable, "-m", "hnd_v02.cometbft_v040_server",
                    "--manifest", str(root / "manifest.json"),
                    "--genesis-hash", genesis_hash,
                    "--network-id", cfg.network_id,
                    "--protocol-version", "2",
                    "--max-amount", str(cfg.max_amount),
                    "--state-path", str(first_state),
                    "--listen", f"127.0.0.1:{first_port}",
                ],
                cwd=ROOT, stdout=replacement_log, stderr=subprocess.STDOUT,
            )
            apps[0] = (replacement, first_port, first_state, replacement_log)
            wait_port(first_port, replacement, "restarted HND ABCI replica")
            restarted_journal = grpc_query(first_port, "/evidence")
            restarted_info = grpc_info(first_port)
            if restarted_journal != journals[0] or restarted_info.last_block_app_hash != hashes[0]:
                raise AssertionError("Restarted HND app did not restore its evidence journal and app hash")
            if restarted_info.last_block_height != heights[0]:
                raise AssertionError("Restarted HND app height changed")
            print(json.dumps({
                "marker": "HND_WP4_11_P2P_EVIDENCE_REPLICAS_OK",
                "chain_id": cfg.network_id,
                "evidence_count": len(evidence),
                "evidence_height": evidence[0].get("height"),
                "commit_height": heights[0],
                "app_hash": hashes[0].hex(),
                "replicas": 4,
                "restart_verified": True,
                "balances_unchanged": True,
            }, sort_keys=True))
        finally:
            for process, _, _, _ in apps:
                stop(process)
            for log in logs:
                try:
                    log.close()
                except Exception:
                    pass
            test_file.write_text(original)


if __name__ == "__main__":
    main()
