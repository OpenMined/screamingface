---
description: How to work in the ScreamingFace polyglot monorepo with many concurrent developers — which app/component a change belongs to, the per-stack toolchain (Python/Go/JS/TS), how to add a new app or shared package, which CI runs, who reviews, and the branch/commit/PR/merge/release rules. Use when starting any change here, when unsure where code goes, which tests or CI apply, who reviews, or how to open and merge a PR.
user_invocable: true
---

# Working in this repo

ScreamingFace is a **polyglot monorepo** worked on by 10+ developers concurrently. This skill is the **routing map**: given a change, it tells you which component you're in, the toolchain, the CI that will gate it, who reviews, and the branch/PR/release lane.

> **This skill routes; it does not restate policy.** Process rules live in **`docs/team-development.md`** (the canonical process doc). Setup lives in **`CONTRIBUTING.md`**. Per-app guardrails live in each app's `CLAUDE.md`. When this skill and a canonical doc disagree, the canonical doc wins — fix the drift.

## 1. Component taxonomy

- **`apps/<name>`** — an independently deployable service or app. Has its own toolchain, lockfile, CI workflow, and release lane.
- **`packages/<name>`** — a shared library consumed by **≥2** components; **not** independently deployed. (None exist yet — the convention is reserved. Put shared code here instead of importing one app's internals from another.)
- **`web/`** — static site (`web/public/` → GitHub Pages; `web/portal/` leaderboard). No build toolchain.

**Rule:** apps never import another app's internals. Cross-app sharing goes through `packages/` (or a stable HTTP contract). This keeps each app independently testable and releasable.

## 2. Current apps — the routing table

| Component | Stack | Run / test / lint / typecheck | Gating CI | Release lane | Key guardrails |
|---|---|---|---|---|---|
| `apps/server` | Python · uv · FastAPI (plugins, CLI `sf`) | `make run-server` · `make test-server` (`-fast` skips e2e) · `make test-e2e` · `make lint` · `make typecheck` | `server-tests.yml` + `pre-commit.yml` (pyright gate) | release-please → `server-v*` → `release-server.yml` (GHCR image + sf-installer mirror) | **Core must not import plugins.** New behavior = a plugin. Deprecated intercept plugins are off-limits (see root `CLAUDE.md`). |
| `apps/aigateway` | Python · uv · FastAPI (LiteLLM) | `make run-aigateway` · `make test-aigateway` (`-fast`, `-live`) · `make check-no-enterprise` · `make lint` · `make typecheck` | `aigateway-tests.yml` (matrix 3.12/3.13) | release-please → `aigateway-v*` → `release-aigateway.yml` (GHCR image + Helm chart + mirror) | **Never import `litellm-enterprise`** (guarded). Credentials via ORMStore/Tortoise `credential_blobs`, **no OS keychain**; secrets AES-256-GCM; master key `AIGATEWAY_SECRET_KEY` never stored/logged. See `apps/aigateway/CLAUDE.md`. |
| `apps/scoreboard` | Python · uv · FastAPI | `cd apps/scoreboard && uv run pytest` · `uv run ruff check .` · `uv run pyright` (not in the root Makefile) | `scoreboard-tests.yml` (also fires on `web/portal/**`) | **Manual** tag `scoreboard-v*` → `release-scoreboard.yml` (GHCR image + Helm; **not** in release-please) | Portal artifacts under `web/portal/` are covered by this workflow. |
| `apps/desktop` | TS · npm · Electron + Vite | `cd apps/desktop && npm run dev` · `npx vitest run` · `npm run lint` · `npm run build` (no `test` npm script) | `desktop-tests.yml` | release-please → `desktop-v*` → `release-desktop.yml` (electron-builder artifacts + mirror) | Bundles `apps/server` + `apps/aigateway` **source** at build time. External HTTP (scoreboard/portal) must run in the Electron **main** process, not the renderer (CORS). |
| `web/public` | Static HTML/CSS/JS | edit files directly | — | `deploy-website.yml` on push to `main` touching `web/public/**` (unversioned) | — |

**Owner / reviewer per path:** see `.github/CODEOWNERS` (once added) or the **Cross-Service Collaboration** section of `docs/team-development.md`. This skill deliberately does not hardcode owners — read them from one place.

## 3. Which CI runs on my PR?

CI is **path-filtered**: a PR only triggers the workflow(s) for the paths it touches. A desktop-only PR runs `desktop-tests.yml`, not the Python suites. A PR touching two apps runs both. Each `<component>-tests.yml` also self-triggers when its own YAML changes.

## 4. Adding a new component (any stack: Python / Go / JS / TS)

Bring whatever stack fits; satisfy this **invariant contract** so the coordination machinery sees it:

| Stack | Pkg manager | Layout | Lint | Typecheck | Test | CI: copy from | Release |
|---|---|---|---|---|---|---|---|
| Python | uv + hatchling | `src/<pkg>/` | ruff | pyright | pytest (+ markers) | `aigateway-tests.yml` | release-please `python`, or manual tag |
| JS / TS | npm | `src/` | eslint | `tsc --noEmit` | vitest | `desktop-tests.yml` | release-please `node`, or manual tag |
| Go | go modules | `cmd/` + `internal/` / `pkg/` | golangci-lint | `go vet` / build | `go test ./...` | new `go-<comp>-tests.yml` | release-please `go`, or manual tag |

**7-step checklist for a new component:**
1. Pick `apps/` (deployable) or `packages/` (shared lib).
2. Self-contained toolchain + lockfile; no dependency on another app's internals.
3. Add a path-filtered `.github/workflows/<component>-tests.yml` running that stack's lint + typecheck + test.
4. Register a release lane — add to `release-please-config.json` **or** document a manual tag (or mark "not released").
5. Add a `.github/CODEOWNERS` entry.
6. Add the matching `dependabot.yml` ecosystem (`uv` / `npm` / `gomod`).
7. Wire it into the root `Makefile` dispatcher.

## 5. Where does my change belong? (core vs plugin)

- **`apps/server`:** almost everything is a **plugin** under `src/screamingface/plugins/<name>/`. Core defines ports (registries); plugins implement them. **Core must not import plugins.** New CLI/route/hook/base-lib → a plugin (use the `create-plugin` skill). Never route new behavior through the deprecated `claude_intercept` / `mitmproxy_intercept` / `claude_env_intercept` shims.
- **`apps/aigateway`:** new providers/secrets backends implement the port and register in the factory — never edit ORMStore. See `apps/aigateway/CLAUDE.md`.
- **Shared logic used by ≥2 apps:** it belongs in `packages/`, not copied.

## 6. Branch / commit / PR / merge — the 5-second version

Full rules: **`docs/team-development.md`**. Quick reference:

- **Branch:** `SF-{n}-{description}`, `n` = the Asana `SF` field (auto-assigned; don't invent one). Never commit to `main`.
- **Commit:** `SF-N: summary` or `feat(SF-N): …`; put the Asana permalink in the body; **no `Co-Authored-By`** lines.
- **Keep current:** rebase on `origin/main` (don't merge `main` into your branch); force-push only your own branch.
- **Merge:** squash-merge; the author merges after review approval + green required checks.
- **Checks are path-dependent.** Live tests (`AIGW_LIVE=1`, `e2e_live`) are opt-in diagnostics, **not** merge gates.
- **WIP limit:** 2 tickets per dev (one coding, one in review).
- **PR body:** Asana link · summary · test plan · screenshots for UI. If a PR spans two owners' areas, state the cross-service contract in the body.

## 7. Pointers (single source of truth)

- **Process policy:** `docs/team-development.md`
- **Setup / run-from-source:** `CONTRIBUTING.md`
- **Per-app guardrails:** `apps/*/CLAUDE.md`, `apps/server/CONTRIBUTING.md`
- **Glossary / architecture:** `docs/GLOSSARY.md`, `docs/architecture/`
- **Scaffold a server plugin:** the `create-plugin` skill
- **Brand / UI law:** the `screamingface-design` skill
