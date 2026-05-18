"""Helpers for translating SF plugin settings into a gateway
``ProfileDefaults`` payload sent on ``POST /v1/auth/{provider}/profiles``.

Kept separate from ``routes.py`` so the resolution logic can be unit-tested
without standing up the FastAPI router.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from screamingface.plugins.aigw_base import build_profile_defaults_from_settings

if TYPE_CHECKING:
    from screamingface.plugins.aigw_claude_backend.plugin import AigwClaudeBackendSettings


def _build_profile_defaults_from_settings(
    settings: AigwClaudeBackendSettings,
) -> dict[str, Any]:
    """Resolve the ``defaults`` payload for ``POST /v1/auth/{provider}/profiles``.

    Precedence per field: profile-level (``settings.profiles[default_profile]``)
    wins over top-level settings. Missing/None fields are omitted from the
    resulting dict — never sent as ``null``. ``temperature`` and ``max_tokens``
    have no SF source and are always omitted.
    """
    out = build_profile_defaults_from_settings(settings)
    # claude_backend_api never applied SF's generic `default_effort` to Claude.
    # Leaving it out preserves that behavior and avoids enabling Anthropic
    # thinking for every gateway-routed Claude request by accident.
    out.pop("reasoning_effort", None)
    return out
