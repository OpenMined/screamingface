"""Fail if any source file imports LiteLLM enterprise code.

LiteLLM is dual-licensed: the core `litellm/` package is MIT, but
`litellm.enterprise.*` and the separate `litellm_enterprise` package are
governed by the BerriAI Enterprise License (paid). This guard keeps us
firmly inside the MIT half.

Run via `python scripts/check_no_enterprise.py` (also wired into
`uv run pytest` via `tests/test_no_enterprise.py`).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"\b(?:from|import)\s+litellm\.enterprise|\blitellm_enterprise\b")


def main() -> int:
    offenders: list[tuple[Path, int, str]] = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".venv", "__pycache__", "scripts"} for part in path.parts):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if PATTERN.search(line):
                offenders.append((path.relative_to(ROOT), lineno, line.strip()))
    if offenders:
        print("LiteLLM Enterprise imports detected (forbidden):", file=sys.stderr)
        for path, lineno, line in offenders:
            print(f"  {path}:{lineno}: {line}", file=sys.stderr)
        return 1
    print("OK: no LiteLLM Enterprise imports found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
