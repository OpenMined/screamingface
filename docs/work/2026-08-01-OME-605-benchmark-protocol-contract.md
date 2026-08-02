---
ticket: OME-605
stack: screamingface
status: active
started: 2026-08-01
---

# OME-605 — Linked Benchmark and Candidate expressions

## Intent

Keep Candidate and Benchmark authoring minimal while preserving one complete, independently
executable URL4 per Candidate. Validate the design against every executable benchmark in the
latest `screamingface-benchmarks` checkout rather than treating DRACO as the universal shape.

## Decision

- Keep `screamingface.benchmark.v1`; the response represents a Benchmark, not a “program.”
- Replace the YAML manifest and Candidate-specific POST plan with one JSON Benchmark GET carrying
  a canonical Candidate-independent expression in `url4`.
- Compile the Candidate expression in the SDK and link it structurally through `$candidate`.
- Invoke it inside the Engine through the universal `/candidate` interface with `$input` bound.
- Use “Benchmark expression,” “Candidate expression,” and “Candidate Invocation”; avoid program,
  manifest, plan, workflow, harness, and template for the new contract.
- Keep Benchmark authoring in ordinary Engine-side Python returning typed URL4 nodes; add only a
  `candidate(input)` builder and no Client-interpreted DSL.

The accepted rationale and rejected alternatives are recorded in
`docs/adr/0001-link-benchmark-and-candidate-expressions.md`.

## Capability evidence

Throwaway probes against the installed URL4 runtime established that a bound expression is data
and a binding cannot choose a dynamic route, while static dependencies do carry earlier results.
A second probe used the public `Url4Node.evaluate(expression, env=...)` interface behind a generic
route and successfully invoked the same Candidate twice; the second input included the first
answer. No `url4` package change or nested control-plane request was required.

## Compatibility baseline

- Repository: `OpenMined/screamingface-benchmarks`
- Revision: `23524fdb60de5a56c7618339cc0423303997f529`
- Profiles: `draco`, `healthbench`, `medxpert`, `scicode`
- Existing fixed SDK runner: DRACO only

## Test plan

- Benchmark GET decoding and structural linking through sync/async Client interfaces.
- Candidate default and override precedence through public Model/Fusion construction.
- `/candidate` execution invariants for Model, Fusion, state, tools, usage, cancellation, and
  failures.
- Benchmark expression fixtures for all four benchmark families.
- Missing Benchmark assets fail with a typed error before Candidate execution.
- Raw and encoded full-suite URL4 size gates.
- DRACO URL4 Cloud unit/integration and live lifecycle execution.
- Full lint, type, coverage, notebook-blob, build, and distribution gates.

## Outcome

The foundational vertical slice is implemented:

- URL4 Cloud serves one cacheable JSON Benchmark resource and no Candidate-specific planning POST.
- DRACO builds a Candidate-independent typed URL4 expression through the shared `Benchmark`
  authoring boundary.
- The SDK compiles Candidate policy locally, links the two ASTs once per Candidate, and uses a
  single Benchmark fetch for an Evaluation of any number of Candidates.
- The Runner's reserved `/candidate` route executes Model and nested Fusion expressions in-process
  with bounded recursion/calls and inherited cancellation, errors, and usage.
- The same boundary preserves HealthBench-style native histories, MedXpert-style reasoning/commit
  turns, and SciCode-style ordered code/sandbox state in representative execution tests.
- A deterministic cross-package DRACO run now covers the actual Engine definition, SDK linker,
  Runner Candidate Invocation, five fixed Judge passes, and production Aggregation code.
- The linked full-suite DRACO URL4 remains compact because Case iteration is not statically
  expanded: a Model measured 1,925 raw / 2,435 encoded-query bytes, and a two-member Fusion
  measured 2,589 raw / 3,265 encoded-query bytes. The corresponding one-Case expressions were
  slightly larger because they carry an explicit slice (1,945 / 2,461 and 2,609 / 3,291 bytes).
- The complete Python package suite passes with 345 tests and 14 skips; the complete URL4 Cloud
  suite passes with 644 tests and 5 skips. Ruff and Pyright pass for both projects.

SciCode, HealthBench, and MedXpert adapters, their full transport-size gates, notebook fixture
reconciliation, and live paid execution remain before OME-605 is complete. The wheel and source
distribution checks pass; the notebook check is intentionally left failing rather than overwriting
the user's two edited notebooks.

### Live DRACO correction — 2026-08-02

A one-Case paid run exposed a semantic failure that the original mocked vertical slice did not:
the nested judge-pass map received literal `$answer`, `$question`, and `$criterion_id` strings.
The URL4 remained syntactically valid and terminated successfully, but the aggregator harvested
the example verdict embedded in the judge prompt 144 times. The resulting report showed
`n_runs=144`, `coverage=0.0207`, and an invalid zero score.

The corrected expression keeps one complete URL4 per Candidate and changes no URL4 package code:

- DRACO's revision-qualified `tasks` route receives the direct `/candidate` result once per Case
  and returns ordinary
  weight-free JSON tasks before criterion iteration. This is a deterministic benchmark-owned
  function, not an opaque evaluator: every paid judge call remains explicit in the URL4.
- each criterion task carries the original question, Candidate answer, criterion id and text, and
  a positive/negative type derived from the private weight sign without exposing the weight;
- the judge calls are direct siblings inside the criterion map, so all dynamic inputs are
  local `$item` fields and do not cross another map scope;
- every explicit Judge call is wrapped by DRACO's revision-qualified `criterion-verdict` binder,
  which validates the official
  `{explanation, criterion_status}` reply and attaches the already-known criterion id; and
- aggregation consumes only those bound records, rejects statuses other than exact `MET`/`UNMET`,
  and reports accepted, invalid, and missing verdict counts alongside coverage.

The binder is deliberately narrower than a grading DSL. It makes no model call, contains no
DRACO score policy, and does not hide the Judge from the shareable URL4. A future Benchmark may
reuse its ordinary Python logic without sharing a public route; deterministic verifiers such as
IFEval and structurally different graders do not need it. Requiring the Judge to echo an id was
rejected because identity is orchestration state, not a model judgment, and the canonical DRACO
schema does not require it.

The next paid one-Case run completed with `121/159` accepted verdicts (`coverage=0.761`), proving
that the Candidate/task scoping correction worked under the then-three-pass configuration but also
exposing ordinary malformed or absent Judge replies. The shared binder now preserves each
malformed reply as an invalid record and the aggregator reports missing calls separately. The SDK
emits a filterable `CoverageWarning` whenever a Benchmark's reported coverage is below its own
target. This is a metric-level diagnostic, so future Benchmarks receive it when they expose the
same metric contract without any Benchmark-specific SDK code.

### DRACO paper alignment — 2026-08-02

The public Benchmark is `draco`, not `draco-lite`. It loads the complete official 100-task dataset;
`limit` is only an execution-time Case slice and does not select a reduced Benchmark variant. The
grading expression now performs the paper's five independent Judge passes for every criterion,
uses low reasoning and temperature `0.2`, preserves the canonical Appendix C.5 Judge prompt, and
retains DRACO's official weighted scoring and aggregation.

One reproducibility limitation is explicit rather than hidden: the paper names `Gemini-3-Pro
Preview`, which Google shut down on 2026-03-09. Google designated Gemini 3.1 Pro Preview as its
replacement and made the retired API id resolve to the newer model. The executable definition
therefore pins that replacement explicitly as `openrouter/google/gemini-3.1-pro-preview`. Results
must disclose this Judge version difference and must not be presented as bit-for-bit reproduction
of the paper's scores. Exact reproduction would require Google to restore the retired model
snapshot; adding its old name to URL4 configuration cannot restore its weights or behavior.

DRACO evaluates an arbitrary Candidate system; the Benchmark does not force every Candidate to
imitate a paper baseline. In particular, reproducing a named paper baseline also requires matching
that system's model, prompt, tools, and execution environment. The five-pass rubric protocol is
Benchmark-owned, while Candidate prompts and capabilities remain Candidate-owned.

The regression gate reproduces the observed inflated-run/low-coverage report, ensures prompt JSON
examples cannot become Judge runs, inspects the actual AI Gateway Judge messages, and asserts one
Candidate call plus exactly five Judge calls for a one-criterion fixture. Post-correction
verification passes all 640 Engine tests (5 skipped) and all 350 SDK tests (14 skipped), plus Ruff
and Pyright across both changed packages. The unchanged URL4 package's previous 1,102-test gate
also remains green.

### Benchmark module deepening — 2026-08-02

The Benchmark registry is now the single source of truth for both resource construction and
Runner installation. A definition owns `build(selection) -> Node` and
`install(node, assets: Path)`; shared Runner code resolves the root and passes only that
Benchmark's directory. Adding a
Benchmark no longer requires editing global `url4.toml`, generating a TOML fragment, maintaining
subprocess CLIs, or coordinating generic `/benchmark` routes. Internal routes include the stable
Benchmark id and opaque immutable revision. Assets load lazily, so missing private data produces
`benchmark_unavailable` only when that Benchmark is selected rather than `endpoint_not_found`
during execution.

The public resource and SDK were reduced to fields that affect behavior or provenance. Removed
capability and Candidate-invocation declarations were decoded and displayed but never enforced;
dynamic work also made a universal exact count misleading. The resource now carries an immutable
revision derived from the pinned DRACO dataset/protocol, and every Report records it. DRACO's
dataset download is pinned to the exact Hugging Face snapshot.

A final interface reduction removed the one-field `BenchmarkExpression` wrapper, duplicate
Benchmark `name`/`title` values from `BenchmarkInfo`, unused baseline/gain result fields, and
Benchmark-specific primary-metric/direction declarations. All Candidate results now use one
higher-is-better `score`; supporting measurements remain in `metrics` without duplicating the
score. The executable Benchmark resource is correspondingly limited to id, revision, Case counts,
required fixed models, and URL4, while the catalog remains responsible for presentation metadata.
DRACO task construction also passes typed values internally instead of encoding and immediately
decoding a JSON payload.

Aggregation is now in-process and receives the row array through URL4 context. This removes the
full-suite `E2BIG` risk from passing Judge output in subprocess argv; a regression test executes a
payload larger than 2 MB. Fusion's zero-configuration synthesizer now uses the Engine-declared
`openrouter/anthropic/claude-haiku-4.5` route, which is seeded in AI Gateway and declared in the
Runner model world.

## Prospective IFEval compatibility

The IFEval reference kit reviewed on 2026-08-02 contains the pinned 541-row `google/IFEval`
dataset and the Apache-licensed Python verifier at commit
`0c495b2f95155e8b10acb919ae283bfb4d5be6e2`. Standard IFEval fits the accepted boundary without an
SDK change: one text Candidate Invocation per Case, one Engine-owned programmatic verifier call
using that Case's instruction IDs and kwargs, and an aggregate over prompt/instruction accuracy
under strict and loose readings. The Benchmark image must pin the verifier, `langdetect`, and
vendored NLTK `punkt`/`punkt_tab` data so grading remains offline and comparable. The official
verifier's randomized non-ASCII preprocessing must also be preserved and reported rather than
quietly "fixed."

The archive's LANL checker-in-the-loop ensemble is a separate Candidate algorithm, not part of the
IFEval grading protocol. The current opaque Fusion returns one final string, so it cannot faithfully
expose each member to mid-loop verification, conditionally retry failed members, and tie-break only
compliant member outputs. Standard IFEval and ordinary Model/Fusion comparisons work now; exact
LANL reproduction requires an explicit future Candidate strategy/interface. It must not add
IFEval-specific dispatch to the SDK or weaken the universal Benchmark resource.
