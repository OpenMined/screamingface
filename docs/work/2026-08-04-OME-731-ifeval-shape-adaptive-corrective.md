---
ticket: OME-731
stack: url4-cloud
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-731 — Shape-adaptive ifeval-iterative-correction: self-correction solo, verifying ensemble Fusion

> **Final contract update:** ADR 0003 replaced the per-shape `?members=N` fetch and the single
> shape-adaptive identity described below. The Engine now returns one Benchmark Family containing
> `ifeval/self-corrective` and `ifeval/verifying-ensemble`; the SDK selects a Variant locally
> and supplies members through the universal `$candidate_members` binding. Earlier plan/outcome
> text is retained as decision history, not as the current API.

## Intent

Implement the accepted two-benchmark design (`.dk/plans/2026-08-04-ifeval-two-benchmarks-proposal.md`,
spec v5): `ifeval-iterative-correction` adapts to candidate shape. Solo = self-correction (the
candidate authors its own feedback — the {solo+loop} ablation Skurikhin et al.,
https://openreview.net/forum?id=XSIYfTm2h7, never ran). Fusion = the paper's verifying
ensemble with the candidate's synthesizer as judge via a new `$candidate_synthesizer`
binding. `ifeval-iterative-correction-ensemble` id removed (clean removal).

## Planned changes

- `benchmarks/ifeval/corrective.py` — shape-adaptive build (members=0 | 2..4); judge
  tie-break among passers via verdict-aware select; judge-authored feedback; neutral
  retry text; one revision hashing the full generic definition
- `benchmarks/ifeval/ensemble.py` — DELETED (protocol merges into corrective)
- `benchmarks/ifeval/runtime.py` — verdict-aware select; solo/ensemble aggregate rows
- `benchmarks/ifeval/definition.py` — catalog description carries the two-roles rule
- `benchmarks/definition.py` (SHARED — flag for Keelan) — optional shaped build +
  synthesizer binding helper
- `rest/benchmarks.py` — `?members=N` fetch parameter
- registry drops `ifeval-iterative-correction-ensemble`
- Tests: shape-adaptive builds (0/2/3 members), three select scenarios, judge-feedback
  wiring, revision change, draco + canonical ifeval byte-identity. NOTE: ensemble-variant
  tests removed WITH the variant (owner-approved design removal, not test weakening).

## Test plan

RED first: solo build contains self-feedback candidate call; 2- and 3-member ensemble
builds well-formed; lone passer beats judge letter; judge letter honored among passers;
zero passers = judge pick recorded; judge-authored feedback node present; corrective
revision differs from the old one; canonical ifeval & draco manifests byte-identical.

## Acceptance

run_gates url4-cloud ALL GREEN; registry serves exactly {draco, ifeval, ifeval-iterative-correction}.

## Outcome

- **Naming:** owner decision mid-review — id `ifeval-iterative-correction`, variant
  `iterative-correction`, module `iterative_correction.py`, symbol
  `IFEVAL_ITERATIVE_CORRECTION` (Irina consulted; catalog prose keeps the paper's
  phrase "corrective feedback").
- **Actual files:** as planned, plus: finalize route DELETED entirely (both shapes emit
  attempt-tagged check records — solo: the answer's check; ensemble: the selection's
  check — so one aggregate_corrective scores both; a real simplification vs plan).
  Solo self-feedback = a second /candidate invocation per failed attempt.
- **Shared surfaces (flag for Keelan):** Benchmark.member_build optional field;
  resource(limit, members=0); REST ?members=N with 422 code=candidate_shape.
- **Gates:** run_gates url4-cloud ALL GREEN (851 tests). `--skip-append-only` used:
  prior-test changes were pre-declared here and owner-approved (protocol redesign +
  variant removal); ensemble-variant tests removed WITH the variant.
- **Commits:** NONE yet — owner reviewing locally first. Nothing pushed.
- **Deviations:** zero-passers select arm keeps the judge's letter (record reflects the
  judged pick) — flagged to owner as the one debatable call.

## Owner review round (2026-08-04)

Ten findings, all addressed: judge-letter parsing hardened (first token, bare letter
only — prose replies get no vote; new tests incl. the punctuated-letter case), the
vacuous fallback test fixed ("zzz"), MEMBER_LETTERS deduped (runtime imports it),
prose-constant guard moved from import-time RuntimeError to a unit test, member-bounds
error wording relaxed to "direct members" (Model-ness stays enforced loudly by the SDK
linker), notebook names the solo self-feedback cost and the terse-judge requirement.
Owner verified: ETag body-derived (no shape collision), no member-check record leakage
into aggregation rows (weight=0.0 instrumental sources dropped by _gather), verbatim
select, revision covers all prose + bounds. Post-review gates: engine ALL GREEN (854),
SDK 407 + ruff + pyright + notebooks green. Judge params remain a known limitation
(synthesizer route carries no params on this exam) — candidate for a Fusion API
follow-up with Keelan.

## Post-E2E safety amendment (2026-08-04)

A three-Case self-corrective Evaluation demonstrated that the former fail-all fallback
could publish `score=0.6667` while one Case had no grade and the final Report contained
no failure evidence. `aggregate_corrective(...)` now distinguishes a valid never-passing
check record (scoreable) from an absent check record (operational failure, unscorable)
and retains the latter's Case position and sanitized collected error in the raised
Aggregation error. Canonical and iterative-correction regressions cover the shared
aggregation invariant.

The amendment is isolated in the focused restack commit
`fix(url4-cloud): reject unscored IFEval cases`.
