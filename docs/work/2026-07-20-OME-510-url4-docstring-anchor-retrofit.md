---
ticket: OME-510
stack: url4
status: done   # planned | in_progress | done | blocked
started: 2026-07-20
finished: 2026-07-20
---

# OME-510 — url4: fix stale docstring cross-refs + adopt semantic-anchor pattern across src

## Intent

Follow-up cleanup after the `OME-499` package reorg was merged into this branch
(merge commit `6912fa8`). The reorg moved `src/url4`'s flat modules into
`core/ io/ dag/ peer/ cli/` subpackages and fixed every executable import, but
left ~94 docstring/RST cross-references (`:mod:`/`:class:` targets like
`url4.errors`, `url4.io_layer`, `url4.server`) pointing at the dead flat paths.
This unit repaths those references and, per owner direction, does a full pass
adopting the `sdlc-python` semantic-anchor comment vocabulary across `src/url4`.
Documentation-only — no behavior change.

## Planned changes

- All 29 `src/url4/**.py` files: rewrite stale `url4.<flat>` cross-references to
  the new package paths (`url4.core.*`, `url4.io.*`, `url4.peer.*`, `url4.dag.*`,
  `url4.cli.*`).
- Normalize the one non-vocabulary anchor (`# SINGLE-PASS:`) into the fixed set.
- Add `WHY:` / `INVARIANT:` / `AIDEV-NOTE:` / `FEATURE:` / `STORY:` anchors where
  rationale is currently un-anchored; remove comments that merely restate code.
- `tests/**` untouched (out of scope, owner decision).

## Test plan

- No new tests: this unit changes only docstrings/comments, which carry no
  behavior. TDD RED/GREEN collapses to "the full existing suite stays green and
  coverage stays ≥95%" — a prior test changing would be a Confidence-Gate stop.
- Guard: `grep` proves zero `url4.<flatmodule>` references remain in `src/url4`
  and zero anchors outside the fixed vocabulary.

## Acceptance

- No `url4.<flatmodule>` reference anywhere in `src/url4` (imports, docstrings,
  comments, RST refs).
- Every comment anchor is in the fixed vocabulary; no invented anchors.
- Gates green: `ruff check`, `ruff format --check`, `pyright`,
  `pytest --cov=url4 --cov-fail-under=95`.
- Behavior unchanged: 1046 tests still pass; coverage unchanged from baseline.

## Outcome

- **Actual files:** 22 of the 29 `src/url4/**.py` files changed (+135/−132). The
  other 7 (module `__init__.py`s, `context.py`, etc.) had no stale refs and no
  anchor gaps. Comment/docstring-only — verified no executable line changed.
- **Cross-references:** all 94 stale `url4.<flat>` docstring/RST refs repathed to
  the new subpackage paths via a token-scoped codemod (legitimate `url4.cli`
  package references correctly preserved). Zero remain.
- **Anchors:** `# SINGLE-PASS:` pseudo-anchor folded into a real `INVARIANT:`
  (single-pass substitution / template-injection guard). Full audit via 4
  read-only scouts (re-run with absolute paths after 3 first resolved against the
  pre-reorg main checkout); applied 20 genuine anchor additions
  (`WHY:` 13→30, `INVARIANT:` 36→40, `AIDEV-NOTE:` 3→4) where un-anchored
  rationale/invariants were hiding. `core-part-2` (ensemble/builders/render/
  context/errors/subrequest) needed none — already well-anchored.
- **Commits:** f1767b9 — docs(url4): repath stale cross-refs + adopt semantic-anchor pattern in src
- **Gates:** run_gates.py url4 → ALL GATES GREEN (append-only check · ruff check ·
  ruff format --check · pyright 0 errors · pytest --cov=url4 --cov-fail-under=95).
  1046 tests pass — unchanged from the post-merge baseline (behavior preserved).
- **Deviations:** `tests/**` left untouched (owner scope decision). The `docs/`
  and `.claude/skills/*` docstring drift the reorg itself left in non-url4 files
  was out of scope. `builders.py`/`render.py` DID receive cross-ref repaths
  (contra one scout that ran against the wrong tree and reported them absent).
