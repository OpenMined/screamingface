---
ticket: OME-829
stack: url4-cloud (+ screamingface notebook rider)
status: in_progress
started: 2026-08-14
finished:
---

# OME-829 — DRACO check adapter (`draco-pass.v1`): CorrectiveLoop's first paid check surface

## Intent

Give DRACO the check surface the OME-796 loop substrate consumes, so
`sf.CorrectiveLoop(..., benchmark="draco")` runs — the first PAID check and the proof
that loop × new benchmark = one benchmark-side adapter, zero engine/client loop code.
Stacked on branch `OME-796-corrective-loop` (PR #598); lands as its own PR.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/draco/`: input-addressed check-surface
  endpoint per DRACO variant — resolve case by exact input, ONE judge pass over the case
  rubric, score with the existing grader math, emit the closed port record
  `{schema, passed, satisfaction, feedback, answer}`.
- Pass criterion `draco-pass.v1`: passed = normalized weighted rubric score (clipped
  [0,1]) ≥ 0.7; satisfaction = that score. The criterion id is a named constant carried
  in the check route (→ manifest + every compiled url4 + topology rider).
- Feedback policy v1: axis-level only, never criterion text; #528-shaped leak test.
- Judge hygiene: the answer participates in the exact request; failed/empty verdicts never
  cached; in-flight checks capped (reuse DRACO's existing judge plumbing).
- Manifest: `check_surface` with `expected_check_cost: "paid"` on the DRACO benchmarks.
- Client (small rider): preflight surfaces expected paid-check spend (EvaluationWarning
  with the rounds × members formula) when `expected_check_cost == "paid"`.
- Notebook: `sf.CorrectiveLoop` cell in the DRACO notebook (one changed `benchmark=`
  line vs notebook 07; prints the spend note; states the pass criterion in prose);
  regenerate via `build_notebooks.py`.

## Test plan

- Adapter unit tests with a canned judge (mock transport): pass/fail thresholding at
  0.7, satisfaction clipping, unknown input → bounded failure, malformed payload.
- Leak test: feedback never contains rubric criterion text (axis names only).
- Salting test: two different answers for the same case produce different judge prompts.
- Engine e2e (extend `test_corrective_loop_e2e.py` pattern): a client-compiled loop
  golden runs against DRACO with a fake judge — cost story counts include the paid
  check calls.
- Client: preflight spend-warning test.
- Gates: url4-cloud + screamingface `run_gates.py` green.

## Acceptance

- `sf.CorrectiveLoop([...], judge=..., max_rounds=N)` with `benchmark="draco-lite"`
  (mock stack) completes and scores; notebook cell reads coherently.
- `draco-pass.v1` reviewable in-PR (Keelan) as a named, one-place constant.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** engine — new `draco/check_policy.py` (criterion, threshold,
  instructions and prompt builder) + `draco/check_surface.py` (adapter);
  `draco/definition.py` (3 check routes + `check_surface=` on all three variants);
  `draco/runtime.py` (register the endpoint per variant, closing over `node`); new
  `tests/unit/test_draco_check_surface.py` (28) + `tests/unit/test_draco_corrective_loop_e2e.py`
  (4) + `tests/unit/data/draco_corrective_loop_candidate.url4`. client —
  `_evaluation/runner.py` (paid-check spend warning); `scripts/build_notebooks.py`
  + regenerated `examples/05_draco_lite_e2e.ipynb` (corrective cell); new
  `tests/test_paid_check_spend.py` (5).
- **Commits:** see branch `OME-829-draco-check-adapter` (stacked on
  `OME-796-corrective-loop`).
- **Gates:** url4-cloud ALL GREEN (1437 passed / 5 skipped, cov ≥80);
  screamingface ALL GREEN (824 passed / 1 skipped, cov ≥95, notebooks, build,
  distribution). Append-only skipped: no prior test modified — new files only.
- **Deviations:**
  1. **One batched judge pass, not one call per criterion.** Canonical DRACO
     judges each criterion in its own call (5 passes x median 38 criteria). At
     loop rates (members x rounds) that is hundreds of calls per case, so the
     check batches the variant's criteria into ONE weight-blind pass. The check
     is a steering instrument; canonical grading still produces the published
     score. Documented at the top of `check_policy.py`; the check prompt is our
     authorship and a revision input, reviewed in-PR.
  2. **Check scores against the variant's own criterion selection** (canonical
     all / lite 10 axis-balanced / smoke 1). Checking the full rubric while the
     variant grades a subset would make satisfaction and score incomparable.
  3. **Pass criterion rides in the route** (`…/check-surface/draco-pass.v1`)
     rather than being hashed into the benchmark `REVISION`: the check adds no
     scoring semantics to DRACO itself, matching IFEval's precedent, and the
     route reaches the manifest, every compiled url4, and the topology rider.
  4. **An unusable judge reply fails the check** after `CHECK_ATTEMPTS` retries
     on fresh cache slots — never a silent `satisfaction=0.0`, which would look
     like a legitimate no-pass round and buy the loop an unearned retry.
  5. **Input uniqueness is guarded at request time**, not at prepare time —
     DRACO's `cases.json` has no uniqueness invariant (unlike IFEval's), so the
     adapter refuses 0-or-many matches. A prepare-time assertion is a follow-up.
  6. Judge-call hygiene uses the answer-bearing prompt as exact cache identity and
     varies a bounded prompt marker on retry. It never forwards invented
     `check_salt` / `check_attempt` parameters through AI Gateway.
