# Plan: capture & view per-run logs for Eval Studio runs

**Status:** plan for review (not yet ticketed/implemented)
**Goal:** Let a user open an Eval Studio run and see the **execution-process logs** for that run — in a read-only popup the same shape as the url4/code editor popup (a "logs" icon in the run-detail header).

This doc covers **how to capture** the logs (the open question). The popup UI is the easy part and is specified at the end.

## Architecture facts (from a full trace of the run path)

- A run is tagged with `X-SF-Run-Id`; `routes.py` (`url4_executor`) puts it in the eval env as `__run_id__` and emits `HOOK_RUN_STARTED/FINISHED/FAILED` (`routes.py:100-139`). `run_id` is reachable at **any** node via `env.lookup("__run_id__")` (`scope.py`).
- **Python logging** is global with no run context — `logging.basicConfig(...)` once in `core/app.py:105`, format `"%(levelname)s:     %(name)s - %(message)s"`, to stdout. Loggers exist throughout the url4 path (`url4_resolve.py:250` "fetching %s", ensemble, python_runner, etc.) but **no run_id is attached**.
- **Tracing** (`plugins/tracing/`) exports OTLP spans to Phoenix (`localhost:6006`), fire-and-forget; **run_id is not on spans**, and there's no server-side query-by-run_id. → not a viable capture sink without significant work.
- **Collected errors** (`ensemble.py:239-250`) are counted and surfaced only as the `X-SF-Collected-Errors` header count (`routes.py:170-172`); per-row error objects live in the response JSON, **not keyed/persisted per run**.
- **Already persisted per run:** `EvalRun` (status/error/accuracy/totals) and `EvalQuestion.raw_output` + `.error` per checked question (`eval_runs/`). This is real per-run data but only for `check_correct` questions — it misses the surrounding execution log (dataset fetch, per-source dispatch, fan-out errors).
- **Desktop** streams the server's whole stdout as untagged `server:log` events (`server-process.ts:171-264`) — not separable per run.

## Candidate capture strategies (and verdict)

| # | Strategy | Choke point | Persists? | Captures | Effort | Verdict |
|---|---|---|---|---|---|---|
| A | **contextvar + logging filter/handler** — set `run_id` contextvar at run entry; a handler tags every LogRecord and buffers it per run_id | `routes.py:105` | in-mem → flush on finish | all server log lines during the run | Low–Med | **Recommended core** |
| B | new **node-level lifecycle hooks** (`eval.node.started/finished/failed`) at the dispatch choke points | `url4_resolve.py:_dispatch_backend_call:133`, `ensemble.py:226/372` | new `EvalLog` table | structured per-node timeline | Med | Phase 2 (structured) |
| C | response trailing metadata / headers | `routes.py:170` | none | per-run summary only | Low | rejected (no persistence, header limits) |
| D | expose existing `EvalQuestion.raw_output`/`error` | `eval_runs/plugin.py` | already | per-question model output | Very low | **Fold in** (free) |
| E | query Phoenix spans by run_id | `routes.py:107` | Phoenix | span tree | Med–High | rejected (Phoenix may drop traces; needs OTLP client + run_id on spans) |

## Recommended design: **A (capture log lines per run) + D (merge question outputs)**

This gives the user the actual *process* log (what the run did + errors) with minimal new infra, keyed by run_id and persisted for later viewing.

### Server (`apps/server`)
1. **Run-id context** — module-level `run_id_var: ContextVar[str|None]` (new `plugins/eval_runs/_run_context.py`). Set it in `url4_executor` `routes.py` right where `__run_id__` is put in env (`:105`), reset in a `finally`. Contextvars are async-safe and propagate across the `asyncio.gather` fan-out, so child tasks inherit the run_id.
   - *Dependency-direction note:* the context var belongs to `eval_runs` (the capture owner); `url4_executor` already imports `eval_runs` hook payloads, so importing the contextvar setter is consistent. Alternatively expose it via `app.state` to avoid the import. Decide in impl.
2. **Capturing log handler** — a `logging.Handler` added in `eval_runs` setup that, when `run_id_var` is set, appends the formatted record to a bounded per-run buffer (`dict[run_id, deque(maxlen=2000)]`). Cheap, in-memory, no I/O on the hot path.
3. **Persist on finish** — in `_on_run_finished` / `_on_run_failed`, join the buffer (+ collected-error objects if we thread them through) into a text blob and store it. Storage options:
   - **(a) `EvalRun.log` TextField** (additive column, same idempotent-migration pattern as `favorite` — SF-253). Simplest; one row per run.
   - (b) new `EvalRunLog` table (rows). More structured, supports B later.
   - → **Recommend (a)** now; migrate to a table only if/when node-level (B) lands.
   Drop the in-mem buffer for that run_id after persisting.
4. **Endpoint** — `GET /eval_runs/{id}/logs` → `{ log: string }` (the persisted text). For a still-running run, return the live buffer so the popup can poll. Merge in **(D)** each `EvalQuestion`'s `raw_output`/`error` as labelled sections so model outputs show too.
5. **Capture collected errors (small add):** thread the per-row error objects (`ensemble.py:239-250`) into the buffer (or onto the run) so fan-out failures appear in the log, not just a count.

### Desktop (`apps/desktop`)
6. `use-eval-run-logs.ts` — fetches `GET /eval_runs/{id}/logs`; polls while the run is `running` (mirrors `useEvalRunDetail`).
7. **Logs icon** in `EvalRunDetail` header (next to Delete/Edit) → opens **`CodeEditorPopup`** read-only (`language="log"` or plaintext, `inset="10%"`, no Save/Re-run — just Close), showing the fetched log text. Reuses the exact popup shape the user asked for. Lazy-loaded like the editor.

## Tradeoffs / notes
- A captures **everything logged at INFO+** during the run — rich, but only as good as existing `logger.*` calls. Pairs well with adding a few targeted `logger.info` lines at dispatch points later (or B for structure).
- In-mem buffer is per-process; fine for the local single-user server. Persisted text survives restarts for viewing.
- No PII concern beyond what's already in the expression/outputs (local app).

## Out of scope
- Full distributed tracing UI (that's Phoenix).
- Streaming logs line-by-line over IPC (poll the endpoint instead).
- Node-level structured timeline (B) — note as a clear Phase 2.

## Open questions for the user
1. Is "logs" = **server execution log lines** for the run (A, recommended), or a **structured per-node timeline** (B), or just **per-question model outputs** (D)? (A+D covers the first and third.)
2. Persist as a **text blob on EvalRun** (a) vs a **log table** (b)? (Recommend (a).)
3. Should the logs popup **poll live** while a run is running, or only show logs once finished?
