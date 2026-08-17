# OME-798 — Implementation plan

Spec: `docs/spec/2026-08-13-OME-798-portal-js-in-ci.md` · Ledger:
`docs/work/2026-08-13-OME-798-portal-js-in-ci.md`

Two files, one stack. The invocation is already settled by measurement (spec §2), so the work is
wiring plus proving the wiring fails when it should.

## Step 1 — RED: prove nothing runs them today

`uv run .claude/scripts/run_gates.py scoreboard --base origin/main` and confirm the output lists
four gates, none of them JS. This is the baseline the change has to alter.

## Step 2 — GREEN: the gate card

`.claude/sdlc.local.md`, `scoreboard` stack, append to `gates:`:

```
- node --test tests/portal/leaderboard-logic.test.js
```

Gates run with `cwd` = the stack root (`apps/scoreboard`), so the path is relative to that — not to
the repo root. Verify by running the gate runner, not by reasoning about it.

## Step 3 — GREEN: the workflow

`.github/workflows/scoreboard-tests.yml`:

- add `actions/setup-node` with a **pinned** major (spec §3), placed before the test step;
- add a step running the same explicit command;
- an `AIDEV-NOTE` recording why it is not a glob, with the measured exit codes, so the next person
  does not "simplify" it into a silently-green step.

Path filters already cover `apps/scoreboard/**` — confirm, don't change.

## Step 4 — prove it actually fails

The important step, and the one the ticket calls out:

1. break an assertion in `leaderboard-logic.test.js`;
2. `run_gates.py scoreboard` must report a **failed gate** (not a pass, not a skip);
3. revert; confirm green again.

Without this, a passing pipeline is unfalsifiable evidence.

## Step 5 — gates, ledger, commit, PR

Full `run_gates.py scoreboard --base origin/main`, fill the ledger Outcome, commit with
`Refs: OME-798`.

## Risks

- **#516 edits the same workflow file** and is awaiting review. Both add distinct steps, so the
  merge is trivial, but whichever lands second rebases. Not worth blocking on.
- **The card is committed repo config** shared by every stack; touching the wrong stack's `gates:`
  block would change what other apps must pass. Edit only the `scoreboard` entry and re-read the
  diff.
