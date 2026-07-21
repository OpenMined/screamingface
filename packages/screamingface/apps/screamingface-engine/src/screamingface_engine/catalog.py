"""Canonical executable model catalog and engine registry."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from screamingface_engine.aggregators import MEAN_ROUTE, REPORT_SCHEMA
from screamingface_engine.benchmarks import (
    GPQA_CASES_ROUTE,
    GPQA_ID,
    GPQA_TITLE,
    BenchmarkRoute,
)
from screamingface_engine.graders import CASE_GRADE_SCHEMA, EXACT_CHOICE_ROUTE
from screamingface_engine.reducers import MAJORITY_VOTE_ROUTE
from screamingface_engine.settings import MAX_REQUEST_TARGET_BYTES

type AuthMethod = Literal["oauth", "api_key"]

_CLAUDE_MODEL = re.compile(r"^claude-([a-z0-9-]+)-(\d+)-(\d+)$")
_HUGGINGFACE_MODEL = re.compile(
    r"^huggingface/(?P<organization>[A-Za-z0-9._-]+)/"
    r"(?P<model>[A-Za-z0-9._-]+):(?P<inference_provider>[A-Za-z0-9._-]+)$"
)
_CAPABILITY_POLICY = {
    "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra": ("web_search", "web_fetch"),
    "huggingface/zai-org/GLM-5.2~deepinfra": ("web_search", "web_fetch"),
}

BENCHMARK_ROUTES = (
    BenchmarkRoute(
        GPQA_ID,
        GPQA_TITLE,
        GPQA_CASES_ROUTE,
        "exact_choice",
        EXACT_CHOICE_ROUTE,
        "mean",
        MEAN_ROUTE,
    ),
)


@dataclass(frozen=True, slots=True)
class GatewayModel:
    """One strictly decoded AI Gateway model-catalog record."""

    id: str
    owned_by: str

    def __post_init__(self) -> None:
        _nonblank(self.id, "Gateway model ID")
        _nonblank(self.owned_by, "Gateway model owner")


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    """One public provider identity and its private AI Gateway adapter details."""

    id: str
    display_name: str
    gateway_provider: str
    auth_methods: tuple[AuthMethod, ...]
    callback_path: str | None

    @property
    def public(self) -> PublicProvider:
        return PublicProvider(self.id, self.display_name, self.auth_methods)


@dataclass(frozen=True, slots=True)
class PublicProvider:
    """Provider metadata safe to advertise through the engine registry."""

    id: str
    display_name: str
    auth_methods: tuple[AuthMethod, ...]


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """One public URL4 model route and its private AI Gateway model id."""

    id: str
    gateway_model: str
    provider: str
    tool_capabilities: tuple[str, ...] = ()

    @property
    def route(self) -> str:
        return f"/{self.id}"


PROVIDER_ROUTES = (
    ProviderRoute("codex", "OpenAI Codex", "codex", ("oauth",), "/auth/callback"),
    ProviderRoute(
        "gemini",
        "Google Gemini",
        "gemini-cli",
        # Gemini OAuth is intentionally not advertised until AI Gateway completes the
        # Code Assist onboarding/readiness flow. API-key connections remain supported.
        ("api_key",),
        "/oauth2callback",
    ),
    ProviderRoute(
        "anthropic",
        "Anthropic",
        "anthropic",
        ("oauth", "api_key"),
        "/callback",
    ),
    ProviderRoute(
        "huggingface",
        "Hugging Face",
        "huggingface",
        ("api_key",),
        None,
    ),
)

# WHY: Model providers come from AI Gateway, while Tavily is appended because its
# credential and future tool execution are owned by ScreamingFace engine itself.
PUBLIC_PROVIDERS = tuple(provider.public for provider in PROVIDER_ROUTES) + (
    PublicProvider("tavily", "Tavily", ("api_key",)),
)

# AIDEV-NOTE: This explicit provider/auth policy is temporary. AI Gateway is expected
# to expose provider and auth-method discovery soon; replace this tuple with one
# validated startup snapshot when that protected contract exists. Never infer auth
# methods from model IDs.


def resolve_model_routes(models: Sequence[GatewayModel]) -> tuple[ModelRoute, ...]:
    """Derive executable public routes from one Gateway startup snapshot."""

    routes: list[ModelRoute] = []
    public_ids: set[str] = set()
    # WHY: Gateway owns availability; ScreamingFace owns stable public naming and capabilities.
    for model in models:
        resolved = _model_route(model)
        if resolved is None:
            continue
        if resolved.id in public_ids:
            raise ValueError(f"duplicate public model ID {resolved.id!r}")
        public_ids.add(resolved.id)
        routes.append(resolved)
    if not routes:
        raise ValueError("AI Gateway catalog contains no models for a supported provider")
    return tuple(routes)


def _model_route(model: GatewayModel) -> ModelRoute | None:
    if model.owned_by == "anthropic":
        match = _CLAUDE_MODEL.fullmatch(model.id)
        if match is None:
            raise _alias_error(model)
        family, major, minor = match.groups()
        public_id = f"claude/{family}-{major}.{minor}"
        gateway_model = f"anthropic/{model.id}"
        provider = "anthropic"
    elif model.owned_by == "codex":
        if not model.id.startswith("codex/") or not model.id.removeprefix("codex/"):
            raise _alias_error(model)
        public_id = model.id
        gateway_model = model.id
        provider = "codex"
    elif model.owned_by == "gemini-cli":
        prefix = "gemini-cli/gemini-"
        if not model.id.startswith(prefix) or not model.id.removeprefix(prefix):
            raise _alias_error(model)
        public_id = f"gemini/{model.id.removeprefix(prefix)}"
        gateway_model = model.id
        provider = "gemini"
    elif model.owned_by == "huggingface":
        match = _HUGGINGFACE_MODEL.fullmatch(model.id)
        if match is None:
            raise _alias_error(model)
        organization, name, inference_provider = match.groups()
        # INVARIANT: ':' remains private to AI Gateway's provider pin; '~' keeps the
        # public model ID unambiguous inside URL4 paths and expressions.
        public_id = f"huggingface/{organization}/{name}~{inference_provider}"
        gateway_model = model.id
        provider = "huggingface"
    else:
        return None
    return ModelRoute(
        public_id,
        gateway_model,
        provider,
        _CAPABILITY_POLICY.get(public_id, ()),
    )


def _alias_error(model: GatewayModel) -> ValueError:
    return ValueError(
        f"cannot derive public model ID from Gateway model {model.id!r} owned by {model.owned_by!r}"
    )


def registry_document(
    model_routes: Sequence[ModelRoute],
    *,
    max_request_target_bytes: int = MAX_REQUEST_TARGET_BYTES,
) -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": [
            "screamingface.recipe-result.v1",
            CASE_GRADE_SCHEMA,
            REPORT_SCHEMA,
        ],
        "limits": {"max_request_target_bytes": max_request_target_bytes},
        "providers": [
            {
                "id": provider.id,
                "display_name": provider.display_name,
                "auth_methods": list(provider.auth_methods),
            }
            for provider in PUBLIC_PROVIDERS
        ],
        "models": [
            {
                "id": model.id,
                "provider": model.provider,
                "supported_tools": list(model.tool_capabilities),
            }
            for model in model_routes
        ],
        "benchmarks": [benchmark.public for benchmark in BENCHMARK_ROUTES],
        "reducers": [{"id": "majority_vote", "route": MAJORITY_VOTE_ROUTE}],
    }


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value
