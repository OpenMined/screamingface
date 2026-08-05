# OME-712 ScreamingFace Engine benchmark runtime — hardening plan

**Ticket:** OME-712  
**Spec:** `docs/spec/2026-08-05-OME-712-screamingface-engine-benchmark-runtime.md`

## Goal

Turn the rebased Engine benchmark layer into one independently reviewable landing: flat
Benchmark resources, a restricted Candidate Invocation world, protocol-owned validation,
fail-loud results, deployment parity, and documentation matching the executable contract.

## Confirmed test seams

1. **Discovery seam:** Engine REST catalog/detail/Case routes expose flat
   `screamingface.benchmark.v1` resources by complete id.
2. **Evaluation seam:** `build_aigateway_world(...)` plus
   `world.node.evaluate(complete_url4)` executes a linked Candidate using the assembled Engine
   world.
3. **Validation seam:** the complete verifying-ensemble URL4 rejects an invalid Candidate shape
   before any provider-backed Model handler is called, and a valid Candidate is decoded and
   validated once for the complete Evaluation.
4. **Integrity seam:** public Evaluation/result behavior exposes collected Case failures and
   rejects empty or all-invalid grading results.
5. **Deployment seam:** chart image references match development and release workflow outputs.

Tests observe those interfaces rather than private helper call graphs.

## Phase 1 — Traceability and inherited-test audit

- [x] Rebase the clean Engine branch onto the certified AI Gateway layer.
- [x] Record the settled domain terms, contract, ADR, plan, and work ledger.
- [x] Run the append-only audit and identify nine inherited tests changed by the existing stack.
- [x] Obtain initial owner approval for five strict Confidence-Gate replacements:
  - exact assembled Engine route set;
  - canonical Anthropic model id in two files;
  - reserved TOML table example after `[data]` became supported;
  - exact Benchmark-author URL4 import allowlist.
- [x] Restore four unrelated inherited files and move genuinely new cases into focused append-only
      modules.
- [x] Re-run append-only enforcement and record the exact approved remainder.
- [x] Obtain the owner's expanded Confidence-Gate approval for all sixteen modified test files
      after confirming the replaced contracts belong only to this unpublished stack. The work
      ledger records each file and replacement reason; no compatibility behavior is retained.

## Phase 2 — Flat Benchmark resources

- [x] Add one failing REST behavior test for a slash-qualified flat Benchmark id.
- [x] Replace `BenchmarkFamily` and `screamingface.benchmark-family.v1` with one
      `screamingface.benchmark.v1` resource per executable protocol.
- [x] Keep one stable full `case_count`; remove `total_case_count` and `required_models`.
- [x] Remove family/default-synthesizer compatibility code and update catalog/detail/Case routes.
- [x] Repeat red → green for catalog shape, canonical id, limit slicing, ETag, and missing assets.

## Phase 3 — Isolated Candidate Invocation

- [x] Add a failing assembled-world test proving a Candidate cannot read a private Benchmark
      route.
- [x] Move Candidate Invocation out of the AI Gateway connector into a focused Engine runtime
      module and delegate to a restricted Candidate `Url4Node`.
- [x] Add an assembled-world regression test proving absolute outbound access is denied to the
      Candidate even when orchestration permits it.
- [x] Preserve valid Model/Fusion execution, retrieval policy, usage, cancellation, recursion
      protection, total-call limits, commands, and data through focused vertical slices.

## Phase 4 — Protocol validation and result integrity

- [x] Pin Benchmark-owned Models in URL4 and validate the production Runner declaration through
      the static cross-stack contract; generic command-only and IFEval-only worlds remain valid.
- [x] Validate verifying-ensemble direct members and its explicit synthesizer before paid calls;
      leave Model-route availability to ordinary Candidate Invocation.
- [x] Bind the validator's canonical member array once outside Case iteration and reuse it in
      every attempt without a repeated decoder route or fallback representation.
- [x] Emit every member once as ordinary `$candidate_member_N` URL4 and bind
      `$candidate_members` as a native struct of references; retain no Base64/JSON execution
      payload or compatibility decoder.
- [x] Keep the existing parameterized Candidate Invocation wrapper; URL4 parser/compiler changes
      are explicitly outside this Engine landing.
- [x] Verify DRACO zero-Case and IFEval empty/all-error paths fail loudly.
- [x] Preserve per-Case collected errors in structured result failures.

## Phase 5 — Structure, deployment, and certification

- [x] Keep the inherited connector/config modules intact by owner direction; record the existing
      450-line guidance deviation instead of mixing unrelated decomposition into this landing.
- [x] Restore development workflow parity for the Benchmark runner image used by the chart.
- [x] Remove stale Family/default-synthesizer/fallback documentation and update notebooks only
      after the Engine contract is stable.
- [x] Run focused tests after each vertical slice, then the complete URL4 Cloud gate.
- [ ] Prepare reviewer packets and proposed Linear/PR/group-chat notes without publishing them.

## Phase 6 — Safe DRACO notebook protocol

- [x] Add a new contract test for `draco/smoke` before production code.
- [x] Build canonical and smoke DRACO from one constructor; smoke reduces only Case count,
      criterion count, and Judge-pass count.
- [x] Give smoke its own flat id, revision, private routes, and Candidate result identity.
- [x] Prove canonical DRACO remains 100 Cases, all criteria, and five Judge passes.
- [x] Add `draco/lite` with five pinned typical-complexity Cases from the five most represented
      domains, every criterion, and one Judge pass.
- [x] Prove lite discovery and execution expose exactly the same ordered pinned Case ids.
- [ ] Keep notebook execution disabled by default; the SDK chooses a Benchmark id and never
      rewrites DRACO protocol multiplicity itself.

## Explicit process deviations

- OME-712 remains one cross-cutting issue by owner direction; cleanup sub-issues are not created.
- This layer is stacked on the URL4 and AI Gateway landings by explicit owner decision.
- The owner explicitly removed new `packages/url4` work from this landing after reviewing the
  semantic blast radius of deferred AST lowering.
- The implementation predates this hardening ledger. Existing test edits are retained under the
  owner-approved Confidence-Gate exception recorded in the work ledger. Removed assertions cover
  only discarded, unpublished contracts; no shipped behavior receives a compatibility fallback.
