"""Fail-closed CometBFT process launch adapter for HND Station 2.

This adapter binds the authorized activation transaction to a pinned executable
and launches it only after activation commits. It is a supervisor building
block, not a complete OS security boundary: production deployment must ensure
this is the only permitted CometBFT launch path and protect the executable,
evidence, backend, environment, and host from privileged modification.
"""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from hnd_v02.activation_transaction import AtomicActivationBackend
from hnd_v02.startup_authorization import authorize_then_start


class CometBFTSupervisorError(RuntimeError):
    """The pinned CometBFT process could not be safely authorized or launched."""


def _pinned_executable(path: str, expected_sha256: str) -> str:
    if type(path) is not str or not os.path.isabs(path):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-ABSOLUTE-PATH")
    if type(expected_sha256) is not str or len(expected_sha256) != 64:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-DIGEST")
    try:
        int(expected_sha256, 16)
    except ValueError as exc:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-DIGEST") from exc

    candidate = Path(path)
    try:
        metadata = candidate.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-FILE-TYPE")
        if metadata.st_mode & 0o111 == 0:
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-NOT-EXECUTABLE")
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
    except OSError as exc:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-READ") from exc
    if digest != expected_sha256.lower():
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-DIGEST-MISMATCH")
    return str(candidate)


def start_authorized_cometbft(
    *,
    backend: AtomicActivationBackend,
    vsp_raw: bytes,
    trust_manifests: list[bytes],
    operator_acks_raw: bytes,
    profile_artifact: bytes,
    context: Mapping,
    trusted_witness_keys: Mapping[str, bytes],
    expected_operator_keys: Mapping[str, bytes],
    binary_path: str,
    expected_binary_sha256: str,
    arguments: Sequence[str],
    cwd: str,
    environment: Mapping[str, str] | None = None,
    popen: Any = subprocess.Popen,
) -> tuple[Any, Any]:
    """Authorize, atomically activate, then launch only the pinned binary.

    The executable digest is checked before evidence processing and again in
    the launch callback. No shell is used. Callers must provide an immutable,
    root-controlled binary path and must prevent all alternate launch routes.
    The returned pair is (committed ActivationState, child process handle).
    """
    executable = _pinned_executable(binary_path, expected_binary_sha256)
    if type(arguments) not in (list, tuple) or any(type(arg) is not str for arg in arguments):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-ARGUMENTS")
    if type(cwd) is not str or not os.path.isabs(cwd) or not os.path.isdir(cwd):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-CWD")
    if environment is not None:
        if not isinstance(environment, Mapping) or any(
            type(key) is not str or type(value) is not str for key, value in environment.items()
        ):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-ENVIRONMENT")
        child_environment = dict(environment)
    else:
        child_environment = None

    def launch_after_commit(_state: Any) -> Any:
        _pinned_executable(executable, expected_binary_sha256)
        return popen(
            [executable, *arguments],
            executable=executable,
            cwd=cwd,
            env=child_environment,
            shell=False,
            close_fds=True,
            start_new_session=True,
        )

    return authorize_then_start(
        backend=backend,
        vsp_raw=vsp_raw,
        trust_manifests=trust_manifests,
        operator_acks_raw=operator_acks_raw,
        profile_artifact=profile_artifact,
        context=context,
        trusted_witness_keys=trusted_witness_keys,
        expected_operator_keys=expected_operator_keys,
        launch=launch_after_commit,
    )
