# Spec — `url4 serve`: minimal CLI to run the engine as an HTTP node

- **Ticket:** OME-466
- **Stack:** url4 (`packages/url4`)
- **Status:** approved (design-session converged 2026-07-15; twice revised — see history)
- **Related doctrine:** `url4-engine` skill (N1 GET-as-address, N4 subprocess leaf, N5 registry adapters)

## Revision history

| Date | Change |
|---|---|
| 2026-07-15 | Approved — design session converged. |
| 2026-07-15 | **Pivot 1 (owner-approved).** The released v1 SDK already ships `url4.Url4Node` — a node that *is* an `IOLayer`, with `endpoint()`/`data()`/`holdings()` registries, in-process `evaluate()`, a framework-free raw-ASGI `asgi()`, GET-only dispatch, and `Url4Error → HTTP` mapping. The CLI is therefore built **on top of `Url4Node`**, not as a from-scratch Starlette app. No Starlette, no `GatewayIOLayer`, no `url4/server/` package. |
| 2026-07-16 | **Pivot 2 (owner-directed).** The aigateway connector is deleted; `[commands]` is the only backend kind. Serve-layer `processor` → `default_route`. Core keeps the `processor` name but loses the hardcoded `/claude` default. |
| 2026-07-17 | **Review round 2 (PR #402).** Body rewritten to describe the system as built. |
| 2026-07-18 | **Scope extension 3 (owner-directed).** The served node gains its READ surface: `[data]`, `[holdings]`, `[identities.<name>]` in `url4.toml` (§5.2), and command backends receive the caller's protocol params (§5.1). Folded into OME-466 rather than split off, because a node that cannot resolve `@` or a bare relative URI is not yet "the engine as an HTTP node" — the goal in §1. |

> **AIDEV-NOTE — why this history is a table and not a stack of banners.** Both pivots were
> originally recorded as revision *banners* prepended to an unchanged body. Readers (and the
> PR description, which was copied from the work ledger) took the stale body as current, and
> shipped four artifacts contradicting the code. **A spec states the current target: the body
> below is rewritten in place, and the table carries the history.** If the body disagrees with
> the code at head, the body is the bug — fix it here, do not add a banner.

---

## 1. Goal & non-goals

**Goal.** Ship a minimal CLI + HTTP server that exposes the framework-free `url4` engine as a
runnable **url4 node**, using the existing optional `url4[server]` extra on `packages/url4`.
Running `url4 serve` stands up an HTTP endpoint that evaluates url4 expressions and dispatches
every leaf to an operator-declared local command. `url4 eval` is the network-free companion.

A served node must be able to resolve **both halves** of an expression: the *write* half
(intent processors — `[commands]`, §5.1) and the *read* half (data routes and holdings —
§5.2). An operator declares the whole surface in one `url4.toml`, under one provider model.

**Non-goals (v1, explicitly deferred).**
- WebSocket / SSE streaming and the three-signal telemetry (`logs`/spans/`cost.usage`),
  Enclave trace store, and `Link`-header trace resolution (design-stage doctrine, F4 open).
  **No `Link` header is emitted in v1.**
- Daemonization (`--detach`, PID/state files, `start/stop/status/logs`). Foreground only.
- Node→node passthrough/chaining.
- Python-plugin **loader** (the `(context, intent) -> str` handler *seam* exists via
  `node.endpoint`; auto-loading/entry-points deferred).
- Log-verbosity flags (`-v`/`-vv`, `--json` NDJSON, `NO_COLOR`). Not implemented in v1.
- Any bundled LLM/aigateway connector — see §5.

**Invariant preserved.** `packages/url4`'s core import graph stays framework-free. Starlette is
**never** a dependency. uvicorn is reachable only through the `url4[server]` extra and is
imported lazily, inside `_serve_forever`, so `url4 --version` and `url4 eval` work on the base
install. `url4/__init__.py` and `url4.dag` never import a web framework. This mirrors how
`io_http.py` quarantines httpx.

---

## 2. Distribution & packaging

`packages/url4/pyproject.toml`:

```toml
[project.optional-dependencies]
# Url4Node.serve() and `url4 serve` — the ASGI app itself is framework-free; only
# serving over HTTP needs uvicorn.
server = ["uvicorn>=0.30"]

[project.scripts]
url4 = "url4.cli:main"
```

- Modules: `src/url4/cli.py` (argparse entry point) + `src/url4/_serve.py` (config, command
  handlers, node/app assembly). There is **no `url4/server/` package** — `url4/server.py` is
  the existing v1 SDK (`Url4Node`), which this CLI consumes.
- Hatch already packages `src/url4`, so both modules ship with the base install; only the
  uvicorn *dependency* is gated by the extra.
- **Lazy-import rule:** `url4.cli` imports only stdlib + `url4` core at module top. `_serve` is
  imported inside `_run_serve`, and uvicorn inside `_serve_forever` (via `importlib`, so the
  type checker does not demand the optional extra). Running `serve` without the extra prints
  `pip install 'url4[server]'` and exits 2.

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

| Flag | Env | Toml | Default | Notes |
|---|---|---|---|---|
| `--host` | `URL4_HOST` | `host` | `127.0.0.1` | Non-loopback is an explicit choice; triggers warnings (§7). Empty is rejected (§7). |
| `--port` | `URL4_PORT` | `port` | `4404` | SDK default. int. |
| `--default-route` | `URL4_DEFAULT_ROUTE` | `default_route` | *(unset ⇒ first declared command)* | Reduce route; an explicit value must be a declared `[commands]` route (validated at startup). |
| `--eval-path` | `URL4_EVAL_PATH` | `eval_path` | `/v1` | Eval endpoint path. Must start with `/`; may not be `/healthz`. |
| `--concurrency` | `URL4_CONCURRENCY` | `concurrency` | `32` | `run(concurrency=…)` run-wide I/O cap; int ≥ 1. |
| `--max-inflight` | `URL4_MAX_INFLIGHT` | `max_inflight` | `16` | Max simultaneous evaluations; over → 503. int ≥ 1. |
| `--timeout` | `URL4_TIMEOUT` | `timeout` | `120` | Per-request eval timeout (seconds); float > 0. Also the per-command timeout. |
| `--config` | `URL4_CONFIG` | — | `./url4.toml` if present | TOML config path. |

- **`[commands]` is TOML-only.** Argv templates are operator config, not something to squeeze
  through a repeatable flag. There is no `--route`/`--command` flag.
- **An empty env var means UNSET**, not `""` — `URL4_HOST=` in a `.env`/compose file is an
  unresolved interpolation and must fall through to toml > default, exactly as an absent
  variable does. This is uniform across every field (§7).
- No secrets are handled by the serve layer: the connector is gone, so there is no token to
  place on argv or in the environment.

### 3.2 `eval`

- `url4 eval '<expr>'` or `echo '<expr>' | url4 eval`. Reads the expression from the first
  positional arg, else stdin.
- Uses `StaticIOLayer` with no routes/fetch-map — **network-free by design**. Text/group/
  reduce-by-merge expressions resolve; any expression that *fetches* raises `ResolutionError`
  (exit 1).
- Result to **stdout**; nothing else on stdout. Exit 0 success, 1 `Url4Error`, 2 usage.

### 3.3 Output & process discipline

- **stdout = the answer only.** Bind banner, warnings, errors → **stderr**.
- Exit codes: `0` success/clean shutdown, `1` runtime error, `2` usage/config error.
- `serve` prints one stderr line when bound:
  `url4 serve: listening on http://127.0.0.1:4404 (eval /v1?q=…)`.

---

## 4. HTTP contract

The node's framework-free **raw-ASGI** `asgi()` app, wrapped by `_serve.build_asgi_app` and run
under uvicorn. **Command routes like `/upper` are node endpoints resolved in-process** by the
engine while it evaluates an expression — they are reachable over HTTP as intent-processor
paths (that is the node model, doctrine N1), but the front door for a caller is the eval path.

| Method / path | Purpose | Success | Body |
|---|---|---|---|
| `GET {eval_path}?q=<expr>` | Transactional eval (idempotent, cacheable — doctrine N1: expression-as-address ⇒ GET). Default `/v1`. | 200 `text/plain` | evaluated result |
| `GET /healthz` | Liveness — a `data()` route, no engine run. | 200 `text/plain` `ok` | — |
| any non-GET | Nodes speak GET only (N1). | 405 | `{"error": {"code": "method_not_allowed", …}}` |

- **There is no `POST` escape hatch.** It was dropped at Pivot 1 to honor the node's GET-only
  contract; long expressions are a known v1 limitation bounded by URL length.
- **No `Link` header in v1** (deferred with the trace store — §1).
- `q` is a full url4 expression (URL-decoded). The node runs it under the wrapper's
  per-request timeout and in-flight guard, reducing fan-outs via `default_processor`.

### 4.1 Error → status mapping

The **node** owns this mapping and dispatches on the `Url4Error.code`, not the exception class
(`server.py::_status_for`). The CLI wrapper adds only 503 and 504.

| Source | Code / condition | HTTP |
|---|---|---|
| node | `malformed_source` (parse), `unbound_reference` (scope) | 400 |
| node | `endpoint_not_found`, `unknown_identity`, `identity_unavailable` | 404 |
| node | `identity_access_denied`, `consent_required`, `consent_withheld` | 403 |
| node | non-GET method | 405 |
| node | `ResolutionError` with `permanent=False` (transient upstream/source) | 502 |
| node | any other `Url4Error` / unexpected | 500 |
| wrapper | over `--max-inflight` | 503 + `Retry-After: 1` |
| wrapper | exceeded `--timeout` | 504 |

Error body: `{"error": {"code": "<error code>", "message": "<str>"}}`, `Content-Type:
application/json`. A failing command surfaces as `ResolutionError` ⇒ 502.

---

## 5. Backends — the node's declared surface

An expression touches the node in two ways, and `url4.toml` declares both:

| Half | Registry | Node port | Resolves |
|---|---|---|---|
| **write** (intent processing) | `[commands]` | `endpoint()` | `/route(ctx)!'intent'`, fan-out reduce |
| **read** (sources) | `[data]` | `data()` | bare relative URIs — `(/rubrics/42)` |
| **read** (holdings) | `[holdings]` | `holdings()` | `@` — the node's own shelves |
| **read** (holdings) | `[identities.<name>]` | `identity()` | `@name[/collection]` |

Everything is **operator-declared, TOML-only**. Argv templates and file paths are operator
config, never flags or env vars — there is no `--route`/`--command`/`--data` flag.

### 5.1 Write side — command routes as node endpoints

**`[commands]` is the only intent-processor kind.** There is no LLM/aigateway connector, no
route→model map, and no `httpx` in the serve layer. An operator who wants an LLM backend writes
their own gateway script and mounts it as a command; the SDK/CLI ships no such script. Routes
and commands are the same thing at the SDK core — an endpoint — so the serve layer keeps one
concept (N5: the core defines the port, the operator supplies the adapter).

`url4.toml`:

```toml
[commands]
"/upper" = ["tr", "a-z", "A-Z"]          # list form: argv as given
"/gw"    = "python gateway.py -m opus"    # string form: shlex-split
```

`_serve.build_node(config)` assembles a `Url4Node` and registers, per declared command, one
intent-processor endpoint (`make_command_handler`) plus the `/healthz` data route.

**Command handler** (doctrine N4 — subprocess leaf). The argv template exposes the **whole
`Request` surface a Python endpoint handler sees, 1:1** — a command is a first-class backend,
not a degraded one:

| Token | Substituted with |
|---|---|
| `{intent}` | the resolved intent |
| `{context}` | the resolved context (also piped to stdin) |
| `{param:<name>}` | one decoded protocol param (`/model?temperature=0.7`); `""` when absent |
| `{params}` | the full param mapping as JSON, key-sorted for stable output |

- Substitution is per argv **token**, never re-split, and **single-pass**: tokens are recognized
  in the *operator's template only*. Token-shaped text arriving in caller-controlled intent,
  context, or param values is never re-scanned, so a caller cannot smuggle `{param:x}` into an
  intent and have it expand on a second round (§7).
- The resolved context is piped to the command's **stdin**; **stdout** is the result.
- Non-zero exit or timeout → `ResolutionError` (with a stderr tail) ⇒ 502.
- stdout/stderr are decoded with `errors="replace"` — a command emitting non-UTF-8 bytes must
  not escape the handler's `ResolutionError` contract as a raw `UnicodeDecodeError` (bare 500).
- No shell: `asyncio.create_subprocess_exec` with an argv **list**.

**Reduce / `default_route`.** `FanoutReduceNode` reduces by dispatching to the node's default
processor, so the reduce step is just another command call. `default_route` must therefore name
a declared command (enforced at startup); unset, it resolves to the **first declared** command
(TOML declaration order — the tie-breaker the operator controls).

### 5.2 Read side — data routes, holdings, identities

Without these, a served node has **no sources**: a bare relative URI (spec §5.4.2) has nothing
to resolve against, and `@` / `@name` (spec §5.6) fail with "serves no holdings". The three
registries close that gap.

```toml
[data]                                   # bare relative URIs
"/rubrics/42" = "score 1-5 on clarity"           # inline string
"/corpus"     = { file = "corpus.md" }           # re-read per request
"/rows"       = { command = ["./rows.sh"], media_type = "application/json" }

[holdings]                               # `@` — the node's own shelves
default = "my working notes"                     # the unqualified shelf
science = { file = "shelves/science.md" }

[identities.emily]                       # `@emily[/collection]`
default = "Emily's default holdings"
notes   = { file = "emily/notes.md" }
```

**One provider shape for all three** — an inline string, or a table with **exactly one** of:

| Source | Behavior |
|---|---|
| `value` | serves the inline text |
| `file` | re-read **per request**, in a worker thread (never on the loop) — operators edit the backing file with no restart, the same liveness a command gets by running per request. Missing/unreadable → `ResolutionError` (the *source's* failure, like a failing command), not a node error |
| `command` | an argv template — **doctrine N4 applied to reads**: no shell, argv list, empty stdin, stdout is the result. `{collection}` substitutes the requested holdings collection |

`media_type` is accepted on **`[data]` only**, and declares the route's Content-Type so a
collection served there parses **by declared type rather than by sniffing** (spec §5.3.7) — a
one-line JSON array served as `text/plain` would line-split into a single element. Holdings
carry no type channel, so `media_type` there is a config error rather than a silent no-op.

**Collection keys.** TOML has no null key, so the reserved key `default` normalizes to `None` —
the node's fallback shelf. A collection literally named `"default"` is therefore not
declarable; this mirrors how the node itself treats `None`.

**Identity fallback.** The node keeps **one handler per identity** (it has no per-collection
registry for principals), so `make_identity_handler` resolves exact-collection-then-default
*inside* the handler — deliberately mirroring `Url4Node.fetch_holdings`'s self-holdings lookup,
so `@` and `@name` resolve collections identically. An identity with no matching and no default
shelf raises `ResolutionError`; an *undeclared* identity keeps the node's own `unknown_identity`
(404), untouched.

> **Known limitation — a scoped SELF shelf has no expression syntax.** `HoldingsNode` carries
> `(identity, collection)`, and `fetch_holdings(None, "science")` works, but the grammar parses
> a bare `@` as `SelfRef()` with **no collection** (`grammar.py:619`); `@/science` is a parse
> error. Non-`default` `[holdings]` collections are therefore reachable only through the SDK
> surface today, not from an expression. `@name/collection` is unaffected. Declared here as a
> *grammar* gap, not a serve-layer one — closing it is a spec/grammar change, out of scope.

### 5.3 Startup validation (fail-fast, before bind)

All raise `ConfigError` ⇒ exit 2, never a mid-request failure or a traceback:
- `concurrency` ≥ 1; `max_inflight` ≥ 1; `timeout` > 0.
- `host` non-empty (§7).
- `eval_path` starts with `/` and is not the reserved `/healthz` (it would collide with the
  health data route at build time as an uncaught `ValueError`).
- **`[commands]` non-empty** — the connector is gone, so a node with zero commands has nothing
  to dispatch to. Zero-config serve is gone by design.
- Each command path starts with `/`, has a non-empty argv, and does not collide with
  `eval_path` or `/healthz`.
- An explicit `default_route` is a declared command.
- **Data paths** start with `/` and clash with neither a command route nor `eval_path`/
  `/healthz`. All three share the node's one path namespace; a clash would otherwise surface as
  an uncaught `ValueError` from `Url4Node._check_routable` at build time.
- **Identity names** satisfy the node's own registration rule (`_IDENTITY_NAME_RE`), keeping the
  failure a clean pre-bind `ConfigError` instead of a build-time `ValueError`.
- **Every provider** declares exactly one of `value`/`file`/`command`, carries no unknown key
  (`media_type` outside `[data]` is unknown), and has a non-empty argv if it is a command.
- A registry written as a **scalar instead of a table** (`data = "x"`) is rejected by name.

---

## 6. Concurrency model (per concurrency-expert)

- **Workload class:** I/O-bound (subprocess); single-threaded asyncio event loop. No CPU work
  on the loop; `run()` is awaited directly.
- **Backpressure (bounded-queue principle):** a per-app in-flight counter checked-and-
  incremented with **no `await` between check and increment** — atomic on the single-threaded
  loop. Over `--max-inflight` → 503 immediately (shed, don't queue unboundedly). This bounds
  cost as well as load.
- **Run-wide I/O cap:** the node's `concurrency` — the engine's `BoundedIOLayer` — layered
  under any `;foreach.concurrency`.
- **Per-request isolation:** each run builds its own `ExecutionContext`; handlers hold no
  mutable cross-request state, so concurrent runs never share it. No lock held across `await`.
- **Shutdown:** uvicorn traps SIGINT/SIGTERM → lifespan shutdown → `node.aclose()` releases the
  node's owned outbound adapter. Per-request `asyncio.timeout` bounds a single evaluation, and
  a `_StartGuard` ensures a timeout cannot double-send once the response has started.
  There is **no shared HTTP client** to close — the connector is gone.

---

## 7. Security posture (v1 minimum; deeper layers later, per owner)

Command routes are **arbitrary code execution over HTTP — an intended capability**, to be
hardened in later layers. v1 minimum bar:

- **Localhost default bind.** Binding a non-loopback host prints a loud stderr warning;
  combined with any command route, an **additional** warning that command routes are now
  remotely reachable. Loopback means exactly `127.0.0.1`, `::1`, `localhost`.
- **An empty host is rejected** (`ConfigError` ⇒ exit 2). `host=""` binds `0.0.0.0` **and**
  `::` — every interface — while reading as "unset", and it must never be mistaken for
  loopback. An operator who wants every interface writes `0.0.0.0`, which warns.
  Correspondingly, an **empty `URL4_*` env var is treated as unset** (§3.1): an unresolved
  `.env`/compose interpolation must fall through to the default, never silently become `""`.
  These are two independent guards because they cover two distinct vectors — the env var and
  an explicit `--host ""` flag.
- **Operator-controlled command vs caller-controlled payload.** The *command* (argv list) is
  server config; the HTTP caller supplies only stdin/substituted text. No `shell=True`; argv is
  a list; `{context}`/`{intent}`/`{param:…}`/`{params}` are substituted as single argv tokens,
  never re-split.
- **Single-pass substitution.** Widening the token set from two to four made a second-order
  question real: could a caller put `{param:x}` *inside* an intent and have it expand? No — the
  regex scans the operator's template once, and substituted values are never re-scanned. Chained
  `str.replace` would have had exactly this cascade, which is why substitution moved to one
  regex pass rather than two more `.replace()` calls.
- **Read providers are operator config too.** A `command` provider is the same N4 model (argv
  list, no shell, empty stdin); a `file` provider reads an operator-declared path — the caller
  never supplies or influences it, so a data route cannot be turned into arbitrary file read.
  `{collection}` is the one caller-influenced substitution on the read side, and it lands as a
  single argv token like every other.
- **Per-command timeout** (shared by read-side command providers); process killed on overrun.
- **SSRF acknowledgment.** Absolute-URL fetches in an expression are unrestricted in v1
  (documented risk); an allowlist is a later layer. The localhost default contains blast radius.
- No secrets in the serve layer at all — the connector that needed a token is gone.

---

## 8. Acceptance criteria

- [x] `url4[server]` yields a working `url4` console script; base install (no extra) still
      imports `url4`/`url4.dag` and runs `url4 --version` + `url4 eval`; `serve` without the
      extra prints the install hint and exits 2.
- [x] `import url4` and `import url4.dag` never import Starlette/uvicorn (Starlette is not a
      dependency at all; uvicorn is imported lazily).
- [x] `GET {eval_path}?q=` evaluates expressions; a fan-out `(a,b)!x` reduces via
      `default_route`; a non-GET returns 405.
- [x] A command route runs a subprocess and returns stdout; `{intent}`/`{context}` substitute
      per token; non-zero exit, timeout, and non-UTF-8 output all surface as `ResolutionError`.
- [x] **A command receives the caller's protocol params:** `{param:<name>}` substitutes a
      decoded param (`""` when absent, dotted names accepted), `{params}` the key-sorted JSON
      mapping, end-to-end through node dispatch; substitution is single-pass, so token-shaped
      text in caller-supplied values stays literal.
- [x] Startup validation per §5.3 fails fast with exit 2 and an actionable message: empty
      `[commands]`, undeclared `default_route`, bad `concurrency`/`max-inflight`/`timeout`,
      reserved-path collisions, `eval_path == /healthz`.
- [x] Over `--max-inflight` → 503 + `Retry-After`; exceeding `--timeout` → 504; lifespan
      shutdown closes the node.
- [x] Error→status mapping covered for §4.1; stdout/stderr discipline; exit codes 0/1/2.
- [x] **An empty host cannot bind every interface:** `URL4_HOST=` falls through to
      `127.0.0.1`; an explicit `--host ""` exits 2; a non-loopback bind still emits both
      warnings. Empty `URL4_PORT`/`URL4_EVAL_PATH`/`URL4_DEFAULT_ROUTE` likewise fall through.
- [x] **`eval_path` is validated:** a relative (`"v1"`) or empty eval path exits 2.
- [x] **A `[data]` route resolves a bare relative URI** in an expression; a `file` provider
      re-reads live (edit between two requests → new content, no restart); a missing file is a
      `ResolutionError`; a declared `media_type` makes a JSON route parse as a collection of
      three rather than one.
- [x] **`@` and `@name/collection` resolve through expressions** against `[holdings]` /
      `[identities.<name>]`; an undeclared collection falls back to the default shelf for both;
      an identity with no default shelf raises `ResolutionError`; an undeclared identity still
      returns the node's own `unknown_identity`. A `command` provider receives `{collection}`.
- [x] **Read-registry declarations fail before bind:** zero-or-multi-source providers, unknown
      keys (`media_type` on holdings), empty command argv, empty collection name, data paths
      that are relative or clash with a command/reserved route, invalid identity names, and a
      registry declared as a scalar.
- [x] `ruff check` + `ruff format --check` + `pyright` clean; `pytest --cov=url4
      --cov-fail-under=95` at 97% (`_serve.py` 100%). **796 passed, 0 failed, with the
      `[server]` extra installed** — the suite no longer depends on the ambient environment
      (§10). The append-only check was run with `--skip-append-only` for the two prior tests
      fixed under that item, an explicit owner decision; every other test in this unit is new.

> **On ticking these boxes.** Every box above was re-verified against the code at head on
> 2026-07-18, not carried forward on trust. Two — the empty-host and `eval_path` criteria —
> had been left `[ ]` since review round 2 even though that round shipped, tested, and
> probe-verified both, and Linear's copy of the checklist had them ticked. That is the same
> document-drift this spec's history note warns about, in the one section where it is most
> load-bearing: an unticked box on shipped work is indistinguishable from unfinished work.

---

## 9. Test plan (RED first)

- **Packaging/isolation:** importing `url4` + `url4.dag` leaves `starlette`/`uvicorn` absent
  from `sys.modules`.
- **Config:** precedence (flag > env > toml > default) per field; every §5.3 validation
  failure; empty-env fall-through per field (and fall-through to *toml*, not straight to the
  default, when toml declares the key).
- **Backends:** command handler stdin piping, `{intent}`/`{context}` substitution, timeout,
  non-zero exit, non-UTF-8 output; the LLM handler is absent from the module surface.
- **Protocol params** (`test_serve_params.py`): `{param:<name>}` present/absent/dotted,
  `{params}` JSON, the no-cascade guarantee, and one end-to-end pass through node dispatch.
- **Read registries** (`test_serve_reads.py`): each provider form parses; `default` normalizes
  to `None`; every declaration error; data route resolving a bare relative URI; live file
  re-read; missing file; `media_type`-driven collection parsing; self-holdings and identity
  fallback; `{collection}` substitution; `@` + `@name/collection` end-to-end in an expression.
- **App:** GET happy path; error→status rows; 503 backpressure (max-inflight=1, two concurrent
  slow runs); 504 timeout; `/healthz` runs no engine; lifespan closes the node.
- **CLI:** `eval` arg + stdin; `--version`; usage error → 2; removed connector flags rejected
  by argparse; empty-commands serve → 2; `--host ""` → 2; `_warn_exposure` emits both warnings
  for a non-loopback bind **and** for an empty host (defense in depth, guarding the
  `_LOOPBACK` set against a future removal of the `validate()` guard).

---

## 10. Open items / deviations

- **Label drift:** the task-board card's Epic/workstream group (e.g. "url4 Engine") has been
  removed from Linear. OME-466 carries `pkg/url4-python-sdk` + `autonomous` + `agentic` only.
  Card taxonomy needs an owner reconcile (tracked in the ledger).
- **Process drift:** the card mandates "Linear via MCP only; API tokens forbidden", but the MCP
  has been inactive and the owner has twice supplied an API key for the `linear` CLI. The card
  and the practice disagree — owner reconcile (tracked in the ledger).
- ~~**Test fragility:**~~ **RESOLVED 2026-07-18** — and it was never "fragility". Diagnosed:
  `test_cli.py::test_serve_forever_without_uvicorn_prints_hint` and
  `test_server.py::test_serve_requires_uvicorn` asserted the *missing*-uvicorn branch while
  relying on the ambient venv to lack the `[server]` extra — neither test created the condition
  it asserted. With uvicorn installed, `_serve_forever` fell through to the real `uvicorn.run()`,
  bound `127.0.0.1:4404` and **served forever: the suite hung, with no failure and no timeout**
  (verified by killing `pytest` at 25s). It had appeared to fail fast only because an unrelated
  `url4 serve` process happened to hold 4404, turning the hang into `errno 98` — so the symptom
  depended on an unrelated process, which is why it went misdiagnosed for three rounds.
  Fixed by a `hide_uvicorn` fixture (`tests/conftest.py`) that makes only `uvicorn` unimportable,
  so both tests now create their own precondition and pass with or without the extra. An autouse
  `_no_real_listen` guard turns any future `socket.listen` in a unit test into an immediate,
  actionable failure rather than a hang. Suite: **796 passed**, all gates green with the extra
  installed. Editing two prior tests was a rule-5 confidence-gate decision, taken explicitly by
  the owner.
- ~~**No README:**~~ **RESOLVED 2026-07-18.** `QUICKSTART.md` is now `README.md`, wired via
  `readme = "README.md"` in `pyproject.toml`, and carries a package-level header (what url4 is,
  install, the framework-free core) ahead of the serve walkthrough. Verified in the built wheel:
  `Description-Content-Type: text/markdown` with the README as the long description.
- **Scoped self shelf unreachable from an expression** (§5.2) — a grammar gap, not a serve gap.
  Either the grammar gains a syntax (`@/collection` is currently a parse error) or non-`default`
  `[holdings]` collections stay SDK-only. Needs a spec decision; follow-up ticket, not blocking.
- **`_serve.py` imports `_IDENTITY_NAME_RE` from `url4.server`**, which itself re-exports it
  from `url4.grammar`. Private-name reuse across two hops. It buys a real guarantee (config
  validation cannot drift from the node's own registration rule), but the honest fix is for the
  grammar to export the identity-name predicate publicly. Follow-up, not blocking.
