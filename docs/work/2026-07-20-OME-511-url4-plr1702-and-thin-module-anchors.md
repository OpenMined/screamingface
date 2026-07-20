---
ticket: OME-511
stack: url4
status: done   # planned | in_progress | done | blocked
started: 2026-07-20
finished: 2026-07-20
---

# OME-511 — url4: activate the inert PLR1702 gate + anchor the two thin modules

## Intent

Close the two real findings from the url4 code-quality reports (the rest were
stale, pre-reorg snapshots). `PLR1702` (too-many-nested-blocks) is selected in
url4's ruff config but silently inert (ruff 0.15 gates it behind preview), so it
enforces nothing. And the two "hardest" modules — `dag/compiler.py` and
`peer/server.py` — carry almost no semantic anchors. Fix both, url4 only.

## Planned changes

- `packages/url4/pyproject.toml` — under `[tool.ruff.lint]`, add `preview = true`
  + `explicit-preview-rules = true` so ONLY the explicitly-selected preview rule
  (PLR1702) activates, not ruff's broad preview behavior.
- `packages/url4/src/url4/dag/compiler.py` — add anchors to un-anchored rationale.
- `packages/url4/src/url4/peer/server.py` — add anchors to un-anchored rationale.

## Test plan

- **PLR1702 (RED→GREEN):** proven in scratchpad that the surgical config flags a
  6-deep nested function and drops the "no effect" warning; the current url4 tree
  has zero PLR1702 violations (`ruff check --preview` clean), so the gate goes
  green immediately after activation. The gate config IS the test here.
- **Anchors:** documentation-only, no behavior; guard = full suite stays green,
  vocabulary-only anchors, coverage unchanged.

## Acceptance

- `ruff check` (url4) emits no `PLR1702 has no effect` warning; nesting enforced.
- compiler.py + server.py carry anchors on their genuine rationale/invariants.
- Gates green (run_gates.py url4); 1046 tests still pass.

## Out of scope

- `apps/scoreboard` / `apps/aigateway` share the same inert PLR1702 select — left
  for a separate ticket (this is a url4 branch).

## Outcome

- **Actual files:** exactly as planned — `packages/url4/pyproject.toml` (+5),
  `dag/compiler.py`, `peer/server.py`.
- **PLR1702:** activated surgically (`preview = true` + `explicit-preview-rules =
  true` under `[tool.ruff.lint]`). Verified it enforces (6-deep nesting flagged
  in a scratchpad probe) and the `PLR1702 has no effect` warning is gone; the
  current tree has zero violations. Thresholds untouched — this only turns ON a
  rule that was inert; it does not relax anything.
- **Anchors:** `dag/compiler.py` 1→7 (two build-order INVARIANTs, the OME-508
  eager-reject WHY, the fan-out list-op WHY, the inline-collection WHY, the F2
  path-parity AIDEV-NOTE); `peer/server.py` 0→5 (GET-only doctrine WHY,
  `_TRANSPORT_PARAMS` DERIVED INVARIANT, opaque-context AIDEV-NOTE, data-route
  membership INVARIANT, processor-consumed AIDEV-NOTE). Prefix-only on existing
  prose; vocabulary-only, no invented anchors, no restated code.
- **Commits:** 1cc9549 — fix(url4): activate the inert PLR1702 gate + anchor compiler.py and server.py
- **Gates:** run_gates.py url4 → ALL GREEN (append-only · ruff check · ruff format
  --check · pyright 0 errors · pytest --cov=url4 --cov-fail-under=95). 1046 tests
  pass — unchanged (docs/config only, no behavior change).
- **Deviations:** none. apps/scoreboard + apps/aigateway carry the same inert
  PLR1702 select (both clean under `--preview`); left for a separate ticket per
  the ticket's out-of-scope note.
