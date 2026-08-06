---
title: Certify the OME-712 DRACO Runner contract
ticket: OME-712
status: draft
date: 2026-08-04
source: Linear issue OME-712 and PR 464 at b2c64433c34e12982dfbdcd19ac2664dc975f846
---

# Certify the OME-712 DRACO Runner contract

## Purpose

This document makes the contract used to review PR #464 explicit. It does not retroactively approve
behavior added after the work item was filed, and it does not replace Linear as the scope or status
authority. Where the branch and the live issue disagree, the disagreement is a finding that needs an
owner decision.

The fixed review range is merge base `e39f9fbaec4827fe41a3bb9bd924e40b2e7eb2d2` through branch
head `b2c64433c34e12982dfbdcd19ac2664dc975f846`. Current `origin/main` is separately checked for
drift; it is not merged into this certification worktree.

## Certification verdict

**Blocked.** The branch is valuable source material, but it is not safe to merge or describe as a
complete end-to-end implementation at this head. Four independently reproducible defects block a
release:

1. Aggregation reports a normal successful `CandidateResult` after scoring zero Cases.
2. Candidate code runs on the same `Url4Node` as private Benchmark routes and can read hidden
   criterion requirements or invoke the Aggregator as a scoring oracle.
3. Candidate code can make absolute-URL requests through the node's unrestricted outbound I/O,
   bypassing the Gateway and Tavily retrieval guards entirely.
4. The default Helm registry derivation selects an ACR Benchmark image that neither the dev nor
   release workflow publishes.

The live issue also says that no deployed run has yet produced a correct hand-checked score, and the
branch is 36 commits behind current `main`. Those are independent completion blockers even after the
four defects are repaired.

Local remediation status, not yet committed or present on PR #464: the certification worktree now
raises a typed `benchmark_unavailable` failure whenever Aggregation produces no scored Cases, and the
dev workflow publishes the paired Benchmark image to ACR. The source-head findings below remain
historically accurate for the fixed review range.

## Normative work-item contract

The live issue requires all of the following:

1. A real DRACO evaluation runs as an ordinary URL4 expression on the url4-cloud Runner path:
   Kubernetes Job → AI Gateway → provider.
2. Every Judge call is an ordinary observable URL4 model call. Judge behavior is not hidden inside
   a Python command or deterministic Aggregator.
3. Benchmark inputs and weight-free criteria are first-class Runner addresses. Weighted rubrics are
   available only to Aggregation and are never exposed as declared Candidate-facing data.
4. Deterministic Aggregation performs arithmetic only and never calls a model.
5. The control-plane image remains dataset- and rubric-free; only the Runner benchmark image carries
   private evaluation assets.
6. A run that cannot establish a score fails closed. Zero harvested verdicts, an unavailable rubric,
   a Judge timeout, or an unprovable Case mapping must not become a successful score.
7. At least one Kubernetes Job produces a scored `CandidateResult` whose criterion outcomes agree
   with a hand-checked sample.
8. The full-scale configuration is exercised, or the exact unexercised scale and resulting risk are
   disclosed. Smoke evidence must never be described as full conformance.
9. Every paid live acceptance run receives explicit budget approval immediately before execution.

## Explicit original exclusions

The issue states that the URL4-native path and the separately developed SDK/Engine registry were
independent architectures and that convergence was not in scope. The following therefore require a
new owner-approved parent decision or separate landing work; they are not silently inherited
requirements of `OME-712`:

- an Engine-owned `screamingface.benchmark.v1` resource consumed by the SDK;
- structural `$candidate` linking and the generic `/candidate` invocation route;
- provider-connection discovery or mutation through url4-cloud;
- an AI Gateway provider catalogue and canonical provider/model identifiers;
- generic Benchmark methods or variants for future Benchmarks;
- unrelated Runner cancellation repairs;
- generic command/data configuration retained after DRACO moved to in-process deterministic routes.

ADR 0001 records an accepted convergence design in the branch, but neither the ADR nor PR body
identifies the approving issue or changes the live issue's exclusion. Certification therefore treats
the design as evidence of direction, not sufficient scope authorization.

## Repository acceptance

In addition to the product contract, a merge-ready landing must:

- branch from current `main`, contain one landing stack, and use a cross-cutting parent plus one
  sub-issue per affected stack;
- carry a task mirror, approved specification, implementation plan, and work ledger before code;
- preserve prior tests unless every exception is owner-approved and disclosed in the PR body;
- use conventional commits with `Refs: OME-N` in every commit body;
- pass the canonical stack gate on the supported CI platforms without relying on an unrelated flaky
  test waiver;
- keep modules focused (normally no more than 450 lines) and place remote-owned behavior behind a
  small port with production and in-memory adapters;
- state the cross-service request, response, error, identity, timeout, and telemetry contract in the
  PR body; and
- distinguish deterministic fixture evidence, local integration evidence, deployed smoke evidence,
  and paid full-scale evidence.

## Evidence required to close the work item

The minimum close record is:

- exact Engine, Gateway, benchmark image, dataset, Judge, prompt, and protocol revisions;
- exact Candidate, selected Case/criterion fixture, predicted paid-call count, actual paid-call
  count, and budget approval;
- raw criterion verdicts and the hand calculation used to compare Aggregation;
- terminal result plus failures, so fail-closed behavior is visible;
- commands and results for the URL4, AI Gateway, and url4-cloud gates; and
- disclosure of every deviation from the paper, including the replacement Judge, missing reasoning
  setting, retrieval implementation, reduced Cases/passes, or incomplete verdict coverage.

## Spec review findings

### Release blockers

#### S1 — Zero scored Cases report success

`benchmarks/draco/aggregate.py:334` returns `case_count: 0`, a score of `0.0`, `n_runs: 0`, and an
empty failure list for `rows_json == "[]"`. This behavior is intentionally pinned by
`test_no_rows_at_all_yields_a_zero_result_rather_than_an_exception` and
`test_no_rows_at_all_does_not_trip_the_guard`. It directly contradicts requirement 6 and Linear's
explicit acceptance note that a run scoring zero Cases must not report success.

The same interface treats a partially scored run as a normal result and computes score and coverage
only over successful Cases. For example, one perfect Case plus one failed Case can report score and
coverage `1.0`, with the failed Case visible only in `failures`. The stacked SDK instead requires
`case_count` to equal the selected evaluation count and `failures` to be empty. The Engine and SDK
therefore disagree on whether partial completion is a result or an execution failure.

Required correction:

- raise a typed Aggregation failure when zero Cases score;
- define selected, attempted, and scored Case counts in one wire contract;
- decide whether any incomplete Case fails the whole evaluation or yields an explicitly partial
  terminal state; and
- make denominators and SDK validation follow that decision.

#### S2 — The Candidate can invoke private Benchmark routes

`runner/connector.py:336-410` evaluates the Candidate on `self._node`. The same node registers
Candidate invocation, all model routes, all Benchmark routes, commands, and data at
`runner/connector.py:672-687`. Lexical isolation of `$input` does not provide capability isolation.

A deterministic in-memory probe made the Candidate call the DRACO task route and returned the
private criterion identifier and requirement (`secret`, `The answer is four.`). Weighted rubric
files are not directly registered, but the weight-free requirements are private Judge inputs and the
Aggregate route is a scoring oracle. The ADR and README statements that Benchmark routes are private
are therefore false for the implemented graph.

Required correction: create a separate Candidate evaluation boundary whose route table contains
only explicitly granted model, command, data, and action capabilities. It must not expose Candidate
invocation or Benchmark-internal task, verdict, or aggregate routes. Shared usage, identity,
cancellation, and retrieval state should travel through small ports rather than a shared route
namespace.

#### S3 — Absolute-URL fetch bypasses retrieval policy

The shipped config enables `allow_outbound`; `build_aigateway_world` consequently constructs the
node with `outbound=None` at `runner/connector.py:669-676`, which lazily permits arbitrary HTTP I/O.
Because Candidate code runs on that node, it can fetch an absolute URL without passing through
AI Gateway's `exclude_domains` union or url4-cloud's Tavily guard. An in-memory probe fetched a
synthetic `https://public.example/answer-key` and returned its private contents.

This is both a Benchmark-integrity bypass and an SSRF-shaped capability. Fix it at the Candidate
capability boundary; protecting only the declared task route or adding another hostname string check
would leave other URL4 fetch surfaces reachable.

#### S4 — ACR deployments select an image that is never published

The Helm helper derives the Runner image as `<image.repository>-benchmark`. The dev image workflow
publishes its base image to both GHCR and `acropenmined.azurecr.io`, but its Benchmark job
authenticates to and tags only GHCR. A dev install using the supported ACR control-plane repository
therefore renders a matching ACR Benchmark path and fails later with `ImagePullBackOff`. The release
workflow has no corresponding mismatch: both its base and Benchmark images are GHCR-only.

Required correction: publish the paired dev Benchmark image to every dev base-image registry, or
decouple the documented default and require an explicit Runner repository. Add a workflow assertion
that the Helm-derived reference is among the produced tags.

#### S5 — The deployed acceptance artifact does not exist

The live issue records a smoke that proved plumbing and call count but says no correct score was
achieved. The branch's deterministic one-Case/one-criterion tests are useful, but they are not a
Kubernetes acceptance artifact. Closure still requires a hand-checked deployed result and a deployed
fail-closed zero-score case. No paid run is authorized by this document.

#### S6 — The branch is stale against `main`

The head is 36 commits behind current `main`, including incompatible workflow action updates. It
must be reconstructed or rebased onto current `main`, conflicts resolved semantically, and every
owning-stack gate rerun. A green check attached to the old head is not evidence for the final tree.

### Additional correctness risks

- `case_id_of` accepts the first echoed Case ID but does not prove that every accepted verdict in the
  row carries that same ID. A corrupt mixed-Case row can therefore be scored against one rubric.
- The reducer does not reject more than `judge_passes` accepted verdicts per criterion. Extra
  duplicates can create a sixth scoring run even though the protocol pins five.
- Coverage below the stated 0.95 target remains an ordinary result and score is calculated over the
  restricted observed rubric. Publication readiness needs an explicit fail/warn contract.
- `_candidate_env` reserves ordinary text beginning `case: …, input: …` as a future multi-slot
  envelope. That is an ambiguous magic-string protocol and belongs to the separately tracked action
  work, preferably as a versioned structured payload.

### Protocol baseline and disclosure

The code's `JUDGE_PASSES = 5` is correct. The
[DRACO paper](https://arxiv.org/abs/2602.11685) evaluates 100 tasks over five independent grading
runs and reports an average of 39.3 criteria per task. Linear's current progress text saying “53
criteria × N Cases × 3 runs” is stale and should be corrected; code must not be reduced to three
passes to match it.

A paper-scale Candidate evaluation is approximately `100 × 39.3 × 5 = 19,650` Judge calls, before
Candidate graph calls. That cost and the run-wide I/O concurrency cap need to be measured and put in
the approval record before a paid run.

The implementation must also disclose that it is not bit-for-bit reproduction of the reference
harness:

- the configured replacement Judge is Gemini 3.1 Pro Preview rather than the paper's Gemini 3 Pro;
- the reference low-reasoning setting is not currently forwarded;
- retrieval mixes provider-native search with a Tavily loop rather than the reference product; and
- a result below the verdict coverage target currently remains a warning rather than a failure.

The prepared dataset revision is pinned to
[`ce076749809027649ebd331bcb70f42bf720d387`](https://huggingface.co/datasets/perplexity-ai/draco/tree/ce076749809027649ebd331bcb70f42bf720d387),
and the generated 100-Case URL4 resource is roughly 28 KB; the exact deployed request transport still
needs a full-size test.

## Standards review findings

| Area | Result | Evidence and required disposition |
|---|---|---|
| Work-item traceability | Red | The branch predates its required mirror/spec/plan/ledger, implements excluded convergence, and its final 76-file commit has no `Refs:` body. Create a cross-cutting parent and stack-local children before re-landing. |
| Commit discipline | Red | Subjects are conventional, but 24 of 36 commits have no `Refs: OME-N`; the final commit mixes 76 files and multiple products. Reconstruct by accepted interface, not by cherry-picking the current head. |
| Append-only tests | Red | Twelve pre-existing tests are modified relative to the fixed merge base, and the final commit deletes four tests added earlier in the same branch. Two seed changes and one Helm change have owner-approved exceptions; the remaining cumulative exceptions still need explicit disclosure and approval. |
| Canonical gates | Red | url4-cloud is green. URL4 has one macOS portability failure; AI Gateway has one repeatable timing assertion failure. Green GitHub checks at the stale head do not waive either supported-platform failure. |
| CI/release evidence | Red | PR CI never builds `Dockerfile.benchmark`; the first real image build happens after merge on dev push or tag. Helm-render tests skip locally because Helm is absent. Add a PR image-build gate and a rendered-reference/tag assertion. |
| Reproducibility | Red | The Benchmark Dockerfile copies a floating `uv:python3.12-bookworm-slim` image and installs `datasets>=2.19` outside the lock. Pin the tool image by digest and the build-only dependency through a lock or exact version. |
| Module depth | Needs redesign | `runner/connector.py` is 1,393 lines, `runner/config.py` 588, `benchmarks/draco/aggregate.py` 520, and `rest/routes.py` 451. Extract a deep Candidate-runtime boundary and split scoring parse/validation from deterministic reduction. |
| Scope isolation | Red | Cancellation, provider discovery, generic Benchmark methods/actions, REST Case access, generic command/data support, and repo vocabulary are bundled with DRACO. Move them to their existing or proposed owners. |

## Gate evidence at the fixed head

The canonical runner defaults its append-only comparison to `HEAD`, which only checks uncommitted
changes. This review therefore ran behavior gates separately and audited prior tests against the
fixed merge base.

| Stack | Result |
|---|---|
| url4-cloud | Ruff, format, Pyright, layering, and coverage gate green: 771 passed, 10 skipped, 129 warnings. |
| URL4 | Ruff, format, Pyright, and 97.48% coverage green; 1,115 passed and 1 failed. The failing test assumes Linux `MAX_ARG_STRLEN`; macOS accepted the same argv payload. |
| AI Gateway | Ruff, format, Pyright, no-enterprise, and 92.48% coverage green; 2,664 passed, 40 skipped, and 1 failed. The unknown-user versus wrong-password timing-ratio assertion failed again in isolation with varying ratios. |
| GitHub PR checks | Green at `b2c64433`, but they do not build the Benchmark image and are attached to a head 36 commits behind current `main`. |

The exact pre-existing tests modified against the merge base are:

- AI Gateway: `test_openrouter_dispatch.py`, `test_openrouter_settings.py`, and `test_health.py`.
- url4-cloud: `test_aigateway_connector.py`, `test_aigateway_connector_default_model.py`,
  `test_catalog_aigateway.py`, `test_catalog_wiring.py`,
  `test_declared_models_match_aigateway.py`, `test_local_app.py`, `test_runner.py`,
  `test_runner_config.py`, and `test_url4_executor.py`.

The final commit also deletes same-cycle tests for Runner merge-config stripping, DRACO aggregate
stdin, Runner merge-config, and manifest/world consistency. The architectural replacement may make
some obsolete, but deletion must be reviewed rather than hidden inside the consolidation commit.

## Owner decisions still required

1. Does ADR 0001 formally supersede the issue's no-convergence constraint? If yes, the work needs a
   cross-cutting parent and separately owned landings before implementation is considered authorized.
2. Is `OME-712` closed by the original URL4-native acceptance only, or is it now the parent for the
   broader Engine-owned Benchmark architecture?
3. Are generic `[commands]`/`[data]` support and command-stdin still product requirements now that
   the implemented DRACO runtime installs deterministic functions in-process?
4. Which deployed live run is the acceptance artifact? The issue says no correct score was achieved;
   the branch ledger/PR narrative describes later partial runs but no attached hand-checked result.
5. Is incomplete verdict coverage a failed evaluation, an explicitly partial evaluation, or a
   publishable result with warnings? The Engine and stacked SDK currently implement different
   answers.
6. Which Candidate capabilities are allowed: declared models only, models plus specific tools/data,
   or a benchmark-defined capability set? Absolute outbound HTTP and Benchmark internals must not be
   implicit.
