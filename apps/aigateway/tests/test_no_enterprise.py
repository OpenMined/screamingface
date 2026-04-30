"""CI guard: ensure no source file imports LiteLLM Enterprise code.

The check script is the source of truth; this test just shells into it
so the rule runs as part of `pytest` (and therefore CI).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_no_enterprise_imports() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_no_enterprise.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
