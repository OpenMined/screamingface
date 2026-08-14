---
ticket: OME-826
stack: screamingface
status: done
started: 2026-08-14
finished: 2026-08-14
---

# OME-826 — Fix PR #571 post-merge review findings

## Intent

PR #571 (OME-786 pipeline composition) merged with 8 review findings surviving adversarial
verification (plan: `.dk/plans/2026-08-14-pr571-review-findings.md`, local). The worst is a
money bug: duplicate member display names pass construction, compile, and preflight, then
`report.py::_members` raises **after the paid evaluation** — the researcher pays and loses
the run, violating the fail-before-spend doctrine. The rest: a structural-equality lie
(hidden `_is_named`), a deleted rendered-surface guard, 3 duplicate topology walkers,
dead kind machinery, `then()` re-implementing Pipeline flattening, a per-candidate re-parse
of the invariant benchmark url4, and the unclosed OME-786 ledger/mirror.

## Planned changes

- `packages/screamingface/src/screamingface/report.py` — drop `_members` uniqueness raise; disambiguate duplicate display names at render
- `packages/screamingface/src/screamingface/pipeline.py` — `_is_named` excluded from equality (`field(compare=False)`) or repr un-suppressed; document topology effect
- `packages/screamingface/src/screamingface/_evaluation/linking.py` — re-add `_require_every_reference_bound`; hoist benchmark parse out of per-candidate loop
- `packages/screamingface/src/screamingface/_evaluation/topology.py` — one shared dependency walker
- `packages/screamingface/src/screamingface/_evaluation/url4.py` — use shared walker
- `packages/screamingface/src/screamingface/_evaluation/candidate.py` — delete `_recipe_kind`, dead `synthesis_root` param; one typed kind-function
- `packages/screamingface/src/screamingface/_ui/cards.py` — import the kind-function
- `packages/screamingface/src/screamingface/recipe.py` — `then()` → `Pipeline((self, next_recipe))`
- `docs/work/2026-08-12-OME-786-*.md` + `docs/tasks/2026-08-11-ome-786-*.md` — close (bookkeeping)
- Tests per finding in `packages/screamingface/tests/`

## Test plan

- RED: duplicate-display-name Fusion run reaches Report without ValueError; report renders disambiguated names (protects fail-before-spend: no post-spend raise)
- RED: `Pipeline(["p/a","p/b"], name="a->b") == Pipeline(["p/a","p/b"])` iff spec's structural equality (protects spec promise)
- RED: unresolved `$candidate*` in rendered surface fails at plan time (protects walker-blindness insurance)
- Walker unification, `then()` one-liner, hoist: behavior-identical — existing suite is the net; add dependency-tuple equivalence test for the shared walker
- Kind-function: subclass rename doesn't break cards (protects against `type(...).__name__` fork)

## Acceptance

- All 7 code findings fixed, #8 ledger/mirror closed, gates green (`ruff`, `pyright`, pytest cov≥95, notebooks, build, distribution)
- Draft PR open on `OME-826-pr571-review-fixes`

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus `_evaluation/compilation.py` (uses the hoisted
  `_prepare_benchmark`) and `_ui/report_view.py` `MemberResult` type import; the shared
  walker landed as `_topology_bindings` in `topology.py` (the plan's named
  `url4.py::_validate_topology_node` did not exist — the three real walkers were
  `_topology_model_nodes`, `_validate_topology_dependencies`,
  `_topology_operation_dependencies`, all unified).
- **Commits:** b20630a6 — fix(screamingface): resolve PR #571 post-merge review findings;
  (docs close commit follows)
- **Gates:** ALL GATES GREEN — append-only test check, ruff check, ruff format, pyright,
  pytest 794 passed / 1 skipped with cov ≥95, notebooks, uv build, distribution check.
- **Deviations:** (1) equality fix #2 chose repr-visibility (keep `_is_named` in `__eq__`,
  always show `name=` when explicitly named) over `field(compare=False)` — the spec makes
  namedness behavioral (named nested Pipelines keep their grouping), so hiding it from
  equality would create the opposite lie. (2) Adversarial topology metadata carrying the
  same binding twice with equal nodes but different dependencies now raises "conflicting
  Recipe topology metadata" instead of "does not match its model calls" — same ValueError
  type, unreachable from compiler output. (3) Render disambiguation suffixes the provider
  (first route segment) only for colliding names.
