"""Tests for the witness gate at the ABCI listener boundary."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hnd_v02 import cometbft_v040_server as server


class CometBFTABCIStartupGateTests(unittest.TestCase):
    def _arguments(self):
        return dict(
            application=object(),
            backend=object(),
            witness_client=object(),
            activation_id="abci-startup-test-001",
            expected_witness_id="witness-ci",
            expected_config_epoch=7,
            vsp_raw=b"vsp",
            trust_manifests=[b"manifest"],
            operator_acks_raw=b"acks",
            profile_artifact=b"profile",
            context={},
            trusted_witness_keys={"witness-ci": b"k" * 32},
            expected_operator_keys={"operator-a": b"p" * 32},
            application_binding_verifier=lambda app, state, profile: True,
        )

    @patch("hnd_v02.cometbft_v040_server.start_grpc_server")
    @patch("hnd_v02.cometbft_v040_server.authorize_then_start_witnessed")
    def test_listener_is_created_inside_post_witness_callback(
        self, authorize, start_server
    ):
        state = object()
        expected_server = object()
        start_server.return_value = (expected_server, 26658)

        def authorize_and_launch(**kwargs):
            # The launcher is the only place that may create the socket.
            return state, kwargs["launch"](state)

        authorize.side_effect = authorize_and_launch
        result = server.start_witnessed_grpc_server(**self._arguments())

        self.assertEqual(result, (state, (expected_server, 26658)))
        start_server.assert_called_once()
        authorize.assert_called_once()
        self.assertEqual(
            authorize.call_args.kwargs["activation_id"], "abci-startup-test-001"
        )

    @patch("hnd_v02.cometbft_v040_server.start_grpc_server")
    @patch("hnd_v02.cometbft_v040_server.authorize_then_start_witnessed")
    def test_witness_failure_opens_no_listener(self, authorize, start_server):
        authorize.side_effect = RuntimeError("witness unavailable")
        with self.assertRaisesRegex(RuntimeError, "witness unavailable"):
            server.start_witnessed_grpc_server(**self._arguments())
        start_server.assert_not_called()

    @patch("hnd_v02.cometbft_v040_server.start_grpc_server")
    @patch("hnd_v02.cometbft_v040_server.authorize_then_start_witnessed")
    def test_application_binding_mismatch_opens_no_listener(
        self, authorize, start_server
    ):
        authorize.side_effect = lambda **kwargs: kwargs["launch"](object())
        arguments = self._arguments()
        arguments["application_binding_verifier"] = lambda app, state, profile: False
        with self.assertRaisesRegex(RuntimeError, "APPLICATION-BINDING"):
            server.start_witnessed_grpc_server(**arguments)
        start_server.assert_not_called()

    @patch("hnd_v02.cometbft_v040_server.start_grpc_server")
    def test_standalone_cli_is_disabled(self, start_server):
        with self.assertRaises(SystemExit) as caught:
            server.main([])
        self.assertEqual(caught.exception.code, 2)
        start_server.assert_not_called()


if __name__ == "__main__":
    unittest.main()
