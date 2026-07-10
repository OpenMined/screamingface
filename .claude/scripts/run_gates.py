#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""Deterministic quality-gate runner for the sdlc plugin.

Reads the project's stack card (.claude/sdlc.local.md), runs the named stack's
gates in order (cwd = stack root), preceded by the append-only test check.
Stops at the first red gate and prints its output verbatim — the caller needs
the raw failing signal, not a summary.

Usage:
    uv run run_gates.py <stack-name> [--card PATH] [--base REF] [--skip-append-only]

Exit codes: 0 all green · 1 a gate or the append-only check failed · 2 config error.
"""
import argparse
import fnmatch
import pathlib
import subprocess
import sys
from typing import NoReturn

try:
    import yaml
except ImportError:  # bare python3 without PyYAML
    print(
        "ERROR: PyYAML is required. Run via `uv run run_gates.py …` (PEP 723 resolves it) "
        "or install it: pip install pyyaml"
    )
    sys.exit(2)

GREEN, RED = "✓", "✗"


def fail_config(msg: str) -> NoReturn:
    print(f"CONFIG ERROR: {msg}")
    print("If the card is missing: copy templates/sdlc.local.md from the sdlc plugin "
          "into .claude/, fill it, and re-run.")
    sys.exit(2)


def load_card(path: pathlib.Path) -> dict:
    if not path.exists():
        fail_config(f"stack card not found: {path}")
    lines = path.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        fail_config(f"{path} has no YAML frontmatter (must start with ---)")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        fail_config(f"{path} frontmatter is not closed with ---")
    try:
        data = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        fail_config(f"{path} frontmatter is not valid YAML: {exc}")
    if not isinstance(data.get("stacks"), list):
        fail_config(f"{path} frontmatter must define a `stacks:` list")
    return data


def append_only_check(root: pathlib.Path, base: str, globs: list[str]) -> bool:
    """True when no previously committed test file was modified/deleted/renamed."""
    proc = subprocess.run(
        ["git", "diff", "--relative", "--name-status", base],
        cwd=root, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        fail_config(f"git diff failed in {root}: {proc.stderr.strip()}")
    offenders = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        status, paths = parts[0], parts[1:]
        if status[:1] not in "MDR":  # A(dded)/C(opied) etc. are fine — adding tests is always fine
            continue
        for p in paths:
            if any(fnmatch.fnmatch(p, g) for g in globs):
                offenders.append(f"  {status}\t{p}")
                break
    if offenders:
        print(f"{RED} append-only test check — prior tests were modified/deleted (vs {base}):")
        print("\n".join(offenders))
        print("Tests are append-only across cycles (sdlc rule 5). Changing a prior test is a "
              "Confidence-Gate decision — STOP and ask.")
        return False
    print(f"{GREEN} append-only test check (vs {base})")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stack", help="stack name from the card's stacks[].name")
    ap.add_argument("--card", default=".claude/sdlc.local.md", type=pathlib.Path)
    ap.add_argument("--base", default="HEAD", help="git ref for the append-only check")
    ap.add_argument("--skip-append-only", action="store_true")
    args = ap.parse_args()

    card = load_card(args.card)
    stack = next((s for s in card["stacks"] if s.get("name") == args.stack), None)
    if stack is None:
        names = ", ".join(s.get("name", "?") for s in card["stacks"])
        fail_config(f"stack '{args.stack}' not in {args.card} (has: {names})")

    root = pathlib.Path(stack.get("root", ".")).resolve()
    if not root.is_dir():
        fail_config(f"stack root does not exist: {root}")
    gates = stack.get("gates") or []
    if not gates:
        fail_config(f"stack '{args.stack}' defines no gates")

    ok = True
    if args.skip_append_only:
        print("- append-only test check skipped (--skip-append-only)")
    else:
        ok = append_only_check(root, args.base, stack.get("test_globs") or [])

    if ok:
        for gate in gates:
            proc = subprocess.run(gate, shell=True, cwd=root, capture_output=True, text=True)
            if proc.returncode == 0:
                print(f"{GREEN} {gate}")
            else:
                ok = False
                print(f"{RED} {gate}  (exit {proc.returncode})")
                # verbatim failing signal — the fix loop needs it raw
                if proc.stdout:
                    print(proc.stdout, end="")
                if proc.stderr:
                    print(proc.stderr, end="", file=sys.stderr)
                break  # fix-and-rerun works one failing signal at a time

    print("ALL GATES GREEN" if ok else "GATE FAILED — fix the code, never the gate")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
