---
ticket: OME-712
stack: screamingface-engine
status: in_progress
started: 2026-08-04
finished:
---

# OME-712 — harden the ScreamingFace Engine benchmark runtime

## Intent

Certify the Engine-owned Benchmark layer after the URL4 and AI Gateway foundations: publish one
flat executable resource per protocol, isolate Candidate Invocation from private Benchmark data,
validate protocol-owned constraints before spend, preserve failures, and make local/deployed
runtime behavior agree.

`apps/url4-cloud` is the current physical host and deployment package. The domain owner recorded
here is the ScreamingFace Engine; Candidate semantics do not enter `packages/url4` or AI Gateway.

## Baseline

- **Worktree:** `/private/tmp/sf-OME-712-runtime-clean`
- **Branch:** `OME-712-benchmark-runtime`
- **Base:** AI Gateway certification commit `35e6fd2b`
- **Existing implementation:** 35 rebased commits, 125 changed files, approximately 19k added
  lines relative to the AI Gateway base.
- **Preserved audit worktree:** `/private/tmp/sf-ome-712-certification` remains dirty and
  untouched; useful findings are ported deliberately rather than copying its tree wholesale.

The initial canonical URL4 Cloud gate stopped at append-only enforcement before behavior ran.
Nine inherited tests had been edited by the existing stack. The owner approved five narrow
strict replacements; additions in four other inherited files will move to new focused modules.

On 2026-08-05, after the final hardening pass, the append-only gate reported sixteen modified
test files relative to the current branch HEAD. The owner confirmed that none of the replaced
Benchmark contracts has merged into `main` or shipped and explicitly approved one expanded
Confidence-Gate exception rather than retaining draft compatibility behavior:

- `test_aigateway_connector.py` — the private member route was replaced by the one-time Candidate
  resolver route.
- `test_benchmark_manifests.py` — the discarded Family resource, `required_models`, and
  `total_case_count` contract was replaced by flat `screamingface.benchmark.v1` resources.
- `test_benchmark_runtime.py` — shared installer terminology and Engine-bound DRACO Case identity.
- `test_candidate_invocation.py` — Candidate execution moved to its isolated Engine-owned world.
- `test_catalog_aigateway.py`, `test_catalog_wiring.py` — the discarded Engine-wide default
  synthesizer enrichment was removed; the upstream catalog remains verbatim.
- `test_draco_aggregate.py`, `test_draco_aggregate_case_mapping.py` — scoring was separated from
  reduction and positional Case fallback was replaced by mandatory Engine-bound identity.
- `test_draco_prepare.py` — the scoring helper moved to its focused module without behavior drift.
- `test_ifeval_aggregate.py`, `test_ifeval_iterative_correction.py` — immutable Benchmark revision
  and the settled flat Variant identities are part of Candidate-result behavior.
- `test_ifeval_feedback.py` — the obsolete internal Family assertion was replaced by the public
  slash-qualified id relationship after the internal field was removed entirely.
- `test_ifeval_grading.py` — two assertions that converted verifier defects into Candidate failures
  were removed; the replacement public-route test requires a typed fail-loud error.
- `test_ifeval_member_shape.py` — repeated member decoding was replaced by one pre-spend resolver.
- `test_runner_config_commands.py` — command timeouts now enforce their documented numeric type.
- `test_url4_executor.py` — the directory-wide Benchmark import exemption was tightened to an
  exact reviewed URL4 importer set.

This approval permits `run_gates.py url4-cloud --skip-append-only` for this landing only. Every
substantive gate still runs unchanged; the gate implementation and prior test history are not
modified or hidden.

## Planned files and modules

- `CONTEXT.md` — executable Benchmark and Model-ownership vocabulary.
- `docs/adr/0004-flat-benchmarks-and-isolated-candidate-invocation.md` — hard-to-reverse resource
  and execution-world decision.
- Linked spec, plan, and this evidence ledger.
- Engine Benchmark registry/resource/REST modules.
- A focused Engine Candidate Invocation/world-assembly module extracted from the AI Gateway
  connector.
- Append-only behavior tests at the confirmed seams.
- Deployment workflow/chart files only where parity evidence requires a correction.

No database schema or migration change is planned.

## Test plan

- First restore or relocate inherited test changes, leaving exactly the approved strict pins.
- Resource slice: one failing flat-id REST test, minimal implementation, focused verification.
- Isolation slice: one failing private-route access test, minimal separate-world implementation,
  focused verification.
- Outbound slice: one failing absolute-fetch test, minimal denial policy, focused verification.
- Validation slice: invalid verifying-ensemble shape/Judge fails before the mock provider sees a
  request.
- Integrity slices: zero/all-invalid Case behavior and structured collected failures.
- Finish with layering, formatting, lint, type checking, coverage, and the canonical URL4 Cloud
  gate.

## Current decisions

- Public schema: `screamingface.benchmark.v1` only.
- Public ids: `draco`, `ifeval`, `ifeval/self-corrective`,
  `ifeval/verifying-ensemble`.
- Resource count: one full `case_count`; Evaluation `limit` is embedded in URL4 and the Report
  records the effective count.
- No public Family, parameter DSL, validation schema, default synthesizer, `required_models`, or
  compatibility fallback.
- `/candidate` is an Engine-owned standard URL4 route; `packages/url4` remains ScreamingFace-blind.
- Benchmark-owned Models are pinned in URL4; Candidate-owned Models arrive through bindings.
- Candidate execution uses a restricted node without `/candidate`, private Benchmark routes, or
  arbitrary absolute outbound access.

## Evidence log

- `origin/main` contains no `/candidate` implementation. The adapter entered the stack in
  `8005f845` (`feat: link benchmark and candidate URL4 expressions`, 2026-08-02).
- Today’s notebook artifacts visibly invoked `/candidate`; canonical IFEval used one invocation
  site and self-corrective used repeated sites.
- `packages/url4` contains no Candidate-specific route or type. The host endpoint uses the public
  `Url4Node.evaluate()` interface.
- The prior draft's `required_models` field was consumed only by upper-SDK preflight. The settled
  design removes it: Benchmark-owned Models remain literal URL4 routes, Candidate-owned Models are
  checked by private validation, and the production Runner declaration is statically cross-tested.
- The initial inherited-test audit reported five owner-approved strict replacements. Subsequent
  hardening expanded the approved exception to the sixteen files enumerated above.
- With the initial append-only exception recorded, the then-current URL4 Cloud gate was green:
  Ruff lint/format, Pyright, layering, and the coverage suite all pass. The obsolete
  `default_synthesizer` catalog enrichment was the only initial behavior/type mismatch and has
  been removed end to end.
- Flat discovery now publishes `draco`, `ifeval`, `ifeval/self-corrective`, and
  `ifeval/verifying-ensemble` independently. Detail and Case routes accept complete slash ids;
  one full `case_count` remains stable while `limit` changes only URL4 `iteration.slice`.
  `BenchmarkFamily`, `screamingface.benchmark-family.v1`, `required_models`, and
  `total_case_count` are absent from production code.
- Candidate Invocation now lives in `runner/candidate.py` and delegates from the orchestration
  world to a distinct restricted `Url4Node`. The restricted world receives declared Model,
  command, and data adapters but no private Benchmark routes, `/candidate`, or outbound HTTP.
  The full Candidate contract passes 24 focused tests, command-only linked Candidate execution
  passes, and the complete URL4 Cloud gate remains green.
- The inherited verifying-ensemble URL4 couples member validation to its per-attempt collection
  source, producing three decode/validation route calls per Case. A temporary preflight proved
  invalid synthesizers can fail before provider spend but still retained those decoder calls.
  The Engine-only replacement binds the validator's canonical member array once outside Case
  iteration and lets the inherited outer-binding behavior carry it into every Case and attempt.
  The synthesizer is validated in the same operation and then reused from its immutable binding.
- A proposed `LazyExprNode(render(...))` URL4-core change was rejected after review: despite its
  small diff, it would defer every captured nested AST expression, change graph/observation shape,
  and reject valid AST-only intent-less expressions during rendering. All uncommitted
  `packages/url4` production, test, lockfile, and follow-up-document changes were removed. The
  Engine keeps its existing parameterized Candidate-call wrapper.
- The Engine-only member-validation slice is green through the assembled-world seam: the public
  verifying-ensemble URL4 contains one validation route and one Benchmark-local `$members` binding;
  the valid three-member protocol completes; a missing synthesizer fails permanently with
  `benchmark_candidate_invalid` before the mock Gateway receives any request. Focused result:
  37 passed. The complete URL4 Cloud gate is green (Ruff lint/format, Pyright, layering, and the
  coverage suite); the unfiltered suite reports 852 passed and 10 skipped. Append-only
  enforcement used the already owner-approved five strict-test exceptions recorded above.
- A shareability audit rejected both Base64 and the intermediate compact-JSON member payload.
  The linker now emits each complete Model expression exactly once as ordinary
  `$candidate_member_N` URL4 and binds `$candidate_members` to a native URL4 struct containing
  only names and references. The artifact round-trips unchanged and executes through the same
  one-time `/resolve-candidate` route. That route derives direct-Model shape from each URL4
  expression rather than trusting client metadata, assigns protocol-local member letters, and
  returns `$members` for the attempt loops without choosing a Judge. No URL4-core change or legacy
  decoder remains.
- Final integrity hardening requires one unique Engine-bound DRACO `case_id` per scoreable row,
  preserves bounded typed errors for partially failed Cases, and propagates immutable
  `benchmark_revision` beside `benchmark_id` in every serialized Candidate result. IFEval verifier
  defects now fail loudly as `benchmark_unavailable` rather than becoming incorrect Candidate
  answers.
- The internal `Benchmark.family` draft field is removed rather than renamed. Slash-qualified
  public ids provide the Cases asset prefix, and shared IFEval installation is deduplicated by its
  installer function. There is no public or internal Family abstraction left.
- Development workflow parity now pushes the existing Ionesio-owned Benchmark Runner image to ACR
  under the same two immutable tags as the App image. This completes the existing chart derivation;
  it does not redesign the Runner architecture. The workflow contract parses locally; full chart
  rendering awaits CI because Helm is not installed on this machine.
- Final canonical gate under the explicitly approved append-only exception: Ruff lint/format,
  Pyright, layering, and the complete coverage suite all green; **877 passed, 10 skipped, 94% total
  coverage**. The append-only gate itself remains visibly skipped only under the owner approval
  enumerated above; no substantive gate is bypassed.

## Outcome

In progress. Exact changed files, tests, gate counts, remaining risks, commits, and approved
deviations will be recorded here before handoff.
