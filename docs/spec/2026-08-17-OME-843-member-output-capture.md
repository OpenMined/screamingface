# OME-843 — Capture member and synthesis output text in benchmark case artifacts

Status: DRAFT — pending owner approval. Sub-issue of OME-784; client fold-in of
usage/timing stays OME-699; stats export stays OME-842.

## Problem

A Fusion case artifact (`CaseResult`, `apps/url4-cloud/src/url4_cloud/benchmarks/contract.py`)
keeps only the fused answer. Member answers exist transiently in the engine —
`_gather()` binds them (`packages/url4/src/url4/dag/nodes.py:588-610`) and
`ProcessNode.resolve` discards them after substitution (`nodes.py:706-720`); the model
connector holds each terminal output + finish_reason (`runner/connector.py:409-418`) —
but nothing persists them. Contribution analysis (draco 2026-08-17: breadth 0.43 vs
presentation 0.87, cause unknowable) requires paid re-runs.

## Non-solutions (ruled out by recon)

- **`url4.observe` telemetry**: the nested candidate run is unobserved
  (`packages/url4/src/url4/peer/server.py:374-382` builds an `ExecutionContext` with no
  observer; `dag/executor.py:177-181` skips sink binding). No per-member spans exist, and
  `SpanData` carries no output text. Fixing observation is a url4-package unit of its own —
  out of this slice (rule: url4 core changes get their own ticket).
- **Manifest/protocol change**: the benchmark protocol expression is contractually frozen
  (`tests/unit/test_benchmark_protocol.py`); nothing here may alter it.

## Design — widen the CandidateInvocation envelope (the `execution` precedent)

The frozen protocol moves `$candidate_invocation` as opaque text and
`/benchmarks/case-execution` is a pure re-encoder, so the envelope can grow without any
protocol change — the exact path OME-796 used for `CorrectiveExecution`
(`contract.py:177-185` → `case_records.py:53-55` → `draco/case_results.py`).

### Engine (url4-cloud) — the OME-843 unit

1. **Recorder**: a task-local `capture_operation_outputs()` beside
   `model_outcomes.py`, started in `benchmarks/invocation.py` alongside
   `capture_model_outcomes`. The connector contributes `(model_route, output_text,
   finish_reason)` at the same point it reports outcomes today
   (`runner/connector.py:417`).
2. **Binding attribution**: the engine derives the operation identity by parsing the
   candidate expression it already holds (`candidate_adapter.py:30-50`) with
   `url4.build` — source name `model_N`/`synthesis_N` → `op_<binding>`, the same total
   function the client uses (`_evaluation/candidate.py:209-211`). Attribution maps the
   **resolved request fingerprint (model route + params)** → binding, so two members on
   the same model with different params (e.g. temperature) stay distinct. Residual
   ambiguity — byte-identical member calls — resolves as: identical recorded outputs →
   attribute that text to every matching binding (no information invented); differing
   outputs → `output: null` for the contested bindings (never a positional guess).
   Solo candidates record nothing (no member section invented). [Owner-decided
   2026-08-17: fingerprint keying + this ambiguity rule; synthesis output recorded.]
3. **Envelope**: `CandidateInvocation` gains an optional `operations` list —
   `{operation_id, output, finish_reason}` per attributed operation — threaded
   `encode/decode_candidate_invocation` (`contract.py`) → `CandidateAnswer`
   (`evaluation.py`) → `bind_case_record` (`case_records.py`) → the four
   `*_case_result` builders (`aggregation.py`) → `CaseResult.operations` (optional,
   `None` for solos/absent). Deterministic ordering: candidate expression source order.
4. **Bounds**: values pass the existing `_is_json_value` validation; outputs are
   ≤ max_tokens-sized by construction. The 1 MiB `result_cap`
   (`runner/executor.py:327-344`) is acknowledged: N members × full text per case can
   approach it on large runs — if the cap trips, capture degrades to `null` outputs
   rather than corrupting the artifact (same "never fabricate, never break the run"
   stance as the rest of the contract).

### Client (py-screamingface) — lockstep prerequisite, separate sub-issue

`_case_result` hard-rejects unknown case keys (`_evaluation/results.py:355-366`, pinned
by `test_case_outcome_decoding.py`). Therefore a **client PR ships first**: add
`operations` to the decoder's `optional={...}` set and surface it on
`case_result.CaseResult` / `to_dict()`. Until the engine emits it, the field is absent —
no behavior change. Engine PR follows once the tolerant SDK is merged.

Ship order is a hard constraint: engine-first would make new engines break existing SDKs.

## Acceptance

- Fusion run: each case artifact carries `operations` with the member and synthesis
  outputs + finish_reasons, keyed by `op_<binding>`, in expression source order.
- Solo run: artifact byte-identical to today (no `operations` key).
- Ambiguous route attribution → `output: null` for the contested operations, run
  unaffected.
- Old SDK + old engine, new SDK + old engine, new SDK + new engine all green;
  new engine + old SDK is prevented by ship order.
- Contract tests extended, protocol-expression test untouched.

## Open questions (owner)

1. RESOLVED 2026-08-17: attribution keys on the resolved request fingerprint
   (route + params); byte-identical calls attribute only identical outputs, else null.
2. RESOLVED 2026-08-17: synthesis output is recorded.
3. Client sub-issue: filed as a second sub-issue of OME-784 (py-screamingface,
   ships first — SDK must tolerate the optional `operations` key before any engine
   emits it).
