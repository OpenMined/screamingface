---
ticket: OME-830
stack: url4-cloud (+ screamingface notebook rider)
status: done
started: 2026-08-14
finished: 2026-08-14
---

# OME-830 — HealthBench check surface + the `rubric_check` extraction

## Intent

Onboard a SECOND rubric benchmark to the corrective loop, and let that second
customer force the shared component out (rule of three: an abstraction from one
example is a guess). Stacked on `OME-829-draco-check-adapter`; lands as its own PR.

## Planned changes

- New shared `benchmarks/rubric_check.py`: the marking work every rubric benchmark
  repeats — input-addressed case resolution, rubric reading through a declared
  shape, one weight-blind judge pass with answer-hash salting and bounded retries,
  clamped weighted scoring, sanitized feedback, the closed port record.
- Migrate DRACO onto it: `draco/check_policy.py` becomes a declaration,
  `draco/check_surface.py` is deleted, behavior byte-identical (stage-3 tests keep
  passing with only their import line moved).
- HealthBench: `healthbench/check_policy.py` = one `RubricCheck` declaration
  (`healthbench-pass.v1`, threshold 0.5 on the clamped score, flat points-weighted
  rubric shape, chat-envelope question rendering, severity feedback) + route +
  `expected_check_cost: "paid"` + endpoint registration.
- HealthBench notebook gains the `sf.CorrectiveLoop` cell.

## Test plan

- HealthBench adapter tests: points-weighted thresholds, the scoring contract's
  worked example, negative-total clamping, unscorable rubric, chat-envelope
  transcript rendering, severity feedback, leak test.
- **Deletion test**: `healthbench/check_policy.py` contains no `def`/`class`/control
  flow, and no `healthbench/check_surface.py` exists.
- Declaration validation: a shape with no area fields cannot claim area feedback.
- DRACO's 32 stage-3 tests must pass unchanged (the migration's acceptance).

## Acceptance

- `sf.CorrectiveLoop(..., benchmark="healthbench/worst30")` compiles and runs.
- HealthBench's adapter is arguments only — if it had needed new Python, the
  template failed and two concrete adapters would have been the honest ship.

## Outcome

- **Actual files:** engine — new `benchmarks/rubric_check.py` (the component);
  `draco/check_policy.py` (now a declaration), `draco/check_surface.py` DELETED,
  `draco/definition.py` (owns `CHECK_CRITERION`), `draco/runtime.py` (calls the
  component); new `healthbench/check_policy.py` (declaration only),
  `healthbench/definition.py` (+ route, `CheckSurface`), `healthbench/runtime.py`
  (registers the endpoint); new `tests/unit/test_healthbench_check_surface.py` (15);
  `tests/unit/test_draco_check_surface.py` (import line + one construction line).
  client — `scripts/build_notebooks.py` + regenerated
  `examples/08_healthbench_worst30.ipynb`.
- **Commits:** see branch `OME-830-healthbench-rubric-check`.
- **Gates:** url4-cloud ALL GREEN (1452 passed / 5 skipped, cov ≥80); screamingface
  ALL GREEN (824 passed / 1 skipped, cov ≥95, notebooks, build, distribution).
  Append-only skipped: the only prior-test edit is `test_draco_check_surface.py`'s
  import block plus one construction line — every assertion is untouched, which is
  precisely what proves the migration preserved behavior.
- **Deviations:**
  1. **`healthbench-pass.v1` threshold is 0.5, not DRACO's 0.7.** This is the
     worst-30% subset, where strong baselines average negative; a 0.7 bar would
     never trigger and `max_rounds` would stop being a cost cap and become a fixed
     price. Named so it is reviewable and bumpable. Reviewed in-PR.
  2. **Severity feedback, not areas.** HealthBench's prepared rubric keeps only the
     criterion text and points — the upstream theme/category columns are dropped at
     build time, so there is no safe vocabulary to name. Feedback says only whether
     the shortfall was an omission or a violation. If that proves too thin to steer,
     the fix is richer prepared metadata, never leaking criteria.
  3. **The component owns its own scoring formula** rather than importing a
     benchmark's grader — core must not import a plugin, and check semantics are
     pinned by `<benchmark>-pass.vN` so a canonical-grading change can never
     silently move a check threshold.
  4. **`RubricCheck` validates itself**: a benchmark whose shape declares no area
     fields cannot claim area-level feedback. The alternative was a runtime
     "unknown" area leaking into a Candidate prompt.
  5. No HealthBench cross-stack e2e: its protocol needs the full 157-case frozen
     asset set, and the DRACO e2e already proves the client→engine loop path on a
     paid surface. The HealthBench adapter is covered by unit + deletion tests.
