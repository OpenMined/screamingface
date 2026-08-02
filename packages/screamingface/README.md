# screamingface

Evaluate Models and Fusions against URL4-native research Benchmarks.

> **Development status:** immutable Model/Fusion authoring, Engine-backed discovery, the direct
> evaluation API, Model/Fusion authoring, and the confirmed `url4-cloud` lifecycle are
> implemented. The current Engine publishes `draco-lite` through the implemented one-fetch
> Benchmark-expression contract and its Runner-native URL4 routes. Additional Benchmark adapters
> remain pre-release work. There is no fixture, embedded benchmark runtime, or Client-side
> execution fallback.

## Target v1 workflow

The approved Python workflow is:

```python
import screamingface as sf

sf.connect()  # notebook panel; connect the Engine's OpenRouter account once

opus = sf.Model("openrouter/anthropic/claude-opus-4.8")
gpt = sf.Model("openrouter/openai/gpt-5.5")

frontier_pair = sf.Fusion(
    [opus, gpt],
    name="frontier-pair",
)

report = sf.evaluate(
    [opus, gpt, frontier_pair],
    limit=1,
)
```

`evaluate(...)` uses the Engine's explicitly declared default Benchmark, fetches its
Candidate-independent URL4 expression once, compiles and structurally links every Candidate,
executes those complete URL4s concurrently, and returns one immutable `Report` in declared order.
Pass `benchmark="draco-lite"` only when making that default explicit. All no-spend validation
finishes before the first paid Run starts. Execution requires a Benchmark Runner image containing
the expression's referenced data, grading, and Aggregation routes.

### Candidate policy defaults

Models and Fusions work without prompt configuration. The SDK supplies a general answer prompt,
and a Fusion additionally receives the SDK's default synthesizer and constraint-aware synthesis
prompt:

```python
plain = sf.Model("openrouter/openai/gpt-5.5")
pair = sf.Fusion([opus, gpt])
```

Researchers can override only Candidate-owned policy when an experiment needs it:

```python
careful = sf.Model(
    "openrouter/openai/gpt-5.5",
    prompt="Answer from primary evidence and follow every requested output constraint.",
    params={"reasoning": "high"},
)

constraint_aware = sf.Fusion(
    [opus, gpt],
    synthesizer="openrouter/openai/gpt-5.5",
    prompt="Produce one final answer that preserves every constraint in the original request.",
    params={"reasoning": "high"},
)
```

These overrides never alter Benchmark-owned Cases, fixed judge models or prompts, Grading, or
Aggregation. Resolved defaults and overrides are embedded in each final URL4.

The Benchmark resource uses `screamingface.benchmark.v1` and carries its canonical expression in
`url4`. The SDK compiles a Model or Fusion into an expression accepting `$input`, binds it once as
`$candidate`, and links it to the Engine expression using URL4's AST. A Benchmark invokes it with
`/candidate(input)!$candidate`; that route evaluates it inside the same Engine job, not through an
additional Client or control-plane request. Unsupported Candidates fail with typed errors instead
of falling back to Client-side execution.

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

The module-level interface constructs one process-wide Client lazily. Set the Engine URL before
the first catalogue, connection, or evaluation operation only when overriding the local default:

```python
import os

os.environ["SCREAMINGFACE_ENGINE_URL"] = "https://engine.screamingface.ai"

import screamingface as sf

report = sf.evaluate(candidates, limit=1)
```

The Client hides Benchmark resolution, URL4 compilation, REST/WebSocket transport, Event replay,
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
The current Engine advertises one OpenRouter API-key row. The key is sent only to the SF Engine,
which asks AI Gateway to validate and store it; the Python Client does not persist it and never
calls AI Gateway or OpenRouter directly.

```python
sf.connect()
sf.connections.list()
sf.connections.get("openrouter")
sf.disconnect("openrouter")
```

The same panel retains the OAuth, pending, authorization, cancellation, and reauthentication UI
states for Engines that advertise those methods later. They do not add a second connection path:
the Engine catalogue remains authoritative.

Local and hosted Engines use the same Client contract. Local mode may run the URL4 executor
in-process with an in-memory event bus; hosted mode may use the REST/WebSocket control plane with
NATS and scheduled workers. From the Client's perspective only `engine_url` changes. Generic URL4
execution does not itself provide the still-missing ScreamingFace Benchmark and capability
contracts.

## Progress and Reports

`evaluate` consumes the Engine's REST and WebSocket lifecycle internally. An optional callback
receives typed CloudEvents views in sequence:

```python
def observe(event: sf.Event) -> None:
    print(event.kind)


report = sf.evaluate(
    candidates,
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
required capabilities, and execution policy.

Equivalent resolved Model calls deduplicate by content inside a compiled Candidate graph.
Explicit Model names identify intentional independent samples. Durable reuse across Candidates,
retries, and resumed Evaluations belongs to the Engine's provenance-aware response cache.

## Discovery

An Engine implementing the provisional catalogue contract exposes typed discovery:

```python
models = sf.models.list()
benchmarks = sf.benchmarks.list()
```

Explicit Clients provide the same interface through `client.models.list()` and
`client.benchmarks.list()`; asynchronous Clients use the same names with `await`. These catalogue
schemas remain provisional until the production SF Engine contracts are finalized.

The returned catalogues are immutable ordered sequences: iteration, indexing, slicing, and
`len()` work normally in scripts and sidecars. Evaluating one in Jupyter automatically renders a
searchable catalogue when the `notebook` extra is installed, with escaped static HTML and compact
terminal representations as fallbacks. Notebook rendering does not change the underlying values
or introduce a separate discovery operation.

## Examples

- [`examples/00_quickstart.ipynb`](examples/00_quickstart.ipynb): runnable Model/Fusion authoring
  plus the canonical direct evaluation flow.
- [`examples/05_draco_lite_e2e.ipynb`](examples/05_draco_lite_e2e.ipynb): one-case local
  DRACO-Lite vertical slice.
- [`examples/06_draco_full_e2e.ipynb`](examples/06_draco_full_e2e.ipynb): the complete seven-solo,
  nine-Fusion DRACO experiment ported from `screamingface-benchmarks` to the Client SDK.

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
