"""The run mode's declared world — `url4.toml`, read once at startup.

Endpoints are DECLARED, never discovered. A route path is exactly
``"/" + gateway_id``: no renaming and no synthesized aliases. Gateway ids are unique by
construction (they are aigateway's own registry keys), so route uniqueness is inherited
rather than re-derived.

WHY declared: the aliasing this replaces derived a bare name via ``split("/", 1)[-1]``, which
turned ``openrouter/openai/gpt-5.5`` into ``/openai/gpt-5.5`` (reads as the OpenAI API, bills
OpenRouter) and ``openrouter/anthropic/claude-opus-4.8`` into ``/anthropic/claude-opus-4.8``.
Aliases were also collision-dependent, so adding a model elsewhere in the catalog could
silently REMOVE an alias an expression depended on.

The file format mirrors ``url4 serve``'s (``url4.cli._serve``). ``[data]``, ``[commands]``,
``[holdings]`` and ``[identities]`` are reserved here but not parsed yet — declaring one is a
loud error rather than a silent no-op, so a config that looks like it works actually does.

# AIDEV-NOTE: this loader deliberately duplicates ~120 lines of `_serve.py`'s tested parsing
# rather than depending on it — `_serve` is a private CLI module in `packages/url4`, and the
# Runner is the only other consumer today. Extract a shared public module when a THIRD
# consumer appears; until then the duplication is cheaper than the coupling.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from url4_cloud import job_env

DEFAULT_CONFIG_PATH = "/etc/url4/url4.toml"
"""Where the declared world lives unless :data:`job_env.RUNNER_CONFIG` overrides it. Image-level
wiring: the App never writes that variable — the file is baked into the image."""

_AIGATEWAY_KEYS = frozenset({"base_url", "default_route", "models", "allow_outbound", "timeout_s"})
_MODEL_KEYS = frozenset({"id", "web_tools"})
_RESERVED_TABLES = frozenset({"data", "commands", "holdings", "identities"})
_TOP_LEVEL_KEYS = frozenset({"aigateway"})


class RunnerConfigError(ValueError):
    """The Runner's configuration is unusable — raised at startup, before any run."""


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """One declared route: the gateway id, plus the per-route capabilities it opts into.

    A route is addressed as a table rather than a bare id so capabilities are declared WHERE
    the route is, not in a parallel list that can silently disagree with it. `web_tools` is the
    first such capability; the shape is what a second one extends.

    WHY `web_tools` defaults to False: the tool loop rewrites the request the model sees (a
    `tools`/`tool_choice` payload, then extra round trips feeding results back). That is a
    behavior change per model, and not every provider handles an OpenAI-shape tool call the
    same way — so it is opted INTO per route, never inherited from the mere presence of a
    Tavily key. An operator who supplies a key but declares no `web_tools = true` route gets
    exactly the plain completions they declared.
    """

    id: str
    web_tools: bool = False


@dataclass(frozen=True, slots=True)
class AigatewaySection:
    """One declared aigateway world: which routes exist, and how to reach them."""

    base_url: str
    default_model: str
    models: tuple[ModelSpec, ...]
    allow_outbound: bool = True
    timeout_s: float = 60.0


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    """The whole declared world. ``aigateway is None`` is a legitimate tokenless world."""

    aigateway: AigatewaySection | None = None


def routes_for(models: Sequence[ModelSpec]) -> dict[str, ModelSpec]:
    """Map each route path — ``"/" + id``, 1:1, no aliases — to the spec that declared it.

    The VALUE is the whole spec, not the bare id: the endpoint that serves a route needs the
    capabilities declared alongside it (`web_tools`), and resolving them from the same lookup
    that resolves the id is what keeps a route and its capabilities from being fetched through
    two different paths that can disagree.
    """
    return {"/" + model.id: model for model in models}


def load_config(env: Mapping[str, str]) -> RunnerConfig:
    """Read and validate the declared world from ``env``'s config path."""
    path = Path(env.get(job_env.RUNNER_CONFIG, DEFAULT_CONFIG_PATH))
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RunnerConfigError(f"cannot read runner config {str(path)!r}: {exc}") from exc
    return parse_config(raw, env)


def parse_config(raw: Mapping[str, object], env: Mapping[str, str]) -> RunnerConfig:
    """Validate a parsed TOML mapping into a :class:`RunnerConfig`. Fail-fast."""
    _reject_unsupported_tables(raw)
    table = raw.get("aigateway")
    if table is None:
        return RunnerConfig()
    if not isinstance(table, Mapping):
        raise RunnerConfigError(f"[aigateway] must be a table, got {table!r}")
    return RunnerConfig(aigateway=_parse_aigateway(table, env))


def _reject_unsupported_tables(raw: Mapping[str, object]) -> None:
    declared = set(map(str, raw))
    reserved = sorted(declared & _RESERVED_TABLES)
    if reserved:
        raise RunnerConfigError(
            f"{reserved} is reserved in the runner config format but not supported yet — "
            "remove it, or land the endpoint kind that reads it"
        )
    unknown = sorted(declared - _TOP_LEVEL_KEYS - _RESERVED_TABLES)
    if unknown:
        raise RunnerConfigError(
            f"unknown top-level table(s) {unknown} (expected {sorted(_TOP_LEVEL_KEYS)})"
        )


def _parse_aigateway(table: Mapping[str, object], env: Mapping[str, str]) -> AigatewaySection:
    unknown = sorted(set(map(str, table)) - _AIGATEWAY_KEYS)
    if unknown:
        raise RunnerConfigError(
            f"[aigateway] has unknown key(s) {unknown} (expected {sorted(_AIGATEWAY_KEYS)})"
        )
    models = _models(table.get("models"))
    section = AigatewaySection(
        base_url=_str(table, "base_url", "http://127.0.0.1:9105"),
        default_model=_normalize_id(_str(table, "default_route", "")),
        models=models,
        allow_outbound=_bool(table, "allow_outbound", default=True),
        timeout_s=_float(table, "timeout_s", 60.0),
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
        raise RunnerConfigError(
            f"default_route {'/' + default_model!r} is not a declared model — "
            f"declared: {sorted(ids)}"
        )


def _models(value: object) -> tuple[ModelSpec, ...]:
    if not isinstance(value, list):
        raise RunnerConfigError(f"[aigateway] models must be a list, got {value!r}")
    if not value:
        raise RunnerConfigError("[aigateway] must declare at least one model")
    models: list[ModelSpec] = []
    seen: set[str] = set()
    for entry in value:
        spec = _model_spec(entry)
        if spec.id in seen:
            raise RunnerConfigError(f"[aigateway] declares duplicate model id {spec.id!r}")
        seen.add(spec.id)
        models.append(spec)
    return tuple(models)


def _model_spec(entry: object) -> ModelSpec:
    """One `[[aigateway.models]]` entry — a table, or a bare id string as shorthand.

    The string form is exactly ``{ id = "<it>" }``: a route that opts into nothing. It stays
    supported because "declare a plain route" should not require a table, and because every
    capability defaults off, so the two spellings cannot mean different things.
    """
    if isinstance(entry, Mapping):
        return _model_table(entry)
    if isinstance(entry, str):
        return ModelSpec(id=_model_id(entry))
    raise RunnerConfigError(
        f"[aigateway] model entry must be a table or an id string, got {entry!r}"
    )


def _model_table(table: Mapping[str, object]) -> ModelSpec:
    unknown = sorted(set(map(str, table)) - _MODEL_KEYS)
    if unknown:
        raise RunnerConfigError(
            f"[[aigateway.models]] has unknown key(s) {unknown} (expected {sorted(_MODEL_KEYS)})"
        )
    raw_id = table.get("id")
    if raw_id is None:
        raise RunnerConfigError("[[aigateway.models]] entry is missing its `id`")
    web_tools = table.get("web_tools", False)
    if not isinstance(web_tools, bool):
        raise RunnerConfigError(
            f"[[aigateway.models]] web_tools must be a boolean, got {web_tools!r}"
        )
    return ModelSpec(id=_model_id(str(raw_id)), web_tools=web_tools)


def _model_id(model: str) -> str:
    if not model:
        raise RunnerConfigError("[aigateway] declares an empty model id")
    if model.startswith("/"):
        raise RunnerConfigError(
            f"model id {model!r} must not start with '/' — the route path is derived as '/' + id"
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
        raise RunnerConfigError(f"[aigateway] {key} must be a boolean, got {value!r}")
    return value


def _float(table: Mapping[str, object], key: str, default: float) -> float:
    value = table.get(key)
    if value is None:
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise RunnerConfigError(f"[aigateway] {key} must be a number, got {value!r}") from None


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "AigatewaySection",
    "RunnerConfig",
    "RunnerConfigError",
    "load_config",
    "parse_config",
    "routes_for",
]
