# OME-833 — Local-mode concurrent run ceiling

## Problem

Local mode refuses a Run too early. The Engine answers `503` with the detail
`the runner is at capacity — retry shortly`.

`InProcessJobRunner` accepts 8 Runs at the same time. The Client starts one Run for each
Candidate, and it starts up to 8 Runs at the same time. The two limits are equal. Thus there is
no spare capacity.

One Evaluation with 8 Candidates fills the runner completely. If one more Run is active, the
next Run fails. A second notebook cell, a second Client, or an abandoned Run each cause this.

An abandoned Run keeps its slot for a long time. A WebSocket disconnect does not stop the Run.
Only an explicit stop frame or `DELETE /?topic=` stops it. Thus an abandoned Run keeps its slot
until it ends, or until the run deadline of 57600 seconds (16 hours).

Only the in-process runner refuses. The Kubernetes runner does not refuse, because the cluster
scheduler holds the surplus Jobs.

## Sources

| Constant | Location | Value |
|---|---|---|
| `local_max_concurrent_runs` | `apps/url4-cloud/src/url4_cloud/config.py:129` | 8 |
| `DEFAULT_MAX_CONCURRENT_RUNS` | `apps/url4-cloud/src/url4_cloud/adapters/inprocess.py:40` | 8 |
| `_MAX_CANDIDATES_IN_FLIGHT` | `packages/screamingface/src/screamingface/_evaluation/runner.py:40` | 8 |

## Decision

Increase the local ceiling to 32.

32 is four times the Client fan-out. It permits approximately four Evaluations at the same
time. It also gives spare capacity for abandoned Runs.

Keep the two url4-cloud constants equal. `local.py` reads the setting. The adapter default
applies when a caller supplies no setting. If the two values differ, the behaviour changes with
the call path.

## Constraint to protect

The url4-cloud ceiling must stay larger than the Client fan-out. If the two become equal again,
the failure returns.

A test cannot read the Client constant. `apps/url4-cloud` does not depend on
`packages/screamingface`. Its `pyproject.toml` does not list the package, and no module imports
it. A direct check needs one of these changes:

- The Client depends on the server app. This inverts the layer order. Rejected.
- A shared constant moves to `packages/url4`, which both sides already use. This is correct,
  but it changes three units. Out of scope.

Therefore the test asserts a floor. The floor is larger than the known Client fan-out. The test
rationale names the Client constant and its location.

## Out of scope

- Move the shared concurrency contract to `packages/url4`.
- Hold surplus Runs in a queue instead of a refusal. The code comments compare local mode with
  Kubernetes, which holds surplus Jobs. This supports a queue. The `Retry-After: 1` header shows
  that a delay of one second is sufficient.
- Make the Client obey `Retry-After`. The Client retries only on `428`.
- Stop or reap an abandoned Run before the 16-hour deadline.
- Give `ProblemException` a real `type_`. The Client now shows `Code: about:blank`.

## Acceptance

- Both url4-cloud constants read 32.
- A test fails if the ceiling becomes 8 or smaller.
- The url4-cloud gates pass.
