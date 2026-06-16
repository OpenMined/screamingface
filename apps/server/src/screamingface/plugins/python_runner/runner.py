"""Subprocess runner for Python source.

Pure async function: source-in, JSON-payload-on-stdin, parsed-JSON-stdout-out.
No path arguments — the caller is responsible for producing the source from
wherever it lives (config-stored at /data/code/, vendored, remote URL).
Sandboxing wraps this transparently in DEMO-012; /python wires it up in
DEMO-013.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from screamingface.plugins.python_runner.sandbox import build_subprocess_argv

__all__ = ["PythonRunnerError", "run_script_main", "run_script_source"]

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


def _script_defines_main(source: str) -> bool:
    """True if the source defines a top-level ``def main`` (call-main mode)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name == "main"
        for n in tree.body
    )


# Harness that imports a user script as a module (skipping __main__),
# introspects main()'s signature, and calls it with only its declared params.
# Uses importlib.util so the __main__ guard in user scripts is never triggered.
_MAIN_HARNESS = (
    "import json, sys, inspect, importlib.util\n"
    "_spec = importlib.util.spec_from_file_location('_url4_user', sys.argv[1])\n"
    "_mod = importlib.util.module_from_spec(_spec)\n"
    "_spec.loader.exec_module(_mod)\n"
    "_payload = json.loads(sys.stdin.read() or 'null')\n"
    "_params = list(inspect.signature(_mod.main).parameters)\n"
    "if isinstance(_payload, dict):\n"
    "    _result = _mod.main(**{k: v for k, v in _payload.items() if k in _params})\n"
    "elif isinstance(_payload, list) and len(_params) == 1:\n"
    "    _result = _mod.main(_payload)\n"
    "else:\n"
    "    _result = _mod.main(_payload)\n"
    "sys.stdout.write(json.dumps(_result))\n"
)


def _run_blocking(
    argv: list[str],
    stdin_bytes: bytes,
    timeout: float,
) -> tuple[int, bytes, bytes]:
    """Run the subprocess synchronously; return (returncode, stdout, stderr).

    Uses ``subprocess.run`` rather than ``asyncio.create_subprocess_exec`` on
    purpose (SF-287): the asyncio Unix subprocess path calls
    ``events.get_child_watcher()``, which raises a bare ``NotImplementedError``
    whenever a uvloop event-loop policy is installed process-wide (the
    per-session frontend uvicorn does this via ``loop="auto"``) while we run on
    the main server's standard ``loop="asyncio"`` loop. ``subprocess.run`` never
    touches the child watcher, so it is immune to that policy/loop mismatch —
    and forward-compatible with Python 3.14, which removes child watchers
    entirely. Meant to be called via :func:`asyncio.to_thread`.

    Raises PythonRunnerError(kind="timeout") on timeout (the child is killed by
    ``subprocess.run``) and PythonRunnerError(kind="io_error") on OSError.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — argv is built by the sandbox
            argv,
            input=stdin_bytes,
            capture_output=True,
            timeout=timeout,
            env={"PATH": "/usr/bin", "HOME": "/tmp"},
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise PythonRunnerError(
            kind="timeout",
            message=f"Script exceeded {timeout}s timeout",
        ) from e
    except OSError as e:
        raise PythonRunnerError(kind="io_error", message=str(e)) from e

    return completed.returncode, completed.stdout, completed.stderr


async def _spawn_collect(
    argv: list[str],
    stdin_bytes: bytes,
    timeout: float,
) -> tuple[int, bytes, bytes]:
    """Spawn a subprocess off the event loop, returning (returncode, stdout, stderr).

    Delegates to :func:`_run_blocking` in a worker thread so the event loop
    stays responsive while the script runs, without depending on the asyncio
    child watcher (SF-287).
    """
    return await asyncio.to_thread(_run_blocking, argv, stdin_bytes, timeout)


def _parse_output(
    stdout_b: bytes,
    stderr_b: bytes,
    exit_code: int,
) -> dict[str, Any]:
    """Decode subprocess output and return parsed JSON.

    Raises PythonRunnerError on nonzero exit or invalid JSON.
    """
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")

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


async def run_script_source(
    source: str,
    payload: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Run Python source in a subprocess; return parsed JSON output."""
    script_path = _cache_script(source)
    payload_bytes = json.dumps(payload).encode("utf-8")
    argv = build_subprocess_argv(script_path)
    exit_code, stdout_b, stderr_b = await _spawn_collect(argv, payload_bytes, timeout)
    return _parse_output(stdout_b, stderr_b, exit_code)


async def run_script_main(
    source: str,
    payload: Any,
    timeout: float = 30.0,
) -> Any:
    """Import user script as a module and call its ``main()`` with introspected kwargs.

    The script's ``if __name__ == "__main__":`` block is never executed.
    Only the parameters declared by ``main()`` are extracted from *payload*;
    extra keys in a dict payload are silently dropped.
    """
    harness_path = _cache_script(_MAIN_HARNESS)
    user_path = _cache_script(source)
    payload_bytes = json.dumps(payload).encode("utf-8")
    # harness is the launched script; user script path is passed as argv[1]
    argv = build_subprocess_argv(harness_path, extra_args=[user_path])
    exit_code, stdout_b, stderr_b = await _spawn_collect(argv, payload_bytes, timeout)
    return _parse_output(stdout_b, stderr_b, exit_code)
