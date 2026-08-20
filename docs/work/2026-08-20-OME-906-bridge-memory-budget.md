---
ticket: OME-906
stack: screamingface-engine
status: planned
started: 2026-08-20
finished:
---

# OME-906 — Bound the event bridge by memory, not by event count

## Intent

`_Bridge` raises `BridgeOverflowError` at 8192 buffered events and blames the consumer. The
consumer is not the cause. Measurement shows the peak backlog is flat across a 100x range of
publish latency, and that the buffer holds one uninterrupted producer burst whose size scales
with DAG width — because `url4/dag/executor.py:182` emits `NodeStarted` before it awaits and
`:186` fans out over `node.deps` with an unbounded `asyncio.gather`.

So the cap is a ceiling on DAG width. A 100-Case DRACO Fusion is legitimately about 3500
nodes wide and sits at the limit. The quantity defended is 2.1 MB, in a process that accepts
a 1 GiB result.

This unit replaces the count bound with a memory budget and makes the error say what
happened.

## Planned changes

- `apps/screamingface-engine/src/screamingface_engine/runner/executor.py` — derive the hard
  cap from `BRIDGE_MEMORY_BUDGET_BYTES`; add a drained counter beside the high-water mark;
  rewrite the overflow message to distinguish a legitimate burst from a stuck consumer.
- `apps/screamingface-engine/src/screamingface_engine/job_env.py` — read the budget from the
  environment, with the existing result caps as the model.
- Tests in `apps/screamingface-engine/tests/`.

## Test plan

RED first:

- A DAG whose single burst exceeds 8192 events completes through the real bridge and the real
  publish loop. This test fails today.
- A producer that never stops fails at the budget, not before it.
- A consumer that never drains fails the run, with a message that says the consumer is stuck.
- A burst over budget fails with a message naming the width and the budget.
- `Log` is still the only event kind ever dropped.
- The budget is read from the environment and falls back to the default.

## Acceptance

The six criteria in `docs/spec/2026-08-20-OME-906-bridge-memory-budget.md`.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:**
