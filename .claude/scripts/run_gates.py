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
import ast
import fnmatch
import pathlib
import re
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
    print(
        "If the card is missing: copy templates/sdlc.local.md from the sdlc plugin "
        "into .claude/, fill it, and re-run."
    )
    sys.exit(2)


def load_card(path: pathlib.Path) -> dict:
    if not path.exists():
        fail_config(f"stack card not found: {path}")
    lines = path.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        fail_config(f"{path} has no YAML frontmatter (must start with ---)")
    try:
        end = next(
            i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        fail_config(f"{path} frontmatter is not closed with ---")
    try:
        data = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as exc:
        fail_config(f"{path} frontmatter is not valid YAML: {exc}")
    if not isinstance(data.get("stacks"), list):
        fail_config(f"{path} frontmatter must define a `stacks:` list")
    return data


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


# WHY: an ALLOWLIST of data-holding node types, not a denylist of "everything
# except X". A denylist means every statement type nobody thought to exclude
# (a docstring, an `if __name__ == "__main__":` block, an import nested inside
# a version-guard) silently becomes a false positive the next time someone
# edits one. Assign/AnnAssign/AugAssign hold the kind of shared test data (e.g.
# a `_BASE_KW = {...}` dict, or a `_CASES += [...]` accumulator) rule 5 needs
# to protect.
_MODULE_LEVEL_DATA = (ast.Assign, ast.AnnAssign, ast.AugAssign)


def _old_protected_ranges(root: pathlib.Path, base: str, path: str) -> list[tuple[int, int]]:
    """Line ranges (1-indexed, inclusive) of every protected node in `path` at `base`:
    every function body, plus every direct module-level Assign/AnnAssign/AugAssign
    statement.
    """
    # AIDEV-NOTE: `path` is cwd-relative (it comes from `git diff --relative`), but
    # `git show rev:path` resolves a bare path relative to the REPO ROOT, not cwd —
    # the `./` prefix is what makes it cwd-relative. Without it, this silently
    # returns `[]` (falls into the "didn't exist" branch) for every stack whose
    # root isn't the repo root, i.e. every real stack in `.claude/sdlc.local.md`.
    proc = subprocess.run(
        ["git", "show", f"{base}:./{path}"], cwd=root, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return []  # file didn't exist at base — nothing to protect
    try:
        tree = ast.parse(proc.stdout)
    except SyntaxError:
        return []  # can't parse — fall through to the safe (permissive) side
    ranges = []
    # INVARIANT: covers EVERY function, not just `test_*`-named ones — a
    # `conftest.py` fixture or a plain helper a test depends on is just as
    # protected as the test itself.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # INVARIANT: a decorator (e.g. @pytest.mark.parametrize(...), @pytest.fixture)
            # is part of the protected body — node.lineno points at `def`, not the
            # decorator line(s) above it.
            start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
            ranges.append((start, getattr(node, "end_lineno", node.lineno)))
    # INVARIANT: module-level test data is just as protected as a fixture — a
    # `-` line there is invisible to the function-only pass above.
    for node in tree.body:  # direct top-level children only — see AIDEV-NOTE below
        if isinstance(node, _MODULE_LEVEL_DATA):
            ranges.append((node.lineno, getattr(node, "end_lineno", node.lineno)))
    # AIDEV-NOTE: known, deliberate gaps — tracked as follow-ups, not chased here:
    # (1) class-level attributes (e.g. a shared constant on a unittest.TestCase
    #     subclass) aren't covered — would need the same per-statement treatment
    #     inside class bodies, not a whole-class-span shortcut (that would
    #     reopen "insert a new method between two existing ones" as a false
    #     positive, the same way OME-369's original bug worked).
    # (2) an Assign/AnnAssign/AugAssign nested inside a module-level If/Try/With
    #     (e.g. a version-guarded conditional constant) isn't covered either,
    #     since this loop only walks direct `tree.body` children, not recursively.
    # (3) a bare module-level walrus statement (`(_TOTAL := 10)`, parsed as an
    #     ast.Expr wrapping an ast.NamedExpr) isn't covered — an exotic enough
    #     pattern in real test code that it isn't worth a special-case check.
    return ranges


def _diff_positions(root: pathlib.Path, base: str, path: str) -> tuple[set[int], set[int]]:
    """Old-file positions the diff for `path` vs `base` touches, in two forms:

    - `removed`: an old line number itself changed/removed (a `-` line) — checked
      against a protected range INCLUSIVE on both ends (`lo <= ln <= hi`).
    - `inserted_after`: an old line number that NEW content was inserted directly
      after, with no old line consumed for it — checked EXCLUSIVE at the upper end
      (`lo <= n < hi`).
    """
    # AIDEV-NOTE: the exclusive bound on `inserted_after` is load-bearing. A pure
    # insertion (e.g. a whole new test function typed directly after an existing
    # one, zero blank lines between them) anchors at `n == hi` of the PRECEDING
    # function — that must stay unflagged, or this reopens the exact false-positive
    # OME-369 exists to fix (pure additions rejected as violations). Inserting as a
    # new first/middle statement anchors at `lo <= n < hi` and must be caught: a
    # pure `+`-only diff can still silently neuter a prior test's assertions (e.g.
    # forcing a variable's value right before the check) with zero `-` lines, which
    # `removed` alone can never see.
    #
    # AIDEV-NOTE: file-level header lines (`diff --git`, `index`, `--- a/...`,
    # `+++ b/...`) only ever appear BEFORE the first `@@` hunk line — track that
    # boundary structurally (`in_hunk`) instead of prefix-matching `---`/`+++`
    # against line content. A *removed* line whose actual content starts with `--`
    # at column 0 (e.g. a bare `---` separator) renders as `----` in the diff,
    # which would false-match a content-based header check and silently vanish
    # from `removed` while desyncing `old_line` for every later line in the hunk.
    proc = subprocess.run(
        ["git", "diff", "--relative", "--unified=0", base, "--", path],
        cwd=root, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        fail_config(f"git diff failed in {root}: {proc.stderr.strip()}")
    removed: set[int] = set()
    inserted_after: set[int] = set()
    old_line = 0
    in_hunk = False
    pure_insert_hunk = False
    for line in proc.stdout.splitlines():
        if line.startswith("@@"):
            m = _HUNK_HEADER.match(line)
            if m:
                old_line = int(m.group(1))
                old_count = int(m.group(2)) if m.group(2) is not None else 1
                # WHY: a hunk whose header declares old-count 0 is UNAMBIGUOUSLY a
                # pure insertion straight from the header. Inferring "pure insert"
                # by pairing "-"/"+" lines line-by-line instead would mis-anchor a
                # replace pair (a "-" immediately followed by a "+") one line later
                # than the line it actually replaces — which can land exactly on
                # the start of the NEXT protected range and false-positive an edit
                # that never touched it (e.g. replacing the blank separator line
                # between two functions falsely flags the second function).
                pure_insert_hunk = old_count == 0
            in_hunk = True
        elif not in_hunk:
            continue  # pre-hunk file header (diff --git / index / --- a/ / +++ b/)
        elif line.startswith("\\"):
            continue  # "\ No newline at end of file" — never consumes a line number
        elif line.startswith("-"):
            removed.add(old_line)
            old_line += 1
        elif line.startswith("+"):
            if pure_insert_hunk:
                inserted_after.add(old_line)  # anchored right after the current old_line
            # else: part of a replace pair with a preceding "-" in THIS hunk —
            # already captured via `removed`; anchoring it too would double-count
            # and can mis-fire per the WHY note above.
        else:
            old_line += 1  # context line (present only if a non-zero unified context is used)
    return removed, inserted_after


def append_only_check(root: pathlib.Path, base: str, globs: list[str]) -> bool:
    """True when no previously committed test/fixture/data was modified/deleted
    (rule 5).

    Pure additions (new test functions, new fixtures/helpers, new module-level
    data, new imports for them, even a whole new function typed directly next to
    an existing one) are always fine — a violation is either a removed/changed
    line, OR new content inserted, that falls INSIDE a protected range (a
    function body — test, fixture, or helper — or a module-level Assign/AnnAssign
    statement) that already existed at `base`. Deleting or renaming a whole test
    file is always a violation regardless of content.
    """
    proc = subprocess.run(
        ["git", "diff", "--relative", "--name-status", base],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        fail_config(f"git diff failed in {root}: {proc.stderr.strip()}")
    offenders = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        status, paths = parts[0], parts[1:]
        if (
            status[:1] not in "MDR"
        ):  # A(dded)/C(opied) etc. are fine — adding tests is always fine
            continue
        matched = [p for p in paths if any(fnmatch.fnmatch(p, g) for g in globs)]
        if not matched:
            continue
        p = matched[-1]  # for R(ename), name-status gives "old\tnew" — the new path is what's on disk
        if status[:1] != "M":
            offenders.append(f"  {status}\t{p}")
            continue
        ranges = _old_protected_ranges(root, base, p)
        removed, inserted_after = _diff_positions(root, base, p)
        bad_removed = sorted(ln for ln in removed if any(lo <= ln <= hi for lo, hi in ranges))
        bad_inserted = sorted(n for n in inserted_after if any(lo <= n < hi for lo, hi in ranges))
        if bad_removed or bad_inserted:
            detail = []
            if bad_removed:
                detail.append(f"removed/changed old line(s) {bad_removed}")
            if bad_inserted:
                detail.append(f"new content inserted after old line(s) {bad_inserted}")
            offenders.append(f"  M\t{p}  ({'; '.join(detail)} — inside an existing test/fixture)")
    if offenders:
        print(
            f"{RED} append-only test check — prior tests were modified/deleted (vs {base}):"
        )
        print("\n".join(offenders))
        print(
            "Tests are append-only across cycles (sdlc rule 5). Changing a prior test is a "
            "Confidence-Gate decision — STOP and ask."
        )
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
            proc = subprocess.run(
                gate, shell=True, cwd=root, capture_output=True, text=True
            )
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
