"""Configuration, backend handlers, and node/app assembly for ``url4 serve``.

This is the transport-adapter layer behind the CLI (:mod:`url4.cli`). It builds a
:class:`~url4.server.Url4Node` from a :class:`ServeConfig` — registering one
intent-processor endpoint per configured route (LLM routes call the aigateway;
command routes run a local subprocess, doctrine N4) — and wraps the node's
framework-free ``asgi()`` with the run-level concerns the node does not own:
bounded in-flight admission (503), a per-request timeout (504), and graceful
shutdown of the shared HTTP client.

# INVARIANT: this module imports no web framework. Serving is the existing
# ``Url4Node.asgi()`` (raw ASGI) run under uvicorn (the ``url4[server]`` extra);
# Starlette is never involved. The core import graph stays framework-free.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
import tomllib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from url4.errors import ResolutionError
from url4.server import Request, Url4Node

# WHY: friendly url4 route -> aigateway ``provider/model``. The single bump point
# when model ids drift (they will); fully overridable via url4.toml [routes] /
# --route. Deliberately concrete so ``url4 serve`` works against a running
# aigateway with zero config.
DEFAULT_ROUTES: dict[str, str] = {
    "/claude": "claude/claude-opus-4-8",
    "/gemini": "gemini/gemini-2.0-flash",
    "/codex": "codex/gpt-5-codex",
}

_CHAT_PATH = "/v1/chat/completions"
_HEALTH_PATH = "/healthz"

EndpointHandler = Callable[[Request], Awaitable[str]]


class ConfigError(ValueError):
    """A serve configuration is invalid — raised before bind (fail-fast)."""


@dataclass(frozen=True, slots=True)
class ServeConfig:
    """Everything ``url4 serve`` needs, resolved from flags > env > toml > default."""

    host: str = "127.0.0.1"
    port: int = 4404
    backend_url: str = "http://127.0.0.1:9105"
    backend_token: str | None = None
    processor: str = "/claude"
    eval_path: str = "/v1"
    concurrency: int = 32
    max_inflight: int = 16
    timeout: float = 120.0
    routes: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_ROUTES))
    commands: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def validate(self) -> None:
        """Raise :class:`ConfigError` for any unusable setting, before bind."""
        _require(self.concurrency >= 1, f"concurrency must be >= 1, got {self.concurrency}")
        _require(self.max_inflight >= 1, f"max-inflight must be >= 1, got {self.max_inflight}")
        _require(self.timeout > 0, f"timeout must be > 0, got {self.timeout}")
        _require_paths(self.routes, "route")
        _require_paths(self.commands, "command")
        _require_argv(self.commands)
        _require(not (set(self.routes) & set(self.commands)), "route/command paths collide")
        reserved = {self.eval_path, _HEALTH_PATH} & (set(self.routes) | set(self.commands))
        _require(not reserved, f"route/command paths clash with reserved {sorted(reserved)}")
        # The node registers /healthz as a data route; an eval path equal to it
        # would collide at build time (an uncaught ValueError) — reject it here so
        # the misconfiguration fails fast with a clean config error before bind.
        _require(
            self.eval_path != _HEALTH_PATH,
            f"eval path cannot be the reserved health path {_HEALTH_PATH!r}",
        )
        # INVARIANT: a fan-out reduce dispatches to ``processor`` at runtime, so it
        # MUST be a registered LLM route or the reduce fails mid-evaluation.
        _require(
            self.processor in self.routes,
            f"processor {self.processor!r} is not a configured route: {sorted(self.routes)}",
        )


def _require(ok: bool, message: str) -> None:  # noqa: FBT001 - tiny internal guard
    if not ok:
        raise ConfigError(message)


def _require_paths(paths: Mapping[str, object], label: str) -> None:
    for path in paths:
        _require(path.startswith("/"), f"{label} path {path!r} must start with '/'")


def _require_argv(commands: Mapping[str, tuple[str, ...]]) -> None:
    for path, argv in commands.items():
        _require(bool(argv), f"command {path!r} has an empty argv")


# --- config resolution -----------------------------------------------------------


def resolve(
    overrides: Mapping[str, object], env: Mapping[str, str], toml_path: Path | None
) -> ServeConfig:
    """Build a :class:`ServeConfig` — flag > env > url4.toml > default, per field.

    ``overrides`` holds CLI flag values (``None`` == unset). Route maps merge
    across layers (defaults <- toml ``[routes]`` <- ``--route`` flags); commands
    come from url4.toml ``[commands]`` only.
    """
    toml = _read_toml(toml_path)
    routes = {**DEFAULT_ROUTES, **_toml_str_map(toml.get("routes")), **_flag_routes(overrides)}
    return ServeConfig(
        host=_pick_str("host", overrides, env, toml, "127.0.0.1"),
        port=_pick_int("port", overrides, env, toml, 4404),
        backend_url=_pick_str("backend_url", overrides, env, toml, "http://127.0.0.1:9105"),
        backend_token=_resolve_token(overrides, env),
        processor=_pick_str("processor", overrides, env, toml, "/claude"),
        eval_path=_pick_str("eval_path", overrides, env, toml, "/v1"),
        concurrency=_pick_int("concurrency", overrides, env, toml, 32),
        max_inflight=_pick_int("max_inflight", overrides, env, toml, 16),
        timeout=_pick_float("timeout", overrides, env, toml, 120.0),
        routes=routes,
        commands=_toml_command_map(toml.get("commands")),
    )


def _pick(
    name: str, overrides: Mapping[str, object], env: Mapping[str, str], toml: Mapping
) -> object:
    flag = overrides.get(name)
    if flag is not None:
        return flag
    from_env = env.get(f"URL4_{name.upper()}")
    return from_env if from_env is not None else toml.get(name)


def _pick_str(name, overrides, env, toml, default: str) -> str:
    value = _pick(name, overrides, env, toml)
    return default if value is None else str(value)


def _pick_int(name, overrides, env, toml, default: int) -> int:
    value = _pick(name, overrides, env, toml)
    if value is None:
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ConfigError(f"{name} must be an integer, got {value!r}") from None


def _pick_float(name, overrides, env, toml, default: float) -> float:
    value = _pick(name, overrides, env, toml)
    if value is None:
        return default
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise ConfigError(f"{name} must be a number, got {value!r}") from None


def _resolve_token(overrides: Mapping[str, object], env: Mapping[str, str]) -> str | None:
    # WHY: keep secrets off argv — the flag carries a *path* (or '-' for stdin),
    # never the raw token; the value itself comes from a file, stdin, or env.
    source = overrides.get("backend_token")
    if source is None:
        return env.get("URL4_BACKEND_TOKEN")
    if source == "-":
        return sys.stdin.readline().strip()
    try:
        return Path(str(source)).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError(f"cannot read backend-token file {source!r}: {exc}") from exc


def _read_toml(path: Path | None) -> Mapping[str, object]:
    if path is None:
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config {str(path)!r}: {exc}") from exc


def _toml_str_map(value: object) -> dict[str, str]:
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, Mapping) else {}


def _toml_command_map(value: object) -> dict[str, tuple[str, ...]]:
    return {str(k): _as_argv(v) for k, v in value.items()} if isinstance(value, Mapping) else {}


def _as_argv(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(shlex.split(value))
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    raise ConfigError(f"command must be a string or list, got {value!r}")


def _flag_routes(overrides: Mapping[str, object]) -> dict[str, str]:
    raw = overrides.get("routes")
    items = raw if isinstance(raw, Sequence) and not isinstance(raw, str) else ()
    result: dict[str, str] = {}
    for item in items:
        path, sep, model = str(item).partition("=")
        if not sep:
            raise ConfigError(f"--route must be PATH=MODEL, got {item!r}")
        result[path] = model
    return result


# --- backend handlers ------------------------------------------------------------


def _merge(intent: str, context: str) -> str:
    """Combine a leaf's instruction and data into one prompt (engine convention)."""
    # WHY: mirrors url4.dag.node.default_process so a served leaf reads exactly like
    # an in-engine (sources)!intent merge — HTTP and in-process cannot diverge.
    if intent and context:
        return f"{intent}\n\n{context}"
    return intent or context or ""


def make_llm_handler(
    client: httpx.AsyncClient, backend_url: str, model: str, token: str | None
) -> EndpointHandler:
    """An intent processor that runs ``model`` via the aigateway chat API.

    # FEATURE: ensemble model routes. The engine dispatches ``/claude?q=(ctx)!intent``
    # here for BOTH leaf calls and the fan-out reduce; the handler shapes it into an
    # OpenAI-compatible completion and returns the assistant text.
    """
    url = backend_url.rstrip("/") + _CHAT_PATH
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def handler(request: Request) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": _merge(request.intent, request.context)}],
            "stream": False,
        }
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ResolutionError(f"aigateway call for model {model!r} failed: {exc}") from exc
        return _extract_content(response, model)

    return handler


def _extract_content(response: httpx.Response, model: str) -> str:
    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ResolutionError(
            f"aigateway returned an unexpected response for model {model!r}: {exc}"
        ) from exc


def make_command_handler(argv: Sequence[str], timeout: float) -> EndpointHandler:
    """An intent processor that runs a local subprocess (doctrine N4).

    # AIDEV-NOTE: security — the argv is OPERATOR config; only the piped stdin
    # (resolved context) and the {intent}/{context} substitutions are caller-
    # influenced. No shell: exec an argv LIST, never a command string.
    """
    template = tuple(argv)

    async def handler(request: Request) -> str:
        command = [_subst(token, request) for token in template]
        return await _run_command(command, request.context, timeout)

    return handler


def _subst(token: str, request: Request) -> str:
    return token.replace("{intent}", request.intent).replace("{context}", request.context)


async def _run_command(command: list[str], stdin_text: str, timeout: float) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise ResolutionError(f"command {command[0]!r} failed to start: {exc}") from exc
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin_text.encode()), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ResolutionError(f"command {command[0]!r} timed out after {timeout}s") from None
    if proc.returncode != 0:
        raise ResolutionError(
            f"command {command[0]!r} exited {proc.returncode}: "
            f"{err.decode(errors='replace')[:500].strip()}"
        )
    # errors='replace': a command that emits non-UTF-8 bytes must not escape the
    # handler's ResolutionError contract as a raw UnicodeDecodeError (→ bare 500).
    return out.decode(errors="replace")


# --- node + ASGI assembly --------------------------------------------------------


def build_client(config: ServeConfig) -> httpx.AsyncClient:
    """The shared outbound HTTP client (one pool for all LLM-route calls)."""
    return httpx.AsyncClient(timeout=config.timeout)


def build_node(config: ServeConfig, client: httpx.AsyncClient) -> Url4Node:
    """Assemble a :class:`Url4Node` with one endpoint per configured route."""
    node = Url4Node(
        "url4-serve",
        eval_path=config.eval_path,
        default_processor=config.processor,
        concurrency=config.concurrency,
    )
    node.data(_HEALTH_PATH, "ok")
    for path, model in config.routes.items():
        handler = make_llm_handler(client, config.backend_url, model, config.backend_token)
        node.endpoint(path)(handler)
    for path, argv in config.commands.items():
        node.endpoint(path)(make_command_handler(argv, config.timeout))
    return node


AsgiApp = Callable[[Mapping, Callable, Callable], Awaitable[None]]


def build_asgi_app(node: Url4Node, client: httpx.AsyncClient, config: ServeConfig) -> AsgiApp:
    """Wrap ``node.asgi()`` with admission control, timeout, and shutdown cleanup.

    The node owns dispatch and ``Url4Error`` -> HTTP mapping; this wrapper adds only
    what the node does not: 503 over max-inflight, 504 on per-request timeout, and
    closing the shared client + node on lifespan shutdown.
    """
    base = node.asgi()
    state = {"inflight": 0}

    async def app(scope: Mapping, receive: Callable, send: Callable) -> None:
        if scope["type"] == "lifespan":
            await _lifespan(receive, send, node, client)
        elif scope["type"] == "http":
            await _serve_http(base, scope, receive, send, state, config)
        else:  # pragma: no cover - no websocket surface in v1
            await base(scope, receive, send)

    return app


async def _serve_http(base, scope, receive, send, state, config: ServeConfig) -> None:
    if state["inflight"] >= config.max_inflight:
        # INVARIANT: check-then-increment is atomic on the single-threaded loop (no
        # await between), so two requests can never both pass a full gate.
        await _send_error(send, 503, "overloaded", "server at capacity, retry shortly", retry=True)
        return
    state["inflight"] += 1
    guard = _StartGuard(send)
    try:
        async with asyncio.timeout(config.timeout):
            await base(scope, receive, guard.send)
    except TimeoutError:
        if not guard.started:  # nothing sent yet — the node computes the body before sending
            await _send_error(send, 504, "timeout", f"evaluation exceeded {config.timeout}s")
    finally:
        state["inflight"] -= 1


class _StartGuard:
    """Tracks whether the response has started, so timeout can't double-send."""

    def __init__(self, send: Callable) -> None:
        self._send = send
        self.started = False

    async def send(self, message: Mapping) -> None:
        if message["type"] == "http.response.start":
            self.started = True
        await self._send(message)


async def _send_error(
    send: Callable, status: int, code: str, message: str, *, retry: bool = False
) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    headers = [(b"content-type", b"application/json")]
    if retry:
        headers.append((b"retry-after", b"1"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _lifespan(
    receive: Callable, send: Callable, node: Url4Node, client: httpx.AsyncClient
) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await client.aclose()  # graceful: release the shared pool + node's outbound
            await node.aclose()
            await send({"type": "lifespan.shutdown.complete"})
            return


__all__ = [
    "DEFAULT_ROUTES",
    "ConfigError",
    "EndpointHandler",
    "ServeConfig",
    "build_asgi_app",
    "build_client",
    "build_node",
    "make_command_handler",
    "make_llm_handler",
    "resolve",
]
