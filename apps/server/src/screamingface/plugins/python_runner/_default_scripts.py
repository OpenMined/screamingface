"""Load vendored Python scripts as defaults for the ``scripts`` setting.

Reads committed ``.py`` files at import time so they're embedded as default
values for ``PythonRunnerSettings.scripts``. The vendor directory is populated
by DEMO-016; until then this returns an empty dict, which is a valid initial
state.
"""

from __future__ import annotations

from pathlib import Path

VENDOR_ROOT = Path(__file__).resolve().parent / "_vendored"


def load_vendored_defaults() -> dict[str, str]:
    """Return ``{stem: source}`` for every ``.py`` under ``_vendored/``.

    Empty dict when the directory is absent or empty.
    """
    if not VENDOR_ROOT.is_dir():
        return {}
    return {path.stem: path.read_text(encoding="utf-8") for path in VENDOR_ROOT.glob("*.py")}
