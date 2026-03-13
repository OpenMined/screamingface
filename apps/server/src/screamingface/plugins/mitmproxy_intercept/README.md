# mitmproxy-intercept plugin

Transparent traffic interception via mitmproxy `--mode local`.
Intercepts outgoing API calls (e.g. from Claude CLI) and routes them
through ScreamingFace frontend plugins before forwarding upstream.

## How it works

```
Claude CLI ──► mitmproxy (local redirect) ──► SF frontend proxy ──► api.anthropic.com
                 addon.py rewrites              proxy.py forwards
                 host/port to frontend          with tracing spans
```

1. **mitmproxy_rs** sets up OS-level traffic redirection using a macOS
   "redirector app" (Network Extension) or pf rules (Linux).
2. **addon.py** runs inside the `mitmdump` subprocess — it reads
   `~/.screamingface/frontends.json` and rewrites each intercepted
   flow's host/port/scheme to the matching frontend.
3. The **frontend proxy** (e.g. `claude_frontend/proxy.py`) receives
   the rewritten request, creates OTEL spans, and forwards to the
   real upstream API.

## macOS setup

`--mode local` on macOS uses a helper "redirector app" that registers
as a transparent proxy via macOS Network Extension APIs.

### First-time approval

The first time you run `sf run` with this plugin enabled, macOS will
prompt you to approve the mitmproxy network extension:

1. A system dialog should appear — click **Allow**.
2. If you missed it, go to **System Settings > General > Login Items
   & Extensions > Network Extensions** and enable the mitmproxy entry.

Without this approval, mitmproxy starts without errors but silently
intercepts nothing.

### Verifying it works

While the server is running:

```bash
# Check the redirector app is running
ps aux | grep -i mitmproxy | grep -v grep

# Check system extensions
systemextensionsctl list

# Check pf rules (if pf-based)
sudo pfctl -sr
sudo pfctl -a '*' -sr
```

### Manual test

**Terminal 1** — start mitmdump directly:

```bash
cd apps/server
sudo .venv/bin/mitmdump \
  --mode local:claude \
  --listen-port 8888 \
  --allow-hosts 'api\.anthropic\.com' \
  -s src/screamingface/plugins/mitmproxy_intercept/addon.py \
  -v
```

Expected output:

```
[...] Existing mitmproxy redirector app is up-to-date.
[...] Loading script .../addon.py
[...] Initializing macOS proxy ...
[...] Starting redirector app...
[...] Loaded frontend mapping: ['api.anthropic.com']
```

**Terminal 2** — run Claude CLI:

```bash
claude -p "Say exactly: INTERCEPT_TEST" --output-format text
```

If interception works, Terminal 1 should show addon trace lines:

```
[E2E-TRACE] ADDON intercepted api.anthropic.com:443 → routing to 127.0.0.1:9101 | trace=<uuid>
```

### Crash recovery

The macOS network extension persists independently of the mitmdump
process. If the SF server crashes or is killed without a clean shutdown
(`kill -9`), the extension keeps redirecting traffic into a void —
Claude CLI will hang or fail.

**Automatic recovery**: the plugin clears any stale intercept on
startup (via `mitmproxy_rs.local.set_intercept("")`), so restarting
`sf run` restores normal operation. An `atexit` handler also ensures
cleanup on most exit paths (Ctrl+C, uncaught exceptions, `sys.exit`).

**Manual recovery** if `sf run` isn't available:

```bash
# Option 1: disable the extension in System Settings
# System Settings > General > Login Items & Extensions > Network Extensions

# Option 2: clear the intercept programmatically
cd apps/server
uv run python -c "
import asyncio
from mitmproxy_rs.local import start_local_redirector
async def clear():
    r = await start_local_redirector(lambda s: None, lambda s: None)
    r.set_intercept('')
asyncio.run(clear())
print('Intercept cleared')
"
```

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| mitmdump starts, no traffic intercepted | macOS network extension not approved — check System Settings |
| `Password:` prompt appears multiple times | `sudo` credential cache expired between calls |
| addon loads but no `[E2E-TRACE] ADDON` lines | Process filter mismatch — verify with `ps -eo comm \| grep claude` |
| `ADDON intercepted` but no `PROXY received` | `frontends.json` missing or wrong — check `~/.screamingface/frontends.json` |

## Configuration (sf.json)

```json
{
  "mitmproxy-intercept": {
    "enabled": true,
    "rules": [
      {
        "domain": "api.anthropic.com",
        "frontend": "claude-frontend",
        "process_filter": "claude"
      }
    ],
    "proxy_port": 8888
  }
}
```

- **domain** — the upstream domain to intercept
- **frontend** — which frontend plugin handles this domain
- **process_filter** — only intercept traffic from processes matching
  this name (verified via `ps -eo comm`); maps to `--mode local:<filter>`
- **proxy_port** — mitmdump listen port (used for `--listen-port`)

## Trace ID propagation

The addon injects an `x-sf-trace-id` header (UUID) into every
intercepted request. This ID propagates through the full chain:

```
mitmproxy addon  →  x-sf-trace-id header  →  SF proxy (sf.trace_id span attr)  →  upstream
```

In Phoenix, filter by `sf.trace_id` to see the complete journey of a
single request across all layers.

## Files

| File | Runs in | Role |
|---|---|---|
| `plugin.py` | SF server process | Starts mitmdump, writes `frontends.json`, manages lifecycle |
| `addon.py` | mitmdump subprocess | Routes intercepted flows to frontends, injects trace ID |
| `state.py` | SF server process | Crash recovery — persists PID/port to `~/.screamingface/mitmproxy-intercept-state.json` |
