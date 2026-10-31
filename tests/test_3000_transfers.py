import unittest

from hnd_prototype import HNDLedger, SUPPLY, make_tx


class TestThreeThousandTransfers(unittest.TestCase):
    def test_3000_signed_sequential_transfers_preserve_supply(self):
        ledger = HNDLedger()
        alice_wallet = ledger.create_account("ALICE")
        bob_wallet = ledger.create_account("BOB")

        allocation_per_account = 10_000
        ledger.accounts["GENESIS"].balance -= 2 * allocation_per_account
        ledger.accounts["ALICE"].balance += allocation_per_account
        ledger.accounts["BOB"].balance += allocation_per_account
        ledger.state_hash = ledger._calc_state_hash()

        initial_supply = ledger._total_supply()
        initial_state_hash = ledger.state_hash

        for index in range(3_000):
            if index % 2 == 0:
                sender, recipient, wallet = "ALICE", "BOB", alice_wallet
            else:
                sender, recipient, wallet = "BOB", "ALICE", bob_wallet

            nonce = ledger.accounts[sender].nonce
            transaction = make_tx(sender, recipient, 1, nonce, wallet)
            accepted, reason = ledger.apply(transaction)
            self.assertTrue(accepted, msg=f"transfer {index + 1} rejected: {reason}")

        self.assertEqual(ledger._total_supply(), initial_supply)
        self.assertEqual(ledger._total_supply(), SUPPLY)
        self.assertEqual(len(ledger.history), 3_000)
        self.assertEqual(len(ledger.accepted), 3_000)
        self.assertEqual(ledger.accounts["ALICE"].nonce, 1_500)
        self.assertEqual(ledger.accounts["BOB"].nonce, 1_500)
        self.assertNotEqual(ledger.state_hash, initial_state_hash)
        self.assertEqual(ledger.state_hash, ledger._calc_state_hash())


if __name__ == "__main__":
    unittest.main(verbosity=2)
