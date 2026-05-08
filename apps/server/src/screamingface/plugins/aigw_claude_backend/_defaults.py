"""Helpers for translating SF plugin settings into a gateway
``ProfileDefaults`` payload sent on ``POST /v1/auth/{provider}/profiles``.

Kept separate from ``routes.py`` so the resolution logic can be unit-tested
without standing up the FastAPI router.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from screamingface.plugins.aigw_claude_backend.plugin import AigwClaudeBackendSettings


# The gateway's ``ProfileDefaults.reasoning_effort`` field accepts only these
# three values. SF additionally allows ``"max"`` as an effort, but the gateway
# does not — drop anything outside this set rather than send a value that
# would be rejected.
_GATEWAY_REASONING_EFFORTS = frozenset({"low", "medium", "high"})


def _build_profile_defaults_from_settings(
    settings: AigwClaudeBackendSettings,
) -> dict[str, Any]:
    """Resolve the ``defaults`` payload for ``POST /v1/auth/{provider}/profiles``.

    Precedence per field: profile-level (``settings.profiles[default_profile]``)
    wins over top-level settings. Missing/None fields are omitted from the
    resulting dict — never sent as ``null``. ``temperature`` and ``max_tokens``
    have no SF source and are always omitted.
    """
    profile = None
    profiles = getattr(settings, "profiles", None) or {}
    default_profile = getattr(settings, "default_profile", None)
    if default_profile and default_profile in profiles:
        profile = profiles[default_profile]

    out: dict[str, Any] = {}

    # model: profile.model -> settings.default_model
    model = getattr(profile, "model", None) if profile is not None else None
    if model is None:
        model = getattr(settings, "default_model", None)
    if model is not None:
        out["model"] = model

    # system_prompt: profile.system_prompt only (no top-level equivalent)
    if profile is not None:
        sp = getattr(profile, "system_prompt", None)
        if sp is not None:
            out["system_prompt"] = sp

    # timeout_seconds: profile.timeout_seconds -> settings.timeout_seconds
    timeout: float | None = None
    if profile is not None:
        timeout = getattr(profile, "timeout_seconds", None)
    if timeout is None:
        timeout = getattr(settings, "timeout_seconds", None)
    if timeout is not None:
        out["timeout_seconds"] = timeout

    # reasoning_effort: profile.effort -> settings.default_effort.
    # Drop "max" (SF-only) and anything outside the gateway's enum.
    effort: str | None = None
    if profile is not None:
        effort = getattr(profile, "effort", None)
    if effort is None:
        effort = getattr(settings, "default_effort", None)
    if effort in _GATEWAY_REASONING_EFFORTS:
        out["reasoning_effort"] = effort

    return out
