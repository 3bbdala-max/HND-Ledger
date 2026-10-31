"""Characterization tests for known v0.1 type-validation weaknesses.

These are diagnostic exposure tests, NOT security/conformance tests.
The bool/float nonce and bool amount tests intentionally pass only while
v0.1 retains its current permissive Python type/equality behavior. Keep this
suite separate from the normal v0.1 baseline tests; do not interpret a green
run as evidence that the behavior is safe.
"""
from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from hnd_prototype import HNDLedger, make_tx, SUPPLY  # noqa: E402


class TestV01TypeValidationExposure(unittest.TestCase):
    def setUp(self):
        self.ledger = HNDLedger()
        self.alice = self.ledger.create_account("ALICE")
        self.bob = self.ledger.create_account("BOB")
        self.ledger.accounts["GENESIS"].balance -= 1_000
        self.ledger.accounts["ALICE"].balance += 1_000

    def signed_tx(self, amount, nonce):
        return make_tx("ALICE", "BOB", amount, nonce, self.alice)

    def advance_alice_nonce_to_one(self):
        first = self.signed_tx(1, 0)
        self.assertEqual(self.ledger.apply(first), (True, "accepted"))
        self.assertEqual(self.ledger.accounts["ALICE"].nonce, 1)

    def test_bool_amount_is_accepted_as_one_unit(self):
        """Known defect: bool is a subclass of int, so True passes amount checks."""
        tx = self.signed_tx(True, 0)
        self.assertIs(type(tx["amount"]), bool)
        self.assertEqual(self.ledger.validate(tx), (True, "ok"))
        self.assertEqual(self.ledger.apply(tx), (True, "accepted"))
        self.assertEqual(self.ledger.accounts["ALICE"].balance, 999)
        self.assertEqual(self.ledger.accounts["BOB"].balance, 1)
        self.assertEqual(sum(a.balance for a in self.ledger.accounts.values()), SUPPLY)

    def test_bool_nonce_is_accepted_when_integer_nonce_is_one(self):
        """Known defect: True == 1 lets a bool nonce match nonce 1."""
        self.advance_alice_nonce_to_one()
        tx = self.signed_tx(1, True)
        self.assertIs(type(tx["nonce"]), bool)
        self.assertEqual(self.ledger.validate(tx), (True, "ok"))
        self.assertEqual(self.ledger.apply(tx), (True, "accepted"))

    def test_float_nonce_is_accepted_when_integer_nonce_is_one(self):
        """Known defect: 1.0 == 1 lets a float nonce match nonce 1."""
        self.advance_alice_nonce_to_one()
        tx = self.signed_tx(1, 1.0)
        self.assertIs(type(tx["nonce"]), float)
        self.assertEqual(self.ledger.validate(tx), (True, "ok"))
        self.assertEqual(self.ledger.apply(tx), (True, "accepted"))

    def test_non_integer_amount_forms_are_rejected(self):
        """Control cases: current amount validation rejects these values."""
        for value in (1.0, "1", 0, -1, None):
            with self.subTest(amount=value):
                tx = self.signed_tx(value, 0)
                self.assertEqual(self.ledger.validate(tx), (False, "amount"))

    def test_string_nonce_is_rejected_at_nonce_one(self):
        """Control case: unlike bool/float, a string does not equal integer 1."""
        self.advance_alice_nonce_to_one()
        tx = self.signed_tx(1, "1")
        self.assertEqual(self.ledger.validate(tx), (False, "nonce"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
