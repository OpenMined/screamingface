---
ticket: UNFILED
stack: url4-cloud
status: done
started: 2026-08-05
finished: 2026-08-07
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

Both shipped as **PR #515, merged 2026-08-07 as `b113f41c`** (spec r9 / plan r7 — re-synced to
the merged #507). This branch was cut from `main` and carries code only, so the two PRs stayed
independent rather than stacked (the repo squash-merges; stacking has bitten before — see
`feedback_no_stacked_prs_squash`). The file sets were disjoint, so neither blocked the other.

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
blockers verified on #507's branch, and **re-verified on merged `main` 2026-08-07 — both still
stand**; the honoured path is written and dormant.

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
4. ~~**End-to-end verification not run.**~~ — **RUN 2026-08-07, ALL CHECKS PASSED.** See below.

## End-to-end verification — 2026-08-07, after #507 merged

The gap this ledger flagged is closed. #507 merged as `4f2a55ea`, which made the run possible
for the first time.

**What made it an E2E rather than a restatement of the same belief.** The request bodies were
not hand-written. They came out of url4-cloud's own production chain —
`parse_cache_control()` → `resolve()` → `policy_to_body_field()` — and were POSTed over real
HTTP to a real aigateway process running merged `main`. Had the reading of `global_controls.py`
been wrong, these assertions fail; the mock suite would not have moved.

**Harness** (scratchpad only, nothing tracked): a stub Ollama on `:11499` counting its own
calls, and aigateway on `:9155` with `AIGW_REQUEST_CACHE_ENABLED=true`,
`AIGATEWAY_AUTH_ENABLED=false`, `AIGW_OLLAMA_HOST` pointed at the stub, and an isolated sqlite
(a shared DB would let a previous run's rows decide this run's hit/miss). Schema built the way
`tests/conftest.py:184` does — `main.py` never creates tables; aerich does that out of band.

| # | check | result |
|---|---|---|
| 1 | default body clears the control gate (`provider_projection`, **not** a caller-attributed reason) | ✅ |
| 2 | `Cache-Control: no-store` → `bypass` / **`opted_out`** | ✅ |
| 2 | `Cache-Control: no-cache` → `bypass` / **`opted_out`** | ✅ |
| 3 | `max-age=60` and `max-age=0` → `bypass` / `opted_out` (D11 degrade) | ✅ |
| 4 | **negative control** — raw `{"no-store":true}`, `{"ttl":60}`, `{"use-cache":true,"s-maxage":30}` → `unsupported_control` | ✅ |
| 5 | a default run's egress body carries no `cache` key (spec §9.1) | ✅ |

**Check 4 is what makes check 2 mean anything.** If the gateway answered `opted_out` for
everything, check 2 would pass for the wrong reason. Sending the v1 vocabulary url4 deliberately
no longer emits, and getting a *different* reason back, proves the distinction is real and that
collapsing at the url4 edge buys something.

### The one thing still not proven end to end, and why

**`default → miss → hit` was not driven through url4.** Not a defect and not skipped for
convenience — it is unreachable locally:

- ollama inherits `CacheBypass(provider_projection)` from `ProviderPluginBase` and can never
  produce a hit. Its `parameters.py:83-90` states this and names the conformance test enforcing it.
- **anthropic and openrouter are the only providers implementing `global_cache_projection`**, and
  both PIN their `api_base` deliberately (openrouter D7, "request-local api_base beats every
  LiteLLM global/env fallback"). Neither is stubbable; a real miss needs a paid credential.

**Why the residual risk is small.** url4's default egress body is byte-identical to a pre-#518
body — it carries no `cache` field at all (check 5). So miss→hit is aigateway's own contract on a
body url4 does not touch, and aigateway's suite covers it directly. Verified passing on merged
`main` alongside this run:

```
test_repeated_bare_request_still_hits                        ← a BARE request repeated,
test_a_second_account_hits_the_first_accounts_stored_response   the exact shape url4 sends
test_a_different_profile_hits_the_same_global_entry
test_a_profile_that_cannot_authenticate_still_gets_a_hit
tests/unit/test_chat_global_cache_route.py                   ← 25 passed
```

### An ordering fact worth recording

`global_plan.build_global_cache_plan` evaluates: `cache_enabled` → `participates_in_global_cache`
→ **`controls.participate`** → projection. url4's opt-out is adjudicated at the third step, which
is why the *same* provider returns `opted_out` for an opt-out and `provider_projection` for a
default. Two different reasons from one provider is the evidence the control gate saw
participation — the E2E leans on that rather than on a header taken at face value.

`GATEWAY_REPORTS_AGE = False` re-verified on `main`: `git grep -E '"Age"|Cache-Status' --
'apps/aigateway/src/**/*.py'` returns nothing. D11's honouring half stays correctly dormant.
