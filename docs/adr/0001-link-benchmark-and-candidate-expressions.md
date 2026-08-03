---
status: accepted
date: 2026-08-02
---

# Link Engine-owned Benchmark expressions with SDK-owned Candidate expressions

ScreamingFace will fetch one Candidate-independent Benchmark resource from the Engine, compile
each Model or Fusion into a Candidate URL4 expression in the SDK, and structurally link the two
into one complete URL4 per Candidate. The Engine-supplied Benchmark expression owns loading,
Candidate Invocation sites, Grading, and Aggregation and refers to one external `$candidate`
binding. The Candidate expression accepts `$input` and returns an answer. A generic Engine-owned
`/candidate` route evaluates that expression in-process against the same URL4 node. The linked
URL4 is submitted through the ordinary execution GET and can be saved or shared independently of
the SDK.

The Benchmark resource keeps the existing `screamingface.benchmark.v1` schema name and carries its
canonical expression in a `url4` field. “Benchmark program” and
`screamingface.benchmark-program.v1` are deliberately avoided: URL4 already names its executable
artifact an expression, while the response represents the whole Benchmark rather than only its
executable field. “Manifest,” “plan,” “workflow,” “harness,” and “template” are also avoided for
this contract because they either describe the superseded architecture or suggest a second DSL.

This puts knowledge with its owner. Benchmark authors can implement DRACO, HealthBench, MedXpert,
SciCode, or a future unusual protocol in Engine-side Python and generate typed, canonical URL4
without teaching the SDK Benchmark semantics. Candidate authors keep the small Model/Fusion
interface. The SDK performs one universal AST link instead of interpreting an action list or
workflow schema, so a new Benchmark requires an Engine deployment rather than an SDK release.

The design also preserves the one-fetch constraint. The Benchmark response is reusable across all
Candidates in an Evaluation and may be cached by Benchmark revision and Case selection. There is
no Candidate-specific planning request before execution. The final URL4 contains both complete
expressions; Candidate Invocation sites are explicit, while the Candidate expression is included
once and invoked like a function. “Complete” means self-contained and directly executable on an
Engine with the referenced Benchmark routes and data installed, not macro-expanded duplication of
the same Candidate graph at every invocation site.

The current URL4 runtime supports this without a `url4` package change. A binding alone is data and
cannot be called, and a binding cannot select a dynamic route. However, nested expressions capture
outer bindings, named dependencies carry earlier results into later calls, and
`Url4Node.evaluate(expression, env=...)` evaluates the bound Candidate expression in-process. A
runtime probe demonstrated two ordered Candidate Invocations where the second input contained the
first answer. The production implementation and regression suite now cover ordered calls, nested
Fusions, concurrent calls, usage, cancellation, typed failures, recursion, and total-call bounds.
The `/candidate` route exposes that existing capability through one deep interface: Candidate
expression plus input in, answer out.

Benchmark-owned execution policy crosses that same boundary. In particular, retrieval cannot be
a global model-route default once one Runner hosts both DRACO (which requires guarded web search)
and IFEval (which requires no search at all). A Benchmark therefore annotates its `/candidate`
call with the narrow Runner-interpreted retrieval controls. The Runner applies them task-locally
to every model call inside that Candidate, after Candidate-owned params, and resets them when the
invocation ends. DRACO embeds its excluded-domain set in the expression and hashes it into the
Benchmark revision; IFEval explicitly disables search. This keeps policy visible in the complete
shareable URL4 without adding Benchmark logic to the SDK or leaking policy between concurrent
Candidate invocations.

A cross-package DRACO execution test additionally runs the Engine-produced expression after SDK
linking against the real Runner node: one Candidate Invocation, five fixed Judge passes, and the
real aggregate implementation. This test caught and removed an invalid reduce-over-iteration
encoding that parse-only tests accepted, so executable linkage—not textual round-tripping—is the
contract gate.

Each registered Benchmark also owns installation of the deterministic routes referenced by its
expression. Routes are private, revision-qualified names such as
`/benchmarks/draco/<revision>/tasks`; the public identity remains the stable name `draco` and the
resource separately reports its immutable revision. The same registry builds the control-plane
resource and installs the Runner routes, preventing expression/Runner drift where a valid resource
later fails with `endpoint_not_found`. Asset reads are lazy, so a general Runner can install
definitions whose private dataset is present only in the corresponding Benchmark image.

Deterministic functions run in-process rather than through benchmark-specific TOML commands. The
cross-Case row collection reaches Aggregation in URL4 context, not a subprocess argv token. A
complete DRACO run can exceed the operating system's argument-size limit; in-process context has
no such boundary, preserves typed Engine errors, and removes TOML/CLI/path coordination from
Benchmark authoring.

Candidate input has one universal transport boundary rather than one protocol per Benchmark.
Ordinary text crosses as a string. Benchmarks that need native chat turns use the versioned
`screamingface.candidate-input.v1` envelope produced by `chat_input(messages)`. The Runner
validates that envelope and preserves its user, assistant, developer, and system roles before
adding Candidate-owned system policy. HealthBench-style histories and MedXpert's reasoning/commit
turns therefore remain native chat without adding Benchmark knowledge to the SDK or changing the
Candidate expression interface.

The structural link is deliberately small. The SDK parses both expressions, binds the canonical
Candidate text once as a weight-zero source named `candidate`, and nests the Benchmark as an
unnamed source under the same lexical scope. An empty outer intent returns the nested Benchmark's
result without adding a result label. A top-level Benchmark `Iteration` first receives a
weight-zero `benchmark_result` passthrough because URL4's surface grammar otherwise interprets a
nested top-level `*(...)` as the outer reduce envelope. This is an AST construction rule, not a
Benchmark template or protocol branch.

## Considered options

- **A Client-interpreted workflow schema** was rejected because it is a second execution language.
  A novel Benchmark would require SDK semantics, version negotiation, and another compiler beside
  URL4.
- **A universal ordered action list** was rejected because order does not define data flow, state,
  privacy, failure, or aggregation semantics. Making it sufficient recreates a workflow schema
  under less precise names.
- **Candidate-specific Engine compilation via POST** was rejected because it adds a request for
  every Candidate, makes the Engine compile SDK-owned policy before execution, and prevents one
  reusable fetch from supplying everything needed to construct every final URL4.
- **One opaque Benchmark execution route** was rejected because it hides the Benchmark computation
  and does not satisfy the independently inspectable and shareable URL4 goal.
- **Shipping Benchmark compilers in the SDK** was rejected because every new Benchmark or protocol
  change would require an SDK release and duplicate Engine-owned knowledge.
- **Manually authored URL4 templates** were rejected as the Benchmark-author interface. Benchmark
  implementations generate typed URL4 trees, and the SDK parses and links those trees
  structurally; neither side performs unsafe string replacement.
- **Changing URL4 to add functions, modules, or a sequential fold** could provide a cleaner
  language-level abstraction later, but it is not currently available and is unnecessary for the
  required architecture.
- **Inlining the Candidate graph at every invocation** is possible but duplicates large Fusion
  graphs, inflates GET targets, and adds no behavior. It remains a fallback only if in-process
  Candidate Invocation cannot satisfy an execution or telemetry invariant.

## Consequences

- `/candidate` must inherit the outer Evaluation's cancellation, capabilities, credentials,
  accounting, Benchmark-owned retrieval policy, and failure semantics, and enforce recursion and
  total-call limits.
- Benchmark expressions must be canonical, parseable, Candidate-independent, and validated before
  the first paid call. The SDK must link ASTs rather than concatenate URL4 text.
- The executable resource reports only exact, reusable facts: stable identity, immutable
  revision, Case counts, required fixed models, and canonical URL4. Human-facing title and
  description remain in the catalog. It does not
  publish unused capability declarations or predicted invocation/operation counts; actual usage
  belongs to execution telemetry.
- Every Candidate result has one canonical, higher-is-better `score`. `metrics` contains only
  supporting diagnostics, not a second copy of the score. Benchmark-specific score names and
  direction flags are deliberately absent from the universal Client interface.
- Reports carry both Benchmark id and revision, so scores from different dataset/protocol snapshots
  never look interchangeable merely because the public name stayed stable.
- Stateful Benchmarks express ordered Candidate Invocations and dependencies in their generated
  expression. SciCode is the acceptance case for repeated invocation with prior Candidate output.
- Full-suite expression and encoded-GET sizes must be measured against the deployed transport
  limit. Size is an acceptance gate, not a reason to introduce a workflow schema pre-emptively.
- The Candidate-specific planning endpoint and its SDK request/response types are superseded once
  the one-fetch Benchmark contract passes the vertical-slice gates. They have been removed from
  the implemented DRACO vertical slice.
