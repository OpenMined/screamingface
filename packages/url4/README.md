# url4

**A standalone, framework-free core library for the url4 expression protocol.**

url4 expresses multi-source computation as `(sources)!intent` — *"given this data, do
this"* — recursively, with `$name` / `$N` references resolved through a lexical scope. An
expression compiles into an executable **DAG** of typed nodes: each node owns its own logic
behind a small protocol, independent nodes run in parallel, and nested fragments parse
lazily inside the node that owns them. All I/O is inverted behind an `IOLayer` port, so the
core is deterministic and testable.

Part of [ScreamingFace](https://screamingface.ai) by [OpenMined](https://openmined.org).

## Install

```bash
pip install url4              # library + `url4 eval`
pip install 'url4[server]'    # adds uvicorn, for `url4 serve`
```

url4 requires Python 3.12+ and ships type information (PEP 561). From a checkout of the
monorepo:

```bash
cd packages/url4
uv sync --extra server
```

## Quickstart

```python
from url4 import Client, StaticIOLayer, evaluate_sync

io = StaticIOLayer(fetch_map={"https://x": "some article text"})
text = "(a=https://x, tone='formal')!'Summarize $a in a $tone tone'"

# scripts and REPLs: one call, no event loop to manage
print(evaluate_sync(text, io).text)

# async code owns a Client (Client() with no io speaks real HTTP)
async with Client(io) as client:
    res = await client.evaluate(text)
    print(res.request)               # the canonical url4 text that ran
```

The execution engine — DAG compilation, executor, lowering — lives one level down:
`from url4.dag import compile_expression, run`.

## Features

- **Expression-as-computation** — `(sources)!intent` with recursive fan-out and `$name`/`$N`
  lexical references.
- **Typed DAG** — expressions compile to a graph of typed nodes; independent nodes execute
  concurrently.
- **Inverted I/O** — all side effects go through the `IOLayer` port (`StaticIOLayer` for
  tests/offline, HTTP for real fetches), keeping the core pure and deterministic.
- **Fully typed** — passes `pyright`; type hints ship to consumers.

## The `url4` CLI — serve a node

A url4 expression *is* the address. `(/upper(hello)!'go')` names a route, a context, and an
intent in one string; the engine compiles it to a DAG, fans out, and reduces. Nodes speak
GET, and any leaf can be a local command. The `url4` console script runs the engine as an
HTTP node (`url4 serve`) or evaluates an expression locally (`url4 eval`) — `serve` needs the
`url4[server]` extra above.

### Configure — `url4.toml`

One file declares the node's whole surface: what it can **do** (`[commands]`) and what it can
**read** (`[data]`, `[holdings]`, `[identities]`).

```toml
# url4.toml
host = "127.0.0.1"
port = 4404
eval_path = "/v1"          # GET-only eval endpoint
default_route = "/model"   # reduce route for fan-out; defaults to first command

[commands]
"/upper" = ["tr", "a-z", "A-Z"]
"/bash"  = "bash -lc {intent}"   # arbitrary local exec — 127.0.0.1 only
"/model" = "python gateway.py --temp {param:temperature}"   # your own LLM backend
```

> **Picking `default_route`.** A fan-out `(a, b)!'pick'` reduces by calling this route with
> the per-source results **merged into its `{intent}`, and empty stdin**. So a reduce backend
> must consume `{intent}` — a stdin-only command like `["tr", "a-z", "A-Z"]` reads nothing and
> returns an empty `200`. Unset, `default_route` is the first declared command, which is only
> a sensible reduce backend by coincidence; name one deliberately.

#### Commands — what the node can do

`[commands]` maps a route path to an argv template. The template sees everything a Python
handler would, each substituted as a **single token** (never re-split):

| Token | Value |
|---|---|
| `{intent}` | the resolved intent |
| `{context}` | the resolved context — also piped to the command's **stdin** |
| `{param:<name>}` | one query param (`/model?temperature=0.7`); `""` if absent |
| `{params}` | all params as JSON |

**stdout** is the result. Substitution happens in one pass over *your* template, so
token-shaped text in a caller's input stays literal — it never expands.

#### Reads — what the node can see

Without these, a served node has no sources: `(/rubrics/42)` has nothing to resolve against
and `@` fails. Each entry is an inline string, or a table with **exactly one** of
`value` / `file` / `command`.

```toml
[data]                                    # bare relative URIs in an expression
"/rubrics/42" = "score 1-5 on clarity"
"/corpus"     = { file = "corpus.md" }    # re-read per request — edit, no restart
"/rows"       = { command = ["./rows.sh"], media_type = "application/json" }

[holdings]                                # `@` — this node's own holdings
default = "my working notes"              # the unqualified shelf
science = { file = "shelves/science.md" }

[identities.emily]                        # `@emily` / `@emily/notes`
default = "Emily's default holdings"
notes   = { file = "emily/notes.md" }
```

- A `file` provider is read **per request**, so edits land without a restart.
- A `command` provider runs your argv (no shell, empty stdin) and uses its stdout;
  `{collection}` substitutes the requested holdings collection.
- `media_type` works on `[data]` only, and decides how a collection parses — a one-line JSON
  array served as `text/plain` would collapse to a single element.
- The key `default` means the unqualified shelf, so a collection can't be *named* `"default"`.

**Addressing a shelf.** A bare `@` is your `default` shelf. To pick another, qualify the eval
path — per the URL4 spec a bare `@` takes no collection suffix (`@/science` is a parse error),
so the collection travels in the path:

```bash
curl 'http://127.0.0.1:4404/v1?q=(@)!%27%27'              # default shelf
curl 'http://127.0.0.1:4404/v1/science?q=(@)!%27%27'      # the "science" shelf
curl 'http://127.0.0.1:4404/v1/drafts/2026?q=(@)!%27%27'  # segments join with "/"
```

An unknown qualifier falls back to `default`. The qualifier scopes *your* shelves only —
`@emily/notes` keeps its own collection either way. Because `{eval_path}/…` is reserved for
this, declaring a command or data route under it is a config error.

### Run

```bash
uv run --extra server url4 serve --config url4.toml
```

Flags override env vars (`URL4_HOST`, `URL4_PORT`, `URL4_DEFAULT_ROUTE`, `URL4_EVAL_PATH`,
`URL4_CONFIG`, ...) which override the TOML file, which overrides built-in defaults. An
**empty** env var counts as unset — `URL4_HOST=` in a `.env`/compose file falls through to the
TOML value, then the default, exactly as an absent variable would.

### Binding & exposure

A command route is **arbitrary local execution reachable over HTTP** — that is the point of
the feature, and it is why the node binds `127.0.0.1` by default.

- Loopback is exactly `127.0.0.1`, `::1`, `localhost`. Anything else prints a loud warning,
  plus a second one naming the command routes now remotely reachable.
- To bind every interface, write `0.0.0.0` explicitly (it warns). An **empty** host is
  rejected outright: it would bind `0.0.0.0` *and* `::` while reading as "unset".
- Config problems fail fast **before** the bind, with exit code 2 — an undeclared
  `default_route`, an empty `[commands]`, an `eval_path` that is not a `/path` or collides
  with `/healthz`, a `[data]` path clashing with a command or reserved route, an invalid
  identity name, or a provider declaring zero or several of `value`/`file`/`command`.

Put an authenticating reverse proxy in front of the node before exposing it. v1 ships no
authn/authz of its own.

### Try it

```bash
# liveness
curl http://127.0.0.1:4404/healthz

# eval — dispatch to the /upper command
curl 'http://127.0.0.1:4404/v1?q=(/upper(hello world)!%27go%27)'

# fan-out + reduce — both results reach default_route as its {intent}
curl 'http://127.0.0.1:4404/v1?q=(/upper(a)!%27go%27,+/upper(b)!%27go%27)!%27choose+the+best%27'

# read a [data] route as a bare relative URI
curl 'http://127.0.0.1:4404/v1?q=(/rubrics/42)!%27%27'

# holdings — the node's own `@`, and a named identity's shelf
curl 'http://127.0.0.1:4404/v1?q=(@)!%27%27'
curl 'http://127.0.0.1:4404/v1?q=(@emily/notes)!%27%27'
```

### Errors

Errors come back as JSON: `{"error": {"code": "...", "message": "..."}}`.

| Status | Cause |
|---|---|
| 400 | parse error / unbound reference |
| 404 | unknown route |
| 502 | command exited non-zero |
| 503 | over `--max-inflight` |
| 504 | request exceeded `--timeout` |

### One-shot eval (no server)

```bash
uv run url4 eval "(/upper(hi)!'go')"
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
