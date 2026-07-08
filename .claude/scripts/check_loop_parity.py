#!/usr/bin/env python3
"""LOOP PARITY gate.

The `SHARED-LOOP`-marked regions of the sdlc-* skills must be verbatim-identical.
Exit 0 on parity, 1 on drift (with a unified diff), 2 on structural errors
(missing file/markers or unbalanced marker pairs).
"""
import difflib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent  # .claude/
SKILLS = ["sdlc-python", "sdlc-electron"]
MARKER = re.compile(r"<!-- SHARED-LOOP:BEGIN -->\n(.*?)<!-- SHARED-LOOP:END -->", re.S)


def shared_regions(name: str) -> str:
    path = ROOT / "skills" / name / "SKILL.md"
    if not path.exists():
        print(f"ERROR: {path} missing")
        sys.exit(2)
    text = path.read_text()
    if text.count("SHARED-LOOP:BEGIN") != text.count("SHARED-LOOP:END"):
        print(f"ERROR: unbalanced SHARED-LOOP markers in {name}")
        sys.exit(2)
    regions = MARKER.findall(text)
    if not regions:
        print(f"ERROR: no SHARED-LOOP regions in {name}")
        sys.exit(2)
    return "\n<<<REGION>>>\n".join(regions)


def main() -> int:
    baseline_name, *rest = SKILLS
    baseline = shared_regions(baseline_name)
    drift = False
    for name in rest:
        other = shared_regions(name)
        if other != baseline:
            drift = True
            print(f"DRIFT: {name} shared regions differ from {baseline_name}:")
            sys.stdout.writelines(
                difflib.unified_diff(
                    baseline.splitlines(keepends=True),
                    other.splitlines(keepends=True),
                    fromfile=baseline_name,
                    tofile=name,
                )
            )
    if drift:
        return 1
    print(f"LOOP PARITY OK: {', '.join(SKILLS)} share identical SHARED-LOOP regions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
