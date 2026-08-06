---
ticket: UNFILED
stack: url4-cloud
status: in_progress
started: 2026-08-05
finished:
---

# UNFILED — implement the url4 per-run cache policy

## PROCESS DEVIATION

**No Linear issue backs this unit.** Linear MCP unauthenticated; `.claude/task-board.local.md`
names it the only permitted transport. Fifth occurrence this session; the owner has consistently
chosen "proceed and record the deviation".

**This one is worse than the previous four**: the work spans `packages/url4` **and**
`apps/url4-cloud`, so CLAUDE.md rule 8 requires an **epic + one sub-issue per landing**. It is
being executed as a single unit because there is no way to file the epic. Back-fill on MCP:
epic + 2 sub-issues, branch rename, `docs/tasks/` mirrors, `Refs:` on commits.

## Intent

Implement the design approved in plain words by the owner on 2026-08-05.

- **Spec:** `docs/spec/2026-08-05-url4-cache-policy-spec.md` (r7 — decision-complete)
- **Plan:** `docs/plan/2026-08-05-url4-cache-policy.md` (r6 — 8 batches)

Both live on branch `url4-cloud-cache-policy-spec` (PR #515), **not yet on `main`**. This branch
is cut from `main` and carries code only, so the two PRs stay independent rather than stacked
(the repo squash-merges; stacking has bitten before — see `feedback_no_stacked_prs_squash`).

## Locked design

| | |
|---|---|
| Default | caching **ON**; only disabling is explicit |
| Carriers | `Cache-Control` header on `GET /` **and** `AttachData.cache` on the WS attach frame |
| Precedence | **header wins**; override emits a `LogEvent` at `warn` |
| Frame shape | extend `AttachData` — no new inbound verb |
| `max-age` | **honour it** — inert today (§6 of the plan), value preserved rather than collapsed |
| Read-back | prefer `Cache-Status` (RFC 9211), fall back to the `X-AIGW-*` triple |
| aigateway | **no change** — PR #507 owns the upstream |

## Method

Executed as a **sequential agent pipeline** (one agent per plan batch, `/workflows`), each
running its stack's gates and stopping the chain on red. Sequential rather than parallel because
the batches form a dependency chain and share `rest/routes.py`; the value here is bounded
context per batch and a deterministic stop-on-red, not concurrency.

## APPEND-ONLY EXCEPTION — owner-approved 2026-08-06

Batch 6 widened the `IdentityAwareJobRunner` port with `cache: CachePolicy | None = None`. Two
test **doubles** had to accept the new parameter or stop implementing the port, which tripped
`run_gates.py`'s append-only check and stopped the pipeline — correctly, since sdlc rule 5 makes
that a Confidence-Gate decision.

**What changed — +10 lines, two files, zero assertions:**

| file | change |
|---|---|
| `tests/unit/_fakes.py` | import `CachePolicy`; `RecordingJobRunner.schedule` accepts `cache=None` |
| `tests/integration/test_e2e_compose_flow.py` | import `CachePolicy`; `MockRunnerJobRunner.schedule` accepts `cache=None` |

No assertion was altered, nothing was deleted, and no test's meaning changed. The implementing
agent explicitly declined the one change that *would* have crossed the line, and said so in the
code:

> *"deliberately NOT recorded onto `ScheduledRun`: that tuple is compared whole by an existing
> test, so widening it would change what an already-written assertion means."*

**Owner ruling:** accepted as port conformance rather than an assertion change.

**Why the gate could not decide this itself:** it is a `git diff --name-status` over the test
globs, so it cannot distinguish "changed what a test asserts" from "kept a double compiling
against a widened interface". Only the first is what rule 5 protects. Escalating rather than
guessing is the right behaviour for the gate; the cost is that port-widening work always stops
here.

**Everything else was green at the stop point** — `ruff`, `ruff format`, `pyright`,
`check_layering.py`, and the full suite with coverage.

## Acceptance

Plan §Verification, items 1-5. Notably:
- the Batch 2 property test — `cache` never carries a key other than `use-cache`
- a default run's egress body is byte-identical to today's
- `no-store` produces `opted_out`, **not** `unsupported_control`

## Known-inert

`max-age` degrades to opt-out until aigateway either accepts a bound or reports `Age`. Both
blockers verified on #507's branch; the honoured path is written and dormant.

## Batch 7 — two design notes the owner should see

**1. The read-back seam widened `packages/url4`, which the plan's Batch 7 bullet did not name.**
The connector holds an HTTP response; `SpanData` is built in `runner/executor.py` from
`url4.observe` events. The only channel between them is the observation stream, so the outcome
had to ride one. It was added to the EXISTING `ModelResponse` (`cache_status` / `cache_reason`,
both defaulted) rather than as a new event kind: the fact is per-round-trip exactly as
`finish_reason` is, both are read off the same response, and a second event would force a
consumer to correlate two streams to answer one question about one call. `ctx.report_response`
and the `ResponseSink` contract gained the same two optional kwargs — every existing caller
compiles and behaves unchanged (pinned by
`test_a_caller_that_reports_no_cache_outcome_still_works`).

**2. Age is read from `Age`, NOT from `Cache-Status; ttl=`.** Spec §7's mapping table says
`ttl=` → entry age; RFC 9211 §2.4 defines `ttl` as the *remaining freshness lifetime*, which is
the inverse quantity — and against a corpus whose rows never expire it has no meaning at all.
Reading it as an age would make a `max-age` decision on a number that means the opposite, the
day the gateway starts emitting it. `Age` (RFC 9111 §5.1) is "the sender's estimate of the time
since the response was generated", which is exactly what a bound is compared against, and is
already what spec §2.2 and §3.5's blocker table name. Written down here rather than silently.

**D11's shape, concretely.** `requires_revalidation` re-issues with an explicit opt-out ONLY for
a hit whose age is unknown or beyond the bound. A miss or a bypass was generated just now, so
its age is zero and every bound already holds — re-issuing there would double the cost of every
call a bounded run makes, for an answer that was never stale. The discarded response is read for
its headers and nothing else; its usage is never reported, or the turn would be billed twice.

## Outcome

- **Gates:** green on both stacks.

  ```
  url4        ✓ append-only ✓ ruff ✓ format ✓ pyright ✓ pytest --cov (97.45%, 1100 passed)
  url4-cloud  ✓ ruff ✓ format ✓ pyright ✓ check_layering ✓ pytest --cov (>80%)
              append-only: the owner-approved exception above
  ```

- **8 batches, 9 agents.** The pipeline stopped once (batch 6, append-only) exactly as designed;
  resumed after the owner ruling with batches 1-6 replayed from cache.

- **Agents overruled the plan twice, both correctly.**
  1. Batch 1 found the plan self-contradictory — Batch 1's bullet said `CachePolicy` has "exactly
     one field", Batch 3 said it carries a second (`max_age`). Batch 3 must win, since it lives in
     `apps/url4-cloud` and cannot add a field to a `packages/url4` model. Spec r8 corrected.
  2. Batch 1 placed protocol tests in `apps/url4-cloud/tests/` rather than `packages/url4/tests/`,
     because `packages/url4/pyproject.toml` omits `src/url4/streaming/*` from its own coverage with
     the comment *"its tests live with its only consumers"*. Repo convention over plan text; both
     gates run either way.

## The adversarial review changed the shipped behaviour

The 9th agent reviewed against the spec's acceptance criteria and returned 10 findings. Two were
substantive; the rest were doc staleness, fixed in spec r8.

**The one that mattered:** batch 7 implemented D11 as *participate-then-revalidate* — send the
request participating, and if the answer is a hit whose age cannot be proven, re-issue with an
explicit opt-out and discard the first body. Spec §3.5 said the shipped behaviour is *degrade to
opt-out*.

Since aigateway reports no age today, **every hit under a bound cost two gateway calls** — inside
`for _ in range(cfg.web_tool_max_iterations)`, so a four-iteration tool turn became eight calls,
multiplied again across a fan-out. And D6 deliberately invites intermediaries to inject
`Cache-Control`, making `max-age=0` from a browser reload an accidental trigger.

**Owner ruling: opt out upfront, per the spec.** Implemented in `rest/cache_policy.py` as
`_degrade_unhonourable_bound`, gated on a single `GATEWAY_REPORTS_AGE = False` constant.
`requires_revalidation` and its tests are kept, correct and unreachable — flipping that one flag
is the whole of D11's honouring half. Three batch-5 tests encoding the old behaviour were updated
(new files from this same unit, not prior tests).

## Deviations

1. **Process** — `UNFILED`, no Linear issue, no `docs/tasks/` mirror, no `Refs:` on commits.
   **Also a rule 8 breach**: this spans `packages/url4` + `apps/url4-cloud` and should be an epic
   with one sub-issue per landing. Executed as one unit only because MCP is unauthenticated.
2. **Append-only exception** — owner-approved, documented above.
3. **D11 shipped inert.** `max-age` degrades to opt-out; the honoured path is written and dormant.
4. **End-to-end verification not run.** Plan Verification step 3 needs a local aigateway built
   from #507. Every test here asserts against a mock transport, so the aigateway half of the
   contract is verified by reading `global_controls.py`, not by execution. **Green gates are not
   evidence this works end to end** — the plan says so and it remains true.
