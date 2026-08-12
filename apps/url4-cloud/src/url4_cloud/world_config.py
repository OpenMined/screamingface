"""The Engine's declared world — ``url4.toml``, read once at startup.

Both the control plane and Runner consume this module. Discovery must project onto the exact
configuration the Runner executes; a second partial TOML reader would let the two disagree.

Endpoints are DECLARED, never discovered. A route path is exactly
``"/" + gateway_id``: no renaming and no synthesized aliases. Gateway ids are unique by
construction (they are aigateway's own registry keys), so route uniqueness is inherited
rather than re-derived.

WHY declared: the aliasing this replaces derived a bare name via ``split("/", 1)[-1]``, which
turned ``openrouter/openai/gpt-5.5`` into ``/openai/gpt-5.5`` (reads as the OpenAI API, bills
OpenRouter) and ``openrouter/anthropic/claude-opus-4.8`` into ``/anthropic/claude-opus-4.8``.
Aliases were also collision-dependent, so adding a model elsewhere in the catalog could
silently REMOVE an alias an expression depended on.

The file format mirrors ``url4 serve``'s (``url4.cli._serve``), one way stricter: a model id here
must also be renderable as a URL4 expression path (see ``_MODEL_ID_RE``).

``[data]``, ``[commands]``,
``[holdings]`` and ``[identities]`` are reserved here but not parsed yet — declaring one is a
loud error rather than a silent no-op, so a config that looks like it works actually does.

# AIDEV-NOTE: this loader deliberately duplicates `_serve.py`'s tested parsing rather than
# depending on it — `_serve` is a private CLI module in another package. Within URL4 Cloud this
# module is the single authority shared by the App and Runner.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from url4_cloud import job_env

DEFAULT_CONFIG_PATH = "/etc/url4/url4.toml"

"""Where the declared world lives unless :data:`job_env.RUNNER_CONFIG` overrides it. Image-level
wiring: the App never writes that variable — the file is baked into the image."""

DEFAULT_WEB_TOOL_MAX_ITERATIONS = 5

_AIGATEWAY_KEYS = frozenset(
    {
        "base_url",
        "default_route",
        "models",
        "allow_outbound",
        "timeout_s",
        "web_tool_max_iterations",
    }
)
_MODEL_KEYS = frozenset({"id", "web_search"})
_RESERVED_TABLES = frozenset({"data", "commands", "holdings", "identities"})
_TOP_LEVEL_KEYS = frozenset({"aigateway"})
_MODEL_ID_RE = re.compile(r"[A-Za-z0-9\-_.~]+(?:/[A-Za-z0-9\-_.~]+)*", re.ASCII)


class WorldConfigError(ValueError):
    """The Runner's configuration is unusable — raised at startup, before any run."""


WEB_SEARCH_NATIVE_PROVIDERS = frozenset({"openrouter"})
"""Providers whose aigateway plugin carries a native web-search envelope.

A route served by one of these delegates retrieval to the provider; every other searching
route runs the Tavily tool loop here instead.

WHY only `openrouter`: `web_search` is declared by exactly one aigateway plugin
(`plugins/openrouter_provider/parameters.py`). The other plugins register bespoke
`custom_llm_provider` handlers — `codex` (OpenAI Codex OAuth), `gemini-cli` (Google Code
Assist), `antigravity`, and aigateway's own `anthropic` — rather than litellm's stock vendor
routes, so litellm's `web_search_options` is not reachable through them and a request
carrying an undeclared parameter is refused by the parameter contract.

AIDEV-NOTE: adding an entry here is NOT sufficient on its own. The provider's aigateway
plugin must first declare the parameter, build the envelope from one pure function shared by
the dispatch path and the cache-key projection, key the fields, and bump the cache adapter
revision (OME-777 invariant I1). This set is the LAST step of that work, not the first.
"""

_UNPREFIXED_PROVIDER = "anthropic"


def provider_of(model_id: str) -> str:
    """The provider that serves a route: the segment before the first `/`.

    WHY the segment and not a substring of the whole id: `openrouter/anthropic/claude-opus-4.8`
    is an OpenRouter route and must take OpenRouter's envelope. A substring test hands it to
    any future `anthropic` entry and silently sends it down the wrong provider's mechanism.

    INVARIANT: an id with no `/` is Anthropic's — aigateway's catalog leaves exactly that one
    provider unprefixed (`claude-haiku-4-5`), the `anthropic/` prefix appearing only in
    litellm_params.
    """
    prefix, separator, _ = model_id.partition("/")
    return prefix if separator else _UNPREFIXED_PROVIDER


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """One declared route: the gateway id, plus whether it may search the web.

    A route is addressed as a table rather than a bare id so capabilities are declared WHERE
    the route is, not in a parallel list that can silently disagree with it.

    WHY only THAT it searches, never HOW: which mechanism a model can carry is a property of
    its provider, not a choice an operator should have to encode per route. Declaring the
    mechanism made the operator the keeper of that knowledge and let a route claim one its
    provider could not serve. The mechanism is therefore derived, and this file states intent.

    WHY the default is True: a deployment that supplies a Tavily key wants retrieval. The
    previous per-route opt-in meant a route stayed silently non-searching until somebody
    remembered to declare it. A route that must not search says so with `web_search = false`.
    """

    id: str
    web_search: bool = True

    @property
    def uses_native_web_search(self) -> bool:
        """The provider performs the search; the Runner only sets `web_search` on the body."""
        return self.web_search and provider_of(self.id) in WEB_SEARCH_NATIVE_PROVIDERS

    @property
    def uses_web_tools(self) -> bool:
        """The Runner performs the search itself, through the Tavily tool loop.

        INVARIANT: this and `uses_native_web_search` are mutually exclusive, and their
        disjunction is `web_search` — a searching route has exactly one mechanism.
        """
        return self.web_search and not self.uses_native_web_search


@dataclass(frozen=True, slots=True)
class AigatewaySection:
    """One declared aigateway world: which routes exist, and how to reach them."""

    base_url: str
    default_model: str
    models: tuple[ModelSpec, ...]
    allow_outbound: bool = True
    timeout_s: float = 60.0
    web_tool_max_iterations: int = DEFAULT_WEB_TOOL_MAX_ITERATIONS


@dataclass(frozen=True, slots=True)
class WorldConfig:
    """The whole declared world. ``aigateway is None`` is a legitimate tokenless world."""

    aigateway: AigatewaySection | None = None


def routes_for(models: Sequence[ModelSpec]) -> dict[str, ModelSpec]:
    """Map each route path — ``"/" + id``, 1:1, no aliases — to the spec that declared it.

    The VALUE is the whole spec, not the bare id: the endpoint that serves a route needs the
    capability declared alongside it (`web_search`), and resolving it from the same lookup
    that resolves the id is what keeps a route and its capability from being fetched through
    two different paths that can disagree.
    """
    return {"/" + model.id: model for model in models}


def declared_model_ids(env: Mapping[str, str]) -> frozenset[str]:
    """Return the model ids from the same fully validated world the Runner consumes."""

    section = load_config(env).aigateway
    if section is None:
        return frozenset()
    return frozenset(model.id for model in section.models)


def load_config(env: Mapping[str, str]) -> WorldConfig:
    """Read and validate the declared world from ``env``'s config path."""
    path = Path(env.get(job_env.RUNNER_CONFIG, DEFAULT_CONFIG_PATH))
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise WorldConfigError(f"cannot read world config {str(path)!r}: {exc}") from exc
    return parse_config(raw, env)


def parse_config(raw: Mapping[str, object], env: Mapping[str, str]) -> WorldConfig:
    """Validate a parsed TOML mapping into a :class:`WorldConfig`. Fail-fast."""
    _reject_unsupported_tables(raw)
    table = raw.get("aigateway")
    if table is None:
        return WorldConfig()
    if not isinstance(table, Mapping):
        raise WorldConfigError(f"[aigateway] must be a table, got {table!r}")
    return WorldConfig(aigateway=_parse_aigateway(table, env))


def _reject_unsupported_tables(raw: Mapping[str, object]) -> None:
    declared = set(map(str, raw))
    reserved = sorted(declared & _RESERVED_TABLES)
    if reserved:
        raise WorldConfigError(
            f"{reserved} is reserved in the world config format but not supported yet — "
            "remove it, or land the endpoint kind that reads it"
        )
    unknown = sorted(declared - _TOP_LEVEL_KEYS - _RESERVED_TABLES)
    if unknown:
        raise WorldConfigError(
            f"unknown top-level table(s) {unknown} (expected {sorted(_TOP_LEVEL_KEYS)})"
        )


def _parse_aigateway(table: Mapping[str, object], env: Mapping[str, str]) -> AigatewaySection:
    unknown = sorted(set(map(str, table)) - _AIGATEWAY_KEYS)
    if unknown:
        raise WorldConfigError(
            f"[aigateway] has unknown key(s) {unknown} (expected {sorted(_AIGATEWAY_KEYS)})"
        )
    models = _models(table.get("models"))
    section = AigatewaySection(
        base_url=_str(table, "base_url", "http://127.0.0.1:9105"),
        default_model=_normalize_id(_str(table, "default_route", "")),
        models=models,
        allow_outbound=_bool(table, "allow_outbound", default=True),
        timeout_s=_float(table, "timeout_s", 60.0),
        web_tool_max_iterations=_positive_int(
            table,
            "web_tool_max_iterations",
            DEFAULT_WEB_TOOL_MAX_ITERATIONS,
        ),
    )
    section = _apply_env(section, env)
    _require_declared(section.default_model, models)
    return section


def _apply_env(section: AigatewaySection, env: Mapping[str, str]) -> AigatewaySection:
    """Env beats the file, per field — a deployment overrides without rebuilding the image.

    The token is deliberately NOT here: it is a secret and never lands in a config file.
    """
    if env.get(job_env.AIGATEWAY_BASE_URL):
        section = replace(section, base_url=env[job_env.AIGATEWAY_BASE_URL])
    if env.get(job_env.AIGATEWAY_MODEL):
        section = replace(section, default_model=_normalize_id(env[job_env.AIGATEWAY_MODEL]))
    return section


def _require_declared(default_model: str, models: tuple[ModelSpec, ...]) -> None:
    ids = [model.id for model in models]
    if default_model not in ids:
        raise WorldConfigError(
            f"default_route {'/' + default_model!r} is not a declared model — "
            f"declared: {sorted(ids)}"
        )


def _models(value: object) -> tuple[ModelSpec, ...]:
    if not isinstance(value, list):
        raise WorldConfigError(f"[aigateway] models must be a list, got {value!r}")
    if not value:
        raise WorldConfigError("[aigateway] must declare at least one model")
    models: list[ModelSpec] = []
    seen: set[str] = set()
    for entry in value:
        spec = _model_spec(entry)
        if spec.id in seen:
            raise WorldConfigError(f"[aigateway] declares duplicate model id {spec.id!r}")
        seen.add(spec.id)
        models.append(spec)
    return tuple(models)


def _model_spec(entry: object) -> ModelSpec:
    """One `[[aigateway.models]]` entry — a table, or a bare id string as shorthand.

    The string form is exactly ``{ id = "<it>" }``. It stays supported because "declare a
    plain route" should not require a table, and because both spellings take `web_search`'s
    default of true, so the two spellings cannot mean different things.
    """
    if isinstance(entry, Mapping):
        return _model_table(entry)
    if isinstance(entry, str):
        return ModelSpec(id=_model_id(entry))
    raise WorldConfigError(
        f"[aigateway] model entry must be a table or an id string, got {entry!r}"
    )


def _model_table(table: Mapping[str, object]) -> ModelSpec:
    unknown = sorted(set(map(str, table)) - _MODEL_KEYS)
    if unknown:
        raise WorldConfigError(
            f"[[aigateway.models]] has unknown key(s) {unknown} (expected {sorted(_MODEL_KEYS)})"
        )
    raw_id = table.get("id")
    if raw_id is None:
        raise WorldConfigError("[[aigateway.models]] entry is missing its `id`")
    value = table.get("web_search", True)
    if not isinstance(value, bool):
        raise WorldConfigError(f"[[aigateway.models]] web_search must be a boolean, got {value!r}")
    return ModelSpec(id=_model_id(str(raw_id)), web_search=value)


def _model_id(model: str) -> str:
    if not model:
        raise WorldConfigError("[aigateway] declares an empty model id")
    if model.startswith("/"):
        raise WorldConfigError(
            f"model id {model!r} must not start with '/' — the route path is derived as '/' + id"
        )
    if _MODEL_ID_RE.fullmatch(model) is None:
        raise WorldConfigError(
            f"model id {model!r} is not a valid URL4 expression path — each segment may contain "
            "only ASCII letters, digits, '-', '_', '.', or '~'"
        )
    return model


def _normalize_id(value: str) -> str:
    """Accept both ``/codex/gpt-5.5`` and ``codex/gpt-5.5`` — one leading slash only."""
    return value.removeprefix("/")


def _str(table: Mapping[str, object], key: str, default: str) -> str:
    value = table.get(key)
    return default if value is None else str(value)


def _bool(table: Mapping[str, object], key: str, *, default: bool) -> bool:
    value = table.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise WorldConfigError(f"[aigateway] {key} must be a boolean, got {value!r}")
    return value


def _float(table: Mapping[str, object], key: str, default: float) -> float:
    value = table.get(key)
    if value is None:
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise WorldConfigError(f"[aigateway] {key} must be a number, got {value!r}") from None


def _positive_int(table: Mapping[str, object], key: str, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WorldConfigError(f"[aigateway] {key} must be a positive integer, got {value!r}")
    return value


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "AigatewaySection",
    "WorldConfig",
    "WorldConfigError",
    "declared_model_ids",
    "load_config",
    "parse_config",
    "routes_for",
]
