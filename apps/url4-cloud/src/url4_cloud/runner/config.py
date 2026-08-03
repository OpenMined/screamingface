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

The file format mirrors ``url4 serve``'s (``url4.cli._serve``). ``[holdings]`` and
``[identities]`` are reserved here but not parsed yet — declaring one is a loud error rather
than a silent no-op, so a config that looks like it works actually does. ``[commands]`` (a local
subprocess backend, :class:`CommandSpec`) and ``[data]`` (read-only artifacts at their own url4
addresses, :class:`DataSpec`) ARE parsed.

# AIDEV-NOTE: this loader deliberately duplicates ~120 lines of `_serve.py`'s tested parsing
# rather than depending on it — `_serve` is a private CLI module in `packages/url4`, and the
# Runner is the only other consumer today. Extract a shared public module when a THIRD
# consumer appears; until then the duplication is cheaper than the coupling.
"""

from __future__ import annotations

import shlex
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from url4_cloud import job_env

DEFAULT_CONFIG_PATH = "/etc/url4/url4.toml"
"""Where the declared world lives unless :data:`job_env.RUNNER_CONFIG` overrides it. Image-level
wiring: the App never writes that variable — the file is baked into the image."""

DEFAULT_COMMAND_TIMEOUT_S = 120.0
"""Matches ``url4 serve``'s ``ServeConfig.timeout``, so the same url4.toml behaves the same
under both runtimes. Per route, not global — see :class:`CommandSpec`."""

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
_MODEL_KEYS = frozenset({"id", "web_tools", "native_web_search"})
_COMMAND_KEYS = frozenset({"argv", "timeout_s", "stdin"})
_DATA_KEYS = frozenset({"value", "file", "command", "media_type", "timeout_s"})
_DATA_SOURCES = ("value", "file", "command")
_RESERVED_TABLES = frozenset({"holdings", "identities"})
_TOP_LEVEL_KEYS = frozenset({"aigateway", "commands", "data"})


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

    TWO RETRIEVAL MECHANISMS, one per route, never both:

    * ``web_tools`` — a CLIENT-SIDE loop. The runner declares OpenAI-shape functions, the model
      asks, and the runner executes the search against Tavily and feeds results back. Works for
      any provider that can call a function, which is why it stays: most providers have no
      server-side search of their own.
    * ``native_web_search`` — the PROVIDER runs it. The runner asks the GATEWAY for retrieval
      with a provider-agnostic flag, and the gateway translates it into whatever that provider
      calls it; nothing here knows one provider's spelling. No runner loop, no second search
      backend, and the provider's own controls (notably domain exclusion) apply.

    Prefer native where a provider offers it: it is the surface a published benchmark score was
    produced on, and a client-side loop over a different search backend is a different
    experiment. Declaring BOTH is rejected at parse — one request would then ask the provider to
    search AND hand the model functions to search with, so the turn retrieves twice and bills
    for both.
    """

    id: str
    web_tools: bool = False
    native_web_search: bool = False


@dataclass(frozen=True, slots=True)
class AigatewaySection:
    """One declared aigateway world: which routes exist, and how to reach them."""

    base_url: str
    default_model: str
    models: tuple[ModelSpec, ...]
    allow_outbound: bool = True
    timeout_s: float = 60.0
    # WHY declarable rather than a constant: the runner-driven tool loop posts once per ROUND, and
    # a research answer legitimately takes more rounds than a lookup. MEASURED 2026-08-02 —
    # `kimi-k2.6` spent all 5 default rounds on tool calls and never returned content, for a
    # trivial question with freely reachable sources, so on the Tavily loop the default is a hard
    # per-case failure rather than a safety margin. It stays 5 for everyone who does not declare
    # it: raising the default would change the cost profile of every existing tool-using world.
    web_tool_max_iterations: int = 5


@dataclass(frozen=True, slots=True)
class CommandSpec:
    """One declared subprocess route: ``[commands]"/path" = …``.

    The argv is OPERATOR config and is executed without a shell; only the token substitutions
    (`{intent}`, `{context}`, `{param:<name>}`, `{params}`) carry caller-influenced text, and
    they are substituted in a single pass over this template so a token-shaped string in caller
    input stays literal. See ``url4.cli._serve.make_command_handler``.

    WHY ``timeout_s`` lives HERE rather than once per config: the routes a Job declares have
    genuinely different budgets — a rubric judge that calls a model outruns any bound that must
    still keep a fast data-shaping command honest. A single global value can only be wrong for
    one of them.

    ``stdin`` selects which half of the request is PIPED — ``"context"`` (the default, and the
    only behaviour before this existed) or ``"intent"``. A route whose payload is engine-supplied
    needs the latter: a cross-row reducer receives the JSON array of every row result as its
    intent, and a single argv token is capped by the kernel at 131,072 bytes, so argv is not a
    channel that payload fits in. Choosing the pipe does not withdraw ``{context}`` from argv.

    INVARIANT: the legal VALUES are the engine's (``_serve.COMMAND_STDIN_SOURCES``) and are NOT
    restated here. This module may not import url4 at all — the importer set is pinned by
    `test_only_url4_executor_module_imports_url4` — and a copy would be free to drift, so
    `connector.register_commands` passes the string through and translates the engine's
    `ValueError`, exactly as it already does for `node.endpoint`'s registrability rules.
    """

    path: str
    argv: tuple[str, ...]
    timeout_s: float = DEFAULT_COMMAND_TIMEOUT_S
    stdin: str = "context"


@dataclass(frozen=True, slots=True)
class DataSpec:
    """One declared read-only artifact: ``[data]"/path" = …``.

    Exactly one of ``value`` / ``file`` / ``command`` supplies the bytes. WHY exactly one and not
    a precedence order: two sources would make the served content depend on lookup order, which
    is a silent way to serve the wrong rubric.

    ``file`` is re-read PER REQUEST, so editing an artifact takes effect without a restart —
    the property that makes a declared world editable rather than frozen at build time.

    ``media_type`` declares the route's Content-Type so a collection served here parses by its
    declared type rather than being sniffed. Load-bearing for the case list: a one-line JSON
    array served as text/plain collapses to a SINGLE element, which would silently benchmark
    once against a blob instead of once per case.
    """

    path: str
    value: str | None = None
    file: str | None = None
    command: tuple[str, ...] | None = None
    media_type: str | None = None
    timeout_s: float = DEFAULT_COMMAND_TIMEOUT_S


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    """The whole declared world. ``aigateway is None`` is a legitimate tokenless world."""

    aigateway: AigatewaySection | None = None
    commands: tuple[CommandSpec, ...] = ()
    data: tuple[DataSpec, ...] = ()


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
    section = None
    if table is not None:
        if not isinstance(table, Mapping):
            raise RunnerConfigError(f"[aigateway] must be a table, got {table!r}")
        section = _parse_aigateway(table, env)
    commands = _commands(raw.get("commands"))
    data = _data(raw.get("data"))
    _reject_route_collisions(commands, data, section)
    return RunnerConfig(aigateway=section, commands=commands, data=data)


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


def _commands(value: object) -> tuple[CommandSpec, ...]:
    """Parse ``[commands]`` — a route path per key, an argv template per value.

    Absent is the normal case (a model-only world), so it yields the empty tuple rather than
    an error. TOML forbids duplicate keys, so route uniqueness WITHIN the table is inherited
    from the format; collisions against model routes are checked separately.
    """
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise RunnerConfigError(f"[commands] must be a table, got {value!r}")
    return tuple(_command_spec(str(path), entry) for path, entry in value.items())


def _command_spec(path: str, entry: object) -> CommandSpec:
    """One ``[commands]`` entry — a table, or a bare argv list/string as shorthand.

    The bare forms are exactly ``url4 serve``'s (``_serve._as_argv``), so a url4.toml written
    for a standalone node keeps working here; only the table form can declare `timeout_s`.
    """
    if not path.startswith("/"):
        raise RunnerConfigError(f"[commands] route {path!r} must start with '/'")
    if isinstance(entry, Mapping):
        return _command_table(path, entry)
    return CommandSpec(path=path, argv=_argv(path, entry))


def _command_table(path: str, table: Mapping[str, object]) -> CommandSpec:
    unknown = sorted(set(map(str, table)) - _COMMAND_KEYS)
    if unknown:
        raise RunnerConfigError(
            f"[commands] {path!r} has unknown key(s) {unknown} (expected {sorted(_COMMAND_KEYS)})"
        )
    if "argv" not in table:
        raise RunnerConfigError(f"[commands] {path!r} is missing its `argv`")
    timeout_s = _command_timeout(path, table.get("timeout_s"))
    return CommandSpec(
        path=path,
        argv=_argv(path, table["argv"]),
        timeout_s=timeout_s,
        stdin=_command_stdin(path, table.get("stdin")),
    )


def _command_stdin(path: str, value: object) -> str:
    """The TYPE is this module's business; the VALUE SET is the engine's (see `CommandSpec`).

    A non-string is caught here because it is a config-shape error like any other — `stdin = true`
    is a plausible typo, and letting it reach the engine would surface as a confusing repr in a
    message about allowed source names.
    """
    if value is None:
        return "context"
    if not isinstance(value, str):
        raise RunnerConfigError(f"[commands] {path!r} stdin must be a string, got {value!r}")
    return value


def _command_timeout(path: str, value: object) -> float:
    if value is None:
        return DEFAULT_COMMAND_TIMEOUT_S
    try:
        timeout_s = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise RunnerConfigError(
            f"[commands] {path!r} timeout_s must be a number, got {value!r}"
        ) from None
    if timeout_s <= 0:
        raise RunnerConfigError(f"[commands] {path!r} timeout_s must be > 0, got {timeout_s!r}")
    return timeout_s


def _argv(path: str, value: object) -> tuple[str, ...]:
    """Coerce a declared argv: a list of tokens, or a string split like a shell would.

    INVARIANT: the result is an argv LIST that is exec'd directly — never a command string
    handed to a shell. Splitting happens HERE, at config time, on operator-owned text.
    """
    if isinstance(value, str):
        argv = tuple(shlex.split(value))
    elif isinstance(value, Sequence):
        argv = tuple(str(item) for item in value)
    else:
        raise RunnerConfigError(
            f"[commands] {path!r} must be an argv list, a string, or a table, got {value!r}"
        )
    if not argv:
        raise RunnerConfigError(f"[commands] {path!r} declares an empty argv")
    return argv


def _data(value: object) -> tuple[DataSpec, ...]:
    """Parse ``[data]`` — a route path per key, a provider declaration per value.

    Absent is the normal case, so it yields the empty tuple. TOML forbids duplicate keys, so
    uniqueness WITHIN the table is inherited from the format; cross-family collisions are checked
    separately. Declaration order is preserved — a generated table diffs stably against the
    dataset it was emitted from.
    """
    if value is None:
        return ()
    if not isinstance(value, Mapping):
        raise RunnerConfigError(f"[data] must be a table, got {value!r}")
    return tuple(_data_spec(str(path), entry) for path, entry in value.items())


def _data_spec(path: str, entry: object) -> DataSpec:
    """One ``[data]`` entry — a table, or a bare string as inline-value shorthand.

    Mirrors ``url4 serve``'s ``_as_provider`` so one url4.toml dialect serves both runtimes.
    """
    if not path.startswith("/"):
        raise RunnerConfigError(f"[data] route {path!r} must start with '/'")
    if isinstance(entry, str):
        return DataSpec(path=path, value=entry)
    if not isinstance(entry, Mapping):
        raise RunnerConfigError(f"[data] {path!r} must be a string or a table, got {entry!r}")
    unknown = sorted(set(map(str, entry)) - _DATA_KEYS)
    if unknown:
        raise RunnerConfigError(
            f"[data] {path!r} has unknown key(s) {unknown} (expected {sorted(_DATA_KEYS)})"
        )
    declared = [key for key in _DATA_SOURCES if entry.get(key) is not None]
    if len(declared) != 1:
        raise RunnerConfigError(
            f"[data] {path!r} must declare exactly one of {list(_DATA_SOURCES)}, "
            f"got {declared or 'none'}"
        )
    media_type = entry.get("media_type")
    return DataSpec(
        path=path,
        value=str(entry["value"]) if "value" in declared else None,
        file=str(entry["file"]) if "file" in declared else None,
        command=_argv(path, entry["command"]) if "command" in declared else None,
        media_type=None if media_type is None else str(media_type),
        timeout_s=_command_timeout(path, entry.get("timeout_s")),
    )


def _reject_route_collisions(
    commands: Sequence[CommandSpec],
    data: Sequence[DataSpec],
    section: AigatewaySection | None,
) -> None:
    """A route path has exactly one owner, across all three route families.

    INVARIANT: registering the same path twice raises deep inside `Url4Node._check_routable` at
    world-build time, which names the path but not the config that declared it. Catching it here
    points the operator at the offending line instead.
    """
    command_paths = {cmd.path for cmd in commands}
    overlap = sorted(command_paths & {spec.path for spec in data})
    if overlap:
        raise RunnerConfigError(f"[data] {overlap} already declared as [commands] route(s)")
    if section is None:
        return
    model_routes = routes_for(section.models)
    for label, paths in (("[commands]", command_paths), ("[data]", {s.path for s in data})):
        collisions = sorted(path for path in paths if path in model_routes)
        if collisions:
            raise RunnerConfigError(
                f"{label} {collisions} already declared as aigateway model route(s)"
            )


def _positive_int(table: Mapping[str, object], key: str, default: int) -> int:
    """An `[aigateway]` count that must be a whole number above zero.

    INVARIANT: `bool` is rejected explicitly. It IS an `int` subclass in Python, so `true` would
    otherwise parse as 1 — a world where every tool-using route fails on its second round,
    configured by an operator who thought they were setting a flag.
    """
    value = table.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise RunnerConfigError(f"[aigateway] {key} must be an integer, got {value!r}")
    if value <= 0:
        raise RunnerConfigError(f"[aigateway] {key} must be > 0, got {value!r}")
    return value


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
        web_tool_max_iterations=_positive_int(table, "web_tool_max_iterations", 5),
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
    web_tools = _model_flag(table, "web_tools")
    native_web_search = _model_flag(table, "native_web_search")
    # INVARIANT: one route, one retrieval mechanism. Both would ask the provider to search AND
    # hand the model functions to search with, so the turn retrieves twice and bills for both.
    # Caught here, at parse, like every other route conflict — the alternative surfaces as a
    # doubled bill and a doubled latency nobody attributes.
    if web_tools and native_web_search:
        raise RunnerConfigError(
            f"[[aigateway.models]] {raw_id!r} declares both web_tools and native_web_search — "
            "a route serves ONE retrieval mechanism. Use native_web_search where the provider "
            "runs the search itself, web_tools where the runner must drive it."
        )
    return ModelSpec(
        id=_model_id(str(raw_id)), web_tools=web_tools, native_web_search=native_web_search
    )


def _model_flag(table: Mapping[str, object], key: str) -> bool:
    value = table.get(key, False)
    if not isinstance(value, bool):
        raise RunnerConfigError(f"[[aigateway.models]] {key} must be a boolean, got {value!r}")
    return value


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
