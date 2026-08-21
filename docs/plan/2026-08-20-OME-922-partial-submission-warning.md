# OME-922 — Implementation plan

Spec: `docs/spec/2026-08-20-OME-922-partial-submission-warning.md` · Stack: screamingface

## Shape

Keep the advisory at the Scoreboard submission seam in
`packages/screamingface/src/screamingface/_scoreboard/leaderboards.py`. A private result
decorator shared by synchronous and asynchronous submission preserves one presentation decision:
headless callers get a Python warning, while notebooks get the advisory on the returned
score card. A private, comparison-neutral field carries this transient display fact without
changing the HTTP payload or public constructor behavior.

## Tests first

Append tests in `packages/screamingface/tests/test_leaderboards.py` that prove:

1. A limited Candidate (`len(cases) < benchmark.case_count`, selected coverage `1.0`) warns
   and still posts the unchanged payload.
2. A full-sized Candidate with incomplete Engine coverage warns and still posts.
3. A full, fully graded Candidate emits no warning.
4. The async submission path has the same warning behavior.
5. A notebook partial submission emits no Python warning and renders the branded notice.
6. A notebook full submission omits the notice.

## Implementation

- Validate the Candidate and score as today.
- Determine partiality from selected Case count plus Engine coverage.
- After a successful submission, emit the exact ticket copy as `UserWarning` when headless,
  or mark the returned score for an in-card notice when running in a notebook.
- Render the notice using current canonical light/dark warning tokens and the product UI
  status recipe from `OpenMined/screamingface-brand` commit `7ea35a1`.
- Reuse the validated score when constructing the payload.

## Verification

- Confirm the new tests fail before production changes and pass afterward.
- Run the full `screamingface` gate set through `.claude/scripts/run_gates.py`.
- Review the diff for unchanged full-run payloads and no Scoreboard-side changes.
- Visually confirm the notice reads as a warning state inside the published-score result,
  not as a Jupyter exception banner.
