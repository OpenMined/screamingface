# url4 quickstart

Run a `url4` node that evaluates url4 expressions and dispatches them to local
commands over HTTP.

## Install

```bash
cd packages/url4
uv sync --extra server
```

## Configure — `url4.toml`

`[commands]` maps a route path to an argv template. `{intent}`/`{context}` are
substituted as single tokens; the resolved context is piped to the command's
stdin, stdout is the result.

```toml
# url4.toml
host = "127.0.0.1"
port = 4404
eval_path = "/v1"          # GET-only eval endpoint
default_route = "/upper"   # reduce route for fan-out; defaults to first command

[commands]
"/upper" = ["tr", "a-z", "A-Z"]
"/bash"  = "bash -lc {intent}"   # arbitrary local exec — 127.0.0.1 only
```

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
  collides with `/healthz`.

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
