# OME-833 — Plan

Spec: `docs/spec/2026-08-14-OME-833-local-run-ceiling.md`

## Step 1 — RED

Add a test to `apps/url4-cloud/tests/unit/test_inprocess_runner.py`.

The test asserts that `DEFAULT_MAX_CONCURRENT_RUNS` and `Settings().local_max_concurrent_runs`
are both larger than 8. The docstring states why: the Client starts up to
`_MAX_CANDIDATES_IN_FLIGHT = 8` Runs at the same time, from
`packages/screamingface/src/screamingface/_evaluation/runner.py:40`. It also states that
url4-cloud cannot import that constant.

The test fails first, because both values are 8.

## Step 2 — GREEN

Change `DEFAULT_MAX_CONCURRENT_RUNS` to 32 in
`apps/url4-cloud/src/url4_cloud/adapters/inprocess.py:40`.

Change `local_max_concurrent_runs` to 32 in
`apps/url4-cloud/src/url4_cloud/config.py:129`.

Update the comment above `local_max_concurrent_runs`. Add the reason for the value. Name the
Client fan-out.

## Step 3 — Gates

Run `uv run .claude/scripts/run_gates.py url4-cloud`.

## Step 4 — Close

Fill the ledger outcome. Open the PR. Add the close comment to OME-833.

## Files

| File | Change |
|---|---|
| `apps/url4-cloud/tests/unit/test_inprocess_runner.py` | Add the floor test |
| `apps/url4-cloud/src/url4_cloud/adapters/inprocess.py` | 8 to 32 |
| `apps/url4-cloud/src/url4_cloud/config.py` | 8 to 32, and the comment |

## Risks

The change permits more Runs at the same time. Each Run permits up to 32 fetches at the same
time, from `DEFAULT_RUN_CONCURRENCY` in `packages/url4/src/url4/dag/node.py:174`. Thus the
theoretical maximum becomes 1024 fetches. Real Evaluations stay far below this maximum. Local
mode runs on a developer machine, where the provider rate limit binds first.

No change to the Kubernetes path. The setting applies only to local mode.
