"""Configuration, backend handlers, and node/app assembly for ``url4 serve``.

This is the transport-adapter layer behind the CLI (:mod:`url4.cli`). It builds a
:class:`~url4.server.Url4Node` from a :class:`ServeConfig` — registering one
intent-processor endpoint per configured ``[commands]`` route (a local
subprocess, doctrine N4; there is no other backend kind — a user's LLM backend
is their own gateway script mounted as a command) — and wraps the node's
framework-free ``asgi()`` with the run-level concerns the node does not own:
bounded in-flight admission (503), a per-request timeout (504), and graceful
node shutdown.

# INVARIANT: this module imports no web framework and no HTTP client. Serving is
# the existing ``Url4Node.asgi()`` (raw ASGI) run under uvicorn (the
# ``url4[server]`` extra); Starlette is never involved. The core import graph
# stays framework-free.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import tomllib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from url4.errors import ResolutionError
from url4.server import Request, Url4Node

_HEALTH_PATH = "/healthz"

EndpointHandler = Callable[[Request], Awaitable[str]]


class ConfigError(ValueError):
    """A serve configuration is invalid — raised before bind (fail-fast)."""


@dataclass(frozen=True, slots=True)
class ServeConfig:
    """Everything ``url4 serve`` needs, resolved from flags > env > toml > default.

    ``commands`` is the ONLY backend registry: url4.toml ``[commands]`` maps a
    route path to an operator-owned argv template. ``default_route`` names the
    command a fan-out reduce dispatches to; unset, the FIRST declared command
    is used (see :attr:`resolved_default_route`).
    """

    host: str = "127.0.0.1"
    port: int = 4404
    default_route: str | None = None
    eval_path: str = "/v1"
    concurrency: int = 32
    max_inflight: int = 16
    timeout: float = 120.0
    commands: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def validate(self) -> None:
        """Raise :class:`ConfigError` for any unusable setting, before bind."""
        _require(self.concurrency >= 1, f"concurrency must be >= 1, got {self.concurrency}")
        _require(self.max_inflight >= 1, f"max-inflight must be >= 1, got {self.max_inflight}")
        _require(self.timeout > 0, f"timeout must be > 0, got {self.timeout}")
        # INVARIANT: an empty host is never a loopback bind — it binds 0.0.0.0 AND ::
        # (every interface) while reading as "unset", and it would slip past the
        # non-loopback exposure warnings that are v1's only control in front of the
        # command routes (arbitrary local execution). `_pick` normalizes an empty
        # URL4_HOST away; this covers the explicit `--host ""` flag, which it cannot.
        _require(
            bool(self.host),
            "host cannot be empty — bind 127.0.0.1, or 0.0.0.0 for every interface",
        )
        # The eval path is a route like any other: it must be a path.
        _require_paths({self.eval_path: None}, "eval")
        # WHY: the connector is gone — the operator owns every backend, so a
        # node with zero commands has nothing to dispatch to. Fail fast.
        _require(
            bool(self.commands),
            "url4 serve requires at least one [commands] route in url4.toml — "
            "define your backends as commands (e.g. your own gateway script)",
        )
        _require_paths(self.commands, "command")
        _require_argv(self.commands)
        reserved = {self.eval_path, _HEALTH_PATH} & set(self.commands)
        _require(not reserved, f"command paths clash with reserved {sorted(reserved)}")
        # The node registers /healthz as a data route; an eval path equal to it
        # would collide at build time (an uncaught ValueError) — reject it here so
        # the misconfiguration fails fast with a clean config error before bind.
        _require(
            self.eval_path != _HEALTH_PATH,
            f"eval path cannot be the reserved health path {_HEALTH_PATH!r}",
        )
        # INVARIANT: a fan-out reduce dispatches to the default route at
        # runtime, so an EXPLICIT one must be a declared command or the reduce
        # fails mid-evaluation.
        if self.default_route is not None:
            _require(
                self.default_route in self.commands,
                f"default route {self.default_route!r} is not a declared command "
                f"route: {sorted(self.commands)}",
            )

    @property
    def resolved_default_route(self) -> str:
        """The reduce route: the explicit ``default_route``, else the first command.

        # INVARIANT: only meaningful after :meth:`validate` — commands is
        # non-empty and an explicit default_route is declared.
        """
        if self.default_route is not None:
            return self.default_route
        return next(iter(self.commands))


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

    ``overrides`` holds CLI flag values (``None`` == unset). Commands come from
    url4.toml ``[commands]`` only — argv templates are operator config, not
    something to squeeze through a flag.
    """
    toml = _read_toml(toml_path)
    raw_route = _pick("default_route", overrides, env, toml)
    return ServeConfig(
        host=_pick_str("host", overrides, env, toml, "127.0.0.1"),
        port=_pick_int("port", overrides, env, toml, 4404),
        default_route=None if raw_route is None else str(raw_route),
        eval_path=_pick_str("eval_path", overrides, env, toml, "/v1"),
        concurrency=_pick_int("concurrency", overrides, env, toml, 32),
        max_inflight=_pick_int("max_inflight", overrides, env, toml, 16),
        timeout=_pick_float("timeout", overrides, env, toml, 120.0),
        commands=_toml_command_map(toml.get("commands")),
    )


def _pick(
    name: str, overrides: Mapping[str, object], env: Mapping[str, str], toml: Mapping
) -> object:
    flag = overrides.get(name)
    if flag is not None:
        return flag
    # WHY: an empty env var is an UNSET var, not an empty value — `URL4_HOST=` in a
    # .env/compose file is an unresolved interpolation. Taking it literally let every
    # string field silently adopt "", and host="" binds 0.0.0.0 AND :: (every
    # interface) while reading as "default". Int fields already rejected "" loudly;
    # this makes strings consistent with them by falling through to toml > default.
    from_env = env.get(f"URL4_{name.upper()}")
    if from_env:
        return from_env
    return toml.get(name)


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


def _read_toml(path: Path | None) -> Mapping[str, object]:
    if path is None:
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read config {str(path)!r}: {exc}") from exc


def _toml_command_map(value: object) -> dict[str, tuple[str, ...]]:
    return {str(k): _as_argv(v) for k, v in value.items()} if isinstance(value, Mapping) else {}


def _as_argv(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(shlex.split(value))
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value)
    raise ConfigError(f"command must be a string or list, got {value!r}")


# --- backend handlers ------------------------------------------------------------


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


def build_node(config: ServeConfig) -> Url4Node:
    """Assemble a :class:`Url4Node` with one endpoint per configured command."""
    node = Url4Node(
        "url4-serve",
        eval_path=config.eval_path,
        default_processor=config.resolved_default_route,
        concurrency=config.concurrency,
    )
    node.data(_HEALTH_PATH, "ok")
    for path, argv in config.commands.items():
        node.endpoint(path)(make_command_handler(argv, config.timeout))
    return node


AsgiApp = Callable[[Mapping, Callable, Callable], Awaitable[None]]


def build_asgi_app(node: Url4Node, config: ServeConfig) -> AsgiApp:
    """Wrap ``node.asgi()`` with admission control, timeout, and shutdown cleanup.

    The node owns dispatch and ``Url4Error`` -> HTTP mapping; this wrapper adds only
    what the node does not: 503 over max-inflight, 504 on per-request timeout, and
    closing the node on lifespan shutdown.
    """
    base = node.asgi()
    state = {"inflight": 0}

    async def app(scope: Mapping, receive: Callable, send: Callable) -> None:
        if scope["type"] == "lifespan":
            await _lifespan(receive, send, node)
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


async def _lifespan(receive: Callable, send: Callable, node: Url4Node) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await node.aclose()  # graceful: release the node's owned outbound adapter
            await send({"type": "lifespan.shutdown.complete"})
            return


__all__ = [
    "ConfigError",
    "EndpointHandler",
    "ServeConfig",
    "build_asgi_app",
    "build_node",
    "make_command_handler",
    "resolve",
]
