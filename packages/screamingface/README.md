# screamingface

Evaluate Models and Fusions against URL4-native research Benchmarks.

> **Development status:** immutable Model/Fusion authoring, Engine-backed discovery, the direct
> evaluation API, and the confirmed `url4-cloud` lifecycle are
> implemented. The current MVP Engine publishes canonical `draco` plus the non-comparable
> `draco/lite` and `draco/smoke` development protocols as independently revisioned Benchmark
> resources with complete URL4 expressions. There is no fixture, embedded benchmark runtime, or
> Client-side execution fallback.

## Target v1 workflow

The approved Python workflow is:

```python
import screamingface as sf

sf.connect()  # notebook panel; connect any providers enabled by this Engine

opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

frontier_pair = sf.Fusion(
    [opus, gpt],
    name="frontier-pair",
    synthesizer="openrouter/anthropic/claude-opus-4.8",
)

report = sf.evaluate(
    [opus, gpt, frontier_pair],
    benchmark="draco",
    limit=1,
)
```

`evaluate(...)` requires an explicit Benchmark id, fetches its Candidate-independent URL4
expression once, compiles and structurally links every Candidate, executes those complete URL4s
concurrently, and returns one immutable `Report` in declared order. There is no implicit default
Benchmark selection. All no-spend validation finishes before the first paid Run starts. Execution
requires a Benchmark Runner image containing the expression's referenced data, grading, and
Aggregation routes.

The installed `draco` definition always refers to the complete official 100-task Benchmark;
`limit=1` merely runs one Case. Grading uses five independent Judge passes per criterion. The
current executable Judge is `openrouter/google/gemini-3.1-pro-preview`, Google's official
replacement for the paper's retired `Gemini-3-Pro Preview`. Reports should disclose that Judge
version difference when comparing scores with the paper.

Related protocols are explicit Benchmark ids rather than SDK options. `draco/lite` and
`draco/smoke` reduce the protocol's fixed Case, criterion, and Judge-pass selections for
development, and their scores are deliberately not comparable with canonical DRACO. The SDK
fetches and links each resource generically; it does not dispatch on those names.

### Candidate policy

Models work without prompt configuration. For a Fusion that produces a final answer, name its
synthesizer explicitly; neither the Engine catalogue nor a Benchmark silently chooses one. The SDK
supplies general answer and constraint-aware synthesis prompts, then embeds the explicit Model
routes and resolved prompt defaults in the final URL4:

```python
plain = sf.Model("openrouter/openai/gpt-5.5")
pair = sf.Fusion(
    [opus, gpt],
    synthesizer="openrouter/anthropic/claude-opus-4.8",
)
```

Researchers can override only Candidate-owned policy when an experiment needs it:

```python
careful = sf.Model(
    "openrouter/openai/gpt-5.5",
    prompt="Answer from primary evidence and follow every requested output constraint.",
    params={"reasoning_effort": "high"},
)

constraint_aware = sf.Fusion(
    [opus, gpt],
    synthesizer="openrouter/openai/gpt-5.5",
    prompt="Produce one final answer that preserves every constraint in the original request.",
    params={"reasoning_effort": "high"},
)
```

These overrides never alter Benchmark-owned Cases, fixed Judge models or prompts, Grading, or
Aggregation. Prompt defaults and explicit overrides are embedded in each final URL4. A Fusion may
be authored without `synthesizer=`, but planning rejects it before spend whenever the selected
Benchmark invokes the whole Fusion or its synthesizer. When a Benchmark binds the synthesizer as a
separate structural component, the model route and `params` remain Candidate-owned while the
Benchmark owns that role's instructions; an ordinary whole-Fusion blending prompt is not reused as
a Judge prompt. The Benchmark sets the retrieval ceiling on `/candidate`; ordinary Model and
Fusion-member calls inherit it, while the SDK compiler always pins whole-Fusion synthesis to
`web_search=false`. Users cannot override retrieval through Candidate `params`. DRACO can therefore
offer guarded web access to answer producers without silently giving synthesis a stronger
experiment than the published protocol.

Each flat Benchmark resource uses `screamingface.benchmark.v1` and carries one canonical `url4`
plus an opaque immutable `revision`. The SDK fetches the requested id, compiles a Model or Fusion
into an expression accepting `$input`, and links only the universal bindings referenced by that
Benchmark (`$candidate`, direct members, or an explicit synthesizer). A Benchmark invokes a bound
expression through `/candidate`; that route evaluates it inside the same Engine job, not through
an additional Client or control-plane request. Unsupported Candidate shapes fail with typed errors
instead of falling back to Client-side execution.

The Candidate input is normally plain text. Engine-owned Benchmarks that require native chat
history wrap structured turns in the versioned Candidate-input envelope; the Runner preserves
their roles while the SDK continues to treat `$input` as opaque. This supports multi-turn and
stateful protocols without a Client-interpreted workflow language.

## Install

```bash
pip install screamingface
```

Python 3.12 or newer is required.

## Engine configuration

The module-level interface constructs one process-wide Client lazily against the hosted development
Engine. Configure it explicitly when selecting another Engine:

```python
import screamingface as sf

sf.configure(engine_url="http://127.0.0.1:9108")
report = sf.evaluate(candidates, benchmark="draco", limit=1)
sf.close()
```

`sf.configure(...)` replaces and closes any existing default Client. `sf.close()` releases the
default Client and clears it so the next module-level operation can construct a fresh one. Setting
`SCREAMINGFACE_ENGINE_URL` before the first operation remains supported for environment-driven
configuration.

The Client hides Benchmark fetching, URL4 compilation, REST/WebSocket transport, Event replay,
and Report decoding behind `sf.evaluate(...)`.

### Hosted caller authentication

Hosted Engines may be protected by Cloudflare Access. No authentication selector,
Cloudflare service token, or provider key is passed to the Client:

```python
client = sf.Client(engine_url="https://fusion.dev.screamingface.ai")
client.login()  # optional: the first protected request also starts login
```

The Client discovers the Access application audience from the Engine redirect, creates an
ephemeral encryption keypair, and opens Cloudflare Access login in the user's browser. It polls
Cloudflare's encrypted transfer service and decrypts the returned application token locally. The
token is held only in process memory and sent as `Cf-Access-Token` on REST requests and WebSocket
handshakes. `client.logout()` forgets it and opens the Engine's Cloudflare Access logout endpoint
in the browser. Concurrent callers share one browser login, a server-rejected token starts one fresh
login even before its local expiry, and an Access-specific WebSocket rejection is retried once after
reauthentication.

The login URL is always printed. Desktop Python also attempts to open it automatically; in Jupyter
or Colab, click the displayed URL and complete the configured Access login. This flow does not use
a localhost callback and does not require dynamic client registration or **Allow loopback
clients**. The user's email or identity must be allowed by the Cloudflare Access policy for the
hosted Engine. The Client prints a confirmation after it receives and validates the transferred
token; `client.authenticated` then returns `True`. Local Engines that do not advertise Access
continue to work without authentication.

The public authentication boundary is the URL4 Cloud origin, not AI Gateway. After Cloudflare
Access authenticates the caller, the deployment passes the verified identity to URL4 Cloud as
`X-User-Email`. URL4 Cloud forwards that identity—not the Access token—to the internal AI Gateway.
Consequently, the Python Client never calls AI Gateway or a model provider directly:

```text
Python Client -- Cf-Access-Token --> Cloudflare Access --> URL4 Cloud
                                                          -- X-User-Email --> AI Gateway
                                                                             -- provider key --> Provider
```

These credentials have deliberately different lifetimes and owners:

- The Cloudflare Access token exists only in Client memory and authenticates calls to URL4 Cloud.
- `X-User-Email` is derived from the edge-verified identity and selects the AI Gateway account.
- A provider key entered through `sf.connect()` travels through URL4 Cloud once for AI Gateway to
  validate and store; URL4 Cloud does not retain it.
- No shared Cloudflare key, provider key, or administrator key is configured on the Client.

If the hosted application later adopts Cloudflare Managed OAuth, the Client can migrate to OAuth
discovery and authorization code + PKCE. That is a possible future protocol, not an additional
authentication mode implemented by this package today.

In a notebook, `sf.connect()` displays the connection panel bound to the lazy default Client. For a
remote Engine, the panel first checks noninteractively whether Cloudflare Access is present. An
unprotected remote Engine loads its providers normally; a protected Engine shows the Engine login
row and loads provider rows only after login succeeds. Login waits in the background, so the
notebook remains usable and the row becomes
**Cancel** while the encrypted transfer is pending. Opening `sf.connect()` again reflects that same
in-progress login, and all open panels follow its eventual login/logout state. Cancel stops only the
pending transfer without opening another browser page;
Log out clears the completed token and opens Cloudflare Access logout. An explicit Access rejection
is shown in the panel, while an abandoned browser flow remains cancelable until its timeout. Local
Engines omit this row. This one-time transfer polling is separate from the authenticated WebSocket
used for model execution.
The Engine derives its connection catalogue from AI Gateway's enabled provider plugins. API keys
are supported for any provider that advertises `api_key`, and the panel can start OAuth for any
provider that advertises `oauth`. A key is sent only to the SF Engine,
which asks AI Gateway to validate and store it; the Python Client does not persist it and never
calls AI Gateway or a provider directly. One OpenRouter key covers every enabled `openrouter/...`
route, but does not authorize direct routes owned by other providers.

```python
sf.connect()
flow = sf.connect("codex", method="oauth")
flow.authorize_url
connection = flow.wait()  # or flow.cancel()
sf.connections.list()
sf.connections.get("openrouter")
sf.disconnect("openrouter")
```

The same panel retains OAuth, pending, authorization, cancellation, and reauthentication states.
The Engine catalogue remains authoritative about which methods each provider supports.

Local and hosted Engines use the same Client contract. Local mode may run the URL4 executor
in-process with an in-memory event bus; hosted mode may use the REST/WebSocket control plane with
NATS and scheduled workers. From the Client's perspective only `engine_url` changes. Generic URL4
execution remains benchmark-agnostic; installed Engine definitions own Benchmark semantics.

## Progress and Reports

`evaluate` consumes the Engine's REST and WebSocket lifecycle internally. An optional callback
receives typed CloudEvents views in sequence:

```python
def observe(event: sf.Event) -> None:
    print(event.kind)


report = sf.evaluate(
    candidates,
    benchmark="draco",
    limit=1,
    on_event=observe,
)
```

If a callback raises, the Client attempts to cancel all active Candidate Runs and re-raises the
original exception.

One `Report` shape covers one or many Candidates:

```python
report.ok
report.benchmark
report.case_count
report.candidates[0]
report.candidates["frontier-pair"]
report.candidates["frontier-pair"].run_id
report.candidates["frontier-pair"].url4
report.candidates["frontier-pair"].operations
report.candidates.only
report.failures
report.usage
report.started_at
report.completed_at
report.to_dict()
report.to_json()
```

Each entry in `CandidateResult.operations` is a public immutable `sf.OperationInfo` value.

Authentication, validation, transport, execution, protocol, and invalid-result failures raise
typed exceptions. Partial-result reporting remains a later Engine/Report contract.

Expected SDK failures inherit from `ScreamingFaceError` and always carry a stable error code, plus
an optional HTTP status, structured details, remediation hint, and `permanent`/`retryable`
classification. The public classes reflect distinct recovery actions:

- `EngineUnavailableError`: start, reconfigure, or retry the Engine.
- `AuthenticationError`: authenticate the caller again.
- `PlanningError`: change the Candidate, Benchmark, Model, or evaluation configuration.
- `ExecutionError`: inspect or retry a Run that failed after reaching the Engine.
- `ProviderConnectionError`: change a provider credential or provider connection.

IPython and Jupyter render these failures as a concise message, hint, and code instead of exposing
dependency tracebacks. Notebook panels render the same safe text inline. Programmatic callers can
catch a specific recovery class or catch `ScreamingFaceError` for every expected SDK failure;
translated low-level failures remain attached through `error.__cause__` for debugging. Programmer
errors such as invalid Python argument types retain their normal tracebacks.

If a Benchmark returns both `coverage` and `coverage_target` metrics, evaluation emits the
filterable public
`CoverageWarning` when coverage misses that target; accepted/expected verdict counts are included
when the Benchmark provides them. This warning does not discard the Report.

## Ownership boundary

```text
Researcher or SF App
        ↓
ScreamingFace Python Client
  Recipe authoring · URL4 compilation · Events · Reports
        ↓  REST + WebSocket
SF Engine
  URL4 execution · Benchmarks · grading · aggregation · Tools
        ↓
AI Gateway
  provider credentials · model dispatch
```

The Client calls only its configured SF Engine. It never calls AI Gateway, model providers,
Tavily, or Benchmark datasets directly. Local and hosted Engines expose the same Client-visible
contract; in-memory channels, NATS, workers, and deployment topology are Engine details.

Models and Fusions are immutable, Client-independent, and network-free. Models select routes and
optional answer policy; Fusions declare topology and optional synthesis policy. The SDK resolves
their defaults and compiles the Candidate expression. Benchmarks are immutable Engine protocols
that own Cases, Candidate Invocation order, fixed Judge configuration, Grading, Aggregation,
and execution policy. Reports record the exact Engine-pinned Benchmark revision.

Equivalent resolved Model calls deduplicate by content inside a compiled Candidate graph.
Explicit Model names identify intentional independent samples. Durable reuse across Candidates,
retries, and resumed Evaluations belongs to the Engine's provenance-aware response cache.

## Discovery

An Engine implementing the provisional catalogue contract exposes typed discovery:

```python
models = sf.models.list()
gpt_details = sf.models.get("openrouter/openai/gpt-5.5")
benchmarks = sf.benchmarks.list()
```

Explicit Clients provide the same interface through `client.models.list()` and
`client.models.get(model_id)` alongside `client.benchmarks.list()`; asynchronous Clients use the
same names with `await`. `ModelInfo` rows are lightweight summaries containing the supported
parameter and tool names. `ModelDetails` is the profile-specific contract for one Model, including
typed parameter schemas, gateway policy, provider evidence, tools, transport, and freshness.

Explicit Candidate parameters are preflighted against those details before execution. The SDK
fetches one detail document per distinct Model with explicit overrides on an operation the selected
Benchmark actually invokes; parameter-free Candidates and unused structural components perform no
detail lookup. Missing, disabled, wrong-type, or out-of-range values fail before any paid Run
begins. Model capability data always comes from the Engine/AI Gateway contract—there is no GPT- or
provider-specific parameter table in the SDK.

The returned catalogues are immutable ordered sequences: iteration, indexing, slicing, and
`len()` work normally in scripts and sidecars. Evaluating one in Jupyter automatically renders a
searchable catalogue when the `notebook` extra is installed, with escaped static HTML and compact
terminal representations as fallbacks. Notebook rendering does not change the underlying values
or introduce a separate discovery operation.

## Examples

- [`examples/00_quickstart.ipynb`](examples/00_quickstart.ipynb): one Candidate through the
  bounded, diagnostic `draco/smoke` protocol, from discovery through Report evidence.
- [`examples/01_client_tour.ipynb`](examples/01_client_tour.ipynb): a no-spend tour of Client
  lifecycle, hosted authentication, discovery, connections, authoring, events, errors, Reports,
  and the asynchronous API.
- [`examples/05_draco_lite_e2e.ipynb`](examples/05_draco_lite_e2e.ipynb): an opt-in,
  retrieval-aware comparison over the small, non-comparable `draco/lite` protocol, with typed
  Candidate and Case inspection.
- [`examples/06_draco_full_e2e.ipynb`](examples/06_draco_full_e2e.ipynb): the complete seven-solo,
  nine-Fusion canonical DRACO experiment and audit workflow, with execution disabled by default.

The notebooks are deterministic outputs of `scripts/build_notebooks.py`.

## Development

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov=screamingface --cov-fail-under=95 -q
uv run --extra notebook python scripts/check_notebooks.py
uv build
uv run python scripts/check_distribution.py
```
