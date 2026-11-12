"""Fail-closed CometBFT process launch adapter for HND Station 2.

The executable is opened with O_NOFOLLOW and passed to the child by inherited
file descriptor through /proc/self/fd. This prevents a path replacement between
digest verification and exec. Child environments must be explicit and may not
override the dynamic loader. The installed inode must still be root-controlled
and immutable against privileged writers; this is not a complete OS boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from hnd_v02.activation_transaction import ActivationState, AtomicActivationBackend
from hnd_v02.abci_app import HNDABCIApplication
from hnd_v02.genesis import genesis_manifest_hash, validate_genesis_manifest
from hnd_v02.vsp_canonical import parse_vsp_envelope, profile_digest
from hnd_v02.vsp_verify import validate_roster
from hnd_v02.cometbft_v040_profile import (
    ProfileSchema,
    cometbft_v040_profile_digest,
    parse_cometbft_v040_profile,
)
from hnd_v02.transaction import canonical_json
from hnd_v02.startup_authorization import authorize_then_start_witnessed
from hnd_v02.cometbft_v040_server import start_grpc_server


class CometBFTSupervisorError(RuntimeError):
    """The pinned CometBFT process could not be safely authorized or launched."""


def _reject_duplicate_json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(token):
    raise ValueError(f"non-standard JSON constant: {token}")


def _roster_projection(records):
    if type(records) is not list:
        raise ValueError("CometBFT Genesis validators must be an array")
    projected = []
    for record in records:
        if type(record) is not dict:
            raise ValueError("CometBFT Genesis validator must be an object")
        key = record.get("pub_key")
        if type(key) is not dict:
            raise ValueError("CometBFT Genesis validator public key is missing")
        projected.append({
            "address": str(record.get("address", "")).lower(),
            "pub_key": key,
            "power": record.get("power"),
        })
    return projected


def _read_cometbft_home_file(home: str, filename: str, *, max_bytes: int) -> bytes:
    """Read a regular file below HOME/config without following path symlinks."""
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    home_fd = config_fd = file_fd = None
    try:
        home_fd = os.open(home, directory_flags)
        config_fd = os.open("config", directory_flags, dir_fd=home_fd)
        file_fd = os.open(filename, file_flags, dir_fd=config_fd)
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            raise CometBFTSupervisorError(
                "HND-SUPERVISOR-E-COMETBFT-DEPLOYMENT-FILE"
            )
        chunks = []
        total = 0
        while True:
            chunk = os.read(file_fd, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise CometBFTSupervisorError(
                    "HND-SUPERVISOR-E-COMETBFT-DEPLOYMENT-FILE"
                )
        return b"".join(chunks)
    except CometBFTSupervisorError:
        raise
    except OSError as exc:
        raise CometBFTSupervisorError(
            "HND-SUPERVISOR-E-COMETBFT-DEPLOYMENT-FILE"
        ) from exc
    finally:
        for descriptor in (file_fd, config_fd, home_fd):
            if descriptor is not None:
                os.close(descriptor)


def _validate_cometbft_home_argument(
    arguments: Sequence[str], cwd: str, cometbft_home: str
) -> None:
    if type(cometbft_home) is not str or not os.path.isabs(cometbft_home):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-COMETBFT-HOME")
    # No additional flags are accepted: several CometBFT flags can override
    # config.toml values, which would invalidate the profile digest we checked.
    if (
        type(arguments) not in (list, tuple)
        or len(arguments) != 3
        or arguments[0] != "start"
        or arguments[1] != "--home"
        or type(arguments[2]) is not str
    ):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-COMETBFT-CLI-OVERRIDE")
    supplied = arguments[2]
    if not os.path.isabs(supplied):
        supplied = os.path.join(cwd, supplied)
    if os.path.normpath(supplied) != os.path.normpath(cometbft_home):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-COMETBFT-HOME")


def _verify_cometbft_deployment_artifacts(
    *,
    application: Any,
    vsp_payload: Mapping,
    context: Mapping,
    cometbft_home: str,
    profile_artifact: bytes,
    profile_schema: ProfileSchema,
) -> None:
    """Bind the exact CometBFT Genesis bytes and parsed TOML profile to VSP.

    The ProfileSchema must be produced by the reviewed deployment packaging for
    the pinned CometBFT source commit. A caller-supplied 'complete' flag alone
    is not proof that a schema inventory was correctly classified.
    """
    genesis_raw = _read_cometbft_home_file(
        cometbft_home, "genesis.json", max_bytes=16 * 1024 * 1024
    )
    profile_raw = _read_cometbft_home_file(
        cometbft_home, "config.toml", max_bytes=1_048_576
    )
    if type(profile_artifact) is not bytes or profile_artifact != profile_raw:
        raise CometBFTSupervisorError(
            "HND-SUPERVISOR-E-COMETBFT-PROFILE-FILE-MISMATCH"
        )
    if genesis_raw.startswith(b"\xef\xbb\xbf"):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-COMETBFT-GENESIS-INPUT")
    try:
        genesis = json.loads(
            genesis_raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_json_pairs,
            parse_constant=_reject_json_constant,
        )
        if type(genesis) is not dict:
            raise ValueError("CometBFT Genesis document must be an object")
        genesis_digest = hashlib.sha256(genesis_raw).hexdigest()
        payload_comet = vsp_payload["cometbft"]
        if genesis_digest != payload_comet["genesis_sha256"]:
            raise ValueError("CometBFT Genesis byte digest does not match VSP")
        if genesis.get("chain_id") != vsp_payload["chain_id"]:
            raise ValueError("CometBFT Genesis chain ID does not match VSP")
        validators = genesis.get("validators")
        validate_roster(vsp_payload, validators)
        if _roster_projection(context.get("cometbft_genesis_validators")) != _roster_projection(validators):
            raise ValueError("caller context validators differ from actual Genesis")
        if context.get("cometbft_genesis_chain_id") != genesis["chain_id"]:
            raise ValueError("caller context chain ID differs from actual Genesis")

        expected_app_state_raw = application.application_genesis_bytes()
        expected_app_state = json.loads(
            expected_app_state_raw.decode("utf-8", errors="strict")
        )
        actual_app_state = genesis.get("app_state")
        if (
            type(actual_app_state) is not dict
            or canonical_json(actual_app_state) != expected_app_state_raw
        ):
            raise ValueError("CometBFT Genesis app_state differs from HND application Genesis")

        normalized_profile = parse_cometbft_v040_profile(profile_raw, profile_schema)
        profile_hash = cometbft_v040_profile_digest(normalized_profile, profile_schema)
        if profile_hash != payload_comet["profile_sha256"]:
            raise ValueError("CometBFT normalized profile digest does not match VSP")
        if profile_hash != context.get("cometbft_profile_sha256"):
            raise ValueError("caller context profile digest differs from actual profile")
        if genesis_digest != context.get("cometbft_genesis_sha256"):
            raise ValueError("caller context Genesis digest differs from actual Genesis")
        if (
            profile_schema.source_commit != payload_comet["source_commit"]
            or context.get("cometbft_source_commit") != profile_schema.source_commit
            or payload_comet["version"] != "v0.40.0"
            or context.get("cometbft_version") != payload_comet["version"]
        ):
            raise ValueError("profile schema source/version differs from VSP context")
    except CometBFTSupervisorError:
        raise
    except Exception as exc:
        raise CometBFTSupervisorError(
            "HND-SUPERVISOR-E-COMETBFT-DEPLOYMENT-ARTIFACT-BINDING"
        ) from exc


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
        manifest_valid, _manifest_reason = validate_genesis_manifest(
            application.manifest,
            config=application.config,
            expected_genesis_hash=payload["hnd_genesis_sha256"],
        )
        if manifest_valid is not True:
            raise ValueError("HND Genesis manifest does not validate against application config")
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

    if (
        type(expected_binary_sha256) is not str
        or len(expected_binary_sha256) != 64
        or any(char not in "0123456789abcdefABCDEF" for char in expected_binary_sha256)
        or type(comet) is not dict
    ):
        raise CometBFTSupervisorError("HND-SUPERVISOR-E-BINARY-BINDING")
    expected_binary = expected_binary_sha256.lower()
    if (
        comet.get("binary_sha256") != expected_binary
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


class SupervisedCometBFTNode:
    """Own the ABCI listener for exactly the lifetime of a CometBFT child.

    A daemon monitor waits for the child process and closes the ABCI listener
    whenever that process exits, including an unexpected crash. Explicit wait()
    and poll() calls also reconcile the listener state. Listener shutdown is
    idempotent so the monitor and caller may race safely.
    """

    def __init__(self, *, abci_server: Any, abci_port: int, process: Any):
        if not callable(getattr(process, "wait", None)) or not callable(
            getattr(process, "poll", None)
        ):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-PROCESS-INTERFACE")
        self.abci_server = abci_server
        self.abci_port = abci_port
        self.cometbft_process = process
        self._close_lock = threading.Lock()
        self._listener_closed = threading.Event()
        self._close_finished = threading.Event()
        self._closed = False
        # Keep failures from waiting on the child separate from failures that
        # actually prevent the ABCI listener from shutting down.
        self._process_wait_error: Exception | None = None
        self._listener_shutdown_error: Exception | None = None
        self._monitor = threading.Thread(
            target=self._monitor_process,
            name="hnd-cometbft-abci-lifecycle",
            daemon=True,
        )
        self._monitor.start()

    def _close_listener(self) -> None:
        with self._close_lock:
            already_closing = self._closed
            if not already_closing:
                self._closed = True
        if already_closing:
            # Another caller or the monitor owns the actual stop operation.
            self._close_finished.wait()
            return
        try:
            self.abci_server.stop(grace=0).wait()
        except Exception as exc:
            self._listener_shutdown_error = exc
        else:
            self._listener_closed.set()
        finally:
            self._close_finished.set()

    def _raise_process_wait_error(self) -> None:
        if self._process_wait_error is not None:
            raise CometBFTSupervisorError(
                "HND-SUPERVISOR-E-PROCESS-WAIT"
            ) from self._process_wait_error

    def _raise_cleanup_error(self) -> None:
        if self._listener_shutdown_error is not None:
            raise CometBFTSupervisorError(
                "HND-SUPERVISOR-E-ABCI-LISTENER-CLEANUP"
            ) from self._listener_shutdown_error

    def _monitor_process(self) -> None:
        try:
            self.cometbft_process.wait()
        except Exception as exc:
            self._process_wait_error = exc
        finally:
            # If process monitoring itself fails, close ABCI fail-closed and
            # preserve the monitoring error as a distinct failure reason.
            self._close_listener()

    @property
    def listener_closed(self) -> bool:
        return self._listener_closed.is_set()

    @property
    def cleanup_error(self) -> Exception | None:
        """Return an exception raised while stopping the ABCI listener, if any."""
        return self._listener_shutdown_error

    @property
    def process_wait_error(self) -> Exception | None:
        """Return an exception raised while waiting for the CometBFT child, if any."""
        return self._process_wait_error

    def poll(self):
        result = self.cometbft_process.poll()
        if result is not None:
            self._close_listener()
        self._raise_process_wait_error()
        if result is not None:
            self._raise_cleanup_error()
        return result

    def wait(self, timeout: float | None = None):
        try:
            result = self.cometbft_process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise
        except Exception as exc:
            if self._process_wait_error is None:
                self._process_wait_error = exc
            self._close_listener()
            raise
        self._close_listener()
        self._raise_process_wait_error()
        self._raise_cleanup_error()
        return result

    def terminate(self) -> None:
        self.cometbft_process.terminate()

    def kill(self) -> None:
        self.cometbft_process.kill()

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
    cometbft_home: str,
    profile_schema: ProfileSchema,
    arguments: Sequence[str],
    cwd: str,
    abci_bind_address: str = "127.0.0.1:26658",
    abci_max_workers: int = 16,
    environment: Mapping[str, str] | None = None,
    popen: Any = subprocess.Popen,
) -> tuple[ActivationState, SupervisedCometBFTNode]:
    """Authorize, bind ABCI, and start the pinned CometBFT process as one unit.

    The actual CometBFT Genesis bytes and parsed TOML profile are bound to
    the VSP before activation begins. The five-key etcd activation and
    independent witness acknowledgement are mandatory. The HND application
    binding is checked before the ABCI listener is opened. CometBFT is spawned
    only after that listener is ready; if spawning fails, the listener is
    stopped before the error is returned. The returned
    SupervisedCometBFTNode closes ABCI automatically when the child exits.
    Linux /proc/self/fd is required, and the executable descriptor remains open
    until Popen completes process creation.
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
            key.startswith(("LD_", "CMT_", "TM_"))
            or key in {"GLIBC_TUNABLES", "CMTHOME", "TMHOME"}
            for key in environment
        ):
            # CometBFT v0.40 uses CMT_* configuration overrides and CMTHOME;
            # older TM_* / TMHOME names are also denied to avoid fallback paths.
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-ENVIRONMENT")
        child_environment = dict(environment)

        if not callable(application_binding_verifier):
            raise CometBFTSupervisorError("HND-SUPERVISOR-E-APPLICATION-BINDING")

        # Reject bad deployment files before the witnessed etcd activation
        # mutates durable state. The same home files are re-read after witness
        # finalization and immediately before the ABCI listener is opened.
        try:
            _validate_cometbft_home_argument(arguments, cwd, cometbft_home)
            parsed_vsp_payload = parse_vsp_envelope(vsp_raw)["payload"]
            _verify_cometbft_deployment_artifacts(
                application=application,
                vsp_payload=parsed_vsp_payload,
                context=context,
                cometbft_home=cometbft_home,
                profile_artifact=profile_artifact,
                profile_schema=profile_schema,
            )
        except CometBFTSupervisorError:
            raise
        except Exception as exc:
            raise CometBFTSupervisorError(
                "HND-SUPERVISOR-E-COMETBFT-DEPLOYMENT-ARTIFACT-BINDING"
            ) from exc

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
                _validate_cometbft_home_argument(arguments, cwd, cometbft_home)
                _verify_cometbft_deployment_artifacts(
                    application=application,
                    vsp_payload=parse_vsp_envelope(vsp_raw)["payload"],
                    context=context,
                    cometbft_home=cometbft_home,
                    profile_artifact=profile_artifact,
                    profile_schema=profile_schema,
                )
                application_is_bound = application_binding_verifier(
                    application, state, profile_artifact
                )
            except CometBFTSupervisorError:
                raise
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
                # Re-read the exact files immediately before exec as well as
                # before listener bind. Deployment policy must keep these files
                # immutable; this second check narrows the bind-to-exec window.
                _verify_cometbft_deployment_artifacts(
                    application=application,
                    vsp_payload=parse_vsp_envelope(vsp_raw)["payload"],
                    context=context,
                    cometbft_home=cometbft_home,
                    profile_artifact=profile_artifact,
                    profile_schema=profile_schema,
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
                try:
                    return SupervisedCometBFTNode(
                        abci_server=abci_server,
                        abci_port=abci_port,
                        process=process,
                    )
                except Exception:
                    # If lifecycle monitoring cannot be established, do not
                    # leave a live child attached to an unmonitored listener.
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            process.kill()
                            process.wait(timeout=5)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    raise
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
