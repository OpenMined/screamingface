"""Subprocess runner for Python source.

Pure async function: source-in, JSON-payload-on-stdin, parsed-JSON-stdout-out.
No path arguments — the caller is responsible for producing the source from
wherever it lives (config-stored at /data/code/, vendored, remote URL).
Sandboxing wraps this transparently in DEMO-012; /python wires it up in
DEMO-013.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from screamingface.plugins.python_runner.sandbox import build_subprocess_argv

__all__ = ["PythonRunnerError", "run_script_source"]

ErrorKind = Literal["nonzero_exit", "invalid_output", "timeout", "io_error"]

logger = logging.getLogger(__name__)


@dataclass
class PythonRunnerError(Exception):
    kind: ErrorKind
    message: str
    stderr: str = ""
    stdout: str = ""
    exit_code: int | None = None

    def __str__(self) -> str:
        return f"PythonRunnerError({self.kind}): {self.message}"


_DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "screamingface" / "python-scripts"


def _cache_root() -> Path:
    return Path(os.environ.get("SF_PYTHON_RUNNER__CACHE_ROOT", _DEFAULT_CACHE_ROOT))


def _cache_script(source: str) -> Path:
    root = _cache_root()
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:32]
    target = root / f"{digest}.py"
    if target.exists():
        return target
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    with tempfile.NamedTemporaryFile("w", dir=root, suffix=".py.tmp", delete=False) as tmp:
        tmp.write(source)
        tmp_path = tmp.name
    os.chmod(tmp_path, 0o600)
    os.rename(tmp_path, target)
    return target


async def run_script_source(
    source: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Run Python source in a subprocess; return parsed JSON output."""
    script_path = _cache_script(source)
    payload_bytes = json.dumps(payload).encode("utf-8")

    argv = build_subprocess_argv(script_path)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PATH": "/usr/bin", "HOME": "/tmp"},
        )
    except OSError as e:
        raise PythonRunnerError(kind="io_error", message=str(e)) from e

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=payload_bytes),
            timeout=timeout,
        )
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise PythonRunnerError(
            kind="timeout",
            message=f"Script exceeded {timeout}s timeout",
        ) from e

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    exit_code = proc.returncode

    if exit_code != 0:
        raise PythonRunnerError(
            kind="nonzero_exit",
            message=f"Script exited with code {exit_code}",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        )

    if stderr:
        logger.debug("python_runner stderr (non-empty on success): %s", stderr)

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        raise PythonRunnerError(
            kind="invalid_output",
            message=f"Stdout is not valid JSON: {e}",
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        ) from e
