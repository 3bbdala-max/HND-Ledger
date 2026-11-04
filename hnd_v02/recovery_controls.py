"""Fail-closed recovery supervision and replica convergence controls."""
from __future__ import annotations

import subprocess
import time
from typing import Callable, Iterable


class RecoveryReadinessTimeout(TimeoutError):
    """Recovery did not become ready within its explicit deadline."""


class ReplicaConvergenceError(AssertionError):
    """Recovered replicas disagree on committed consensus/application state."""


def wait_for_recovery_readiness(
    process: subprocess.Popen,
    readiness: Callable[[], bool],
    *,
    timeout_seconds: float,
    poll_interval: float = 0.02,
    terminate_grace_seconds: float = 1.0,
) -> None:
    """Wait boundedly; on timeout terminate the disposable recovery process.

    The caller owns state files. This function never creates, resets, or rewrites
    signer/application state, and it raises rather than returning a false success.
    """
    if timeout_seconds <= 0 or poll_interval <= 0 or terminate_grace_seconds < 0:
        raise ValueError("recovery timeout and polling parameters must be positive")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            raise RuntimeError(f"recovery process exited before readiness (exit={code})")
        if readiness():
            return
        time.sleep(min(poll_interval, max(0.0, deadline - time.monotonic())))

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=terminate_grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.poll() is None:
        raise RuntimeError("recovery process survived timeout termination")
    raise RecoveryReadinessTimeout(
        f"recovery readiness deadline exceeded ({timeout_seconds:.3f}s); "
        f"process_terminated=true; exit={process.returncode}"
    )


def assert_replica_convergence(fingerprints: Iterable[dict]) -> None:
    """Require equal height, block hash, and decoded application hash.

    Each item has validator, height, block_hash, and app_hash fields. On failure,
    the exception names the validators whose fingerprints differ from validator 1.
    """
    items = list(fingerprints)
    if len(items) < 2:
        raise ValueError("at least two replica fingerprints are required")
    required = ("validator", "height", "block_hash", "app_hash")
    for item in items:
        if any(key not in item for key in required):
            raise ValueError("replica fingerprint is missing a required field")
    baseline = items[0]
    fields = ("height", "block_hash", "app_hash")
    divergent = [
        item["validator"]
        for item in items[1:]
        if any(item[field] != baseline[field] for field in fields)
    ]
    if divergent:
        raise ReplicaConvergenceError(
            f"recovered replica divergence: baseline={baseline['validator']}; "
            f"divergent={','.join(map(str, divergent))}"
        )
