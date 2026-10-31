import base64, hashlib, json, os, tempfile
from dataclasses import dataclass, asdict
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SUPPLY = 1_000_000

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def b64e(b): return base64.b64encode(b).decode()
def b64d(s): return base64.b64decode(s.encode())

def tx_payload(tx):
    return {k: tx[k] for k in ("sender", "recipient", "amount", "nonce")}

def tx_id(tx):
    return hashlib.sha256(canonical(tx_payload(tx))).hexdigest()

@dataclass
class Account:
    balance: int
    nonce: int = 0
    public_key: str = ""

class Wallet:
    def __init__(self):
        self._private = Ed25519PrivateKey.generate()
        self.public_key = b64e(self._private.public_key().public_bytes_raw())
    def sign(self, tx):
        return b64e(self._private.sign(canonical(tx_payload(tx))))

class HNDLedger:
    def __init__(self, initial_supply=SUPPLY):
        if initial_supply != SUPPLY:
            raise ValueError("fixed supply")
        self.initial_supply = initial_supply
        self.accounts = {}
        self.accepted = set()
        self.history = []
        self.state_hash = self._calc_state_hash()
        self.accounts["GENESIS"] = Account(initial_supply, 0, "")
        self.state_hash = self._calc_state_hash()

    def create_account(self, name, balance=0, wallet=None):
        if name in self.accounts: raise ValueError("account exists")
        if balance != 0: raise ValueError("only genesis allocation may create supply")
        wallet = wallet or Wallet()
        self.accounts[name] = Account(0, 0, wallet.public_key)
        return wallet

    def _calc_state_hash(self):
        state = {"accounts": {k: asdict(v) for k,v in sorted(self.accounts.items())}, "history": list(self.history)}
        return hashlib.sha256(canonical(state)).hexdigest()

    def _total_supply(self): return sum(a.balance for a in self.accounts.values())

    def validate(self, tx):
        required = {"sender","recipient","amount","nonce","signature"}
        if set(tx) != required: return False, "schema"
        if not isinstance(tx["amount"], int) or tx["amount"] <= 0: return False, "amount"
        if tx["sender"] not in self.accounts or tx["recipient"] not in self.accounts: return False, "account"
        if tx["sender"] == tx["recipient"]: return False, "self-transfer"
        sender = self.accounts[tx["sender"]]
        if tx["nonce"] != sender.nonce: return False, "nonce"
        if tx["amount"] > sender.balance: return False, "balance"
        if tx_id(tx) in self.accepted: return False, "replay"
        if not sender.public_key: return False, "signature"
        try:
            Ed25519PublicKey.from_public_bytes(b64d(sender.public_key)).verify(b64d(tx["signature"]), canonical(tx_payload(tx)))
        except Exception:
            return False, "signature"
        return True, "ok"

    def apply(self, tx):
        ok, reason = self.validate(tx)
        if not ok: return False, reason
        before = self._total_supply()
        self.accounts[tx["sender"]].balance -= tx["amount"]
        self.accounts[tx["sender"]].nonce += 1
        self.accounts[tx["recipient"]].balance += tx["amount"]
        self.accepted.add(tx_id(tx)); self.history.append(tx_id(tx))
        self.state_hash = self._calc_state_hash()
        if self._total_supply() != before or self._total_supply() != self.initial_supply:
            raise RuntimeError("supply invariant violated")
        return True, "accepted"

    def snapshot(self):
        return {"initial_supply": self.initial_supply, "accounts": {k: asdict(v) for k,v in self.accounts.items()}, "accepted": sorted(self.accepted), "history": self.history, "state_hash": self.state_hash}

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f: json.dump(self.snapshot(), f, sort_keys=True, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f: data=json.load(f)
        obj=cls(data["initial_supply"]); obj.accounts={k:Account(**v) for k,v in data["accounts"].items()}; obj.accepted=set(data["accepted"]); obj.history=data["history"]; obj.state_hash=obj._calc_state_hash()
        if obj.state_hash != data["state_hash"]: raise ValueError("state hash mismatch")
        if obj._total_supply() != obj.initial_supply: raise ValueError("supply invariant")
        return obj

def make_tx(sender, recipient, amount, nonce, wallet):
    tx={"sender":sender,"recipient":recipient,"amount":amount,"nonce":nonce,"signature":""}
    tx["signature"] = wallet.sign(tx)
    return tx

class AdaptiveConsensusSimulator:
    def __init__(self, quorum=3): self.quorum=quorum
    def commit(self, proposals):
        canonical_proposals = [json.dumps(p, sort_keys=True, separators=(",", ":")) for p in proposals]
        if not canonical_proposals: raise ValueError("no proposals")
        counts={p:canonical_proposals.count(p) for p in set(canonical_proposals)}
        winner,count=max(counts.items(), key=lambda x:(x[1],x[0]))
        if count < self.quorum: raise ValueError("quorum")
        if sum(v >= self.quorum for v in counts.values()) != 1: raise ValueError("conflicting quorum")
        return json.loads(winner)

if __name__ == "__main__":
    l=HNDLedger(); wa=l.create_account("ALICE"); wb=l.create_account("BOB")
    # Genesis allocation is the only supply creation path.
    l.accounts["ALICE"].balance=100_000
    l.accounts["GENESIS"].balance-=100_000
    print("ALICE:", l.accounts["ALICE"].balance)
    print("Transfer:", l.apply(make_tx("ALICE","BOB",10_000,0,wa)))
    print("ALICE:", l.accounts["ALICE"].balance)
    print("BOB:", l.accounts["BOB"].balance)