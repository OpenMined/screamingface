# OME-922 — Implementation plan

Spec: `docs/spec/2026-08-20-OME-922-partial-submission-warning.md` · Stack: screamingface

## Shape

Keep the policy at the Scoreboard submission seam in
`packages/screamingface/src/screamingface/_scoreboard/leaderboards.py`. The existing shared
`_submission(...)` path serves synchronous and asynchronous clients, so one private helper
can warn exactly once without changing the HTTP adapter or public values.

## Tests first

Append tests in `packages/screamingface/tests/test_leaderboards.py` that prove:

1. A limited Candidate (`len(cases) < benchmark.case_count`, selected coverage `1.0`) warns
   and still posts the unchanged payload.
2. A full-sized Candidate with incomplete Engine coverage warns and still posts.
3. A full, fully graded Candidate emits no warning.
4. The async submission path has the same warning behavior.

## Implementation

- Validate the Candidate and score as today.
- Determine partiality from selected Case count plus Engine coverage.
- Emit the exact ticket copy as `UserWarning` before HTTP.
- Reuse the validated score when constructing the payload.

## Verification

- Confirm the new tests fail before production changes and pass afterward.
- Run the full `screamingface` gate set through `.claude/scripts/run_gates.py`.
- Review the diff for unchanged full-run payloads and no Scoreboard-side changes.
