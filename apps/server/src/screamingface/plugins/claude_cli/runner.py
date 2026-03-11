"""Subprocess execution for the Claude CLI.

Uses asyncio.create_subprocess_exec (not shell) to safely invoke the claude binary.
Arguments are passed as a list, preventing shell injection.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from screamingface.plugins.claude_cli.models import ClaudeRunRequest
    from screamingface.plugins.claude_cli.plugin import ClaudeCliSettings


def build_args(
    request: ClaudeRunRequest,
    settings: ClaudeCliSettings,
    temp_dir: str | None = None,
) -> list[str]:
    """Build the CLI argument list. Prompt is piped via stdin, not as a positional arg."""
    args = ["claude", "-p"]

    # Model: request wins, then settings default
    model = request.model or settings.default_model
    if model:
        args.extend(["--model", model])

    if request.system_prompt:
        args.extend(["--system-prompt", request.system_prompt])

    if request.append_system_prompt:
        args.extend(["--append-system-prompt", request.append_system_prompt])

    # Output format
    fmt = request.output_format
    if fmt:
        args.extend(["--output-format", fmt])

    if request.json_schema:
        args.extend(["--json-schema", json.dumps(request.json_schema)])

    # Budget: request wins, then settings default
    budget = request.max_budget_usd or settings.max_budget_usd
    if budget is not None:
        args.extend(["--max-budget-usd", str(budget)])

    # Effort: request wins, then settings default
    effort = request.effort or settings.default_effort
    if effort:
        args.extend(["--effort", effort])

    if request.tools:
        for tool in request.tools:
            args.extend(["--tools", tool])

    if request.allowed_tools:
        for tool in request.allowed_tools:
            args.extend(["--allowed-tools", tool])

    if request.disallowed_tools:
        for tool in request.disallowed_tools:
            args.extend(["--disallowed-tools", tool])

    if request.mcp_config:
        args.extend(["--mcp-config", request.mcp_config])

    # Permission mode: request wins, then settings default
    perm = request.permission_mode or settings.permission_mode
    if perm:
        args.extend(["--permission-mode", perm])

    # Directories
    add_dirs = list(request.add_dirs or [])
    if temp_dir:
        add_dirs.append(temp_dir)
    for d in add_dirs:
        args.extend(["--add-dir", d])

    if request.fallback_model:
        args.extend(["--fallback-model", request.fallback_model])

    # Skip permissions: request OR settings
    if request.dangerously_skip_permissions or settings.dangerously_skip_permissions:
        args.append("--dangerously-skip-permissions")

    if request.no_session_persistence:
        args.append("--no-session-persistence")

    return args


async def run_claude(
    args: list[str],
    prompt: str,
    timeout: float,
) -> tuple[int, str, str, float]:
    """Run the Claude CLI and return (exit_code, stdout, stderr, duration_seconds)."""
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        proc.communicate(prompt.encode()),
        timeout=timeout,
    )
    duration = time.monotonic() - start
    return (
        proc.returncode or 0,
        stdout_bytes.decode(),
        stderr_bytes.decode(),
        duration,
    )


async def stream_claude(
    args: list[str],
    prompt: str,
    timeout: float,
) -> AsyncGenerator[str, None]:
    """Stream stdout lines from the Claude CLI, ending with a done event."""
    start = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None

    proc.stdin.write(prompt.encode())
    await proc.stdin.drain()
    proc.stdin.close()

    try:
        async with asyncio.timeout(timeout):
            async for line in proc.stdout:
                yield line.decode()
            stderr = (await proc.stderr.read()).decode()
            await proc.wait()
    except TimeoutError:
        proc.kill()
        await proc.wait()
        stderr = (await proc.stderr.read()).decode()
        yield json.dumps({"type": "error", "error": "timeout"}) + "\n"

    duration = time.monotonic() - start
    yield (
        json.dumps(
            {
                "type": "done",
                "exit_code": proc.returncode or 0,
                "stderr": stderr,
                "duration_seconds": round(duration, 3),
            }
        )
        + "\n"
    )
