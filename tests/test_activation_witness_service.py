import unittest
from unittest.mock import Mock

from hnd_v02.activation_witness_service import (
    ActivationWitnessHTTPError, dispatch_witness_request,
)


class WitnessServiceDispatchTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.store.acknowledge.return_value = {"activation_id": "activation-1", "counter": 1}

    def test_valid_acknowledgement_delegates_exact_immutable_values(self):
        result = dispatch_witness_request(
            self.store, "/v1/witness/acknowledge",
            {"activation_id": "activation-1", "activation_digest": "a" * 64},
        )
        self.assertEqual(result["receipt"]["counter"], 1)
        self.store.acknowledge.assert_called_once_with("activation-1", "a" * 64)

    def test_extra_fields_are_rejected(self):
        with self.assertRaises(ActivationWitnessHTTPError):
            dispatch_witness_request(
                self.store, "/v1/witness/acknowledge",
                {"activation_id": "activation-1", "activation_digest": "a" * 64, "counter": 99},
            )
        self.store.acknowledge.assert_not_called()

    def test_malformed_digest_is_rejected(self):
        with self.assertRaises(ActivationWitnessHTTPError):
            dispatch_witness_request(
                self.store, "/v1/witness/acknowledge",
                {"activation_id": "activation-1", "activation_digest": "A" * 64},
            )
        self.store.acknowledge.assert_not_called()

    def test_unknown_route_is_rejected(self):
        with self.assertRaises(ActivationWitnessHTTPError):
            dispatch_witness_request(
                self.store, "/v1/witness/finalize",
                {"activation_id": "activation-1", "activation_digest": "a" * 64},
            )


if __name__ == "__main__":
    unittest.main()
