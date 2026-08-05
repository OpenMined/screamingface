"""Configurable settings for the OpenRouter provider plugin (OME-428).

Disabled by default (plan D2): installing the package must not expose models
or accept API keys until an operator sets ``AIGW_OPENROUTER_ENABLED=true``.

Model seeds are ``list[str]`` gateway IDs (``openrouter/<author>/<model>``) so
the whole list is env-overridable as a JSON array via
``AIGW_OPENROUTER_DEFAULT_MODELS`` — pydantic-settings cannot deserialize a
frozen ``ModelEntry`` dataclass from an env var. Each gateway ID loses exactly
one ``openrouter/`` prefix at the LiteLLM wire; the remainder must be a valid
upstream OpenRouter model ID (plan D8).
"""

from __future__ import annotations

import re

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from aigateway.core.plugin_base import PluginSettings

GATEWAY_MODEL_PREFIX = "openrouter/"

# D8: ASCII upstream ID `<author>/<model>[:variant]` with exactly two non-empty
# segments; the author may carry a single leading `~` alias marker. The
# character classes reject every forbidden shape by construction: Unicode,
# controls, whitespace, backslashes, percent escapes, URL schemes,
# query/fragment markers, empty segments, extra slashes/colons, empty variants.
_UPSTREAM_MODEL_ID_RE = re.compile(
    r"~?[A-Za-z0-9][A-Za-z0-9._-]*"  # author
    r"/[A-Za-z0-9][A-Za-z0-9._-]*"  # model base (exactly one '/')
    r"(:[A-Za-z0-9][A-Za-z0-9._-]*)?"  # optional single non-empty ':variant'
)


def is_valid_upstream_model_id(value: object) -> bool:
    """True when ``value`` is a syntactically valid upstream OpenRouter model ID.

    Purely syntactic (plan D8): models are bootstrap metadata, not request
    authorization, so valid unlisted IDs pass and no catalog lookup happens.
    """
    return isinstance(value, str) and _UPSTREAM_MODEL_ID_RE.fullmatch(value) is not None


def _default_model_slugs() -> list[str]:
    """URL4 leaf seeds in gateway form — recommended bootstrap metadata (D8).

    All were present in the live OpenRouter catalog on 2026-08-05; re-check at release. Never
    treat this list as an authorization boundary.

    Validation here is purely SYNTACTIC (`is_valid_upstream_model_id`, D8) — nothing checks a
    slug against the live catalog, so a typo in one of these surfaces as a dispatch failure
    inside a user's expression, not at boot. Re-checking at release is the only guard.
    """
    return [
        "openrouter/anthropic/claude-fable-5",
        "openrouter/anthropic/claude-haiku-4.5",
        "openrouter/openai/gpt-5.5",
        "openrouter/anthropic/claude-opus-4.8",
        # AIDEV-NOTE: the DRACO benchmark judge. arXiv:2602.11685 §4.2 PINS it, and the
        # benchmarks repo warns that a different judge materially changes the scores — so it is
        # seeded here rather than left to a deployment. `apps/url4-cloud/url4.toml` declares the
        # matching route; `test_declared_models_match_aigateway.py` fails if the two drift.
        "openrouter/google/gemini-3.1-pro-preview",
        # The remaining DRACO candidate lineup, also used by the Fusion and
        # CorrectiveEnsemble examples. These must be real gateway seeds: merely adding them to
        # a dev environment makes catalog checks pass while execution still fails elsewhere.
        # All were present in the live OpenRouter catalog on 2026-08-05; re-check at release.
        "openrouter/google/gemini-3-flash-preview",
        "openrouter/moonshotai/kimi-k2.6",
        "openrouter/moonshotai/kimi-k3",
        "openrouter/deepseek/deepseek-v4-pro",
        "openrouter/qwen/qwen3.6-plus",
    ]


def _validate_gateway_slug(slug: str) -> str:
    """Enforce ``openrouter/<author>/<model>[:variant]`` for configured seeds."""
    if not slug.startswith(GATEWAY_MODEL_PREFIX):
        raise ValueError(f"OpenRouter model must start with {GATEWAY_MODEL_PREFIX!r}: {slug!r}")
    upstream = slug[len(GATEWAY_MODEL_PREFIX) :]
    if not is_valid_upstream_model_id(upstream):
        raise ValueError(
            f"malformed OpenRouter model {slug!r}: expected "
            "'openrouter/<author>/<model>' with an optional single ':variant'"
        )
    return slug


class OpenRouterPluginSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGW_OPENROUTER_",
        extra="ignore",
        populate_by_name=True,
    )

    # Net-new per-provider gate (no other provider has one): discovery still
    # registers the plugin, but a disabled plugin contributes no models and
    # returns no credential strategy, so it can neither store keys nor
    # resolve credentials for dispatch (plan D2 — fail closed in the plugin,
    # never a provider branch in the loader/registry).
    enabled: bool = False
    default_models: list[str] = Field(default_factory=_default_model_slugs)
    validation_model: str = "openrouter/openrouter/free"
    # Domains this deployment asks OpenRouter search to exclude for every caller. A caller's own
    # list is UNIONed with this and can never remove an operator entry. Actual support varies by
    # upstream model/engine; protocols needing hard exclusion must select a compatible route.
    # Empty by default: inventing policy here would silently shape everyone's retrieval.
    web_search_excluded_domains: list[str] = Field(default_factory=list)

    @field_validator("default_models")
    @classmethod
    def _validate_models(cls, value: list[str]) -> list[str]:
        # Rejects malformed entries (defaults AND env overrides) at construction.
        return [_validate_gateway_slug(slug) for slug in value]
