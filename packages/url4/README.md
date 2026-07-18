# url4

Core library for the **url4 expression protocol** — grammar, parser, AST,
interpreter, and scope — plus a CLI that runs the engine as an HTTP node.

A url4 expression *is* the address. `(/upper(hello)!'go')` names a route, a
context, and an intent in one string; the engine compiles it to a DAG, fans out,
and reduces. Nodes speak GET, and any leaf can be a local command.

The library core is framework-free — `import url4` pulls in no web framework.

## Install

```bash
pip install url4              # library + `url4 eval`
pip install 'url4[server]'    # adds uvicorn, for `url4 serve`
```

From a checkout of the monorepo:

```bash
cd packages/url4
uv sync --extra server
```

## Quickstart — serve a node

The rest of this page walks through `url4 serve`: declaring a node's surface in
`url4.toml`, running it, and calling it over HTTP.

## Configure — `url4.toml`

One file declares the node's whole surface: what it can **do** (`[commands]`) and
what it can **read** (`[data]`, `[holdings]`, `[identities]`).

```toml
# url4.toml
host = "127.0.0.1"
port = 4404
eval_path = "/v1"          # GET-only eval endpoint
default_route = "/upper"   # reduce route for fan-out; defaults to first command

[commands]
"/upper" = ["tr", "a-z", "A-Z"]
"/bash"  = "bash -lc {intent}"   # arbitrary local exec — 127.0.0.1 only
"/model" = "python gateway.py --temp {param:temperature}"   # your own LLM backend
```

### Commands — what the node can do

`[commands]` maps a route path to an argv template. The template sees everything a
Python handler would, each substituted as a **single token** (never re-split):

| Token | Value |
|---|---|
| `{intent}` | the resolved intent |
| `{context}` | the resolved context — also piped to the command's **stdin** |
| `{param:<name>}` | one query param (`/model?temperature=0.7`); `""` if absent |
| `{params}` | all params as JSON |

**stdout** is the result. Substitution happens in one pass over *your* template, so
token-shaped text in a caller's input stays literal — it never expands.

### Reads — what the node can see

Without these, a served node has no sources: `(/rubrics/42)` has nothing to resolve
against and `@` fails. Each entry is an inline string, or a table with **exactly one**
of `value` / `file` / `command`.

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
- `media_type` works on `[data]` only, and decides how a collection parses — a
  one-line JSON array served as `text/plain` would collapse to a single element.
- The key `default` means the unqualified shelf, so a collection can't be *named*
  `"default"`.

> **Note.** `@name/collection` works in an expression, but a scoped shelf on *your own*
> node has no syntax yet — `@` always means the default shelf and `@/science` is a parse
> error. Non-`default` `[holdings]` entries are reachable from the SDK, not from an
> expression.

## Run

```bash
uv run --extra server url4 serve --config url4.toml
```

Flags override env vars (`URL4_HOST`, `URL4_PORT`, `URL4_DEFAULT_ROUTE`,
`URL4_EVAL_PATH`, `URL4_CONFIG`, ...) which override the TOML file, which
overrides built-in defaults. An **empty** env var counts as unset — `URL4_HOST=`
in a `.env`/compose file falls through to the TOML value, then the default,
exactly as an absent variable would.

## Binding & exposure

A command route is **arbitrary local execution reachable over HTTP** — that is the
point of the feature, and it is why the node binds `127.0.0.1` by default.

- Loopback is exactly `127.0.0.1`, `::1`, `localhost`. Anything else prints a loud
  warning, plus a second one naming the command routes now remotely reachable.
- To bind every interface, write `0.0.0.0` explicitly (it warns). An **empty** host
  is rejected outright: it would bind `0.0.0.0` *and* `::` while reading as "unset".
- Config problems fail fast **before** the bind, with exit code 2 — an undeclared
  `default_route`, an empty `[commands]`, an `eval_path` that is not a `/path` or
  collides with `/healthz`, a `[data]` path clashing with a command or reserved
  route, an invalid identity name, or a provider declaring zero or several of
  `value`/`file`/`command`.

Put an authenticating reverse proxy in front of the node before exposing it. v1
ships no authn/authz of its own.

## Try it

```bash
# liveness
curl http://127.0.0.1:4404/healthz

# eval — dispatch to the /upper command
curl 'http://127.0.0.1:4404/v1?q=(/upper(hello world)!%27go%27)'

# fan-out + reduce via default_route
curl 'http://127.0.0.1:4404/v1?q=(/upper(a)!%27go%27,+/upper(b)!%27go%27)!%27choose+the+best%27'

# read a [data] route as a bare relative URI
curl 'http://127.0.0.1:4404/v1?q=(/rubrics/42)!%27%27'

# holdings — the node's own `@`, and a named identity's shelf
curl 'http://127.0.0.1:4404/v1?q=(@)!%27%27'
curl 'http://127.0.0.1:4404/v1?q=(@emily/notes)!%27%27'
```

## Errors

Errors come back as JSON: `{"error": {"code": "...", "message": "..."}}`.

| Status | Cause |
|---|---|
| 400 | parse error / unbound reference |
| 404 | unknown route |
| 502 | command exited non-zero |
| 503 | over `--max-inflight` |
| 504 | request exceeded `--timeout` |

## One-shot eval (no server)

```bash
uv run url4 eval "(/upper(hi)!'go')"
```
