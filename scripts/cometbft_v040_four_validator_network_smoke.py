"""Disposable four-validator CometBFT v0.40.0 integration smoke test."""
from __future__ import annotations
import argparse, base64, json, os, re, socket, subprocess, sys, tempfile, time
import urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.transaction import ProtocolConfig, account_id_for_public_key, canonical_json, create_signed_transaction, public_key_b64
from scripts.hnd_peer_relay import DirectedTCPRelay

CHAIN = "hnd-cometbft-v040-four-validator"
N, POWER, SUPPLY, ALICE, TRANSFER, BASE = 4, 10, 1_000_000, 600_000, 1237, 28600

def cmd(args, cwd=None):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=120)
    if p.returncode: raise RuntimeError(f"{args} failed\n{p.stdout}\n{p.stderr}")
    return p.stdout.strip()

def set_toml(text, section, key, value):
    lines, active, hits = text.splitlines(), None, []
    for i, line in enumerate(lines):
        m = re.match(r"^\s*\[([^]]+)\]", line)
        if m: active = m.group(1)
        if active == section and re.match(rf"^\s*{re.escape(key)}\s*=", line): hits.append(i)
    if len(hits) != 1: raise RuntimeError(f"TOML key {section}.{key}: expected 1, got {len(hits)}")
    lines[hits[0]] = f"{key} = {value}"
    return "\n".join(lines) + "\n"

def http(base, path, params=None):
    url = base + path + (("?" + urllib.parse.urlencode(params or {})) if params else "")
    with urllib.request.urlopen(url, timeout=3) as r: return json.loads(r.read())

def post(base, method, params):
    data = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req = urllib.request.Request(base+"/", data=data, headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r: return json.loads(r.read())

def stop(p):
    if p and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=10)
        except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=5)

def wait(predicate, label, timeout=120):
    end, last = time.monotonic()+timeout, None
    while time.monotonic()<end:
        try:
            value=predicate()
            if value: return value
        except Exception as e: last=e
        time.sleep(.3)
    raise TimeoutError(f"{label}; last={last!r}")

def rpc_status(url): return http(url, "/status")["result"]
def account(url, aid):
    r=http(url, "/abci_query", {"path":json.dumps("/account"),"data":json.dumps(aid),"prove":"false"})["result"]["response"]
    if int(r.get("code",0)): raise RuntimeError(r)
    return json.loads(base64.b64decode(r["value"]))
def app_hash(url):
    r=http(url, "/abci_info")["result"]["response"]["last_block_app_hash"]
    return r

def peer_ids(url):
    peers=http(url, "/net_info")["result"]["peers"]
    return {p["node_info"]["id"] for p in peers}

def partition_ready(urls, nodeids, groups):
    group_for={node: group_index for group_index, group in enumerate(groups) for node in group}
    for i, url in enumerate(urls):
        actual=peer_ids(url)
        allowed={nodeids[j] for j in range(N) if j != i and group_for[j] == group_for[i]}
        # Require the exact peer set, not merely the absence of known
        # cross-partition peers. This also proves every expected in-group
        # validator remains connected and rejects unexpected peer routes.
        if actual != allowed:
            return None
    return True

def set_partition(relays, groups):
    group_for={node: group_index for group_index, group in enumerate(groups) for node in group}
    for (source, target), relay in relays.items():
        if group_for[source] == group_for[target]:
            relay.enable()
        else:
            relay.disable()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",required=True); ap.add_argument("--cometbft-source",required=True)
    a=ap.parse_args(); binary=str(Path(a.binary).resolve()); source=Path(a.cometbft_source).resolve()
    if not Path(binary).is_file() or not (source/"go.mod").is_file(): ap.error("missing pinned CometBFT binary/source")
    cfg=ProtocolConfig(network_id=CHAIN,protocol_version=2,max_amount=SUPPLY)
    ak,bk=Ed25519PrivateKey.generate(),Ed25519PrivateKey.generate()
    apub,bpub=public_key_b64(ak),public_key_b64(bk)
    aid,bid=account_id_for_public_key(apub,config=cfg),account_id_for_public_key(bpub,config=cfg)
    alloc=sorted([{"account_id":aid,"public_key":apub,"amount":ALICE},{"account_id":bid,"public_key":bpub,"amount":SUPPLY-ALICE}],key=lambda x:x["account_id"])
    manifest={"manifest_version":1,"network_id":CHAIN,"protocol_version":2,"total_supply":SUPPLY,"allocations":alloc}
    gh=genesis_manifest_hash(manifest)
    appstate={"genesis_hash":gh,"manifest":manifest}
    tx=canonical_json(create_signed_transaction(ak,config=cfg,sender=aid,recipient=bid,amount=TRANSFER,nonce=0))
    with tempfile.TemporaryDirectory(prefix="hnd-four-validator-") as tmp:
        root=Path(tmp); mp=root/"manifest.json"; mp.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
        homes=[]; nodeids=[]; validators=[]
        for i in range(N):
            home=root/f"val{i+1}"; home.mkdir(); cmd([binary,"init","--home",str(home)])
            key=json.loads((home/"config/priv_validator_key.json").read_text())
            nodeids.append(cmd([binary,"show-node-id","--home",str(home)]))
            validators.append({"address":key["address"],"pub_key":key["pub_key"],"power":str(POWER),"name":f"hnd-val-{i+1}"})
            homes.append(home)
        if len(set(nodeids))!=N or len({v["address"] for v in validators})!=N: raise AssertionError("duplicate validator identity")
        genesis=json.loads((homes[0]/"config/genesis.json").read_text())
        genesis.update(chain_id=CHAIN,initial_height="1",validators=validators,app_hash="",app_state={})
        gtext=json.dumps(genesis,indent=2)
        if '"app_state": {}' not in gtext: raise RuntimeError("Genesis app_state placeholder not found")
        gbytes=(gtext.replace('"app_state": {}','"app_state": '+canonical_json(appstate).decode())+"\n").encode()
        for h in homes: (h/"config/genesis.json").write_bytes(gbytes)
        eps=[{"p2p":f"127.0.0.1:{BASE+3*i}","rpc":f"http://127.0.0.1:{BASE+3*i+1}","abci":f"127.0.0.1:{BASE+3*i+2}"} for i in range(N)]
        relays={}
        try:
            for i in range(N):
                for j in range(N):
                    if i != j:
                        target_host, target_port=eps[j]["p2p"].split(":")
                        relays[(i,j)]=DirectedTCPRelay(target_host,int(target_port))
        except Exception:
            for relay in relays.values(): relay.close()
            raise
        for i,h in enumerate(homes):
            p=h/"config/config.toml"; t=p.read_text()
            t=set_toml(t,None,"proxy_app",json.dumps(eps[i]["abci"]))
            t=set_toml(t,None,"abci",'"grpc"')
            t=set_toml(t,"rpc","laddr",json.dumps("tcp://"+eps[i]["rpc"].split("://")[1]))
            t=set_toml(t,"p2p","laddr",json.dumps("tcp://"+eps[i]["p2p"]))
            peers=",".join(f"{nodeids[j]}@127.0.0.1:{relays[(i,j)].address[1]}" for j in range(N) if j!=i)
            t=set_toml(t,"p2p","persistent_peers",json.dumps(peers))
            t=set_toml(t,"p2p","pex","false")
            t=set_toml(t,"p2p","addr_book_strict","false")
            t=set_toml(t,"p2p","allow_duplicate_ip","true")
            p.write_text(t)
        apps=[None]*N; nodes=[None]*N; ah=[]; nh=[]
        try:
            for i,h in enumerate(homes):
                al=(root/f"app{i+1}.log").open("w"); nl=(root/f"node{i+1}.log").open("w"); ah.append(al); nh.append(nl)
                state=root/f"state{i+1}.json"
                apps[i]=subprocess.Popen([sys.executable,"-m","hnd_v02.cometbft_v040_server","--manifest",str(mp),"--genesis-hash",gh,"--network-id",CHAIN,"--protocol-version","2","--max-amount",str(SUPPLY),"--state-path",str(state),"--listen",eps[i]["abci"]],cwd=ROOT,stdout=al,stderr=subprocess.STDOUT)
                host,port=eps[i]["abci"].split(":")
                wait(lambda: socket.create_connection((host,int(port)),timeout=.4).close() is None if apps[i].poll() is None else False,f"ABCI app {i+1} startup",30)
            for i,h in enumerate(homes):
                env=os.environ.copy(); env["CMTHOME"]=str(h)
                nodes[i]=subprocess.Popen([binary,"node","--home",str(h)],cwd=root,env=env,stdout=nh[i],stderr=subprocess.STDOUT)
            def converged(urls, minheight=1):
                s=[rpc_status(u) for u in urls]; heights=[int(x["sync_info"]["latest_block_height"]) for x in s]; hashes=[x["sync_info"]["latest_block_hash"] for x in s]
                return s if min(heights)>=minheight and len(set(heights))==1 and len(set(hashes))==1 else None
            urls=[e["rpc"] for e in eps]
            s0=wait(lambda:converged(urls),"four nodes initial consensus")
            h0=int(s0[0]["sync_info"]["latest_block_height"])
            if any(x["node_info"]["network"]!=CHAIN for x in s0): raise AssertionError("chain ID mismatch")
            if any(account(u,aid)["balance"]!=ALICE for u in urls): raise AssertionError("Genesis balances differ")
            b=post(urls[0],"broadcast_tx_sync",{"tx":base64.b64encode(tx).decode()})["result"]
            if int(b.get("code",0)): raise RuntimeError(f"CheckTx rejected: {b}")
            def tx_all():
                s=converged(urls,h0+1); ac=[account(u,aid) for u in urls] if s else []
                ahashes=[app_hash(u) for u in urls] if s else []
                return (s,ac,ahashes) if s and all(x["balance"]==ALICE-TRANSFER for x in ac) and len(set(ahashes))==1 else None
            s1,ac1,hashes1=wait(tx_all,"transaction committed identically on four nodes")
            txheight=int(s1[0]["sync_info"]["latest_block_height"]); txblock=s1[0]["sync_info"]["latest_block_hash"]
            if any(account(u,bid)["balance"]!=SUPPLY-ALICE+TRANSFER for u in urls): raise AssertionError("recipient balances differ")
            # Stop one node and its app; 3/4 voting power remains.
            stop(nodes[3]); nodes[3]=None; stop(apps[3]); apps[3]=None
            s3=wait(lambda:converged(urls[:3],txheight+1),"three validators commit after one stops")
            qheight=int(s3[0]["sync_info"]["latest_block_height"])
            # Restart the lagging app from its own state, then the CometBFT node.
            al=ah[3]; apps[3]=subprocess.Popen([sys.executable,"-m","hnd_v02.cometbft_v040_server","--manifest",str(mp),"--genesis-hash",gh,"--network-id",CHAIN,"--protocol-version","2","--max-amount",str(SUPPLY),"--state-path",str(root/"state4.json"),"--listen",eps[3]["abci"]],cwd=ROOT,stdout=al,stderr=subprocess.STDOUT)
            host,port=eps[3]["abci"].split(":")
            wait(lambda: socket.create_connection((host,int(port)),timeout=.4).close() is None if apps[3].poll() is None else False,"restarted ABCI app",30)
            env=os.environ.copy(); env["CMTHOME"]=str(homes[3])
            nodes[3]=subprocess.Popen([binary,"node","--home",str(homes[3])],cwd=root,env=env,stdout=nh[3],stderr=subprocess.STDOUT)
            sfinal=wait(lambda:converged(urls,qheight),"restarted validator catch-up",150)
            final_accounts=[account(u,aid) for u in urls]; final_apphash=[app_hash(u) for u in urls]
            if any(x["balance"]!=ALICE-TRANSFER for x in final_accounts) or len(set(final_apphash))!=1: raise AssertionError("post-restart HND state diverged")
            # WP4.7-A: isolate validator 4 while all four node/app processes remain alive.
            partition_groups_31=[[0,1,2],[3]]
            set_partition(relays,partition_groups_31)
            wait(lambda:partition_ready(urls,nodeids,partition_groups_31),"3/1 peer isolation")
            baseline31=[rpc_status(u) for u in urls]
            baseheight31=int(baseline31[0]["sync_info"]["latest_block_height"])
            baseblock31=baseline31[0]["sync_info"]["latest_block_hash"]
            baseapp31=[app_hash(u) for u in urls]
            basealice31=account(urls[3],aid)["balance"]
            part_tx=canonical_json(create_signed_transaction(ak,config=cfg,sender=aid,recipient=bid,amount=77,nonce=1))
            part_broadcast=post(urls[0],"broadcast_tx_sync",{"tx":base64.b64encode(part_tx).decode()})["result"]
            if int(part_broadcast.get("code",0)): raise RuntimeError(f"3/1 partition CheckTx rejected: {part_broadcast}")
            def three_commit_isolated():
                side=converged(urls[:3],baseheight31+1)
                if not side: return None
                isolated=rpc_status(urls[3])
                if int(isolated["sync_info"]["latest_block_height"]) != baseheight31: return None
                if isolated["sync_info"]["latest_block_hash"] != baseblock31: return None
                if account(urls[3],aid)["balance"] != basealice31: return None
                if app_hash(urls[3]) != baseapp31[3]: return None
                if any(account(u,aid)["balance"] != ALICE-TRANSFER-77 for u in urls[:3]): return None
                if any(account(u,bid)["balance"] != SUPPLY-ALICE+TRANSFER+77 for u in urls[:3]): return None
                return side
            side31=wait(three_commit_isolated,"3/1 quorum commit with isolated validator stalled",150)
            if not all(p and p.poll() is None for p in nodes+apps):
                raise AssertionError("a validator or ABCI app process exited during 3/1 partition")
            print(json.dumps({"result":"COMETBFT_V040_3_1_PARTITION_OK","partition":[3,1],"all_four_processes_alive":True,"quorum_height":int(side31[0]["sync_info"]["latest_block_height"]),"isolated_height":baseheight31,"isolated_state_unchanged":True},sort_keys=True),flush=True)

            # Restore the full mesh and require the isolated validator to catch up.
            set_partition(relays,[[0,1,2,3]])
            wait(lambda:partition_ready(urls,nodeids,[[0,1,2,3]]),"3/1 reconnection peer mesh",90)
            def reconnect31():
                state=converged(urls,int(side31[0]["sync_info"]["latest_block_height"]))
                if not state: return None
                if any(account(u,aid)["balance"] != ALICE-TRANSFER-77 for u in urls): return None
                if any(account(u,bid)["balance"] != SUPPLY-ALICE+TRANSFER+77 for u in urls): return None
                hashes=[app_hash(u) for u in urls]
                return (state,hashes) if len(set(hashes))==1 else None
            reconnected31,hashes31=wait(reconnect31,"all validators converge after 3/1 reconnection",150)
            print(json.dumps({"result":"COMETBFT_V040_PARTITION_RECONNECTION_OK","scenario":"3/1","height":int(reconnected31[0]["sync_info"]["latest_block_height"]),"block_hash":reconnected31[0]["sync_info"]["latest_block_hash"],"application_hash":hashes31[0],"all_four_converged":True},sort_keys=True),flush=True)

            # WP4.7-B: 2/2 partition; neither half has the required 30/40 voting power.
            partition_groups_22=[[0,1],[2,3]]
            set_partition(relays,partition_groups_22)
            wait(lambda:partition_ready(urls,nodeids,partition_groups_22),"2/2 peer isolation")
            baseline22=[rpc_status(u) for u in urls]
            heights22=[int(x["sync_info"]["latest_block_height"]) for x in baseline22]
            blocks22=[x["sync_info"]["latest_block_hash"] for x in baseline22]
            apps22=[app_hash(u) for u in urls]
            time.sleep(12)
            after22=[rpc_status(u) for u in urls]
            if [int(x["sync_info"]["latest_block_height"]) for x in after22] != heights22: raise AssertionError("2/2 partition unexpectedly advanced a validator height")
            if [x["sync_info"]["latest_block_hash"] for x in after22] != blocks22: raise AssertionError("2/2 partition changed a validator block hash")
            if [app_hash(u) for u in urls] != apps22: raise AssertionError("2/2 partition changed HND application state")
            if not all(p and p.poll() is None for p in nodes+apps):
                raise AssertionError("a validator or ABCI app process exited during 2/2 partition")
            print(json.dumps({"result":"COMETBFT_V040_2_2_PARTITION_OK","partition":[2,2],"observation_seconds":12,"heights_unchanged":True,"block_hashes_unchanged":True,"application_hashes_unchanged":True,"all_four_processes_alive":True},sort_keys=True),flush=True)

            # Reconnect and verify the full mesh and committed HND state remain identical.
            set_partition(relays,[[0,1,2,3]])
            wait(lambda:partition_ready(urls,nodeids,[[0,1,2,3]]),"2/2 reconnection peer mesh",90)
            def final_partition_convergence():
                state=converged(urls,max(heights22))
                if not state: return None
                ahashes=[app_hash(u) for u in urls]
                if len(set(ahashes))!=1: return None
                if any(account(u,aid)["balance"] != ALICE-TRANSFER-77 for u in urls): return None
                if any(account(u,bid)["balance"] != SUPPLY-ALICE+TRANSFER+77 for u in urls): return None
                return (state,ahashes)
            final22,final22_hashes=wait(final_partition_convergence,"2/2 reconnection convergence",150)
            print(json.dumps({"result":"COMETBFT_V040_PARTITION_RECONNECTION_OK","scenario":"2/2","height":int(final22[0]["sync_info"]["latest_block_height"]),"block_hash":final22[0]["sync_info"]["latest_block_hash"],"application_hash":final22_hashes[0],"all_four_converged":True},sort_keys=True),flush=True)

            print(json.dumps({"result":"COMETBFT_V040_FOUR_VALIDATOR_NETWORK_OK","chain_id":CHAIN,"validators":N,"voting_power_each":POWER,"initial_height":h0,"transaction_height":txheight,"transaction_block_hash":txblock,"application_hash_after_transaction":hashes1[0],"alice_balance_after":final_accounts[0]["balance"],"bob_balance_after":account(urls[0],bid)["balance"],"transfer":TRANSFER,"height_with_one_validator_stopped":qheight,"height_after_catchup":int(sfinal[0]["sync_info"]["latest_block_height"]),"final_block_hash":sfinal[0]["sync_info"]["latest_block_hash"],"all_four_nodes_converged":True,"temporary_keys_and_state_only":True,"scope":"local four-validator crash-stop integration; not Byzantine fault proof"},sort_keys=True),flush=True)
        finally:
            for p in nodes: stop(p)
            for p in apps: stop(p)
            for relay in relays.values(): relay.close()
            for f in ah+nh: f.close()

if __name__=="__main__": main()
