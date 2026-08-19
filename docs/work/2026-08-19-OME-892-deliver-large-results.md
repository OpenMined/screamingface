---
ticket: OME-892
stack: screamingface-engine + screamingface
status: in_progress
started: 2026-08-19
finished:
---

# OME-892 — Deliver large Evaluation results in full instead of cutting them off at 1 MiB

## Intent

The Engine truncates any Candidate Result over 1 MiB mid-JSON, appends `…[truncated]`, and
still terminates the run `succeeded`; the SDK then fails to decode the only copy of the
result (GitHub #642, $6.54 / 1h11m lost). This unit replaces truncate-and-lie with the
industry-standard signaling/bulk split: results ≤ 1 MiB stay inline in the terminal event;
larger results are written to a content-addressed file on the Engine's disk and the terminal
event carries a claim ticket `{artifact_id, size_bytes, sha256}` which the SDK redeems over
HTTP with size+digest verification; results over an env-configurable hard cap (default
1 GiB) terminate `failed` with `result_too_large`. The truncation code path is deleted —
no successful terminal event can carry a mangled body, by construction.

## Planned changes

Engine (`apps/screamingface-engine`):
- `src/screamingface_engine/runner/executor.py` — `build_result()` becomes the 3-way fork
  (inline / artifact spill / `result_too_large`); truncation path + `_TRUNCATION_MARKER`
  deleted; executor gains artifact-store + caps wiring.
- ResultData/Completed model (wherever `ResultData` is defined) — optional
  `artifact: {id, size_bytes, sha256} | null`, exclusive with `body`.
- New artifact store module (content-addressed write, delete-on-fetch, TTL sweep at startup).
- `rest/` — new `GET /artifacts/{id}` route via Starlette `FileResponse`, behind the same
  auth guard as existing routes.
- Env config: inline threshold (default 1 MiB), hard cap (default 1 GiB), artifacts dir.

SDK (`packages/screamingface`):
- Wire/event decode — accept the additive `artifact` field on the terminal result.
- `src/screamingface/_engine/transport.py` — artifact fetch (httpx streaming GET, existing
  auth) with byte-count + sha256 verification before parse.
- `src/screamingface/_evaluation/results.py` — three terminal shapes: inline body /
  artifact ref / legacy `…[truncated]` marker → actionable truncation error naming N bytes.
- Named errors: integrity mismatch; truncated-by-legacy-engine.

## Test plan

Engine:
- `build_result` under cap → inline body, artifact None (byte-identical to today).
- over inline threshold → file exists at `artifacts/<sha256>`, event has ref (id/size/sha),
  body None; file bytes == original.
- over hard cap → run terminates `failed` with `result_too_large`, message carries actual
  and allowed bytes; no file written.
- exactly at threshold → inline (boundary).
- artifact route: GET serves bytes + deletes after success; unknown id → 404; TTL sweep
  removes stale files at startup, keeps fresh ones.
- INVARIANT: no code path emits a body containing `…[truncated]`.

SDK:
- terminal event with inline body → Report as today.
- with artifact ref → fetch, verify, Report identical to inline case.
- wrong sha256 / short body → named integrity error, no Report.
- legacy `…[truncated]` body → error naming truncation + received byte count, not
  "must be JSON".
- deterministic + network-free (in-process ASGI/served fixture); no paid calls.

## Acceptance

- A >1 MiB synthetic result flows Engine→SDK through the real streaming lifecycle into a
  valid Report (network-free test).
- Truncation code deleted; hard-cap breach reports `result_too_large` with both numbers.
- Both caps env-configurable; small-result path byte-identical to today.
- All gates green for `screamingface-engine` and `screamingface` stacks.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
  - `packages/url4/src/url4/streaming/protocol/signals.py` — `ResultArtifact` model;
    `ResultData` body|artifact XOR (+ `tests/unit/test_result_signal.py`, 11 tests)
  - `apps/screamingface-engine/src/screamingface_engine/artifacts.py` — new
    `ArtifactStore` (content-addressed write/serve/delete/sweep) (+
    `tests/unit/test_artifact_store.py`, 7 tests)
  - `.../runner/executor.py` — `build_result` 3-way fork; truncation path +
    `_TRUNCATION_MARKER` deleted; `hard_cap`/`artifact_store` ctor params
  - `.../runner/main.py` — `result_delivery_from_env` + executor wiring
  - `.../job_env.py` — `ARTIFACTS_DIR`, `RESULT_INLINE_CAP_B`, `RESULT_HARD_CAP_B` (+
    defaults) in `DEPLOY_TIME`
  - `.../config.py` — `Settings.artifacts_dir`, `Settings.artifact_ttl_s`
  - `.../rest/artifacts.py` — new `GET /artifacts/{id}` (auth-guarded, FileResponse,
    delete-on-fetch) (+ `tests/unit/test_rest_artifacts.py`, 7 tests)
  - `.../rest/routes.py` — `_result_response` serves artifact results on the sync GET path
  - `.../app.py` — store on app.state, artifact router mounted, `_install_artifact_sweeper`
    (TTL sweep at startup + hourly-default periodic asyncio task, cancelled at shutdown;
    owner decision 2026-08-19: hosted pods live for weeks, startup-only pools orphans);
    `Settings.artifact_sweep_interval_s` in config.py
  - `tests/integration/test_local_spine.py` — 2 end-to-end tests: real executor spills,
    WS carries claim ticket, redemption returns every byte, sync GET path whole
  - `packages/screamingface/src/screamingface/_core/ports.py` — `_ResultArtifact`;
    `_RunOutcome.artifact`, `result_body: str | None`
  - `.../_engine/contract.py` — artifact decode (`_artifact_reference`, strict hex/size)
  - `.../_engine/transport.py` — `_materialize_sync/_materialize_async`: streaming fetch +
    size/sha256 verify before anything decodes; stale `_MAX_FRAME_BYTES` comment updated
  - `.../_evaluation/results.py` — `_decoded_result_body`: legacy `…[truncated]` marker →
    named `result_truncated` error with byte count; None-body guard
  - `tests/protocol_server.py` — `artifact_result` mode + `/artifacts/` handler +
    corruption/missing seams; `tests/test_transport_artifact_fetch.py` (6),
    `tests/test_engine_contract.py` (+3), `tests/test_results_truncation_marker.py` (3)
- **Commits:**
  - 63cbf96f feat(url4): result frames carry an inline body or an artifact claim ticket
  - 81a2f664 feat(screamingface-engine): content-addressed artifact store for spilled results
  - dbdb8386 feat(screamingface-engine): spill or refuse oversized results instead of truncating
  - b4a7823d feat(screamingface-engine): serve spilled results over REST with TTL-only cleanup
  - 412d8439 feat(py-screamingface): redeem and verify artifact results in the transport
  - 013314a3 fix(py-screamingface): name legacy Engine truncation instead of 'must be JSON'
- **Gates:** ALL GATES GREEN × 3 stacks — url4 (1168 tests, cov ≥95), screamingface-engine
  (1763 tests incl. 2 new integration, cov ≥80), screamingface (929 tests, cov ≥95 +
  notebooks + build + distribution)
- **Deviations:**
  1. **Third stack touched: `packages/url4`** — `ResultData` is defined there, not in the
     engine; the ticket's two landing labels under-count. Additive change only.
  2. **Prior tests changed** (gates run `--skip-append-only` for engine + SDK):
     `test_over_cap_result_is_truncated_with_marker` REPLACED by 4 fork tests — it
     asserted the exact behavior the approved ticket deletes; type-narrowing asserts
     added to 4 prior assertions (`str | None` ripple); `protocol_server` double gained
     an additive mode. No prior assertion was weakened.
  3. **k8s backend gap (pre-agreed flag):** runner Job pod and App pod have separate
     disks; `URL4_CLOUD_ARTIFACTS_DIR` must name a shared volume there — chart work, not
     in this unit (AIDEV-NOTE in job_env.py). Local mode (the bug's repro environment)
     is complete end-to-end.
  4. **Multi-candidate "Partial Report" acceptance criterion not implementable as
     written:** the SDK has no partial-report path — any candidate failure aborts the
     whole evaluation (`_evaluation/runner.py` cancel + re-raise). That is pre-existing
     behavior this unit neither caused nor changed; the criterion needs its own ticket.
  5. `uv sync --all-extras` surfaced a pyright error CI never sees (CI syncs only
     `--extra notebook`); env re-pinned to CI's extras.

## Review-fix round (2026-08-19, same unit — 10 verified findings, all addressed)

Owner-run review returned 10 confirmed findings; all fixed before commit:

1+2. **Delete-on-fetch removed entirely (design change).** Content-addressed dedup means
   one file can back many tickets, and Starlette's BackgroundTask fires whether or not the
   client got the bytes (a Range request consumed the parcel). Artifacts now die by TTL
   ONLY; fetching never deletes — refetch/resume/dedup all safe. Route, tests, spine test
   and notebook updated to pin the new contract.
3. Artifact fetch retries transient network failures (3 attempts, backoff); HTTP problems
   and integrity mismatches stay no-retry.
4. Client streams against the ticket's `size_bytes` bound — never buffers past it.
5. Artifact 404 detail now names the multi-pod shared-volume cause alongside TTL expiry.
6. Hard cap checked FIRST in `build_result` — inverted knobs can no longer bypass it into
   an oversized WS frame.
7. Sweep tolerates files vanishing mid-scan, collects `.tmp` write leftovers, and the
   periodic loop survives sweep exceptions (logs, keeps cadence).
8. Claim-ticket redemption moved OUTSIDE the WS socket scope in both transports — a fetch
   failure can no longer trip the stop-on-interrupt arm on a closed socket.
9. Inline result frames byte-identical again: `artifact` serialized only when present
   (`Field(exclude_if=…)`; a wrap-serializer was rejected — it erased the JSON schema and
   failed the engine's OpenAPI docs gate).
10. Result encoded ONCE (`write_bytes`) and `build_result` runs via `asyncio.to_thread`,
   so a gigabyte spill cannot stall heartbeats.
   Also: env caps renamed `_B` → `_BYTES` (owner call — bits/bytes ambiguity), executor
   defaults now reference `job_env` constants, `getattr` wiring fallbacks removed, legacy
   marker error states evidence rather than certainty. Gates re-run green ×3 stacks.
