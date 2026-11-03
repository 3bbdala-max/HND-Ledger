"""Tests for the disposable loopback peer relay."""
import socket
import threading
import time
import unittest

from scripts.hnd_peer_relay import DirectedTCPRelay


class EchoServer:
    def __init__(self):
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.listener.settimeout(0.2)
        self.port = self.listener.getsockname()[1]
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._echo, args=(conn,), daemon=True).start()

    @staticmethod
    def _echo(conn):
        with conn:
            try:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        return
                    conn.sendall(data.upper())
            except OSError:
                return

    def close(self):
        self.stop_event.set()
        self.listener.close()
        self.thread.join(timeout=1)


class DirectedTCPRelayTests(unittest.TestCase):
    def setUp(self):
        self.target = EchoServer()
        self.relay = DirectedTCPRelay("127.0.0.1", self.target.port)

    def tearDown(self):
        self.relay.close()
        self.target.close()

    def test_forwards_both_directions_and_can_be_disabled_and_reenabled(self):
        client = socket.create_connection(self.relay.address, timeout=2)
        client.settimeout(2)
        try:
            client.sendall(b"hello")
            self.assertEqual(client.recv(5), b"HELLO")
            self.assertEqual(self.relay.active_connections, 1)

            self.relay.disable()
            self.assertFalse(self.relay.enabled)
            self.assertEqual(client.recv(1), b"")
            self.assertEqual(self.relay.active_connections, 0)

            self.relay.enable()
            self.assertTrue(self.relay.enabled)
            with socket.create_connection(self.relay.address, timeout=2) as again:
                again.settimeout(2)
                again.sendall(b"world")
                self.assertEqual(again.recv(5), b"WORLD")
        finally:
            client.close()

    def test_disabled_relay_rejects_new_route(self):
        self.relay.disable()
        with socket.create_connection(self.relay.address, timeout=2) as client:
            client.settimeout(2)
            self.assertEqual(client.recv(1), b"")

    def test_non_loopback_routes_are_rejected(self):
        with self.assertRaises(ValueError):
            DirectedTCPRelay("192.0.2.1", self.target.port)


if __name__ == "__main__":
    unittest.main()
