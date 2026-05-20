"""sandbox-exec wrapper for python_runner subprocesses (SF-158 / DEMO-012).

Public surface:
    SANDBOX_PROFILE_PATH — pathlib.Path to macos.sb
    sandbox_is_enabled() -> bool
    build_subprocess_argv(script_path) -> list[str]
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

__all__ = ["SANDBOX_PROFILE_PATH", "build_subprocess_argv", "sandbox_is_enabled"]

logger = logging.getLogger(__name__)

SANDBOX_PROFILE_PATH = Path(__file__).parent / "macos.sb"

# Warn at most once per process so a linux dev box doesn't spam logs.
_warned_unsupported = False


def sandbox_is_enabled() -> bool:
    if sys.platform != "darwin":
        return False
    return os.environ.get("SF_PYTHON_RUNNER__SANDBOX", "").lower() != "off"


def build_subprocess_argv(script_path: Path) -> list[str]:
    """Argv to launch `script_path` under the python interpreter.

    On darwin with sandbox on: wraps with sandbox-exec + macos.sb.
    Anywhere else (or with SF_PYTHON_RUNNER__SANDBOX=off): plain argv,
    logging a one-shot warning on non-darwin platforms.
    """
    if sandbox_is_enabled():
        spec_root = str(script_path.parent.resolve())
        # PY_PREFIX is the *real* cpython install (resolves symlinks); when
        # running inside a uv/virtualenv this points at the underlying
        # interpreter tree the stdlib lives in.
        py_prefix = str(Path(sys.executable).resolve().parent.parent)
        # VENV_PREFIX is the *unresolved* sys.prefix — the venv itself, which
        # owns pyvenv.cfg and the bin/ symlinks Python touches on startup.
        venv_prefix = str(Path(sys.executable).parent.parent)
        return [
            "sandbox-exec",
            "-D",
            f"SPEC_ROOT={spec_root}",
            "-D",
            f"PY_PREFIX={py_prefix}",
            "-D",
            f"VENV_PREFIX={venv_prefix}",
            "-f",
            str(SANDBOX_PROFILE_PATH),
            sys.executable,
            str(script_path),
        ]

    global _warned_unsupported
    if sys.platform != "darwin" and not _warned_unsupported:
        logger.warning(
            "python_runner running unsandboxed: %s has no sandbox-exec equivalent",
            sys.platform,
        )
        _warned_unsupported = True
    return [sys.executable, str(script_path)]
