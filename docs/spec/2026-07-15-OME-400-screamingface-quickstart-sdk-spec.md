---
title: ScreamingFace production quickstart SDK thin slice
ticket: OME-400
status: approved
date: 2026-07-15
updated: 2026-07-16
---

# ScreamingFace production quickstart SDK thin slice

## 1. Purpose

OME-400 needs an importable Python package that makes the product quickstart honest. The exact
connect → pick → compose → run → compare API must execute against real providers by default,
while an explicit deterministic mock mode keeps CI and committed GitHub notebook output safe and
reproducible.

The package lands at `packages/screamingface`, publishes/imports as `screamingface`, and depends
on `url4` for workflow representation and execution. It consumes the existing AI Gateway HTTP
API; it never imports `apps/aigateway` internals.

This is the first production slice, not the entire product-demo contract or DRACO pipeline.

## 2. User story

The live path is:

```python
import screamingface as sf

session = sf.setup()
ids = sf.models.list(max_price=20)

fusion = sf.Fusion(
    "fusion",
    models=ids[:3],
    reduce="majority_vote",
    judge=ids[0],
)

fusion                 # lineup table
fusion.url4            # canonical recipe on explicit request
run = fusion.evaluate("gpqa", first=20, seed=0)
run.score, run.baseline, run.gain
```

`sf.setup()` means real mode. It discovers or connects to AI Gateway, authenticates the user to
their encrypted gateway credential vault, and connects BYOK provider accounts. Gateway login and
provider authorization are distinct: login identifies the vault owner; provider API keys
authorize and bill upstream inference. It never silently falls back to simulation.

The CI/GitHub-rendering path is explicit:

```python
session = sf.setup(mode="mock", static_widgets=True)
```

Mock output must state that model answers and costs are simulated. It must never be presented as
a provider benchmark result.

## 3. Architecture and ownership

```text
Notebook / public ScreamingFace API
                 |
                 v
Fusion + benchmark application layer
                 |
                 v
URL4 expression + public Url4Node
                 |
                 v
CompletionPort
      +----------+------------------+
      |                             |
      v                             v
DeterministicMockAdapter     AIGatewayAdapter (HTTP)
                                    |
                                    v
                    accounts, encrypted credentials,
                    provider routing, token refresh
                                    |
                                    v
                           real model providers
```

Responsibilities:

- ScreamingFace owns an embedded `Url4Node`; notebook users do not start or configure a URL4
  server for OME-400.
- The node resolves each `sf-model://...` source through a ScreamingFace outbound I/O adapter,
  which selects deterministic mock execution or an AI Gateway completion.
- `Url4Node.serve()` and remote `url4.Client("url4://...")` deployment remain valid URL4 SDK
  capabilities but are outside the quickstart's runtime topology.

- `screamingface`: setup UX, gateway client, catalog/pricing view, Fusion, benchmark loading,
  scoring, provenance, and notebook representations.
- `url4`: canonical workflow expression, dependency graph, fan-out, and reduction scheduling.
- `aigateway`: gateway accounts/JWTs, provider OAuth/API keys, encrypted credential storage,
  profile selection, provider calls, retries/cache, and normalized completion responses.
- provider: inference and billing.

Core domain objects depend on ports, never concrete adapters. The SDK talks to AI Gateway only
through its published HTTP contract.

## 4. Session setup and authentication

### 4.1 API

```python
sf.setup(
    *,
    mode: Literal["live", "mock"] = "live",
    gateway: str | None = None,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    profiles: dict[str, str] | None = None,
    static_widgets: bool = False,
    interactive: bool | None = None,
) -> Session | SetupPanel
```

The zero-argument default is production/live mode.

Gateway discovery order:

1. explicit `gateway=`;
2. `SCREAMINGFACE_GATEWAY_URL`;
3. `http://127.0.0.1:9105` when `/healthz` succeeds; and
4. otherwise a typed `GatewayUnavailable` result/error with startup instructions.

There is no implicit hosted URL until one is deployed and configured. There are no default
usernames, passwords, tokens, provider credentials, or mock fallback.

Authentication order:

1. explicit `token=`;
2. `SCREAMINGFACE_GATEWAY_TOKEN` for headless use;
3. explicit `username=` plus `password=` via `POST /v1/auth/login` for programmatic login.

The SDK validates the session with `GET /v1/auth/me`. Gateway JWTs live in memory by default.
Passwords are transient and provider credentials are never retained by the SDK. AI Gateway's
account authentication and OAuth/API-key connection infrastructure is already implemented. This
thin SDK consumes that completed infrastructure through JWT or programmatic username/password
login and existing gateway connections. The brand-demo `01_authentication.ipynb` panel remains a
simulated UX specification rather than production provider execution; it is not copied into this
package.

Repeated `sf.setup()` calls for the same gateway in the same Python process reuse the active,
authenticated Session. Calling `sf.shutdown()`, restarting the kernel, switching gateways, or
supplying explicit credentials/profile selection establishes a new session.

A zero-argument setup in a notebook returns a real `ipywidgets` login panel when the gateway is
reachable but unauthenticated. Password controls are masked and cleared after submission. In a
headless process, the same call fails safely with `LoginRequired`; callers pass a token or an
explicit username/password pair. `interactive=False` forces headless behavior, while
`static_widgets=True` provides the deterministic non-interactive HTML twin used in committed
notebook output.

### 4.2 Provider connections

Setup lists active connections from `GET /v1/oauth/connections` and loaded providers from
`GET /v1/models`. Because the current gateway response does not publish authentication
capabilities, OME-400 uses a clearly marked SDK-local compatibility map for `anthropic`,
`antigravity`, `codex`, `gemini-cli`, `huggingface`, and `ollama`. If model rows provide
`auth_methods`, the SDK prefers that server-owned value. It renders a card for every recognized
loaded provider supporting `oauth`, `api_key`, or both, and a non-secret status card for a loaded
provider mapped to `none`. Provider cards are
sorted by display name as compact rows without nested cards or an internal scrollbar. Credential
fields remain collapsed until the user chooses a connection action. Dual-mode providers expose
separate `Connect with OAuth` and `Use API key` actions. The API-key choice swaps those actions
inline for a masked field plus save/cancel controls. The OAuth choice swaps them for an emphasized
`Authorize <provider>` link plus `Cancel connection`. Active connections expose a visible
`Disconnect` action. The notebook polls AI Gateway at a bounded interval while authorization is
pending and updates the row automatically when it becomes active. `Check connection status`
remains available as a manual recovery action.

The login state renders as a compact, bounded-width card with aligned username/password fields,
a single full-width primary action, concise account/vault copy, masked password entry, and an
inline error region. Password values are cleared after every submission attempt.

OAuth setup uses `POST /v1/oauth/connections`, surfaces the returned provider authorization URL,
and refreshes the pending connection until it becomes active. API-key setup uses a masked control
and submits the key to
`POST /v1/oauth/connections/api-key` over HTTPS (or loopback HTTP locally). Existing connections
can replace their key through `PUT /v1/oauth/connections/{id}/api-key` and can be removed through
`DELETE /v1/oauth/connections/{id}`.

The AI Gateway encrypts credentials at rest and never echoes them. The SDK stores only
non-secret connection IDs/labels and the gateway JWT. Multiple accounts are resolved to an
explicit provider → profile-label mapping; each chat request sends the selected `X-Profile`.

The widget labels AI Gateway account authentication as “unlock your credential vault” and states
why upstream keys are still required. It never implies that a ScreamingFace login includes model
credits. A future managed/subsidized-compute path may make login sufficient, but that is outside
OME-400. `static_widgets=True` changes representation only.

The public headless connection surface is `sf.providers()`, `sf.connections()`,
`sf.connect_oauth(provider)`, `sf.wait_for_connection(...)`,
`sf.connect(provider, api_key=...)`, and `sf.disconnect(...)`. API keys are submitted to the
configured AI Gateway, which persists them through its encrypted credential store. The SDK removes
them from the widget field and does not retain them on Session state. This production behavior
supersedes the product-demo mock's “memory only” copy.

## 5. Model catalog

`sf.models.list(max_price: float | None = None) -> list[str]` uses the active Session.

In live mode it intersects:

- model IDs returned by AI Gateway `GET /v1/models`; and
- a versioned SDK metadata catalog containing display name and pricing provenance.

The current gateway model endpoint does not expose prices. OME-400 therefore does not modify the
gateway: pricing metadata is SDK-owned for this thin slice and records source/as-of date. Models
with unknown price are excluded when `max_price` is specified and remain available when it is
omitted. A non-negative finite maximum is required.

Mock mode exposes a deterministic catalog with the same identifier shape. The caller receives a
new list and cannot mutate catalog state.

Live catalog discovery mirrors the setup panel: `sf.models.list()` returns only SDK-known models
whose provider holds an active gateway connection, and connections are re-read on every call so a
provider connected through the widget appears immediately. Composition stays available for any
SDK-catalog model — Python construction and YAML loading validate against the SDK catalog without
requiring connections — and provider/model readiness is re-verified once more at the evaluation
preflight.

Gateway-authoritative pricing, richer capability metadata, or billing reconciliation requires a
separate AI Gateway work item.

## 6. Fusion

```python
sf.Fusion(
    name: str,
    models: Sequence[str],
    reduce: Literal["majority_vote"],
    judge: str | None,
)
```

The equivalent declarative form is:

```yaml
name: yaml-trio
models:
  - codex/gpt-5.5
  - gemini-cli/gemini-2.5-pro
  - anthropic/claude-sonnet-4-6
reduce: majority_vote
judge: codex/gpt-5.5
```

```python
fusion = sf.Fusion.from_yaml("fusion.yaml")
fusion = sf.Fusion(**config)  # equivalent inline mapping
```

Invariants:

- `name` is non-empty and normalized for URL4 identity.
- At least two model identifiers are required.
- Every model must exist in the SDK model catalog; gateway availability and provider
  readiness are enforced once, at the evaluation preflight.
- A judge must be a fusion member.
- OME-400 supports `majority_vote` only; unknown reducers fail clearly.
- The canonical recipe carries `sf_version`, normalized `sf_name`, and `sf_judge` when configured,
  so a future importer can reconstruct semantic tie-breaking rather than infer it.
- Credentials, gateway JWTs, and profile labels never appear in the recipe.
- YAML is parsed with a safe loader, must be a mapping containing only the Fusion fields, and does
  not execute or contact a provider while loading.
- Model IDs are exact identifiers with the same shape as `sf.models.list()`. Aliases are not
  silently rewritten; unknown model IDs fail during Fusion construction, and unavailable
  models or providers fail at the evaluation preflight.

`Fusion.url4` is canonical URL4 rendered by the URL4 SDK. It must parse and execute through the
public `Url4Node` facade;
it is not an unrelated query string with a `url4://` prefix. `Fusion.url` remains a compatibility
alias for the first SDK draft. Plain and rich notebook representations show a lineup table and do
not expose the recipe until the caller asks for `.url4`.

## 7. Evaluation and scoring

`Fusion.evaluate("gpqa", first=20, seed=0)`:

1. refreshes gateway model/connection state and validates every required model/provider;
2. loads a deterministic, attributed GPQA Diamond sample;
3. builds one URL4 fan-out/reduction expression per question;
4. asks each panel model exactly once through `CompletionPort`;
5. extracts a normalized answer choice or records an explicit invalid answer;
6. applies majority vote; a tied vote selects the configured member judge's existing valid
   answer, falling back to the lexicographically first tied answer only when no judge is
   configured or the judge produced no valid answer;
7. scores the fusion and each member against the answer key; and
8. returns an immutable `Run`.

The baseline is computed from the same panel responses used by the fusion. The evaluator must not
call panel models again to calculate baseline. Retries happen inside the gateway/provider policy
and remain attributable to the original logical call.

`Run` exposes:

- `score`: fusion accuracy percentage;
- `baseline`: best individual member accuracy percentage;
- `gain`: `score - baseline` under one documented rounding policy;
- usage and estimated/actual cost when available;
- `mode`: `live` or `mock`;
- benchmark/sample provenance, models, provider profiles (non-secret labels), seed, URL4 recipe,
  timestamps, and pricing source/as-of date; and
- incomplete/error counts rather than silently dropping failed rows.

The rich notebook representation presents the fusion name and benchmark/sample identity, an
unambiguous live/simulated badge, score/gain/baseline/cost metrics, a fusion accuracy bar,
reducer/judge summary, per-model accuracy bars with best-member and failure labels, incomplete-row
warning, and dataset/pricing/token provenance. It escapes all external strings and never displays
credentials or the URL4 recipe implicitly.

Provider timeouts, transport failures, provider-readiness errors, and invalid answers are attached
as structured per-question/per-model failures. Successful member answers still participate in the
vote and baseline.

Known readiness failures are different from runtime partial failures. Before progress display,
dataset loading, or inference, live evaluation compares the fusion's exact model IDs with the
gateway catalog and its required provider IDs with active connections. Any missing provider or
unavailable model raises one typed `FusionNotReady` containing the complete provider → model
mapping, corrective `sf.setup()` guidance, and an explicit no-calls/no-data-loaded statement.
Python-constructed and YAML-loaded fusions pass through this identical preflight.

In an interactive notebook, live evaluation displays progress before dataset loading and advances
after every completed provider call. Its calculable total is `questions × panel members`; the
display also states the current question and 30-second provider-request timeout. Panel members
execute concurrently within each question, while questions execute sequentially. Failures and
timeouts count as completed calls. `progress=False` disables the display, and static committed
notebook execution does not create a live progress widget.

Mock mode is deterministic for identical input and seed. Live mode is not falsely described as
deterministic; its complete provenance makes the run auditable.

## 8. URL4 integration

URL4 is used for executable fan-out, not only serialization. Each question becomes a URL4
reduction expression whose sources identify model calls and whose reduction intent identifies
majority voting. A ScreamingFace URL4 I/O/processor adapter translates model-source requests to
`CompletionPort` calls.

The live completion adapter sends OpenAI-shaped requests to AI Gateway
`POST /v1/chat/completions`, with gateway JWT and the selected `X-Profile`. It never sends a
provider credential. The mock adapter implements the same port without network access.

Tests must spy on the URL4 execution seam. A direct Python model loop followed by a vote that
bypasses URL4 does not satisfy this specification.

## 9. Dataset behavior

The committed notebook and CI must run without network dataset access. GPQA is gated and its
access terms ask users not to reveal examples online, so no real GPQA question text is bundled or
rendered. Live mode fetches GPQA Diamond only after the user accepts the dataset terms and
provides Hugging Face authorization. Mock mode uses a bundled 20-question, structurally
equivalent synthetic science fixture and labels the Run/notebook output as synthetic—not GPQA
benchmark evidence.

`first` must be positive and may not exceed the available sample. Unsupported benchmark IDs fail
clearly. General Hugging Face dataset support is outside OME-400.

## 10. Notebook contract

`packages/screamingface/examples/00_quickstart.ipynb` is generated from or checked against a
plain reviewable source. It must:

- explain live and mock modes before execution;
- preserve the exact connect → pick → compose → run → compare API;
- use explicit `mode="mock"` and static widgets for committed GitHub outputs;
- show how to change the setup cell to `sf.setup()` for real execution;
- prominently label committed scores as simulated;
- contain no credentials, tokens, absolute paths, or secret-bearing exception text;
- execute from a clean kernel; and
- show URL4, score, baseline, gain, mode, provenance, and cost status.

`mode="mock"` controls execution: bundled synthetic questions and deterministic local model
answers replace gated dataset and provider calls. `static_widgets=True` controls representation
only and must never alter the dataset, answers, scores, network behavior, or spend. Both are used
for the checked-in notebook; a real user run replaces the setup call with zero-argument
`sf.setup()`.

A separate opt-in live smoke test exercises the same SDK path through AI Gateway against at least
two connected providers. Live output is not committed as a stable benchmark claim.

`packages/screamingface/examples/yaml_quickstart.ipynb` is the declarative companion. It is
generated, executed, and drift-checked in CI alongside `00_quickstart.ipynb`. It reviews the
adjacent `fusion.yaml`, validates exact active-catalog IDs, demonstrates `Fusion.from_yaml(...)`
and equivalent `Fusion(**mapping)` construction, shows the lineup before explicitly requesting
`.url4`, and completes the same simulated evaluate/compare path.

## 11. Failure and security contract

Public failures are typed and actionable: gateway unavailable, login required, provider not
connected, ambiguous profile, dataset unavailable, invalid model answer, timeout, and incomplete
run.

Tests inspect recipes, reprs, notebook outputs, logs, HTTP errors, and validation errors for
credential leakage. The SDK does not persist gateway passwords, provider keys, or provider OAuth
tokens. It does not disable TLS verification for remote gateways.

Sessions own their gateway client. Replacing or resetting an active Session closes the old client;
`Session.close()` and `sf.shutdown()` are idempotent, and the synchronous worker loop can be
cleanly recreated after shutdown.

## 12. Packaging and repository integration

The package follows `packages/url4`: Python 3.12+, `uv`, Hatchling, `src/` layout, Ruff, Pyright,
Pytest, and at least 95% package coverage. It receives a path-filtered CI workflow,
release-please entry, CODEOWNERS route, Dependabot entry, and `.claude/sdlc.local.md` stack.

The owner must create the Linear landing label `pkg/screamingface-sdk`; its UUID must then be
registered in `.claude/task-board.local.md`. Linear MCP is unavailable in this session.

## 13. Change boundary

OME-400 changes:

- `packages/screamingface`;
- repository registration/CI/release files needed for that new package; and
- OME-400 documentation artifacts.

OME-400 makes no `apps/aigateway` changes. A separate gateway ticket should add an authoritative
provider-capabilities contract and credential-verification semantics. The temporary SDK mapping
is then removed after supported gateway versions expose that contract.

## 14. Non-goals

- DRACO ingestion, rubric judging, repeated judging, full cost ledgers, statistics, or plots.
- SDK-local or gateway-wide runtime budget enforcement.
- Hosting or operating a public AI Gateway deployment.
- Gateway-authoritative pricing or provider billing reconciliation.
- Every API in the broader product-demo notebook series.
- Stacked fusions, custom reducers, leaderboards, tuning, or publishing.
- Moving provider implementations from `apps/aigateway` into the SDK.

## 15. Acceptance criteria

- The exact OME-400 API imports and runs in explicit mock mode in CI.
- `sf.setup()` defaults to live gateway authentication and never silently mocks.
- The same Fusion/evaluate API passes an opt-in live smoke test through AI Gateway with at least
  two providers.
- Fusion fan-out is executed by URL4 and baseline reuses the same panel responses.
- No credential appears in files, outputs, URL4, reprs, logs, or surfaced exceptions.
- Every Run discloses mode and complete provenance.
- The committed notebook is clean-kernel executable with visibly simulated outputs.
- Package and existing URL4 quality gates remain green.
