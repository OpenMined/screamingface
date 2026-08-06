---
status: accepted
date: 2026-08-05
supersedes: 0003-benchmark-family-resource-and-universal-candidate-bindings.md
amends: 0001-link-benchmark-and-candidate-expressions.md
---

# Publish flat Benchmarks and isolate Candidate Invocation in the ScreamingFace Engine

The ScreamingFace Engine publishes one `screamingface.benchmark.v1` resource for every
independently executable protocol. Related protocols may share Cases, assets, and runtime code,
but callers select flat ids such as `ifeval`, `ifeval/self-corrective`, and
`ifeval/verifying-ensemble`. There is no public Benchmark Family resource, nested Variant map,
or rolling-compatibility fallback.

The bare id names the canonical default protocol. Each alternative has its own URL4 and immutable
revision. `variant` is descriptive metadata rather than an execution parameter. The resource's
single `case_count` is the complete installed size; an Evaluation limit changes the generated
URL4 slice and the resulting Report count, not the Benchmark metadata.

The SDK links universal structural bindings rather than learning Benchmark protocols:
`$candidate`, `$candidate_members`, and `$candidate_synthesizer`. Engine-owned URL4 chooses which
bindings it uses and owns all retries, verification, Judge calls, and Aggregation. There is no
public binding, parameter, fixed-Model, or validation schema.

The linker emits every direct member once as an ordinary inert `$candidate_member_N` URL4
binding. `$candidate_members` is a native URL4 struct whose ordered `member_N` entries contain a
display name and a reference to that binding. It is not Base64 or embedded JSON carrying another
executable representation: the final linked URL4 is the shareable artifact and visibly exposes
every submitted Model expression. A Benchmark may use the struct directly or prepare it through
its own private route.

`$candidate` contains inert URL4 text. Current URL4 bindings substitute values but do not call a
bound expression with a fresh lexical environment. The ScreamingFace Engine therefore registers
one reserved `/candidate` route. A Benchmark supplies input as context and the linked Candidate
expression as intent; the route evaluates that expression with a fresh `$input`.

`/candidate` is a standard URL4 host extension, not URL4 language behavior. `packages/url4` knows
only that a relative route is resolved through its configured world. A compatible core without
that world reports the ordinary missing-route failure, just as it would for an absent Model or
Benchmark route.

Candidate execution uses a restricted URL4 node rather than the orchestration node. The
restricted node receives permitted Model, command, and data adapters but never `/candidate`,
private Benchmark routes, or unrestricted absolute-URL outbound access. This prevents a
Candidate from reading Cases, rubrics, verifier records, or Aggregation internals. The shared
Candidate Invocation adapter retains limits, recursion protection, task-local retrieval policy,
credentials, cancellation, observation, usage, and typed errors.

Model configuration follows ownership rather than artificial symmetry. A Benchmark-owned Model
is pinned directly in Benchmark URL4, declared by the Runner, contract-tested against AI Gateway,
and hashed into the Benchmark revision; DRACO's grading Judge is the initial example. A
Candidate-owned Model arrives
through the submitted Model or Fusion; `ifeval/verifying-ensemble` uses the Fusion's explicit
synthesizer as its protocol Judge. Its private route parses the referenced URL4 expressions and
enforces two-to-four direct Models plus one direct-Model synthesizer before paid calls. Model-route
availability remains the ordinary Candidate Invocation contract. Neither case needs public
`required_models` metadata.

## Considered options

- **Public Benchmark Family resources** were rejected because the container is not executable,
  forces local Variant selection, and adds a second public noun without protocol behavior.
- **A public Benchmark parameter or validation schema** was rejected because it grows a second
  execution DSL beside the opaque URL4.
- **Calling `Url4Node.evaluate()` from Benchmark Python** was rejected because Candidate
  Invocation would leave the complete URL4 artifact.
- **Adding callable bindings to `packages/url4`** was rejected for this landing because it adds a
  general language capability solely for a ScreamingFace domain operation.
- **Inlining the Candidate graph at every call site** was rejected because it duplicates Fusion
  graphs and complicates Benchmark-owned policy propagation without changing behavior.
- **Evaluating the Candidate against the orchestration node** was rejected because it exposes
  private Benchmark routes and unrestricted outbound access to Candidate-controlled URL4.
- **Treating the paper's evaluated Judge models as a protocol allowlist** was rejected because its
  table records experimental configurations, not a stated validity constraint. Other Judges are
  custom configurations and must not be presented as reproductions of Ens-1 through Ens-5.
- **Pinning every Judge in the Benchmark** was rejected because the verifying-ensemble Judge is
  part of the submitted system under evaluation.

## Consequences

- Catalog and detail interfaces become flat and breaking; no family-schema compatibility branch
  remains.
- Slash-qualified ids must be routed as complete ids by Engine REST and SDK clients.
- Candidate Invocation moves out of the AI Gateway connector into a focused ScreamingFace Engine
  runtime module; Engine assembly wires provider-backed Model handlers into both URL4 worlds.
- Final artifacts remain valid standard URL4 but require their declared execution world, as they
  already require installed Model and deterministic Benchmark routes.
- Isolation is verified at the assembled Engine-world interface, not through private handler
  call graphs.
