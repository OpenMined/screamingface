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
import difflib
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


# WHY: an ALLOWLIST of data-holding node types, not a denylist of "everything
# except X". A denylist means every statement type nobody thought to exclude
# (a docstring, an `if __name__ == "__main__":` block, an import nested inside
# a version-guard) silently becomes a false positive the next time someone
# edits one. Assign/AnnAssign/AugAssign hold the kind of shared test data (e.g.
# a `_BASE_KW = {...}` dict, or a `_CASES += [...]` accumulator) rule 5 needs
# to protect.
_MODULE_LEVEL_DATA = (ast.Assign, ast.AnnAssign, ast.AugAssign)


def _old_protected_ranges(root: pathlib.Path, base: str, path: str) -> list[tuple[int, int, int]]:
    """(start_line, end_line, def_column) triples — lines 1-indexed inclusive — for
    every protected node in `path` at `base`: every function body, plus every direct
    module-level Assign/AnnAssign/AugAssign statement. `def_column` is the node's
    own column offset, used to tell "new sibling appended after this body" apart
    from "new line appended INTO this body" (see append_only_check).
    """
    # AIDEV-NOTE: `path` is cwd-relative (it comes from `git diff --relative`), but
    # `git show rev:path` resolves a bare path relative to the REPO ROOT, not cwd —
    # the `./` prefix is what makes it cwd-relative. Without it, this silently
    # returns `[]` (falls into the "didn't exist" branch) for every stack whose
    # root isn't the repo root, i.e. every real stack in `.claude/sdlc.local.md`.
    proc = subprocess.run(
        ["git", "show", f"{base}:./{path}"], cwd=root, capture_output=True,
    )
    if proc.returncode != 0:
        return []  # file didn't exist at base — nothing to protect
    try:
        # WHY: bytes + errors="replace", not text=True — a committed undecodable
        # file must fall through to the permissive SyntaxError branch below, not
        # crash the subprocess decode with UnicodeDecodeError. The BOM strip is
        # load-bearing too: CPython's tokenizer skips a UTF-8 BOM when reading
        # source BYTES, but ast.parse of a STR starting with U+FEFF raises
        # SyntaxError — without the strip, a BOM'd (perfectly valid, runnable)
        # test file would fall into the permissive branch and lose ALL protection.
        tree = ast.parse(proc.stdout.decode("utf-8", errors="replace").lstrip("\ufeff"))
    except (SyntaxError, ValueError):
        return []  # can't parse (incl. null bytes) — fall through to the safe (permissive) side
    ranges = []
    # INVARIANT: covers EVERY function, not just `test_*`-named ones — a
    # `conftest.py` fixture or a plain helper a test depends on is just as
    # protected as the test itself.
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # INVARIANT: an EXISTING decorator (e.g. @pytest.mark.parametrize(...),
            # @pytest.fixture) is part of the protected body — node.lineno points
            # at `def`, not the decorator line(s) above it. Stacking a brand-NEW
            # outermost decorator onto an old function is NOT caught — see gap (5).
            start = node.decorator_list[0].lineno if node.decorator_list else node.lineno
            ranges.append((start, getattr(node, "end_lineno", node.lineno), node.col_offset))
    # INVARIANT: module-level test data is just as protected as a fixture — a
    # `-` line there is invisible to the function-only pass above.
    for node in tree.body:  # direct top-level children only — see AIDEV-NOTE below
        if isinstance(node, _MODULE_LEVEL_DATA):
            ranges.append((node.lineno, getattr(node, "end_lineno", node.lineno), node.col_offset))
    # AIDEV-NOTE: known, deliberate gaps — deferred follow-ups (ticket filing
    # queued behind the PR re-review, per owner instruction), not chased here:
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
    #     NOTE: unlike (4), adding `ast.NamedExpr` to `_MODULE_LEVEL_DATA` would
    #     NOT fix this — `tree.body`'s direct child here is the outer `ast.Expr`
    #     wrapper, never the inner `NamedExpr` itself, so that "just add the
    #     type" pattern (used for AugAssign) silently does nothing for this case.
    # (4) mutating a protected object in place (`_CASES.append(...)`,
    #     `del _CASES[1]`, `_BASE_KW["x"] = 999`) rather than rebinding its name
    #     isn't covered by ANY allowlist entry, by design — this is the same
    #     structural name-shadowing/monkeypatching limitation tracked as its own
    #     follow-up (line-diffing can't see what a statement's *effect* is, only
    #     its position), not a gap this allowlist could ever close by growing.
    # (5) stacking a brand-NEW outermost decorator (e.g. @pytest.mark.skip) onto
    #     a previously-existing function isn't caught — it anchors at the same
    #     diff position as legitimately inserting a new function directly above,
    #     which line positions can't distinguish. Needs old-vs-new AST identity
    #     matching (compare each function's decorator list across versions) —
    #     a separate deferred follow-up, same status as (4).
    return ranges


def _diff_positions(root: pathlib.Path, base: str, path: str) -> tuple[set[int], dict[int, int]]:
    """Old-file positions where `path`'s content differs between `base` and the
    working tree, in two forms:

    - `removed`: an old line number itself changed/removed — checked against a
      protected range INCLUSIVE on both ends (`lo <= ln <= hi`).
    - `inserted_after`: maps each old line number that NEW content was inserted
      directly after (no old line consumed) to the INDENT (leading spaces/tabs)
      of the first non-blank inserted line — checked EXCLUSIVE at the upper end
      (`lo <= n < hi`), except that an insertion anchored exactly at a range's
      end (`n == hi`) whose indent is deeper than the range's own definition
      column extends that body and is a violation too (see append_only_check).
    """
    # WHY: diff actual line CONTENT (old file via `git show`, new file read
    # straight off disk) with difflib.SequenceMatcher, rather than hand-parsing
    # `git diff`'s unified-diff TEXT. Three separate rounds of bugs (a removed
    # line starting with `--` false-matching a text-based header check; a
    # replace pair's insertion anchor landing one line later than it should;
    # an EOF-newline-only change rendering as a remove+add of unchanged text,
    # in a way that couldn't be fixed correctly for multi-line hunks without
    # LCS-style pairing) all stemmed from the same root cause: unified-diff TEXT
    # has representational quirks (headers, no-newline markers, replace-pair
    # ambiguity) that have nothing to do with whether a line's CONTENT actually
    # changed. SequenceMatcher's opcodes are computed directly from line
    # sequences, so a line byte-identical between old and new is always
    # "equal" — none of those text-format artifacts can arise by construction.
    #
    # AIDEV-NOTE: the exclusive bound on `inserted_after` is load-bearing. A pure
    # insertion (e.g. a whole new test function typed directly after an existing
    # one, zero blank lines between them) anchors at `n == hi` of the PRECEDING
    # function — that must stay unflagged, or this reopens the exact false-positive
    # OME-369 exists to fix (pure additions rejected as violations). Inserting as a
    # new first/middle statement anchors at `lo <= n < hi` and must be caught: a
    # pure insertion can still silently neuter a prior test's assertions (e.g.
    # forcing a variable's value right before the check) with zero removed lines,
    # which `removed` alone can never see.
    # WHY: compare BYTES on both sides, never decoded text — a working-tree file
    # rewritten with undecodable/binary content would make a text-mode read raise
    # UnicodeDecodeError and crash the gate with a traceback instead of a verdict.
    # Byte lines diff identically for ordinary text, and binary junk replacing a
    # protected test simply differs line-wise → flagged (fail-closed), no crash.
    old_proc = subprocess.run(
        ["git", "show", f"{base}:./{path}"], cwd=root, capture_output=True,
    )
    if old_proc.returncode != 0:
        return set(), set()  # file didn't exist at base — nothing to protect
    # AIDEV-NOTE: `append_only_check` only ever calls this for status "M" files,
    # which are guaranteed to exist in the working tree — reading directly off
    # disk is the correct equivalent of `git diff base -- path`'s implicit
    # "against the working tree" comparison (no second ref given).
    old_lines = old_proc.stdout.splitlines()
    new_lines = (root / path).read_bytes().splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    removed: set[int] = set()
    inserted_after: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            removed.update(range(i1 + 1, i2 + 1))  # old_lines is 0-indexed, ranges are 1-indexed
        if tag == "insert":
            # Indent of the first non-blank inserted line; 0 when all blank
            # (blank lines can never extend a body's logic).
            indent = 0
            for line in new_lines[j1:j2]:
                if line.strip():
                    indent = len(line) - len(line.lstrip(b" \t"))
                    break
            inserted_after[i1] = indent  # anchored right after old 1-indexed line i1
        # "replace" deliberately does NOT also populate inserted_after — the
        # removed lines already comprehensively signal the violation if inside
        # a range, and anchoring the replacement's added lines too would
        # double-count without adding coverage.
    return removed, inserted_after


def append_only_check(root: pathlib.Path, base: str, globs: list[str]) -> bool:
    """True when no previously committed test/fixture/data was modified/deleted
    (rule 5).

    Pure additions (new test functions, new fixtures/helpers, new module-level
    data, new imports for them, even a whole new function typed directly next to
    an existing one) are always fine — a violation is either a removed/changed
    line, OR new content inserted, that falls INSIDE a protected range (a
    function body — test, fixture, or helper — or a module-level
    Assign/AnnAssign/AugAssign statement) that already existed at `base`.
    Deleting, renaming, or type-changing (e.g. replacing with a symlink) a whole
    test file is always a violation regardless of content.
    """
    # WHY: core.quotepath=off — with the default quoting, a non-ASCII filename
    # (e.g. test_ä.py) is emitted as an octal-escaped C-string in double quotes,
    # which never matches any glob → deletions AND rewrites of such files were
    # silently skipped (fail-open). Off = raw UTF-8 paths that match normally.
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=off", "diff", "--relative", "--name-status", base],
        cwd=root, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        fail_config(f"git diff failed in {root}: {proc.stderr.strip()}")
    offenders = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        status, paths = parts[0], parts[1:]
        # WHY: T(ypechange) is in the offender set — replacing a committed test
        # file with a symlink wholesale swaps its effective content, exactly like
        # a delete+recreate. A(dded)/C(opied) stay fine: adding tests is always fine.
        if status[:1] not in "MDRT":
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
        bad_removed = sorted(ln for ln in removed if any(lo <= ln <= hi for lo, hi, _ in ranges))
        # INVARIANT: two distinct insertion violations — (a) anchored strictly
        # inside a range (`lo <= n < hi`), and (b) anchored exactly at a range's
        # end (`n == hi`) with the first non-blank inserted line indented DEEPER
        # than the range's own definition column: that extends the old body
        # (e.g. appending `break` inside a final test's loop flips it green with
        # zero old lines touched), whereas a new sibling def/decorator at the
        # same anchor starts at the same-or-shallower column and stays legitimate.
        bad_inserted = sorted(
            n for n, indent in inserted_after.items()
            if any(lo <= n < hi or (n == hi and indent > col) for lo, hi, col in ranges)
        )
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
