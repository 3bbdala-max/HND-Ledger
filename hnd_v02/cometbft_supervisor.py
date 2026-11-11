"""Fail-closed CometBFT process launch adapter for HND Station 2.

The executable is opened with O_NOFOLLOW and passed to the child by inherited
file descriptor through /proc/self/fd. This prevents a path replacement between
digest verification and exec. Child environments must be explicit and may not
override the dynamic loader. The installed inode must still be root-controlled
and immutable against privileged writers; this is not a complete OS boundary.
"""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

from hnd_v02.activation_transaction import AtomicActivationBackend
from hnd_v02.startup_authorization import authorize_then_start_witnessed


class CometBFTSupervisorError(RuntimeError):
    """The pinned CometBFT process could not be safely authorized or launched."""


def _verify_open_executable(fd: int, expected_sha256: str) -> None:
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-FILE-TYPE")
        if metadata.st_mode & 0o111 == 0:
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-NOT-EXECUTABLE")
        os.lseek(fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        os.lseek(fd, 0, os.SEEK_SET)
    except OSError as exc:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-READ") from exc
    if digest.hexdigest() != expected_sha256.lower():
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-DIGEST-MISMATCH")


def _open_pinned_executable(path: str, expected_sha256: str) -> tuple[int, str]:
    if type(path) is not str or not os.path.isabs(path):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-ABSOLUTE-PATH")
    if type(expected_sha256) is not str or len(expected_sha256) != 64:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-DIGEST")
    try:
        int(expected_sha256, 16)
    except ValueError as exc:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-DIGEST") from exc
    if not hasattr(os, "O_NOFOLLOW") or not os.path.isdir("/proc/self/fd"):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-FD-EXEC-UNSUPPORTED")

    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        code = "HND-SUPERVISOR-E-FILE-TYPE" if getattr(exc, "errno", None) in (20, 40) else "HND-SUPERVISOR-E-READ"
        raise CometBFTSupervisorError(code) from exc
    try:
        _verify_open_executable(fd, expected_sha256)
        return fd, f"/proc/self/fd/{fd}"
    except Exception:
        os.close(fd)
        raise


def start_authorized_cometbft(
    *,
    backend: AtomicActivationBackend,
    witness_client: Any,
    activation_id: str,
    expected_witness_id: str,
    expected_config_epoch: int,
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
    """Require a verified independent witness receipt, then exec the pinned inode.

    The five-key etcd activation and independent witness acknowledgement are
    mandatory. Linux /proc/self/fd is required. The executable descriptor remains open
    until Popen has completed process creation and is explicitly inherited by
    that child; replacing the original path cannot redirect the execution.
    """
    executable_fd, executable_ref = _open_pinned_executable(
        binary_path, expected_binary_sha256
    )
    try:
        if type(arguments) not in (list, tuple) or any(type(arg) is not str for arg in arguments):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-ARGUMENTS")
        if type(cwd) is not str or not os.path.isabs(cwd) or not os.path.isdir(cwd):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-CWD")
        if environment is None or not isinstance(environment, Mapping) or any(
            type(key) is not str or type(value) is not str
            for key, value in environment.items()
        ):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-ENVIRONMENT")
        # Do not inherit the supervisor's ambient environment: glibc loader
        # variables can inject libraries or alter symbol resolution even when
        # the executable itself is pinned by digest and file descriptor.
        if any(
            key.startswith("LD_") or key == "GLIBC_TUNABLES"
            for key in environment
        ):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-ENVIRONMENT")
        child_environment = dict(environment)

        def launch_after_commit(_state: Any) -> Any:
            # Re-hash the same open inode immediately before exec; never reopen
            # the mutable pathname after the initial O_NOFOLLOW open.
            _verify_open_executable(executable_fd, expected_binary_sha256)
            return popen(
                [executable_ref, *arguments],
                executable=executable_ref,
                cwd=cwd,
                env=child_environment,
                shell=False,
                close_fds=True,
                pass_fds=(executable_fd,),
                start_new_session=True,
            )

        return authorize_then_start_witnessed(
            backend=backend,
            witness_client=witness_client,
            activation_id=activation_id,
            expected_witness_id=expected_witness_id,
            expected_config_epoch=expected_config_epoch,
            vsp_raw=vsp_raw,
            trust_manifests=trust_manifests,
            operator_acks_raw=operator_acks_raw,
            profile_artifact=profile_artifact,
            context=context,
            trusted_witness_keys=trusted_witness_keys,
            expected_operator_keys=expected_operator_keys,
            launch=launch_after_commit,
        )
    finally:
        os.close(executable_fd)
