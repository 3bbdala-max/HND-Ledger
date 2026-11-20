"""MODEL-ONLY test for the first P0 signer-fencing acceptance case.

This deliberately does NOT implement a production signer or cryptography. It
models the release-boundary rule using disposable identities and an in-memory
authority so the policy regression can be tested without production keys.
"""
from dataclasses import dataclass
import unittest


class StaleOwnerRejected(Exception):
    pass


@dataclass(frozen=True)
class Ownership:
    owner: str
    epoch: int


class FakeKeyReleaseBoundary:
    """Test double: checks current authority immediately before fake release."""

    def __init__(self):
        self.current = Ownership(owner="signer-A", epoch=1)
        self.released = []

    def transfer(self, new_owner: str) -> Ownership:
        self.current = Ownership(
            owner=new_owner,
            epoch=self.current.epoch + 1,
        )
        return self.current

    def release(self, *, caller: str, epoch: int, request_id: str) -> bytes:
        # This is the modeled policy assertion, not a real key service.
        if caller != self.current.owner or epoch != self.current.epoch:
            raise StaleOwnerRejected("stale signer ownership or epoch")
        signature = f"TEST-ONLY:{caller}:{epoch}:{request_id}".encode("ascii")
        self.released.append((request_id, caller, epoch, signature))
        return signature


class P0SignerFencingModelTests(unittest.TestCase):
    def setUp(self):
        self.boundary = FakeKeyReleaseBoundary()

    def test_fence_00_rejects_previous_owner_after_transfer(self):
        old_epoch = self.boundary.current.epoch

        new_ownership = self.boundary.transfer("signer-B")

        with self.assertRaises(StaleOwnerRejected):
            self.boundary.release(
                caller="signer-A",
                epoch=old_epoch,
                request_id="fence-00-stale-request",
            )

        self.assertEqual(new_ownership, Ownership("signer-B", old_epoch + 1))
        self.assertEqual(self.boundary.current, new_ownership)
        self.assertEqual(self.boundary.released, [])

    def test_current_owner_can_release_in_model(self):
        current = self.boundary.current

        result = self.boundary.release(
            caller=current.owner,
            epoch=current.epoch,
            request_id="fence-00-current-owner-control",
        )

        self.assertTrue(result.startswith(b"TEST-ONLY:"))
        self.assertEqual(len(self.boundary.released), 1)


if __name__ == "__main__":
    unittest.main()
