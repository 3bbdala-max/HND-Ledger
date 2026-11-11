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

from hnd_v02.activation_transaction import ActivationState, AtomicActivationBackend
from hnd_v02.abci_app import HNDABCIApplication
from hnd_v02.genesis import genesis_manifest_hash
from hnd_v02.vsp_canonical import parse_vsp_envelope, profile_digest
from hnd_v02.startup_authorization import authorize_then_start_witnessed
from hnd_v02.cometbft_v040_server import start_grpc_server


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



def _verify_hnd_application_binding(
    *,
    application: Any,
    state: ActivationState,
    vsp_raw: bytes,
    context: Mapping,
    expected_binary_sha256: str,
) -> None:
    """Bind the running HND application to the exact witnessed VSP evidence.

    This verifies the HND application type, chain/network identity, canonical
    HND Genesis manifest/hash, activation state digest, and pinned CometBFT
    binary digest. A separate mandatory deployment verifier must still inspect
    the actual CometBFT Genesis file and parse the actual profile artifact using
    the complete pinned v0.40.0 profile schema.
    """
    if not isinstance(application, HNDABCIApplication):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-APPLICATION-TYPE")
    if type(state) is not ActivationState:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-ACTIVATION-STATE")
    if not isinstance(context, Mapping) or type(vsp_raw) is not bytes or not vsp_raw:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-TRUST-CONTEXT")
    try:
        payload = parse_vsp_envelope(vsp_raw)["payload"]
        vsp_digest = profile_digest(payload).hex()
        manifest_digest = genesis_manifest_hash(application.manifest)
        comet = payload["cometbft"]
    except Exception as exc:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-EVIDENCE-BINDING") from exc

    chain_id = payload.get("chain_id")
    hnd_genesis = payload.get("hnd_genesis_sha256")
    if (
        type(chain_id) is not str
        or type(hnd_genesis) is not str
        or application.config.network_id != chain_id
        or application.manifest.get("network_id") != chain_id
        or application.config.protocol_version != application.manifest.get("protocol_version")
        or application.expected_genesis_hash != hnd_genesis
        or manifest_digest != hnd_genesis
        or context.get("chain_id") != chain_id
        or context.get("hnd_genesis_sha256") != hnd_genesis
    ):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-HND-GENESIS-BINDING")

    if state.profile_digest != vsp_digest:
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-VSP-DIGEST-BINDING")

    expected_binary = expected_binary_sha256.lower()
    if (
        type(expected_binary_sha256) is not str
        or len(expected_binary_sha256) != 64
        or type(comet) is not dict
        or comet.get("binary_sha256") != expected_binary
        or context.get("cometbft_binary_sha256") != expected_binary
    ):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-BINARY-BINDING")

    expected_context = {
        "cometbft_version": comet.get("version"),
        "cometbft_source_commit": comet.get("source_commit"),
        "cometbft_genesis_sha256": comet.get("genesis_sha256"),
        "cometbft_profile_sha256": comet.get("profile_sha256"),
    }
    if any(context.get(key) != value for key, value in expected_context.items()):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-COMETBFT-CONTEXT-BINDING")

def start_authorized_cometbft(
    *,
    backend: AtomicActivationBackend,
    application: Any,
    application_binding_verifier: Any,
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
    abci_bind_address: str = "127.0.0.1:26658",
    abci_max_workers: int = 16,
    environment: Mapping[str, str] | None = None,
    popen: Any = subprocess.Popen,
) -> tuple[Any, Any]:
    """Authorize, bind ABCI, and start the pinned CometBFT process as one unit.

    The five-key etcd activation and independent witness acknowledgement are
    mandatory. The application binding is checked before the ABCI listener is
    opened. CometBFT is spawned only after that listener is ready; if spawning
    fails, the listener is stopped before the error is returned. Linux
    /proc/self/fd is required, and the executable descriptor remains open until
    Popen completes process creation.
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

        if not callable(application_binding_verifier):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-APPLICATION-BINDING")

        def launch_after_commit(state: Any) -> Any:
            # The witness receipt is finalized before this callback is entered.
            # Bind the exact application only after that authorization succeeds.
            try:
                _verify_hnd_application_binding(
                    application=application,
                    state=state,
                    vsp_raw=vsp_raw,
                    context=context,
                    expected_binary_sha256=expected_binary_sha256,
                )
                application_is_bound = application_binding_verifier(
                    application, state, profile_artifact
                )
            except Exception as exc:
                raise CometBFTSupervisorError(
                    "HND-SUPERVISOR-E-APPLICATION-BINDING"
                ) from exc
            if application_is_bound is not True:
                raise CometBFTSupervisorError("HND-SUPERVISOR-E-APPLICATION-BINDING")

            abci_server = None
            try:
                abci_server, abci_port = start_grpc_server(
                    application,
                    bind_address=abci_bind_address,
                    max_workers=abci_max_workers,
                )
                # Re-hash the same open inode immediately before exec; never reopen
                # the mutable pathname after the initial O_NOFOLLOW open.
                _verify_open_executable(executable_fd, expected_binary_sha256)
                process = popen(
                    [executable_ref, *arguments],
                    executable=executable_ref,
                    cwd=cwd,
                    env=child_environment,
                    shell=False,
                    close_fds=True,
                    pass_fds=(executable_fd,),
                    start_new_session=True,
                )
                return {
                    "abci_server": abci_server,
                    "abci_port": abci_port,
                    "cometbft_process": process,
                }
            except Exception:
                # A failed bind or failed process creation must not leave an
                # orphan ABCI listener accepting unaffiliated CometBFT traffic.
                if abci_server is not None:
                    try:
                        abci_server.stop(grace=0).wait()
                    except Exception:
                        pass
                raise

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
