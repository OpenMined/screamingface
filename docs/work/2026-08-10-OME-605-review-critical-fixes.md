---
ticket: OME-605
stack: screamingface
status: in_progress
started: 2026-08-10
finished:
---

# OME-605 — Critical fixes from the PR #539 branch review

## Intent

Close the four blocking findings from the pre-merge review of the ScreamingFace Client
branch. Each one either spends money incorrectly or discards work the user has already paid
for, so none of them can ship. The normative contract is
[`docs/spec/2026-08-10-OME-605-review-critical-fixes.md`](../spec/2026-08-10-OME-605-review-critical-fixes.md);
the findings are inline comments on
[PR #539](https://github.com/OpenMined/screamingface/pull/539#pullrequestreview-4901288332).

Owner decisions taken before implementation: small symmetric async stop (not the scope
redesign), include the replay-safety marking with the status gate, and additive edits to
existing test doubles are permitted.

## Planned changes

Implemented as four commits, in dependency order (pure/self-contained first, riskiest
last).

1. **Linker source-position references** — `_evaluation/linking.py`;
   `tests/test_shape_adaptive_linking.py`.
2. **Unsequenced advisory CloudEvents** — `_engine/contract.py`; `tests/protocol_server.py`
   (new `unsequenced_log` mode), `tests/test_engine_contract.py`,
   `tests/test_client_protocol.py`.
3. **Access challenge gate + replay safety** — `_engine/access_contract.py`,
   `_engine/auth.py`, `_engine/transport.py`; `tests/test_authentication.py`.
4. **Async `cancel_active`** — `_core/ports.py`, `_engine/transport.py`,
   `_evaluation/runner.py`; `tests/test_client_run.py`, plus additive `cancel_active`
   stubs on four existing async test doubles in `tests/test_draco_vertical_slice.py` and
   `tests/test_model_parameter_preflight.py`.

## Test plan

Failing-first tests, per the spec's Verification section:

- **Linker:** a source-position `($candidate)!'x'` links (today: `PlanningError` "does not
  invoke the Candidate"); a mixed source/intent Fusion reference never emits an unresolved
  `$candidate_member_N` (today: no exception, poisoned artifact); a partial member
  reference does not report a wrong arity. Boundaries: `VarRef` with a field path,
  `$candidate_result` plumbing stays a non-reference, `$$candidate` escape, iteration
  collection.
- **Unsequenced:** the real notice wire shape (sequence keys present and null) does not
  kill a Run, end to end and in both sync and async form; unsequenced frames are still
  validated (severity, attributes, run subject); a half-declared sequence still raises;
  unsequenced lifecycle frames still raise.
- **Access:** a 202 async start is never read as a challenge and is never re-sent; the
  challenge/non-challenge status matrix; the WebSocket predicate agrees with the HTTP one;
  an unmarked request raises `access_reauthenticated` instead of replaying.
- **Async stop:** async concurrent cancellation deletes every minted capability (mirrors
  the existing sync assertion); a stop failure is reported rather than swallowed.

## Acceptance

- Each of the four findings has a test that failed first for the stated reason.
- No existing assertion weakened, deleted, or skipped.
- `uv run .claude/scripts/run_gates.py screamingface` green on each commit.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** <vs planned>
- **Commits:** <sha — message>
- **Gates:** <run_gates.py result line / counts>
- **Deviations:** <anything that differed from the plan, or "none">
