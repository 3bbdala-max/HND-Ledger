"""Loopback-only directed TCP relay for disposable CometBFT test networks."""
from __future__ import annotations

import select
import socket
import threading
import time


class DirectedTCPRelay:
    """Forward one directed peer route and forcibly sever it while disabled."""

    def __init__(
        self,
        target_host: str,
        target_port: int,
        *,
        listen_host: str = "127.0.0.1",
        listen_port: int = 0,
        connect_timeout: float = 2.0,
    ) -> None:
        if listen_host != "127.0.0.1" or target_host != "127.0.0.1":
            raise ValueError("test relays must bind and forward only on 127.0.0.1")
        if not 1 <= int(target_port) <= 65535:
            raise ValueError("target_port must be a valid TCP port")
        self.target = (target_host, int(target_port))
        self.connect_timeout = connect_timeout
        self._lock = threading.RLock()
        self._enabled = True
        self._closed = False
        self._stopping = threading.Event()
        self._pairs: set[tuple[socket.socket, socket.socket]] = set()
        self._workers: set[threading.Thread] = set()
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((listen_host, int(listen_port)))
        self._listener.listen(32)
        self._listener.settimeout(0.25)
        self.address = self._listener.getsockname()
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="hnd-peer-relay-accept", daemon=True
        )
        self._accept_thread.start()

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled and not self._closed

    @property
    def active_connections(self) -> int:
        with self._lock:
            return len(self._pairs)

    def enable(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("relay is closed")
            self._enabled = True

    def disable(self) -> None:
        with self._lock:
            self._enabled = False
            pairs = list(self._pairs)
        for pair in pairs:
            self._close_pair(pair)

    def _accept_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                client, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                if not self._enabled or self._closed:
                    client.close()
                    continue
                worker = threading.Thread(
                    target=self._bridge,
                    args=(client,),
                    name="hnd-peer-relay-bridge",
                    daemon=True,
                )
                # Register under the same lock used by close(), so shutdown
                # cannot miss a worker accepted immediately before closure.
                self._workers.add(worker)
                # Start before releasing the lock; close() must never try to
                # join a registered thread that has not started yet.
                worker.start()

    def _bridge(self, client: socket.socket) -> None:
        upstream = None
        pair = None
        try:
            client.settimeout(self.connect_timeout)
            upstream = socket.create_connection(self.target, timeout=self.connect_timeout)
            client.settimeout(None)
            upstream.settimeout(None)
            pair = (client, upstream)
            with self._lock:
                if not self._enabled or self._closed:
                    return
                self._pairs.add(pair)
            while not self._stopping.is_set():
                readable, _, exceptional = select.select(
                    [client, upstream], [], [client, upstream], 0.25
                )
                if exceptional:
                    break
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    destination = upstream if source is client else client
                    destination.sendall(data)
        except (OSError, ValueError):
            pass
        finally:
            if pair is not None:
                self._close_pair(pair)
            else:
                try:
                    client.close()
                except OSError:
                    pass
                if upstream is not None:
                    try:
                        upstream.close()
                    except OSError:
                        pass
            with self._lock:
                self._workers.discard(threading.current_thread())

    def _close_pair(self, pair: tuple[socket.socket, socket.socket]) -> None:
        with self._lock:
            self._pairs.discard(pair)
        for conn in pair:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._enabled = False
        self._stopping.set()
        with self._lock:
            pairs = list(self._pairs)
            workers = list(self._workers)
        for pair in pairs:
            self._close_pair(pair)
        try:
            self._listener.close()
        except OSError:
            pass
        self._accept_thread.join(timeout=2)
        deadline = time.monotonic() + 2
        for worker in workers:
            worker.join(timeout=max(0, deadline - time.monotonic()))

    def __enter__(self) -> "DirectedTCPRelay":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
