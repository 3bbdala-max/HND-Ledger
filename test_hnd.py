import os, tempfile, unittest
from hnd_prototype import HNDLedger, Wallet, make_tx, AdaptiveConsensusSimulator, SUPPLY

class TestHND(unittest.TestCase):
    def setUp(self):
        self.l=HNDLedger(); self.wa=self.l.create_account("ALICE"); self.wb=self.l.create_account("BOB")
        self.l.accounts["GENESIS"].balance -= 1000; self.l.accounts["ALICE"].balance += 1000

    def tx(self,a,b,n,nonce=0): return make_tx(a,b,n,nonce,self.wa if a=="ALICE" else self.wb)
    def test_valid_transfer(self): self.assertTrue(self.l.apply(self.tx("ALICE","BOB",100))[0])
    def test_replay_rejected(self):
        t=self.tx("ALICE","BOB",100); self.assertTrue(self.l.apply(t)[0]); self.assertFalse(self.l.apply(t)[0])
    def test_wrong_nonce(self): self.assertFalse(self.l.apply(self.tx("ALICE","BOB",100,9))[0])
    def test_insufficient_balance(self): self.assertFalse(self.l.apply(self.tx("ALICE","BOB",9999))[0])
    def test_tampered_signature(self):
        t=self.tx("ALICE","BOB",100); t["amount"]=900; self.assertEqual(self.l.apply(t)[1],"signature")
    def test_no_supply_creation(self):
        with self.assertRaises(ValueError): self.l.create_account("X",500000)
        self.assertEqual(sum(a.balance for a in self.l.accounts.values()),SUPPLY)
    def test_state_hash_changes_and_persists(self):
        h=self.l.state_hash; self.l.apply(self.tx("ALICE","BOB",100)); self.assertNotEqual(h,self.l.state_hash)
        with tempfile.TemporaryDirectory() as d:
            p=os.path.join(d,"state.json"); self.l.save(p); r=HNDLedger.load(p); self.assertEqual(r.state_hash,self.l.state_hash); self.assertEqual(r.accounts["BOB"].balance,100)
    def test_tampered_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=os.path.join(d,"state.json"); self.l.save(p)
            with open(p, encoding="utf-8") as f: s=f.read().replace('"balance": 1000','"balance": 999')
            with open(p, "w", encoding="utf-8") as f: f.write(s)
            with self.assertRaises(ValueError): HNDLedger.load(p)
    def test_concurrent_nonce_conflict(self):
        a=self.tx("ALICE","BOB",100); b=self.tx("ALICE","BOB",200); self.assertTrue(self.l.apply(a)[0]); self.assertFalse(self.l.apply(b)[0])
    def test_supply_constant_500(self):
        for i in range(500):
            src="ALICE" if i%2==0 else "BOB"; dst="BOB" if src=="ALICE" else "ALICE"; w=self.wa if src=="ALICE" else self.wb; self.assertTrue(self.l.apply(make_tx(src,dst,1,self.l.accounts[src].nonce,w))[0])
        self.assertEqual(sum(a.balance for a in self.l.accounts.values()),SUPPLY)
    def test_deterministic_consensus(self):
        c=AdaptiveConsensusSimulator(3); p={"state":1}; self.assertEqual(c.commit([p,p,p]),p)
    def test_conflicting_consensus(self):
        c=AdaptiveConsensusSimulator(3)
        with self.assertRaises(ValueError): c.commit([{"state":1}]*3+[ {"state":2}]*3)

if __name__=='__main__': unittest.main(verbosity=2)