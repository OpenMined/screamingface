"""Configurable settings for the Hugging Face provider plugin (SF-345).

Model seeds are ``list[str]`` (not ``list[ModelEntry]``) so the whole list is
env-overridable as a JSON array via ``AIGW_HUGGINGFACE_DEFAULT_MODELS`` —
pydantic-settings cannot deserialize a frozen ``ModelEntry`` dataclass from an
env var. ``register_models`` turns each slug into a ``ModelEntry``.

Every slug is validated to the router-suffix form ``huggingface/<org>/<model>``
(optionally ``:<provider|policy>``). This rejects the unsafe provider-as-path-segment
form ``huggingface/<provider>/<org>/<model>``, which sends a malformed id to the
unified router and — without the pinned ``api_base`` — triggers an env-keyed
``huggingface.co`` mapping lookup that ignores the per-request token.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from aigateway.core.plugin_base import PluginSettings

# Unified OpenAI-compatible router. Pinning this as api_base short-circuits
# litellm's per-request provider-mapping fetch to huggingface.co.
_ROUTER_API_BASE = "https://router.huggingface.co/v1"


def _default_model_slugs() -> list[str]:
    """Seed models in ``huggingface/<org>/<model>:<provider>`` router form.

    Single source of truth for the SF model dropdown via ``GET /v1/models``
    (SF-284), so it must NOT be copied SF-side. Verify live provider mappings
    before relying on any seed (opt-in ``AIGW_LIVE`` test).
    """
    return [
        "huggingface/openai/gpt-oss-120b:cerebras",
        "huggingface/Qwen/Qwen3-Coder-480B-A35B-Instruct:novita",
        "huggingface/deepseek-ai/DeepSeek-R1:novita",
        "huggingface/google/gemma-2-2b-it:featherless-ai",
        "huggingface/meta-llama/Llama-3.1-8B-Instruct:nscale",
    ]


def _validate_model_slug(slug: str) -> str:
    """Enforce the safe router shape ``huggingface/<org>/<model>[:<provider|policy>]``.

    The repo part (before any ``:``) must be exactly ``<org>/<model>`` — one ``/``.
    Rejects the forbidden ``huggingface/<provider>/<org>/<model>`` path-segment form.
    """
    if not slug.startswith("huggingface/"):
        raise ValueError(f"HF model must start with 'huggingface/': {slug!r}")
    body = slug[len("huggingface/") :]
    repo, sep, suffix = body.partition(":")
    org, slash, model = repo.partition("/")
    if not slash or not org or not model or "/" in model:
        raise ValueError(
            f"unsafe/malformed HF model {slug!r}: expected "
            "'huggingface/<org>/<model>[:<provider>]'. The provider-as-path-segment "
            "form 'huggingface/<provider>/<org>/<model>' is forbidden."
        )
    if sep and (not suffix or ":" in suffix or "/" in suffix):
        raise ValueError(
            f"malformed HF model {slug!r}: the ':<provider|policy>' suffix must be a "
            "single non-empty token (e.g. ':novita')."
        )
    return slug


def pinned_router_target(slug: str) -> tuple[str, str] | None:
    """The ``(<org>/<model>, <backend>)`` pair a gateway id pins, or ``None``.

    Lives beside ``_validate_model_slug`` so there is ONE definition of what a
    well-formed HF gateway id is; this adds only the discovery-specific condition.

    WHY an unsuffixed id has no target: without ``:<provider>`` the router selects a
    backend PER REQUEST, so no single backend row describes the next call. Reporting
    one would be a guess dressed as live evidence.
    """
    try:
        _validate_model_slug(slug)
    except ValueError:
        return None
    repo, sep, backend = slug[len("huggingface/") :].partition(":")
    return (repo, backend) if sep else None


class HuggingFacePluginSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGW_HUGGINGFACE_",
        extra="ignore",
        populate_by_name=True,
    )

    default_models: list[str] = Field(default_factory=_default_model_slugs)
    router_api_base: str = _ROUTER_API_BASE
    validation_model: str | None = None

    @field_validator("default_models")
    @classmethod
    def _validate_models(cls, value: list[str]) -> list[str]:
        # Rejects unsafe/malformed entries (defaults AND env overrides) at construction.
        return [_validate_model_slug(slug) for slug in value]
