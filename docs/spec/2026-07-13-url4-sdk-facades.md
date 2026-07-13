# Spec — url4 SDK facades (renderer, builders, client, node)

Status: approved-in-conversation (owner: "plan and develop the gaps"; Linear waived).
Scope: `packages/url4` only. Companion plan: `docs/plan/2026-07-13-url4-sdk-facades.md`.
Ledger: `docs/work/2026-07-13-no-ticket-url4-sdk-facades.md`.

## Problem

The url4 engine (parser → AST → DAG → executor) is complete but has no product
surface: the only entry is `run(text, io) -> str`, there is no AST→text inverse, no
Python-side expression constructors, no result envelope, and no node/server side.
The approved UX direction is: client-side `query/broadcast/iterate/reduce` helpers
and a node-side decorator SDK (`@node.endpoint`, holdings, in-process + ASGI serving).

## Design principles (forced by the spec and the codebase)

1. **Strings stay first-class.** Every facade accepts a raw expression string
   wherever it accepts a Node; every builder output renders to canonical text.
2. **Renderer output is certified.** `render()` re-parses its own output and compares
   ASTs (`check=True` default) — no silently-wrong wire text, ever.
3. **Mode is inferred, never declared** (LLM vs RDS falls out of intent shape, §6).
4. **Two-axis annotations stay visibly separate** in `src()`: attribution =
   `name/weight/budgets`; execution = typed kwargs (closed key set, §8.1.1).
5. **A node IS an IOLayer.** `Url4Node` implements `fetch`/`fetch_ex`/`fetch_holdings`;
   `node.evaluate(expr)` ≡ `run(expr, io=node)`; the ASGI shim reuses the same
   dispatch. GET is the only verb (url4-engine doctrine N1).
6. **Core stays framework-free** (repo hexagonal mandate): ASGI app is a plain async
   callable; uvicorn only inside `serve()` behind the `server` extra.

## G1 — `url4/render.py`

`render(node: Node, *, check: bool = True) -> str` — the inverse of `build()`/`parse()`.

Contract: `build(render(x)) == x` for every parser-producible AST `x` (wrapped in
`Expression(sources=(x,))` when `x` is not an `Expression`/`Iteration` — mirroring
`build()`'s envelope). `check=True` enforces this per call; mismatch or
unrepresentable input raises `RenderError` (new `Url4Error` subclass, code
`unrenderable`) naming the offending node.

Normalization rules (documented, deliberate):
- Descriptor-empty `Source` (name only) renders as the `Binding` form (`name=value`) —
  the grammar produces `Binding` for that shape, so `Source` there is non-canonical.
- `Text` values always render quoted (with `\'`/`\\` escapes); bare-token inputs
  reparse to the same `Text`, so canonical output is quoted.
- `RelExpr`/`RemoteExpr`: sugar form when `params == ()`, canonical `?k=v&q=` form
  when params exist (spec §8.1.4 recommendation).
- Top level: `Expression`/`Iteration` render bare; leaf values render bare; composite
  source nodes (`Binding`, `Source`, `RelExpr`/`RemoteExpr`) render parenthesized —
  `build()` hoists a bare top-level `/p(c)!'i'` intent (verified), parens prevent it.
- `Source.expand` renders as the `*` prefix (spec-preferred sugar, §5.3.12.2).
- Numbers (weights, struct values): decimal-only formatting (`_NUMBER_RE`-safe);
  negative/nonfinite/sub-1e-12 → `RenderError`.
- Struct string values quote unless they match the bare-token class AND are not
  number-shaped (a bare `0.5` would reparse as float).

Unrepresentable (→ `RenderError`): URLs with unbalanced parens / quotes / depth-0
`,;!` (grammar cannot carry them bare; quoting would change the node type to `Text`);
struct nesting > 2 (§24.4.6); `Iteration.reducer` in value position (only the
top-level envelope decodes reduce-over-iteration); a `Source` wrapping an
expression-valued node whose first execution annotation is a dual-scope key
(`t`/`ct_mismatch`/`budget_mode`/`broadcast`) — §8.1.2 boundary would reclassify it.

Supporting change: `grammar.parse_value(text)` — public wrapper over value detection
(§5.2) so builders classify strings exactly as the grammar does.

## G2 — `url4/builders.py`

Constructors lower to the existing frozen AST (no parallel representation):

```python
text(content) -> Text                      ref(name, *path) -> VarRef
self_() -> SelfRef                         identity(name, collection=None) -> IdentityRef
struct(mapping) -> StructObject            expand(value_or_source) -> Source(expand=True)

src(value, *, name=None, weight=None, budgets=None,          # attribution axis
    mode=None, t=None, retry=None, accept=None,              # execution axis
    required=False, optional=False, expand=False,
    annotations=()) -> Source | Binding | Node               # grammar-faithful normalization

expr(*sources, intent=None, broadcast=False, params=()) -> Expression
broadcast(*sources, intent) -> Expression                    # (s)!*intent
iterate(collection, body, *, intent=None, reduce=None,       # coll*(body)!intent
        concurrency=None, on_error=None, slice=None, fmt_result=None) -> Iteration
reduce(calls, instruction) -> Expression                     # (call1,…)!instruction sugar
```

Coercions: `str` source → `grammar.parse(str)` (full descriptor grammar); `str` value →
`grammar.parse_value(str)` (§5.2 value detection — a plain word is a bare token, NOT
text; inline prose requires `text(...)`); `Mapping` → `struct()`; `list`/`tuple`
collection in `iterate` → inline parenthesized collection (bare `Expression` group).
Intent accepts `str | Text | Url | RelUrl` only — the engine's `intent_atom` can
produce nothing else; other nodes raise `TypeError` with guidance.
`iterate(reduce=...)` embedded as a source is auto-rewritten by `expr()` to
`Expression(sources=(iteration-sans-reducer,), intent=reducer)` (identical semantics,
valid in value position).

Validation: `required`/`optional` mutually exclusive; `name` a non-`src` identifier;
weight scalar ≥ 0 or struct dict; budget keys ≠ `weight`/`src`.

## G3 — `url4/client.py`

```python
@dataclass(frozen=True)
class Url4Result:
    text: str          # result body (== str(result))
    request: str       # the canonical expression that ran — the audit artifact
    # .data  → json.loads(text); raises ValueError for non-JSON bodies
    # .elements → .data as list (iterate/broadcast results); raises ValueError
    #   otherwise (right type, wrong payload — Python's ValueError convention)

class Client:
    def __init__(self, io=None, *, node=None, path="/v1",
                 processor=DEFAULT_PROCESSOR, process=default_process,
                 concurrency=DEFAULT_RUN_CONCURRENCY, strict_fields=False)
    async def query(*sources, intent=None, node=None, path=None,
                    quorum=None, triggers=None, t=None, fmt=None,
                    params=()) -> Url4Result
    async def broadcast(*sources, intent, ...) -> Url4Result
    async def iterate(collection, body, *, intent=None, reduce=None, ...) -> Url4Result
    async def reduce(calls, instruction, ...) -> Url4Result
    async def evaluate(expression: str | Node, *, env=None) -> Url4Result
    async def aclose();  __aenter__/__aexit__
```

- One execution path: helpers build AST via G2, wrap in `RemoteExpr` when a node
  target is set (context = rendered sources; protocol params in the `?` position),
  render to canonical text, execute via `run()`. Remote/local differ only in which
  DAG node does the wire hop. The rendered string is `Url4Result.request`.
- Remote queries render parenthesized: `(url4://host/path(ctx)!intent)` — keeps the
  intent on the remote node (verified against the hoisting behavior).
- `io=None` → lazily-owned `HttpIOLayer`, closed by `aclose()`; injected io never closed.
- `env` seeds the lexical scope via a caller-built `ExecutionContext` (`run(ctx=...)`).
- **No module-level `url4.query()`**: a module-global async client binds to an event
  loop (footgun). The `screamingface` app layer may add that sugar with its own
  lifecycle. (Deviation from the mockup, deliberate.)
- Protocol params (quorum/triggers/fmt/…) are carried on the expression; the executor
  already ENFORCES `quorum` (verified — `dag/compiler.py` `_quorum_of`); triggers/fmt
  remain carried-but-unenforced Part C follow-ups.

## G4 — `url4/server.py` (named to avoid `url4/nodes.py`/`url4/dag/node.py` collision)

```python
class Url4Node:                      # implements IOLayer + SupportsFetchEx + SupportsHoldings
    def __init__(self, name="node", *, default_processor=DEFAULT_PROCESSOR,
                 process=default_process, eval_path="/v1", outbound=None,
                 data=None, concurrency=DEFAULT_RUN_CONCURRENCY, strict_fields=False)
    @node.endpoint("/claude")        # handler(Request) -> str | Awaitable[str]
    @node.holdings(collection=None)  # '@'  handler(collection: str | None) -> str
    @node.identity("emily")          # '@emily[/coll]' handler(collection) -> str
    node.data_route("/api/x", provider)   # static str or callable data reads
    async def evaluate(expression, *, env=None) -> Url4Result
    def asgi() -> ASGI app;  def serve(host, port, **uvicorn_kw)   # lazy uvicorn
    async def aclose()
```

Dispatch contract (verified against engine wire conventions):
- **Endpoint paths are intent processors.** `Request(path, context, intent, params)` —
  `context` is *opaque, already-resolved* data (engine-internal dispatches
  wire-escape resolved text; re-evaluating it would mis-parse). Handlers never
  receive unresolved expressions.
- **The eval path is the protocol surface.** `GET /v1?…&q=<expr>` reconstructs the
  decoded expression and evaluates it via `run(expr, io=self)` — sources resolve
  here, the intent dispatches to `default_processor` (a registered endpoint). This is
  what a `Client` remote query targets, closing the loop end-to-end.
- Relative fetches route inbound (endpoints / eval / data routes); absolute
  `http(s)://`, `url4://`, etc. delegate to the outbound layer (lazily-owned
  `HttpIOLayer` unless injected).
- Holdings: `@` → self registry keyed by collection; `@name` → identity registry;
  unknown identity → `unknown_identity` (permanent); handlers may raise
  `identity_access_denied`/`consent_*` themselves. Requestor-identity auth and
  consent hooks are deferred (need URL4-Auth-Token / Part C transport spec).
- ASGI: plain async callable, GET-only (405 otherwise); errors map by code —
  `ParseError`→400, `unknown_identity`/unknown path→404, `identity_access_denied`/
  `consent_*`→403, transient `ResolutionError`→502, other `Url4Error`→500; body
  is the result string (200, text/plain) or `{"error": {code, message}}`.
- No envelope JSON invented: Parts C+ define the response envelope; v1 returns the
  raw result body and reserves the shape.

## Out of scope (explicit)

Quorum/trigger enforcement, streaming delivery, response envelope (§18), settlement/
attribution reporting, policy registries, auth/consent transport, telemetry planes
(url4-engine doctrine T/O/F), module-level query sugar, `screamingface` branding layer.
