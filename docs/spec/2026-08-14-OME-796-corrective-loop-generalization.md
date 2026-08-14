# Spec — OME-796: benchmark-independent corrective loop (check-surface port + client recipes)

Status: approved (Khoa, 2026-08-14) · Epic OME-796 (sub-issues OME-827 engine, OME-828 client)
· Design narrative + diagrams: OME-796 issue body ("Design resolution 2026-08-14").

## What

The LANL corrective protocol (parallel member drafts → per-draft check → earliest passing
answer submitted VERBATIM → judge coaches failures → retry ≤ `max_rounds`) becomes a
benchmark-independent capability:

1. **Engine**: loop machinery moves from `benchmarks/ifeval/` to generic
   `benchmarks/ensemble/`, parameterized by a **check-surface port**.
2. **Manifest**: `screamingface.benchmark.v1` gains an optional block
   `"check_surface": {"check_route": str, "feedback_intent": str, "expected_check_cost": "free"|"paid"}`.
   Absent block = benchmark cannot check mid-run.
3. **Client**: `sf.CorrectiveLoop(members, judge=..., max_rounds=3)` and
   `sf.SelfCorrective(model, max_rounds=3)` compile the ENTIRE loop client-side into ONE
   whole-`$candidate` url4 expression, substituting the manifest's check routes (never
   hardcoded paths). The one-hole linker contract is untouched.
4. **Registry variants retired**: `ifeval/lanl-ensemble` and `ifeval/self-corrective` are
   deleted (they are protocols wearing benchmark costumes); canonical `ifeval` keeps its
   check/feedback endpoints — they ARE the port implementation.
5. **Adapters**: IFEval (`deterministic_check`, free), DRACO (`rubric_check` shape:
   1 judge pass over the case rubric, paid), HealthBench (second rubric customer → extract
   `rubric_check` as a registry component; adapter = named args only).

## Contracts

- **Check-surface port** (per benchmark, behind its adapter):
  `check({input, invocation}) → {schema, passed: bool, feedback: sanitized text,
  satisfaction: float ∈ [0,1], answer: str, invocation: str}`.
  `invocation` is the exact refusal-safe Candidate Invocation envelope; the adapter grades
  the same `answer` that selection can later publish, and malformed mismatches fail closed.
  - `passed` typed bool at the port; graded benchmarks convert behind the adapter.
  - `feedback` sanitized by contract (sealed-envelope rule; IFEval #528 precedent — every
    adapter ships a leak test). DRACO: axis-level only. HealthBench: theme-level only.
  - `satisfaction` ranks never-passing drafts (hoists `_strict_satisfaction` benchmark-side).
  - The `"PASSED"` string sentinel is retired for the structured field (flow-contract
    revision re-hash accepted, pre-launch).
- **Pass criteria are named + revisioned** scoring semantics: `draco-pass.v1` =
  normalized weighted rubric score (clipped [0,1]) ≥ 0.7; satisfaction = same score.
  Proposed by us; reviewed in-PR (Keelan), not pre-decided.
- **Client interface**: one role arg `judge=` (selector/coach are internal roles enforced by
  prompts/gates; a split is a future backward-compatible addition). No `stop_when=`.
  `max_rounds` is a cost cap. Root-only recipes (inside Pipeline/Fusion the benchmark is
  undefined → compile-time rejection). Member floor ≥ 2 structural; LANL's 2–4 is a
  variant parameter, not inherited. Generic member labels are unbounded lowercase base-26
  (`a`…`z`, `aa`…), while actual execution limits remain Engine capabilities.
- **Preflight (fail-before-spend)**: loop recipe + manifest without `check_surface` →
  `PlanningError("benchmark does not support mid-run checking", permanent)` before any
  paid call; `expected_check_cost: "paid"` surfaces expected check spend
  (rounds × members × 1 judge pass).
- **Identity**: `screamingface.recipe.v1` topology (`_RecipeTopology`) extended with
  kinds `corrective_loop` / `self_corrective` carrying members, judge, `max_rounds`, and
  the check-surface revision compiled against.
- **Reporting**: per-case `stop_reason` + `rounds_executed` (generalizing
  `pass_attempt`/`selected_attempt`).
- **Failure semantics kept from shipped precedents**: never-passes → last attempt scored;
  tie → judge label pick; tie-of-tie → first member (deterministic — reproducibility);
  judge/member failure → case fallback, coverage-declared.
- **MCQ benchmarks get NO check surface** (pass/fail feedback over 4 options is an
  elimination attack); preflight refusal is correct behavior.

## Out of scope

- `selector=`/`coach=` split args; `stop_when=`; debate/consensus protocols.
- Live paid runs in CI (manual, Khoa-triggered).
- Third-party check adapters (YAML-tier registration ships with the benchmark-onboarding
  workstream; this unit only makes `rubric_check` a registry component).

## Acceptance

- Manual e2e notebook runs (07 2×2 grid + DRACO + HealthBench corrective cells) on several
  examples against the mock stack, outputs read by a human: drafts differ across rounds,
  feedback useful and leak-free, passing draft verbatim, `stop_reason`/`rounds_executed`
  coherent, cost matches round count.
- Benchmark switch for a loop = one changed line in the notebook.
- Deletion test at the HealthBench stage: its adapter is args-only, zero new Python.
