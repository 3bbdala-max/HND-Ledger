"""Fail-closed startup authorization boundaries for HND Station 2.

The legacy authorize_then_start() seam is retained for isolated reference tests
only. Production launch paths must use authorize_then_start_witnessed(), which
requires the five-key etcd activation transaction and an independently
authenticated witness acknowledgement before invoking the launcher.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from hnd_v02.activation_transaction import (
    ActivationState,
    AtomicActivationBackend,
    activate_verified_bundle,
)
from hnd_v02.witnessed_etcd_activation_coordinator import (
    WitnessedEtcdActivationCoordinator,
)


class StartupAuthorizationError(RuntimeError):
    """Startup was not authorized; no child process may be launched."""


def authorize_then_start(
    *,
    backend: AtomicActivationBackend,
    vsp_raw: bytes,
    trust_manifests: list[bytes],
    operator_acks_raw: bytes,
    profile_artifact: bytes,
    context: Mapping,
    trusted_witness_keys: Mapping[str, bytes],
    expected_operator_keys: Mapping[str, bytes],
    launch: Callable[[ActivationState], Any],
) -> tuple[ActivationState, Any]:
    """Legacy/test-only seam; it does not require an independent witness.

    Do not call this from a production process launcher. SQLite/reference
    backends and unit tests may use it to exercise the pre-witness contract.
    """
    if not callable(launch):
        raise StartupAuthorizationError("HND-STARTUP-E-LAUNCHER")
    if type(vsp_raw) is not bytes or not vsp_raw:
        raise StartupAuthorizationError("HND-STARTUP-E-VSP")
    if type(trust_manifests) is not list or not trust_manifests:
        raise StartupAuthorizationError("HND-STARTUP-E-TRUST-CHAIN")
    if any(type(item) is not bytes or not item for item in trust_manifests):
        raise StartupAuthorizationError("HND-STARTUP-E-TRUST-CHAIN")
    if type(operator_acks_raw) is not bytes or not operator_acks_raw:
        raise StartupAuthorizationError("HND-STARTUP-E-OPERATOR-ACKS")
    if type(profile_artifact) is not bytes or not profile_artifact:
        raise StartupAuthorizationError("HND-STARTUP-E-PROFILE")

    state = activate_verified_bundle(
        backend, vsp_raw, trust_manifests, operator_acks_raw, profile_artifact,
        context=context, trusted_witness_keys=trusted_witness_keys,
        expected_operator_keys=expected_operator_keys,
    )
    result = launch(state)
    return state, result


def authorize_then_start_witnessed(
    *,
    backend: Any,
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
    launch: Callable[[ActivationState], Any],
) -> tuple[ActivationState, Any]:
    """Verify, atomically activate, obtain witness receipt, finalize, then launch.

    The coordinator returns only after exact etcd intent/state/profile read-back
    and Ed25519 witness receipt verification. The launcher is never called on
    an unavailable witness, mismatched receipt, uncertain commit, or failed
    finalization. Callers must still ensure the supplied backend and witness
    are configured in separately administered production trust domains.
    """
    if not callable(launch):
        raise StartupAuthorizationError("HND-STARTUP-E-LAUNCHER")
    if type(activation_id) is not str or not activation_id:
        raise StartupAuthorizationError("HND-STARTUP-E-ACTIVATION-ID")
    if type(expected_witness_id) is not str or not expected_witness_id:
        raise StartupAuthorizationError("HND-STARTUP-E-WITNESS-ID")
    if type(expected_config_epoch) is not int or expected_config_epoch < 1:
        raise StartupAuthorizationError("HND-STARTUP-E-CONFIG-EPOCH")
    if type(vsp_raw) is not bytes or not vsp_raw:
        raise StartupAuthorizationError("HND-STARTUP-E-VSP")
    if type(trust_manifests) is not list or not trust_manifests:
        raise StartupAuthorizationError("HND-STARTUP-E-TRUST-CHAIN")
    if any(type(item) is not bytes or not item for item in trust_manifests):
        raise StartupAuthorizationError("HND-STARTUP-E-TRUST-CHAIN")
    if type(operator_acks_raw) is not bytes or not operator_acks_raw:
        raise StartupAuthorizationError("HND-STARTUP-E-OPERATOR-ACKS")
    if type(profile_artifact) is not bytes or not profile_artifact:
        raise StartupAuthorizationError("HND-STARTUP-E-PROFILE")
    if not isinstance(trusted_witness_keys, Mapping):
        raise StartupAuthorizationError("HND-STARTUP-E-TRUST-STORE")
    if not isinstance(expected_operator_keys, Mapping):
        raise StartupAuthorizationError("HND-STARTUP-E-OPERATOR-KEYS")

    try:
        coordinator = WitnessedEtcdActivationCoordinator(
            backend=backend,
            witness_client=witness_client,
            trusted_witness_keys=trusted_witness_keys,
            expected_witness_id=expected_witness_id,
            expected_config_epoch=expected_config_epoch,
        )
        state = coordinator.activate(
            activation_id=activation_id,
            vsp_raw=vsp_raw,
            trust_manifests=trust_manifests,
            operator_acks_raw=operator_acks_raw,
            profile_artifact=profile_artifact,
            context=context,
            trusted_operator_keys=expected_operator_keys,
        )
    except Exception as exc:
        raise StartupAuthorizationError("HND-STARTUP-E-WITNESSED-AUTHORIZATION") from exc

    result = launch(state)
    return state, result
