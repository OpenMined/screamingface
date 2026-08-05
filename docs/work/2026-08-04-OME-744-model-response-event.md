---
ticket: OME-744
stack: url4
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-744 — a ModelResponse observation event for finish_reason and refusal

## Intent

Sub-issue of `OME-679`. A researcher running HealthBench must be able to tell a provider
**refusal** from a **bad answer**, or a safety-refusing model is scored as if it answered badly.
The concrete ask is to capture `finish_reason` per model call.

`url4.observe` is the engine's observation seam — a passive, pure-data event stream of
`RunStarted | NodeStarted | NodeFinished | Log | Usage | RunFinished`, plus a contextvar-bound
`UsageSink` that lets a world adapter with no `ExecutionContext` of its own attribute a fact to
the currently-resolving node's span. There is **no equivalent seam for response metadata**: a
url4 endpoint's contract is `-> str`, so a call's `finish_reason` and the provider `refusal`
field have nowhere to travel and are dropped at the adapter. This unit adds that seam. It does
not consume it — that is `OME-745` (`apps/url4-cloud`).

**Why a new event rather than fields on `Usage`:** `Usage` is token accounting, and url4-cloud's
executor derives `CostUsageData` from the span's usage tuple. Widening that tuple would push a
non-cost fact into cost accounting and change what every existing cost consumer sees.
`ObservationEvent` is a union and the module docstring frames the event set as the extension
point, so a new member is the sanctioned move.

## Planned changes

- `src/url4/observe.py` — `ModelResponse(span_id, finish_reason, refusal)` frozen/slots
  dataclass; add to the `ObservationEvent` union and `__all__`; `ResponseSink` type,
  `_response_sink` contextvar, `current_response_sink()` — mirroring `_usage_sink` /
  `current_usage_sink()`.
- `src/url4/dag/node.py` — `ExecutionContext.report_response(*, finish_reason, refusal)` beside
  `report_usage` (`:356-364`), same `if self._obs is not None: self._obs.emit(...)` shape.
- `src/url4/dag/executor.py` — bind `_response_sink.set(node_ctx.report_response)` in the same
  `try/finally` that already binds `_usage_sink` (`:197`, `:215`).
- `tests/unit/test_response_sink.py` — new, mirroring `tests/unit/test_usage_sink.py`.
- `tests/unit/test_observe.py` — append event-shape cases (append-only; no prior test touched).

No schema/model change, so S1 (migrations) does not apply.

### Scope moved out during DESIGN

`src/url4/streaming/protocol/signals.py` (`SpanData` gaining `gen_ai.response.finish_reasons`)
was planned here and **moved to `OME-745`**. `pyproject.toml` omits `src/url4/streaming/*` from
this package's coverage on purpose — streaming's tests "live with its only consumers, in
`apps/url4-cloud/tests` — that suite gates it via `--cov=url4.streaming`". A `SpanData` field
changed here could not be driven by a failing test in this stack, so keeping it would split a
change from its test across two PRs (TDD rule 4). It travels with its test into the url4-cloud
unit instead. Both issue descriptions updated.

## Test plan

Failing tests first:

- **Happy path** — a world handler reached from inside `resolve` calls
  `current_response_sink()(finish_reason="stop", refusal=None)` and a `ModelResponse` event
  lands on the observer, attributed to that node's span id.
- **Invariant — no cross-talk.** Two sibling nodes resolving concurrently each see their own
  binding; neither observes the other's sink. This is the property the contextvar-per-Task
  design exists to protect, and the reason it is bound around `resolve` only.
- **Boundary — outside a resolve** `current_response_sink()` is `None` (no observer attached,
  or called outside a node), and the adapter's null-safe path is exercised.
- **Boundary — binding does not leak** past a node's resolve, on both the success and the
  exception path (the `finally` reset).
- **Error path** — an observer that raises propagates, matching the documented contract that an
  embedder bug is loud rather than swallowed.

## Acceptance

- `ModelResponse` is emitted through the same span-attribution path as `Usage`.
- `current_response_sink()` is bound per `asyncio.Task` and reset in `finally`.
- No prior test modified.
- Gates green: `uv run .claude/scripts/run_gates.py url4` — ruff · ruff format --check ·
  pyright · `pytest --cov=url4 --cov-fail-under=95`.

## Outcome

- **Actual files:**

  | File | Planned? | What |
  |---|---|---|
  | `packages/url4/src/url4/observe.py` | yes | `ModelResponse`, union, `__all__`, `ResponseSink`, `_response_sink`, `current_response_sink()`, `_bind_node_sinks()` |
  | `packages/url4/src/url4/dag/node.py` | yes | `ExecutionContext.report_response()` |
  | `packages/url4/src/url4/dag/executor.py` | yes | binds both sinks via `_bind_node_sinks` |
  | `packages/url4/tests/unit/test_response_sink.py` | yes | 9 new tests |
  | `packages/url4/uv.lock` | **no** | see Deviations |
  | `packages/url4/tests/unit/test_observe.py` | planned, **not needed** | the new file covers the event shape; nothing to append without duplicating it |

- **Commits:** `604e070d` — feat(url4): add a ModelResponse observation event and its ctx-less
  sink (this ledger line follows in a second commit so the recorded sha is the real one).
- **Gates:** `run_gates.py url4` — **ALL GATES GREEN**. append-only check ✓ · ruff check ✓ ·
  ruff format --check ✓ · pyright ✓ (no `# type: ignore` added) · pytest `--cov=url4
  --cov-fail-under=95` ✓ — **1100 passed**, coverage **97%**, every new line covered
  (`observe.py` 98%, `dag/executor.py` 98%, `dag/node.py` 93% — all misses pre-existing).
- **Sibling stack verified:** widening `ObservationEvent` touches a public union that
  `apps/url4-cloud` consumes, so its suite was run too — **478 passed, 5 skipped**. Safe because
  no consumer matches the union exhaustively (`_Bridge.map` is an `isinstance` chain documented
  as "Any other event type produces nothing"); a `assert_never` grep across both packages is
  clean.

- **Deviations:**
  1. **`signals.py` moved to `OME-745`** (see "Scope moved out during DESIGN" above) — the
     `SpanData` field could not be TDD'd in this stack, so it travels with its test.
  2. **`_bind_node_sinks` landed in `observe.py`, not `executor.py`.** First written inline in
     `_eval`, which tripped the `too-many-statements` gate (27 > 26). Rather than weaken the
     gate, the binding was extracted — and then moved out of `executor.py` entirely, because the
     ContextVars are `observe.py`'s private state and the executor should not reach into them to
     scope a binding it does not own. It takes the two bound methods rather than an
     `ExecutionContext`, keeping `observe.py` the dependency-free leaf its docstring promises.
     Net effect: `executor.py` **shrank** 496 → 492 lines and no longer imports either private
     ContextVar.
  3. **`uv.lock` carries an unrelated one-line correction.** `pyproject.toml:107` pins
     `graphviz>=0.21` but the committed lock recorded `>=0.20` — the lock was stale on `main` and
     `uv run` regenerated the line deterministically. Kept rather than reverted: CI runs plain
     `uv sync` (not `--frozen`), so the drift was silent rather than failing, and reverting only
     means it returns on the next `uv run`.
  4. **Card gap surfaced (not fixed here):** `.claude/sdlc.local.md` has body sections for
     `aigateway`, `aigateway-ui` and `scoreboard`, but **none for `url4` or `url4-cloud`**, so
     the skill's "read the card BODY for the active stack" step had nothing to bind. Gate
     coverage itself is complete (format · lint · typecheck · test · coverage). Worth a
     card-repair item alongside `OME-743`.
