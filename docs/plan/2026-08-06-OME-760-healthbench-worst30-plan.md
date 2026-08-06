---
title: OME-760 — HealthBench worst-30% implementation plan
status: accepted
created: 2026-08-06
ticket: OME-760
related:
  - docs/spec/2026-08-06-OME-760-healthbench-worst30-spec.md
  - docs/work/2026-08-06-OME-760-healthbench-worst30-engine-exam.md
---

# Implementation plan — healthbench/worst30 + healthbench/smoke

Base: `integration/keelan-all-changes-20260806`. Template: `benchmarks/draco/` (current
shape: definition → runtime `_install_protocol` per variant over shared assets → tasks /
verdict / case_evaluation / scoring / aggregate). HealthBench is draco with: rubric
items for criteria, GPT-5.4 for Gemini, 1 judge pass, pre-rendered grader prompt
(template holes filled engine-side), chat-envelope inputs, no retrieval, unclipped mean.

## Files (apps/url4-cloud/src/url4_cloud/benchmarks/healthbench/)

1. `prompts.py` — `GRADER_TEMPLATE` verbatim from simple-evals (sha-pinned by a test);
   `render_rubric_item(points, criterion) -> "[7] …"`; `build_grader_prompt(question,
   answer, rubric_item) -> str` (`.replace()` holes; transcript + `\n\nassistant: …`).
2. `subset.py` — `WORST30_HF_IDS: tuple[str, ...]` (157, frozen, provenance comment),
   `SMOKE_HF_ID` (1 id chosen from the subset), `subset_sha()`.
3. `prepare.py` — build-time: download pinned HF rev → for each of 525 rows emit
   `cases.json` `[{id, input: chat_input(messages)}]` (sequential case ids, HF id kept
   in private spec) + `rubrics/<case_id>.json` `{hf_id, items: [{rubric_id, criterion,
   points, tags}]}`. Asserts: every `WORST30_HF_IDS` present · all points int ·
   ≥1 positive item per row. Maps HF ids → case ids and emits `case_ids.json`
   (private) so definition constants can pin `WORST30_CASE_IDS` deterministically
   (ordering rule: cases.json ordered by HF file order; ids 1..525).
4. `definition.py` — pins + revisions (worst30 revision hashes: dataset, HF rev,
   protocol id, subset sha, judge model, judge params, GRADER_TEMPLATE, scoring id,
   preparer version; smoke derives from worst30 revision), per-variant routes
   `/benchmarks/healthbench/worst30/<rev>/{cases,rubric-tasks,rubric-verdict,
   case-evaluation,aggregate}` — id contains `/` like `draco/lite`; `_build_protocol
   (case_count, routes…)`: cases iterate → `/rubric-tasks(candidate($item.input,
   web_search=False))!'$item.id'` → per-item inner iterate → judge call
   `RelExpr(path="/openrouter/openai/gpt-5.4", context="$item.grader_prompt",
   intent=Text(""), params=(web_search false, max_tokens 4096))` wrapped by
   `/rubric-verdict(…)!'binding_key'` → `/case-evaluation($…)!'$item.id'` →
   `/aggregate($rows)`. `HEALTHBENCH_WORST30 = Benchmark(id="healthbench/worst30",
   variant="worst30", case_ids=WORST30_CASE_IDS, …)`, `HEALTHBENCH_SMOKE` likewise.
   NOTE: empty judge intent — Runner maps intent→system message; official sends none.
   Retry: `;retry=2` on the judge source (fresh samples at provider-default temp).
5. `verdict.py` — parse judge reply (fence-strip, json.loads, strict-bool
   `criteria_met`, optional `explanation`); `binding_key(intent)` `case:rubric`;
   handler binds ids engine-side; invalid after retries → ValueError → row fails
   (collect).
6. `scoring.py` — `case_score(items, verdicts) -> float | None` (achieved/Σpositive,
   unclamped, judged-items-only guard); `unclipped_mean`, `sample_stdev` (n−1),
   `verdict_coverage`.
7. `aggregate.py` — reducer over collected rows: decode case evaluations; an
   `{"error": …}` row or missing rubric asset → FAILED case result appended (B1 rule);
   result `{schema: candidate-result…, score: unclipped mean, metrics: {coverage,
   stdev, judge_parse_failures, failed_cases}, case_results: […]}` mirroring draco's
   result shape for SDK compatibility.
8. `runtime.py` — `install(node, root)`: per-variant `_install_protocol` (worst30 +
   smoke) over shared assets; `node.data(cases_route)` filtered by case_ids;
   `/rubric-tasks` handler: decode candidate invocation → load rubric → build rows
   `[{case_id, rubric_id, grader_prompt, case_record?}]`; install-time asset preflight
   (S-DR3): cases.json + rubrics dir exist and subset ids resolvable — loud
   ResolutionError otherwise.
9. `__init__.py` + registry entries in `benchmarks/__init__.py`.

## Tests (apps/url4-cloud/tests/unit/)

- `test_healthbench_definition.py` — registry entries, resource shape/revision
  stability, case_ids wiring, route uniqueness, expression renders + size measured
  (S-RT1), judge call has empty intent + web_search=false, template sha pin.
- `test_healthbench_prepare.py` — envelope shape, rubric privacy, subset-id freeze
  (missing id → loud), int points, positive-item invariant (fixture rows).
- `test_healthbench_verdict.py` — fenced/bare/malformed/prose replies, strict bool,
  binding key, id binding engine-side.
- `test_healthbench_scoring.py` — reference-fixture parity (values from simple-evals
  `healthbench_eval_test.py`), negatives subtract, unclamped row, unclipped mean,
  sample stdev, coverage.
- `test_healthbench_aggregate.py` — failed/missing-rubric case reaches results (B1),
  error rows counted, coverage gates validity flag.
- `test_healthbench_runtime.py` — install preflight failures loud; rubric-tasks
  handler happy path + grader prompt byte-check against a hand-built reference string.

## Gates

`uv run python3 ../../.claude/scripts/run_gates.py url4-cloud` (or repo equivalent) —
ruff, format, pyright, layering, pytest. Free only; NO live model calls; NO commits
(owner reviews working tree first).

## Order

prompts → subset → prepare → definition → verdict → scoring → aggregate → runtime →
registry → tests alongside each (RED first per sdlc-python) → gates → ledger outcome.
