# Spec — `url4 serve`: minimal CLI to run the engine as an HTTP node

- **Ticket:** OME-466
- **Stack:** url4 (`packages/url4`)
- **Status:** approved (design-session converged 2026-07-15)
- **Related doctrine:** `url4-engine` skill (N1 GET-as-address, N4 subprocess leaf, N5 registry adapters)

> **REVISION 2026-07-15 (owner-approved pivot).** The released v1 SDK already ships
> **`url4.Url4Node`** — a node that *is* an `IOLayer`, with `endpoint()`/`data()`/`holdings()`
> registries, in-process `evaluate()`, a **framework-free raw-ASGI** `asgi()`, `serve()` over
> the existing `url4[server]` uvicorn extra, GET-only (doctrine N1), and `Url4Error → HTTP`
> mapping. The CLI is therefore built **on top of `Url4Node`**, NOT as a from-scratch Starlette
> app: LLM/command routes are `@node.endpoint(...)` handlers; there is **no `GatewayIOLayer` and
> no Starlette**. Changes vs. the body below: HTTP surface is `GET {eval_path}?q=<expr>`
> (default `/v1`, no `POST`); `/healthz` is a `data()` route; error→status mapping is the
> node's (`ParseError/CollectionError→400`, `ScopeError→400`, `ResolutionError` transient→502,
> `endpoint_not_found→404`, else 500); the CLI's thin raw-ASGI wrapper adds only **503**
> backpressure, **504** timeout, and graceful client/node shutdown. Modules: `url4/cli.py` +
> `url4/_serve.py` (no `url4/server/` package — `url4/server.py` is the existing SDK). Sections
> 5 (GatewayIOLayer) and the Starlette references are superseded; §5's route-registry *concept*
> still holds, realized via node endpoints. Default port `4404` (SDK default).

---

## 1. Goal & non-goals

**Goal.** Ship a minimal CLI + HTTP server that exposes the existing framework-free `url4`
engine as a runnable **url4 node**, distributed as an optional `url4[serve]` extra on
`packages/url4`. Running `url4 serve` stands up an HTTP endpoint that evaluates url4
expressions; model leaves fan out to the aigateway, custom/command leaves run locally.

**Non-goals (v1, explicitly deferred).**
- WebSocket / SSE streaming and the three-signal telemetry (`logs`/spans/`cost.usage`),
  Enclave trace store, `Link`-header trace resolution (design-stage doctrine, F4 open).
- Daemonization (`--detach`, PID/state files, `start/stop/status/logs`). Foreground only.
- Node→node passthrough/chaining (pointing `--backend-url` at another url4 node).
- Python-plugin **loader** (the handler *seam* exists; auto-loading/entry-points deferred).
- aigateway login flow — v1 accepts a pre-issued JWT via env.

**Invariant preserved.** `packages/url4`'s core import graph stays framework-free. Starlette
and uvicorn are reachable **only** through the `[serve]` extra and the `url4.server`
subpackage; `url4/__init__.py` and `url4.dag` never import `url4.server`. This mirrors how
`io_http.py` quarantines httpx today.

---

## 2. Distribution & packaging

`packages/url4/pyproject.toml`:

```toml
[project.optional-dependencies]
serve = ["starlette>=0.40", "uvicorn>=0.30"]

[project.scripts]
url4 = "url4.server.cli:main"
```

- Hatch already packages `src/url4`, so `src/url4/server/` ships automatically.
- **Lazy-import rule:** `url4.server.cli` imports only stdlib + `url4` core at module top.
  The `serve` subcommand imports `url4.server.app` (which imports Starlette/uvicorn) *inside
  the handler*, so `url4 --version` and `url4 eval` work with the base install (no extra).
  Running `serve` without the extra prints a clear install hint (`pip install 'url4[serve]'`)
  and exits 2.

---

## 3. CLI contract

Flat two-verb grammar; foreground only.

```
url4 serve [flags]        # run the node in the foreground; Ctrl-C / SIGTERM stops it
url4 eval '<expr>'        # evaluate one expression network-free (StaticIOLayer); arg or stdin
url4 --version            # prints "url4 <version>"
url4 --help / url4 <cmd> --help
```

### 3.1 `serve` flags & config resolution

Precedence (highest first): **CLI flag > `URL4_*` env > `url4.toml` > built-in default.**

| Flag | Env | Default | Notes |
|---|---|---|---|
| `--host` | `URL4_HOST` | `127.0.0.1` | Non-loopback is an explicit choice; triggers warnings (§7). |
| `--port` | `URL4_PORT` | `4444` | |
| `--backend-url` | `URL4_BACKEND_URL` | `http://127.0.0.1:9105` | aigateway base URL for LLM routes. |
| `--backend-token` | `URL4_BACKEND_TOKEN` | *(unset)* | JWT for `Authorization: Bearer`. **Env/file only — never on argv** (flag reads a *path* or is omitted; secret value comes from env). Unset ⇒ no header (aigateway anon mode). |
| `--processor` | `URL4_PROCESSOR` | `/claude` | Reduce route; must be a registered LLM route (validated at startup). |
| `--concurrency` | `URL4_CONCURRENCY` | `32` | `run(concurrency=…)` run-wide I/O cap; int ≥ 1. |
| `--max-inflight` | `URL4_MAX_INFLIGHT` | `16` | Max simultaneous evaluations; over → 503. int ≥ 1. |
| `--timeout` | `URL4_TIMEOUT` | `120` | Per-request eval timeout (seconds); float > 0. |
| `--config` | `URL4_CONFIG` | `./url4.toml` if present | TOML config path. |
| `--route k=v` | — | — | Repeatable; adds/overrides an LLM route (`/claude=claude/claude-opus-4-8`). |
| `-v` / `-vv` | — | warn/info | Log verbosity; `--json` for NDJSON logs; honor `NO_COLOR`/`--no-color`. |

Secrets never in argv: `--backend-token` accepts a **file path**; the raw token otherwise
comes from `URL4_BACKEND_TOKEN`. (A convenience `--backend-token -` reads one line from stdin.)

### 3.2 `eval`

- `url4 eval '<expr>'` or `echo '<expr>' | url4 eval`. Reads the expression from the first
  positional arg, else stdin.
- Uses `StaticIOLayer` with no routes/fetch-map — **network-free by design**. Text/group/
  reduce-by-merge expressions resolve; any expression that *fetches* (a URL, a `/route`)
  raises `ResolutionError` (exit 1) with a message pointing at `url4 serve`.
- Result to **stdout**; nothing else on stdout. Exit 0 success, 1 `Url4Error`, 2 usage.

### 3.3 Output & process discipline (both audiences)

- **stdout = the answer only.** Banners, bind address, request logs, warnings → **stderr**.
- Exit codes: `0` success/clean shutdown, `1` runtime error, `2` usage/config error.
- `serve` prints one stderr line when bound (`listening on http://127.0.0.1:4444`) and one on
  graceful shutdown. `--json` ⇒ NDJSON logs, flushed per line.

---

## 4. HTTP contract

Starlette app, three routes. **Model routes like `/claude` are NOT HTTP routes** — they are
resolved *in-process* by the IOLayer (§5) while the engine evaluates an expression. The HTTP
surface is only the front door.

| Method / path | Purpose | Success | Body |
|---|---|---|---|
| `GET /?q=<expr>` | Transactional eval (idempotent, cacheable — doctrine N1: expression-as-address ⇒ GET). Primary. | 200 `text/plain` | evaluated result |
| `POST /` | Escape hatch for expressions longer than a safe URL. Body = raw expression (`text/plain`). | 200 `text/plain` | evaluated result |
| `GET /healthz` | Liveness (no engine run). | 200 `text/plain` `ok` | — |

- `GET /` attaches a stub `Link: </traces/{id}>; rel="describedby"` header (trace id = a
  per-request uuid) — a forward-compatible placeholder for the deferred trace store; the URL
  need not resolve in v1.
- `q` is a full url4 expression (URL-decoded). The server calls `run(expr, io=<gateway>,
  processor=…, concurrency=…)` under the per-request timeout + inflight guard.

### 4.1 Error → status mapping

| Engine exception | HTTP | Meaning |
|---|---|---|
| `ParseError` | 400 | malformed url4 expression (include `.position` if present) |
| `ScopeError` | 422 | unbound `$name`/`$item` reference |
| `CollectionError` | 422 | `*` source empty / not iterable |
| `ResolutionError` | 502 | a source/backend failed (upstream) |
| `asyncio.TimeoutError` | 504 | exceeded `--timeout` |
| over `--max-inflight` | 503 | + `Retry-After: 1`; body says try again |
| other `Url4Error` / unexpected | 500 | generic; detail behind `-v` logs, never the trace |

Error body is a small JSON problem object reusing the engine's shape:
`{"error": {"kind": "<ExceptionClassName>", "message": "<str>"}}`, `Content-Type:
application/json`. `q`/expression missing → 400.

---

## 5. The dispatching IOLayer (`url4.server.io_gateway`)

A concrete `IOLayer` (satisfies the core `IOLayer` Protocol) that is a **registry of adapters**
— the hexagonal wiring the doctrine mandates (N5: core never imports backends; adapters
register; dispatch by route). One instance is built at startup and shared across requests
(it owns one pooled httpx `AsyncClient`).

`fetch(target, *, relative)` dispatch:

1. **`relative is False`** (absolute `https://…`) → plain `GET target` → response text. (Data read.)
2. **`relative is True`, no `?q=`** (bare `/path`) → plain `GET {backend_url}{path}`. (Data endpoint.)
3. **`relative is True`, has `?q=`** → `decode_subrequest(query)` → `(context, intent)`; look up
   `path` in the route registry:
   - **LLM route** (`path` in the route→model map): build `messages =
     [{"role": "user", "content": merge(intent, context)}]`; `POST {backend_url}/v1/chat/completions`
     `{"model": <mapped model>, "messages": …, "stream": false}` with
     `Authorization: Bearer <token>` if configured; return `resp["choices"][0]["message"]["content"]`.
   - **Command route** (`path` in `[commands]`, opt-in): run the configured argv (list) with
     `{context}`/`{intent}` token substitution, `context` piped to **stdin**, under the
     per-command timeout; **stdout → result**; non-zero exit / timeout → `ResolutionError`
     (with a stderr tail). No shell (`asyncio.create_subprocess_exec`, argv list).
   - **unknown route** → `ResolutionError(f"no route registered for {path!r}")`.

`merge(intent, context)` mirrors the engine's `default_process`: `f"{intent}\n\n{context}"`
when both are non-empty, else whichever is non-empty, else `""`.

**Note on recursion:** because `FanoutReduceNode` reduces by fetching
`{processor}?q=()!<reducer-input>`, the processor route flows through this same dispatch — the
reduce step is just another LLM-route call. `--processor` must therefore name a registered
LLM route; enforced at startup.

### 5.1 Route registry & defaults

- **Default LLM routes** (one documented constant `DEFAULT_ROUTES` in `config.py`, fully
  overridable): `/claude → claude/claude-opus-4-8`, `/gemini → gemini/gemini-2.0-flash`,
  `/codex → codex/gpt-5-codex`. Values are `provider/model` strings the aigateway resolves.
  (Model ids drift — this constant is the single bump point; documented as such.)
- `[routes]` in `url4.toml` and repeatable `--route k=v` merge over the defaults (flag wins).
- `[commands]` in `url4.toml` defines command routes; **empty/off by default** (no default
  command routes, ever).
- Startup validation (fail-fast, before bind): `--concurrency`/`--max-inflight` ≥ 1;
  `--timeout` > 0; `--processor` ∈ LLM routes; a route path must start with `/` and not
  collide between `[routes]` and `[commands]`.

---

## 6. Concurrency model (per concurrency-expert)

- **Workload class:** I/O-bound (network + subprocess); single-threaded asyncio event loop.
  No CPU work on the loop; `run()` is awaited directly.
- **Backpressure (bounded-queue principle):** a per-app in-flight counter checked-and-
  incremented with **no `await` between check and increment** — atomic on the single-threaded
  loop (same trick as the executor's memo). Over `--max-inflight` → 503 immediately (shed,
  don't queue unboundedly). This bounds cost as well as load (each request can fan out to many
  paid calls).
- **Run-wide I/O cap:** `run(concurrency=--concurrency)` — the engine's `BoundedIOLayer`
  wraps the shared gateway per call, layered under any `;foreach.concurrency`.
- **Per-request isolation:** each `run()` builds its own `ExecutionContext` and `spawn`
  closure; the shared gateway IOLayer is stateless besides its pooled client, so concurrent
  runs never share mutable state. No lock held across any `await`.
- **Shared resource:** one `AsyncClient` in the gateway (keep-alive across a fan-out), created
  on Starlette startup, `aclose()` on shutdown.
- **Cancellation/shutdown:** uvicorn traps SIGINT/SIGTERM → lifespan shutdown drains in-flight
  requests (bounded by uvicorn's timeout) → `aclose()` the client. Per-request
  `asyncio.timeout(--timeout)` bounds a single evaluation.

---

## 7. Security posture (v1 minimum; deeper layers later, per owner)

Command/plugin routes are **arbitrary code execution over HTTP — an intended capability**,
to be hardened in later layers. v1 minimum bar:

- **Localhost default bind.** Binding non-loopback (`--host` not `127.0.0.1`/`::1`) prints a
  loud stderr warning; combined with any command route, an **additional** warning that command
  routes are now remotely reachable.
- **Operator-controlled command vs caller-controlled payload.** The *command* (argv list) is
  server config; the HTTP caller supplies only stdin/substituted text. No `shell=True`; argv
  is a list; `{context}`/`{intent}` are substituted as single argv tokens, never re-split.
- **Per-command timeout**; killed on overrun.
- **SSRF acknowledgment.** Absolute-URL and bare-`/path` fetches are unrestricted in v1
  (documented risk); an allowlist is a later layer. Localhost default contains blast radius.
- Secrets (`URL4_BACKEND_TOKEN`) never logged, never on argv.

---

## 8. Acceptance criteria

- [ ] `pip install 'url4[serve]'` yields a working `url4` console script; base install (no
      extra) still imports `url4`/`url4.dag` and runs `url4 --version` + `url4 eval`.
- [ ] `import url4` and `import url4.dag` never import Starlette/uvicorn (asserted in a test
      that fails if the core import graph pulls them in).
- [ ] `GET /?q=` and `POST /` evaluate expressions; a fan-out `(a,b)!x` reduces via the
      `--processor` route (asserted against a fake transport).
- [ ] LLM route → aigateway POST with correct URL, `model`, `messages` (merged prompt), and
      `Authorization` header; command route → subprocess stdout; unknown route → 502.
- [ ] Startup validation: unknown `--processor` → fail-fast exit 2; bad `--concurrency`/
      `--max-inflight`/`--timeout` rejected; route/command collision rejected.
- [ ] Over `--max-inflight` → 503 + `Retry-After`; exceeding `--timeout` → 504; graceful
      shutdown closes the client.
- [ ] Error→status mapping covered for every row of §4.1; stdout/stderr discipline; exit codes.
- [ ] `ruff check` + `ruff format --check` + `pyright` clean; `pytest --cov=url4
      --cov-fail-under=95` green.

---

## 9. Test plan (RED first)

- **Packaging/isolation:** a test importing `url4` + `url4.dag` asserts `starlette`/`uvicorn`
  absent from `sys.modules` afterward.
- **Config:** precedence (flag > env > toml > default) per field; validation failures.
- **IOLayer dispatch:** each branch (absolute URL, bare path, LLM route, command route,
  unknown) with a fake httpx transport + a real subprocess (`/python = ["python3","-c",…]`);
  `merge` convention; auth header presence/absence; processor reduce path.
- **App:** GET/POST happy path; each error→status row; 503 backpressure (max-inflight=1, two
  concurrent slow runs); 504 timeout; `/healthz`; lifespan close.
- **CLI:** `eval` arg + stdin; `--version`; usage error → 2; `serve` without extra → hint +2;
  serve bind+immediate-shutdown smoke.

---

## 10. Open items / deviations

- **Label drift:** the task-board card's Epic/workstream group (e.g. "url4 Engine") has been
  removed from Linear. OME-466 filed with `pkg/url4-python-sdk` + `autonomous` + `agentic`
  only. Card taxonomy needs an owner reconcile (tracked in the ledger).

---

## 11. Revision (2026-07-16) — commands-only backends + `default_route` (owner-directed)

Supersedes every `[routes]`/aigateway-connector part of this spec (§ affected: the
LLM-route handler, `--backend-url`/`--backend-token`, `DEFAULT_ROUTES`, `--route`):

- **The aigateway connector is DELETED.** `url4 serve` ships exactly one backend
  kind: `[commands]` — operator-owned subprocess argv templates. An LLM backend is
  the operator's own gateway script mounted as a command, e.g.
  `"/claude" = ["python", "ai_gateway_script.py", "--url", "<gw>", "-m", "<model>"]`.
  The SDK/CLI provides no such script.
- **`processor` (serve config) → `default_route`** (`--default-route`,
  `URL4_DEFAULT_ROUTE`, toml `default_route`). An explicit value must be a declared
  command route (fail-fast `ConfigError`); unset resolves to the FIRST declared
  command; an empty `[commands]` is a fail-fast `ConfigError` (zero-config serve is
  gone by design — the operator owns all backend wiring).
- **Core SDK:** the `processor` NAME stays (spec term), but `DEFAULT_PROCESSOR =
  "/claude"` is removed. Unset `processor` resolves to the io world's first
  declared route via a new optional port capability
  `url4.io_layer.SupportsDefaultRoute` (`Url4Node` → first registered endpoint,
  `StaticIOLayer` → first `routes` key); with none declared, a fan-out reduce
  raises a clear `ResolutionError`. The HTTP wire param `processor=` (§3.3.1/§27.3)
  is unchanged.
