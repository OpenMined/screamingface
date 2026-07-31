"""Operator-declared subprocess routes for the URL4 Runner world.

The contract intentionally matches ``url4 serve``: each ``[commands]`` entry is an argv
template, never a shell command. The URL4 request context is also piped to stdin, while
``{context}``, ``{intent}``, ``{params}``, and ``{param:<name>}`` may be substituted into
individual argv entries.

This adapter lives in the Runner because the commands execute inside the Runner Job. The
control plane only schedules the expression and never imports or invokes these handlers.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence

from url4.core.errors import ResolutionError
from url4.io.static import StaticIOLayer
from url4.peer.server import Request, Url4Node
from url4_cloud.runner.config import CommandSpec

_SUBSTITUTION = re.compile(r"\{(intent|context|params|param:([A-Za-z0-9_.\-]+))\}")


def build_command_world(commands: Sequence[CommandSpec], *, timeout_s: float) -> Url4Node:
    """Build a command-only, outbound-denying URL4 world."""
    node = Url4Node("commands", outbound=StaticIOLayer())
    install_command_routes(node, commands, timeout_s=timeout_s)
    return node


def install_command_routes(
    node: Url4Node, commands: Sequence[CommandSpec], *, timeout_s: float
) -> None:
    """Install command routes on an existing node without changing its default route."""
    if timeout_s <= 0:
        raise ValueError(f"command timeout must be positive, got {timeout_s}")
    for command in commands:
        node.endpoint(command.path)(make_command_handler(command.argv, timeout_s=timeout_s))


def make_command_handler(
    argv: Sequence[str], *, timeout_s: float
) -> Callable[[Request], Awaitable[str]]:
    """Return a URL4 endpoint that executes one shell-free argv template."""
    template = tuple(argv)

    async def handler(request: Request) -> str:
        command = _substitute(template, request)
        return await _run(command, stdin=request.context, timeout_s=timeout_s)

    return handler


def _substitute(template: Sequence[str], request: Request) -> list[str]:
    params_json: str | None = None

    def replacement(match: re.Match[str]) -> str:
        nonlocal params_json
        token = match.group(1)
        if token == "params":
            if params_json is None:
                params_json = json.dumps(dict(sorted(request.params.items())))
            return params_json
        if token.startswith("param:"):
            return request.params.get(match.group(2), "")
        return request.intent if token == "intent" else request.context

    return [_SUBSTITUTION.sub(replacement, arg) for arg in template]


async def _run(command: list[str], *, stdin: str, timeout_s: float) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise ResolutionError(f"command {command[0]!r} failed to start: {exc}") from exc
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(stdin.encode()), timeout=timeout_s
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise ResolutionError(f"command {command[0]!r} timed out after {timeout_s}s") from None
    if process.returncode != 0:
        detail = stderr.decode(errors="replace")[:500].strip()
        raise ResolutionError(f"command {command[0]!r} exited {process.returncode}: {detail}")
    return stdout.decode(errors="replace")


__all__ = ["build_command_world", "install_command_routes", "make_command_handler"]
