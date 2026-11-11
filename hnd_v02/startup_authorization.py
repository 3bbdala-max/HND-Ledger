"""Fail-closed application startup authorization boundary for HND Station 2.

This adapter does not claim to authenticate a production process, prevent
alternate direct launch paths, or provide an independent anti-rollback trust
domain. Deployments must supply a reviewed backend in an independent trust domain.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from hnd_v02.activation_transaction import (
    ActivationState,
    AtomicActivationBackend,
    activate_verified_bundle,
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
    """Commit verified activation before invoking the supplied launcher.

    Cryptographic preflight and the backend atomic profile/sequence transaction
    complete before launch is called. Any failure prevents launch.

    The launcher must consume only the committed profile/state. This is an
    integration seam, not an OS process supervisor: deployments must remove
    alternate direct launch paths. SQLite remains reference/test-only for
    anti-rollback because host/database rollback is possible.
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
