# ScreamingFace — Setup Guide

The definitive, end-to-end guide to getting ScreamingFace running, connecting the
AI backends, and cutting a build. This is the source of truth for setup; if the
root `README.md` quickstart disagrees with this file, this file wins.

ScreamingFace is three cooperating pieces:

- **Desktop app** (`apps/desktop/`) — an Electron control plane. It owns the UI
  (Settings, Eval Studio, URL4/Code Studio, Sessions) and **manages the local
  server for you** (creates the venv, syncs deps, starts/stops the process).
- **Local server** (`apps/server/`) — a FastAPI, plugin-based service that runs
  the URL4 engine, the per-provider frontends, and the Python runner. Reads
  `apps/server/sf.json`.
- **AI Gateway** (`apps/aigateway/`) — a LiteLLM-based service that holds your
  provider credentials and brokers all OAuth/refresh. The server starts it
  automatically (the `aigw-runner` plugin) on port `9105`.

Most users only ever touch one thing: **the Settings screen, to connect their
model subscriptions.** Everything else is automatic.

---

## 1. System requirements

| Tool | Version | Notes |
|------|---------|-------|
| OS | macOS (arm64 / x64) or Linux (x64 / arm64) | Windows: packaged app only (NSIS installer); from-source dev is macOS/Linux. |
| Python | ≥ 3.12 | `uv` installs and pins this for you; you do **not** need a system Python. Builds pin `3.12.9`. |
| uv | latest | The Python toolchain/installer. Builds pin `0.6.12`. |
| Node.js | ≥ 18 | Only needed for the desktop app / from-source dev. |
| mkcert | optional | Only if you run the server with SSL on. The default dev config runs plain HTTP, so this is optional. |

Install `uv` and verify everything:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv
python3 --version   # 3.12+  (or let uv manage it)
uv --version
node --version      # 18+
```

There are **two ways** to run ScreamingFace. Pick one:

- **[Option A — Packaged app](#2-option-a--install-the-packaged-app-end-users)** — for users. One command, no toolchain.
- **[Option B — From source](#3-option-b--run-from-source-developers)** — for development.

Either way, you finish at **[Section 4 — Connect the AI backends](#4-connect-the-ai-backends-the-one-step-everyone-does)**.

---

## 2. Option A — Install the packaged app (end users)

The installer lives in the public **`OpenMined/sf-installer`** repo. It detects
your OS/arch, downloads the latest release, and installs it:

```bash
curl -fsSL https://raw.githubusercontent.com/OpenMined/sf-installer/main/install.sh | sh
```

> The installer lives at the root of the `sf-installer` repo. It installs the
> newest release by default. Pin a version with the **full release tag**
> (`SF_VERSION=desktop-v0.3.0`), or change the location with `SF_INSTALL_DIR`.

What it does:

- **macOS** → installs `ScreamingFace.app` into `/Applications`, clears the
  Gatekeeper quarantine flag, and launches it.
- **Linux** → extracts to `~/.local/share/ScreamingFace` and symlinks
  `~/.local/bin/screamingface` (make sure `~/.local/bin` is on your `PATH`).

First launch takes a few seconds: the app provisions a private Python
environment and starts the local server. Then go to
**[Section 4](#4-connect-the-ai-backends-the-one-step-everyone-does)**.

---

## 3. Option B — Run from source (developers)

Running from source is the developer path. The full guide —
clone + git hooks, running via the desktop app or the headless server,
the ports table, tests/lint/typecheck, and the git workflow — lives in the
root **[`CONTRIBUTING.md`](../CONTRIBUTING.md)**.

The short version:

```bash
git clone https://github.com/OpenMined/screamingface.git
cd screamingface
git config core.hooksPath .githooks   # enables the pre-commit guards
make sync                             # uv-syncs apps/server + apps/aigateway

# then either run the desktop app (auto-manages the server)…
cd apps/desktop && npm install && npm run dev
# …or run the server headless:
make run-server                       # http://127.0.0.1:8000, SSL off
```

---

## 4. Connect the AI backends (the one step everyone does)

Open the app, go to **Settings**, and connect the providers you have
subscriptions for. Each is a browser OAuth flow — click *Connect*, sign in,
done. Tokens are brokered and stored by the AI Gateway; you never paste an API
key.

| Provider | What you sign in with | Notes |
|----------|----------------------|-------|
| **Claude** | Anthropic / Claude subscription | OAuth via your Claude account. |
| **Codex** | ChatGPT / OpenAI account | OAuth; uses loopback callback. |
| **Gemini** | Google account (Code Assist) | Google OAuth. |
| **Antigravity** | Google account | Google OAuth, experimental. **See the activation note below.** |
| **Ollama** | — | Local only, no auth. Point it at your Ollama install (`http://localhost:11434`). |

After connecting, the model dropdowns populate from the gateway's live model
list — you don't hand-maintain model names.

### Where credentials live

The gateway stores tokens **encrypted at rest** (AES-256-GCM) in its
`credential_blobs` table — SQLite locally, Postgres when hosted. There is **no
OS keychain** involved on the gateway side. For hosted/multi-worker runs, set a
master key:

```bash
# generate a base64 32-byte key for AIGATEWAY_SECRET_KEY
python3 -c 'import os,base64;print(base64.b64encode(os.urandom(32)).decode())'
```

Locally, a single-worker dev gateway auto-generates and persists a key (with a
warning) so you don't have to.

### ⚠️ Antigravity activation gotcha (read this if Antigravity won't connect)

Antigravity is a Google-side experimental surface. The OAuth sign-in can
**succeed** while the backend still reports **degraded / "provider
unavailable"** on the first calls. This is **not** a ScreamingFace bug — the
Google account has to be **activated for Antigravity first, and then there's a
short wait** before the upstream starts serving.

If Antigravity shows unavailable right after connecting:

1. Confirm the Google account actually has **Antigravity enabled**.
2. **Wait** a few minutes, then retry the run.
3. If it still fails, **re-connect** the provider in Settings (the profile flips
   to an error state on the first failed call and needs a fresh auth).

A healthy Antigravity backend served the demo's best numbers (≈72% on
ScoredLiveTruth with context), so it's worth getting connected.

---

## 5. Verify it works

- **Server up:** `uv run sf plugin list` shows plugins as healthy, or the
  desktop **Dashboard** shows the server running.
- **Gateway up:** `curl -sf http://localhost:9105/healthz`.
- **Backends connected:** Settings shows each provider as *authenticated*.
- **End to end:** in **Eval Studio**, run a small URL4 spec and watch the
  per-row results stream in; a final accuracy score prints at the end.

---

## 6. Cut a new build / release

Releases are automated with **release-please**, which manages three independent
components: `desktop`, `server`, `aigateway` (tags `desktop-v*`, `server-v*`,
`aigateway-v*`).

**A plain PR merge to `main` does not produce a build.** The flow is:

1. Land feature/fix PRs on `main` using conventional commits (`feat:`, `fix:`).
2. The **release-please** workflow opens a *release PR* per changed component
   (version bump + changelog).
3. **Merge that release PR.** release-please then creates the git tag
   (e.g. `desktop-v0.3.0`).
4. The tag push triggers `release-desktop.yml`, which builds installers on
   macOS (arm64 + x64 → `.dmg`, `.zip`) and Linux (x64 → `.AppImage`,
   `.tar.gz`), attaches them to a draft GitHub Release, and mirrors them to the
   public `OpenMined/sf-installer` repo.

To build **on demand** without waiting for release-please, dispatch the release
workflow manually (GitHub → Actions → *Release Desktop* → *Run workflow*, with
the target tag), or push a tag yourself after bumping
`apps/desktop/package.json`:

```bash
# only if you are intentionally cutting a manual release
git tag desktop-v0.3.0
git push origin desktop-v0.3.0
```

Local Linux packaging for a smoke test (no publish):

```bash
docker build -f Dockerfile.build -t sf-build . && \
  docker run --rm -v "$PWD/out:/out" sf-build   # AppImage + tar.gz land in ./out
```

Or directly with electron-builder:

```bash
cd apps/desktop
npm run build       # compile main/preload/renderer
npm run package     # electron-builder → dist/<platform>/
```

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Antigravity "unavailable" right after connecting | Google-side activation + wait; re-connect. See [§4](#-antigravity-activation-gotcha-read-this-if-antigravity-wont-connect). |
| A backend silently scores 0% | The provider isn't connected/healthy — check Settings; the run preflight warns when a referenced backend is down. |
| Port 8000 / 9105 already in use | The server auto-increments; or pass `uv run sf run --port <n>`. |
| `mkcert` not installed but SSL on | Run with `--no-ssl` (default dev config is already HTTP). |
| Desktop won't start the server | Check the app's `debug.log` under the OS app-support dir (macOS: `~/Library/Application Support/`). |
| `uv` not found | Install it: `curl -LsSf https://astral.sh/uv/install.sh | sh`. |

---

## 8. Reference

- **Config:** `apps/server/sf.json` — server block, the plugin list, and
  per-plugin config (ports, upstreams, gateway URL). Override inline with the
  `SF_CONFIG` env var.
- **Dev tasks:** `make help` lists every target (`sync`, `run-server`,
  `run-aigateway`, `test`, `test-fast`, `lint`, `fmt`, `typecheck`).
- **Gateway internals:** `apps/aigateway/README.md` (credential store, secret
  key, migrations, the Antigravity `pluginType` contract note).
- **Desktop internals:** `apps/desktop/ARCHITECTURE.md` (venv bootstrap,
  bundled Python, packaging).
