"""Ensure the production ABCI CLI cannot bypass the witnessed node supervisor."""
import unittest
from unittest.mock import patch

from hnd_v02 import cometbft_v040_server as server


class CometBFTABCIStartupGateTests(unittest.TestCase):
    @patch("hnd_v02.cometbft_v040_server.start_grpc_server")
    def test_standalone_cli_is_disabled(self, start_server):
        with self.assertRaises(SystemExit) as caught:
            server.main([])
        self.assertEqual(caught.exception.code, 2)
        start_server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
