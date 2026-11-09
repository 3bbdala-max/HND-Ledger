"""Regression tests for strict JSON parsing at HND trust boundaries."""
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hnd_v02.cometbft_v040_server import main as abci_server_main
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.strict_json import StrictJSONError, strict_json_loads


class TestStrictJSON(unittest.TestCase):
    def test_duplicate_members_are_rejected_at_every_object_depth(self):
        samples = (
            b'{"member":1,"member":2}',
            b'{"outer":{"member":1,"member":2}}',
            b'{"left":{"ok":1},"right":{"member":1,"member":2}}',
        )
        for raw in samples:
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(StrictJSONError, "duplicate JSON object key"):
                    strict_json_loads(raw, label="test")

    def test_non_finite_constants_are_rejected(self):
        for token in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(token=token):
                with self.assertRaisesRegex(StrictJSONError, "non-finite JSON constant"):
                    strict_json_loads(b'{"value":' + token + b'}', label="test")

    def test_invalid_utf8_is_rejected(self):
        with self.assertRaisesRegex(StrictJSONError, "invalid UTF-8"):
            strict_json_loads(b'{"value":"\xff"}', label="test")

    def test_utf8_bom_is_rejected_explicitly(self):
        with self.assertRaisesRegex(StrictJSONError, "UTF-8 BOM"):
            strict_json_loads(b"\xef\xbb\xbf{}", label="test")

    def test_large_integer_is_preserved_exactly(self):
        expected = 9007199254740993123456789
        value = strict_json_loads(
            b'{"amount":9007199254740993123456789}',
            label="test",
        )
        self.assertIs(type(value["amount"]), int)
        self.assertEqual(value["amount"], expected)

    def test_published_genesis_hash_is_unchanged(self):
        vector_path = (
            Path(__file__).resolve().parents[1]
            / "vectors"
            / "v0.2-genesis-devnet-example.json"
        )
        vector = strict_json_loads(vector_path.read_bytes(), label="Genesis fixture")
        self.assertIs(type(vector), dict)
        self.assertEqual(
            genesis_manifest_hash(vector["manifest"]),
            vector["genesis_hash_sha256"],
        )

    def test_cli_rejects_duplicate_manifest_before_server_start_without_echo(self):
        marker = "DO_NOT_ECHO_MANIFEST_CONTENT"
        raw = (
            b'{"manifest_version":1,"manifest_version":1,"marker":"'
            + marker.encode("ascii")
            + b'"}'
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "duplicate.json"
            manifest_path.write_bytes(raw)
            stderr = StringIO()
            argv = [
                "--manifest", str(manifest_path),
                "--genesis-hash", "0" * 64,
                "--network-id", "hnd-strict-json-test",
                "--max-amount", "100",
                "--state-path", str(Path(directory) / "state.json"),
            ]
            with patch("hnd_v02.cometbft_v040_server.start_grpc_server") as start:
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        abci_server_main(argv)
            self.assertEqual(raised.exception.code, 2)
            start.assert_not_called()
            self.assertNotIn(marker, stderr.getvalue())

    def test_cli_rejects_non_object_manifest_before_server_start(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "array.json"
            manifest_path.write_bytes(b"[]")
            stderr = StringIO()
            argv = [
                "--manifest", str(manifest_path),
                "--genesis-hash", "0" * 64,
                "--network-id", "hnd-strict-json-test",
                "--max-amount", "100",
                "--state-path", str(Path(directory) / "state.json"),
            ]
            with patch("hnd_v02.cometbft_v040_server.start_grpc_server") as start:
                with redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        abci_server_main(argv)
            self.assertEqual(raised.exception.code, 2)
            start.assert_not_called()
            self.assertIn("manifest must be a JSON object", stderr.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
