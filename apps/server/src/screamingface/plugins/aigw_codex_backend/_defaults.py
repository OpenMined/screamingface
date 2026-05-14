from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from screamingface.plugins.aigw_codex_backend.plugin import AigwCodexBackendSettings


_GATEWAY_REASONING_EFFORTS = frozenset({"low", "medium", "high"})


def _build_profile_defaults_from_settings(settings: AigwCodexBackendSettings) -> dict[str, Any]:
    profile = None
    profiles = getattr(settings, "profiles", None) or {}
    default_profile = getattr(settings, "default_profile", None)
    if default_profile and default_profile in profiles:
        profile = profiles[default_profile]

    out: dict[str, Any] = {}

    model = getattr(profile, "model", None) if profile is not None else None
    if model is None:
        model = getattr(settings, "default_model", None)
    if model is not None:
        out["model"] = model

    if profile is not None:
        system_prompt = getattr(profile, "system_prompt", None)
        if system_prompt is not None:
            out["system_prompt"] = system_prompt

    timeout: float | None = None
    if profile is not None:
        timeout = getattr(profile, "timeout_seconds", None)
    if timeout is None:
        timeout = getattr(settings, "timeout_seconds", None)
    if timeout is not None:
        out["timeout_seconds"] = timeout

    effort: str | None = None
    if profile is not None:
        effort = getattr(profile, "effort", None)
    if effort is None:
        effort = getattr(settings, "default_effort", None)
    if effort in _GATEWAY_REASONING_EFFORTS:
        out["reasoning_effort"] = effort

    return out
