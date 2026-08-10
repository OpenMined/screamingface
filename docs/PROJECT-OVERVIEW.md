# ScreamingFace — Project Overview

> **Audience:** technical product managers (and anyone new to the project who wants the whole map in one read).
> **Goal:** what ScreamingFace is, who it's for, how the pieces fit, how a request flows, and how it ships.
> **Last verified against the codebase:** 2026-06-24.
> **Current activity & roadmap:** synthesized from the `#scream-lisbon` working channel (May–June 2026) — see [`scream-lisbon-digest.md`](scream-lisbon-digest.md). Roadmap/status claims below that come from Slack huddle notes are AI-summarized and may be imprecise.

> ⚠️ **Read this first — the docs have drifted from the code.** Several long-standing docs (`CLAUDE.md`, the root `README.md`, the original dev plan) describe an *earlier* layout that no longer matches what's on disk. This document describes **reality as it exists in the repo today** and flags every place the older docs disagree, so you can trust it over them. Where this file and an older doc conflict, this file was checked against the actual files.

---

## 0. Current Status & Roadmap (as of late June 2026)

> Source: the `#scream-lisbon` channel — full detail and links in [`scream-lisbon-digest.md`](scream-lisbon-digest.md). This is the *product/timeline* picture; the rest of this doc is the *verified-architecture* picture.

**The recent North Star was a benchmark-eval demo for Max Katz to run locally** (target "before June 19th"), built to prove one thing: **including the private source documents a benchmark was generated from measurably improves model accuracy.** The demo ran in the week of June 19; by **June 23 `main` was stable** with the scoreboard wiring tested, and **300+ PRs** have shipped. The 11-step demo user story (portal → copy a context-URL ensemble → run in Eval Studio → tweak → publish back to the leaderboard) is reproduced in the digest.

**Headline result (6/19 huddle):** ~**57.6%** accuracy with private data vs. ~**27%** without (~30-point lift); dropping Gemini from the 3-model ensemble costs ~10 points. (Earlier ad-hoc runs on smaller sets showed 36.4→48.5 and 45→100 — treat the numbers as a progression, and note eval **nondeterminism** was observed.)

**Two provider-auth shocks** shaped the demo: **Claude deprecated local auth ("P-FLAG") ~June 15**, and **Google deprecated the Gemini CLI + client ID** — forcing **API-key** mode and a migration to **Antigravity** as the Gemini front-end.

**The plan now: ScreamingFace V1, in two waves** → authoritative detail and the full team/owner split in **[`screamingface-v1-launch-plan.md`](screamingface-v1-launch-plan.md)**.

- **Wave 1 — Ensembles + shared leaderboard (eval-first), ships July 1, 2026.** Create / run / evaluate ensembles on a shared leaderboard, backed by **cached sessions** and **OM-subsidized compute**. This is the experiment-and-prove layer.
- **Wave 2 — SOTA via private data (SyftSpace), TBD.** Private data + private-data access as the route to SOTA on hard evals — the on-ramp to OpenMined's mission (*the public network for non-public information*).
- **Transition:** evaluation first → prove the lift with fake/public "private" data (done in the demo) → real private data via SyftSpace. Launch is **coordinated, not staggered** — one clear invitation so the whole community can step onto the network at once. The aim is to demonstrate an open, decentralized path to more intelligence and democratize access — not to win a market.
- **Where the capability comes from:** ensembling alone is a modest, assumed gain; the large, demonstrated jump comes from **private data + high model diversity** (private data = a specialized model, a private corpus via RAG, or any source the base models can't see). That's why Wave 2 is the payoff, not a sequel.

Supporting engineering directions in play (per the digest): a **CLI terminal-overlay** (Rust/Go PoCs built), **three install presets (cheap/fast/accurate)**, dropping the heavy Python-server dependency, new **HuggingFace + OpenRouter** backends, **tool-calling**, and a token-**cost** dimension. A separate bet — a **Slack→Claude personal-knowledge bridge** with url4-based governance — is dog-fooded in parallel.

---

## 1. What ScreamingFace Is

**ScreamingFace is an AI ensemble system that routes coding-CLI prompts through multiple AI models — Claude Code, Gemini CLI, Codex, and Ollama — to beat state-of-the-art (SOTA) benchmark scores.** Users install it locally; it sits between their coding CLI and the model providers, fans each request out to several models, combines the answers, and (the punchline) posts the resulting accuracy to a public leaderboard. Users can also share their AI credits with friends. It's built by **OpenMined**.

The product thesis in one line: **an ensemble of models, plus a leaderboard, is the entire argument.** The target user is a skeptical, benchmark-literate developer — so the proof isn't marketing copy, it's a reproducible number on a chart.

Three things make the system distinctive:

- **The ensemble** — combining several models to score higher than any single one of them alone.
- **url4** — a small, human-readable protocol for describing how a prompt fans out across models and how the results get reduced back into one answer (see §7).
- **Local-first + plugin-based** — it runs on the user's machine, and on the server side *every feature is a plugin* over a thin core.

---

## 2. Who It's For (personas in brief)

The primary (P0) audience is the **technical developer / AI benchmark enthusiast**: an engineer or ML practitioner who reads Hacker News and r/LocalLLaMA, already pays for Claude/Gemini/etc., runs local models with Ollama, is chronically token-constrained, and is *deeply allergic to marketing fluff*. They trust evidence, charts, and reproducible methodology — not adjectives.

Product/marketing implications that follow directly:

- Lead with **the benchmark number** and **the install command** — those are the hero, not a tagline.
- **No marketing adjectives** ("powerful," "seamless," "cutting-edge") — they cost trust with this audience.
- Transparency signals (GitHub, open methodology, honest "what gets installed") are credibility assets.

There's a secondary audience (thought-leaders / policy, "Audience 2"). **Before doing any copy, design, or positioning work, consult the persona routing doc:** [`personas/weighting-guide.md`](../personas/weighting-guide.md). Audience files live in [`personas/`](../personas/).

---

## 3. Repo Map (reality vs. the older docs)

> ⚠️ **Layout drift.** `CLAUDE.md` and the original dev plan describe top-level `web/`, `app/`, `cloud/`, and `brand/` directories. The **live layout** is `apps/{server, desktop, aigateway, scoreboard}` plus a static `web/portal/`. There is **no** `app/`, `cloud/`, or `brand/` directory on disk. The root `README.md` is *also* partly stale — it references `apps/web/` (Next.js) and a `packages/` folder that do **not** exist; the marketing site is the vanilla `web/portal/` served by the scoreboard app.

What actually exists at the top level:

| Directory | What it is |
|---|---|
| `apps/` | The four real applications — `server`, `desktop`, `aigateway`, `scoreboard` (see §4). |
| `web/portal/` | The static marketing + leaderboard website (vanilla HTML/CSS/JS, no build step). Served by `apps/scoreboard`. See §6. |
| `docs/` | Project docs: this file, [`GLOSSARY.md`](GLOSSARY.md), [`team-development.md`](team-development.md), `architecture/` diagrams, and `superpowers/` (plans & specs). |
| `personas/` | Audience personas, research cohorts, and the weighting/routing guide. |
| `infra/` | Deployment infra — single-node k3s on Azure (`infra/k3s/`). |
| `scripts/` | Build/install automation (Electron packaging, asset download). |
| `eval_scripts/` | Benchmark evaluation runners. |
| `.github/` | CI/CD workflows. |
| `.claude/` | Claude Code project config: commands & skills. |

There is **no** root `package.json`, no `pnpm`/`turbo`/`nx`. The monorepo is coordinated by a root **`Makefile`** and **per-app `release-please`** versioning. Each app builds and releases independently.

---

## 4. The Four Apps

### `apps/server/` — the plugin-based proxy (the heart of the system)
- **Stack:** Python 3.12+, FastAPI + Uvicorn, managed with **`uv`**. CLI via Typer (`sf run`).
- **Idea:** *"every feature is a plugin; the core is just plumbing."* The core provides three extension registries (hooks, classes, routes); all real behavior — frontends, backends, url4, eval — ships as plugins.
- **Config:** [`apps/server/sf.json`](../apps/server/sf.json) is the live manifest of which plugins are active and how they're configured.
- **Run:** `cd apps/server && uv sync && uv run sf run` (reads `sf.json`).
- More engineering detail: [`apps/server/README.md`](../apps/server/README.md) and [`apps/server/CLAUDE.md`](../apps/server/CLAUDE.md).

### `apps/aigateway/` — the unified model gateway
- **Stack:** Python 3.12+, FastAPI, **LiteLLM** for provider routing, Tortoise ORM (SQLite locally, Postgres in prod).
- **Idea:** exposes a single OpenAI-shape `/v1/chat/completions` endpoint and dispatches to upstream providers (Anthropic, OpenAI, Gemini, Ollama, …). The server's `aigw-*` backend plugins call into it.
- **Security:** stores provider credentials encrypted at rest (see §9).
- **Run:** the server's `aigw-runner` plugin spawns it as a child process on **port 9105** (it can also run standalone).

### `apps/desktop/` — the Electron control plane
- **Stack:** Electron 41 + React 19 + Vite (electron-vite), Tailwind CSS v4 + shadcn/ui, Monaco editor, RJSF (JSON-Schema forms), `react-resizable-panels`, `lucide-react`.
- **Idea:** the user-facing app. It **bundles and manages the Python server + aigateway**, including creating the venv, running `uv sync`, starting/stopping the server subprocess, and health checks. Distribution bundles a CPython runtime + `uv` so users don't install Python themselves.
- **Screens:** see §5.
- **Run:** `cd apps/desktop && npm install && npm run dev`. Package with `npm run build && npm run package` (DMG/AppImage/NSIS via electron-builder). Architecture detail: `apps/desktop/ARCHITECTURE.md`.

### `apps/scoreboard/` — the public leaderboard service
- **Stack:** Python 3.12+, FastAPI, Tortoise ORM (SQLite local / Postgres prod).
- **Idea:** ingests and persists benchmark scores, serves leaderboard APIs (e.g. `/v1/leaderboard/{id}`, score submission, health), and **serves the static `web/portal/` site** as the public front door.
- **Deploy:** Docker + Helm chart; runs on the k3s cluster in `infra/`.

---

## 5. The Desktop App Screens

The live navigation (from [`apps/desktop/src/renderer/src/App.tsx`](../apps/desktop/src/renderer/src/App.tsx) and `views/`):

| Screen | View ID | What it does |
|---|---|---|
| **Dashboard** | `dashboard` | Venv bootstrap status, server start/stop/restart, backend (model/provider) health, server logs, Phoenix tracing link. |
| **URL4 Studio** | `url4-studio` | Author and save named url4 expressions/specs. |
| **Sessions** | `sessions` | Proxy sessions for Claude Code / Codex / Gemini CLI; status indicators. |
| **Eval Studio** | `eval-studio` | Create and run benchmark evals (url4 expressions), watch live progress, view scored results, and **publish to the leaderboard**. |
| **Code Studio** | `code-studio` | Monaco-based code/script editing (used by url4 `/python` nodes). |
| **Private Data** | `private-data` | Upload/manage private datasets used in evals. |
| **Settings** | `settings` | Server config + per-plugin enable/disable and settings (JSON-Schema forms, auto-saved). |

Plugins can also contribute their own dynamic screens (`plugin:<id>`).

> ⚠️ **Naming drift.** `CLAUDE.md` lists the four "canonical" screens as *Settings, Spend, Eval Studio, Cache/Log*. The shipping app has evolved past that — Eval Studio and Settings remain, but "Spend" and "Cache/Log" are not current top-level screens. Trust the table above.

> 🚧 **In progress (June 2026):** a token-**cost** feature (research + early build by Sergey) — cost is owned by the AIGateway via per-gateway price lists, summing token usage across the gateway execution tree. This is the modern incarnation of the old "Spend" idea and is a candidate to resurface as a screen / leaderboard axis (accuracy-vs-cost). See the digest.

---

## 6. The Marketing / Leaderboard Site (`web/portal/`)

- **Stack:** plain **HTML/CSS/JS, no build step, no framework.** This is deliberate — minimalism reads as trust to the target audience (the Ollama-landing-page lesson). Served by `apps/scoreboard`.
- **Pages:**
  - `index.html` — landing page + install flow (the install command is treated as the hero element).
  - `benchmark.html` — the leaderboard, including the "climb" chart.
  - `data.html` — viewer for dataset/eval `.jsonl` files.
  - `spec.html` — individual benchmark/spec detail.
- **Charts:** the leaderboard "climb" is **custom CSS/JS bars** — no Recharts/Chart.js/D3 dependency. (Those libraries are referenced as *options* in older docs but aren't actually used in the portal.) For the demo the chart is **1-D (accuracy only)**; a 3-D accuracy/speed/cost view is the long-term goal.
- ⚠️ **Hosting is in flux (June 2026).** The marketing/apex domain was extracted to a separate web repo (Cloudflare), which **broke the portal's static data URLs** (e.g. `screamingface.ai/livetruth-latest.eval.jsonl`) and caused a demo failure; static is being moved under **`scoreboard.screamingface.ai`** (e.g. `…/benchmark.html?id=livetruth`, `?id=hle`). Verify the live host before relying on a URL. (Tracked in [`ISSUES.md`](ISSUES.md) I-19.)
- **Brand system.** Although there's no `brand/` directory on disk (see §3), Bennett shipped a **tokenized brand system** (a private brand repo + `brand.screamingface.ai`, 3 directions + a live demo comparison) intended to be easy for tooling to hook into — this is what `CLAUDE.md`'s design skill points at.

---

## 7. Key Concepts (glossary in brief)

- **url4** — a DAG-based protocol that encodes an AI task chain as a single human-readable string. It can fan a prompt out to multiple backends with weights and then **reduce** the results into one answer. Implemented as a TatSu PEG grammar + interpreter in the `url4-executor` plugin. Example node: `claude:0.40:/claude($item.question)!'Answer this…'` means "send `$item.question` to the `/claude` backend, weight 0.40, with this reduction intent." See real specs in `sf.json` under `url4-specs` (`MainOne`, `ScoredLiveTruth`, etc.). The **full evaluation expressions we actually run** against the LiveTruth benchmark — the three single-model baselines, the ensemble, and the private-data variants — are in **[Appendix A](#appendix-a--evaluation-curl-reference-livetruth)**.
- **LiveTruth / "honest-agi-live"** — the benchmark the system is scored against (`https://screamingface.ai/livetruth-latest.eval.jsonl`; the two names are used somewhat interchangeably in-channel, with benchmark IDs like `honest-agi-live-W24`). Each row carries a `question` and an `answer`; the harness runs the ensemble per row, checks correctness, and computes accuracy. The content + eval metrics live in the **private `github.com/OpenMined/screamingface-benchmarks` repo** (regenerated **weekly**, with a `-latest` pointer; source docs under `output_artifacts/raw_data/<date>/`). A planned **benchmark identity** scheme is filename + benchmark ID + content/signature hash. See Appendix A.
- **Private data** — the **source documents a benchmark was built from**. Injecting them into each model's context is the demo's core argument (big accuracy lift). For the demo these are served as **public** static files (no auth); a general external-connectivity + auth mechanism (HTTP basic/JWT per domain) is **deferred**. See `ISSUES.md` and the digest.
- **Ensemble** — combining multiple models so the blended answer beats any single model. url4 weights (e.g. claude 0.40 / codex 0.30 / gemini 0.30) are how the blend is expressed.
- **Enclave** — a secure, auditable cloud server running model runners and cache.
- **Gates** — the cloud-side token-sharing concept: users create "models" and share rate-limited access with friends.
- **SOTA** — the state-of-the-art benchmark scores the ensemble is trying to beat.

Full reference: [`docs/GLOSSARY.md`](GLOSSARY.md).

---

## 8. How a Request Flows (the architecture story)

```
Coding CLI (Claude Code / Codex / Gemini CLI)
        │  points at a local frontend plugin
        ▼
Frontend plugin   e.g. claude-frontend  (serves /v1/messages on :9101)
        │  resolves the request through a url4 spec
        ▼
url4-executor     fans out per the spec's DAG + weights
        ├──► /claude   ┐
        ├──► /codex    │  backend plugins
        ├──► /gemini   │  (direct provider API  — or — via aigateway)
        ├──► /ollama   │
        └──► /python   ┘  (sandboxed scoring/repro scripts)
        │  results reduced/ensembled per the spec's !intent
        ▼
Eval run scores the result ──► apps/scoreboard ──► web/portal leaderboard
```

Step by step:

1. **Frontend plugins** present provider-shaped endpoints locally. `claude-frontend` serves `/v1/messages` on **:9101**; there are matching Gemini and Ollama frontends (and a configured-but-inactive `codex-frontend` on :9102). A coding CLI is pointed at these instead of the real provider.
2. The request is resolved through a **url4 spec** (e.g. `MainOne`, `ScoredLiveTruth`), which describes the fan-out and the reduction.
3. **Backend plugins** are the dispatch targets — `/claude`, `/codex`, `/gemini`, `/ollama`, `/python`. Each backend either calls the provider API directly or routes through **aigateway**: the `aigw-*` plugins talk to the aigateway subprocess on **:9105**, which uses LiteLLM to reach the actual providers.
4. Results are **reduced/ensembled** per the spec's `!intent`, optionally **scored** (the `/python` runner executes deterministic check/accuracy scripts), and **eval runs publish to the scoreboard**, which drives the public leaderboard.

**The plugin system underneath it all:** the server core exposes three registries — **HookRegistry** (events/signals), **ClassRegistry** (Odoo-style `_inherit` mixins), and **RouteRegistry** (dynamic FastAPI routers). Plugins declare `depends`/`conflicts` and are activated in dependency order; `sf.json`'s `plugins` array is the active list. Engineering detail: [`apps/server/README.md`](../apps/server/README.md).

**Active plugins today** (from [`apps/server/sf.json`](../apps/server/sf.json)): `tracing`, `url4-executor`, `url4-specs`, `claude-frontend`, `data-store`, `private-storage`, `llm-base`, `frontend-base`, `backend-api-base`, `python-runner`, `aigw-codex-backend`, `aigw-gemini-backend`, `ollama-backend-api`, `gemini-frontend`, `ollama-frontend`, `aigw-base`, `aigw-claude-backend`, `aigw-runner`, `state`, `eval-runs`.

> Note: some plugins appear in `sf.json`'s `plugin_config` block but are **not** in the active `plugins` array (e.g. `claude-backend-api`, `codex-frontend`, `mitmproxy-intercept`) — they're configured but not currently loaded.

---

## 9. Data, Credentials & Security

- **Credential storage (aigateway):** provider credentials live in a `credential_blobs` table via **Tortoise ORM** — SQLite locally, Postgres in hosted/prod. Values are **always encrypted at rest** (AES-256-GCM via a `SecretStoreMixin`); the master key comes from the `AIGATEWAY_SECRET_KEY` env var. **No OS keychain / libsecret / Credential Manager** is used in aigateway. (Key file: `apps/aigateway/src/aigateway/core/credential_blob/store.py`.)
  - ⚠️ The root `README.md` still says Anthropic auth flows through the macOS keychain (`Claude Code-credentials`). That reflects an older direct-proxy path; the gateway path uses encrypted ORM storage as above.
- **Architecture mandate (enforced in review):** the system follows Clean / Hexagonal (ports & adapters) rules — **core must not import from plugins/adapters**; plugins import from core. Core defines interfaces; model runners, transports, storage, and UI are adapters outside the core. DRY + SOLID are treated as merge-blocking. See `CLAUDE.md`.

---

## 10. Build, Release & Infra

- **No monorepo build tool.** Coordination is a root **`Makefile`** (`make sync` / `test` / `lint` / `fmt`, targeting the Python apps) plus **`release-please`** for per-package semantic versioning (desktop = Node, server/aigateway/scoreboard = Python).
- **Desktop distribution:** electron-builder produces DMG/AppImage/NSIS, **bundling the Python runtime + `uv` + the server source**, so end users don't install Python.
- **Infra:** single-node **k3s** cluster on Azure (`infra/k3s/`, Ansible bootstrap). CI lives in `.github/workflows/`.
- **Git workflow guardrail:** the `.githooks/pre-commit` hook blocks direct commits to `main` (enable once with `git config core.hooksPath .githooks`).

---

## 11. Deprecated / Don't-Touch

Three legacy **claude-CLI traffic-intercept** plugins are **unmaintained and not part of the live pipeline**:

- `claude_intercept` (`claude-intercept`)
- `claude_env_intercept` (`claude-env-intercept`)
- `mitmproxy_intercept` (`mitmproxy-intercept`)

Rules (from `CLAUDE.md`): don't add features to them, don't treat them as a reference for "how the gateway works," and touch them only to deprecate/delete/keep-compiling. **New gateway behavior belongs in the frontend plugins** (`claude_frontend` / `frontend_base`) that serve `/v1/messages`.

> ⚠️ The root `README.md` still lists `claude-env-intercept` and `claude-intercept` as "built-in plugins" and shows them in example config. Ignore that — they are deprecated and not in the active `sf.json`.

---

## 12. Team & Ways of Working

| Person | Role |
|---|---|
| **Bennett** Farkas | Design lead (brand system + marketing site) |
| **Sergey** Bershadsky | Server, desktop, plugin system, devops/packaging (most prolific contributor) |
| **Kevin** McDonough | App backend, url4 protocol; de-facto demo lead / requirements owner |
| **Dmitry** | Backend, scoreboard/portal, API-key + Antigravity work |
| **Irina** Bejan | Architecture & governance; leads the "next phase" (joined the working channel June 2026) |
| **Ronnie** Falcon | Head of product (network / AI-unification) |
| **Siddhant** Rai | Engineer — OpenRouter / tool-calling / local models (joined June 2026) |
| **Kyle** | Frontend (static site + app UI) |
| **Trask** (Andrew) | Product owner / founder (daily use, testing, requirements, demo handoff) |

> Per the June 2026 channel, several more engineers (e.g. Arena, Sadan, Stephen) were being added for the Q3 push; names/spellings above for newer joiners are approximate.

**Git essentials** (full detail in [`docs/team-development.md`](team-development.md) and `CLAUDE.md`):
- Branch naming: `SF-{n}-{description}` (e.g. `SF-22-fix-auth-bug`).
- **Never commit directly to `main`** (enforced by the pre-commit hook).
- Each commit ties to an **Asana ticket**; include the permalink in the commit body. New tickets go in the default Asana project with the next sequential `SF-N` number.
- Non-trivial work is planned with the "superpowers" skills; plans/specs land in `docs/superpowers/`.

---

## 13. Where to Go Next

- [`README.md`](../README.md) — top-level pitch + quick start *(note: partly stale on layout; see §3)*.
- `CLAUDE.md` — developer rules, architecture principles, git/Asana workflow, persona system.
- [`docs/GLOSSARY.md`](GLOSSARY.md) — the full term-by-term reference.
- `docs/architecture/` — system, app↔server, and auth-flow diagrams.
- [`personas/weighting-guide.md`](../personas/weighting-guide.md) — **start here for any copy/design/positioning work.**
- [`apps/server/README.md`](../apps/server/README.md) — the plugin system in depth.
- `apps/desktop/ARCHITECTURE.md` — desktop bootstrap + packaging.
- [`scream-lisbon-digest.md`](scream-lisbon-digest.md) — **what the team actually did/decided in May–June 2026** (demo, results, post-demo roadmap).
- [`ISSUES.md`](ISSUES.md) — the living list of open problems (now incl. channel-sourced I-18 → I-32).

---

## Appendix A — Evaluation cURL reference (LiveTruth)

> **Source:** the **"URL4 MANUAL E2E"** canvas in Slack `#scream-lisbon`, and — confirmed — **Kevin's 2026-06-09 post of the same eight cURLs in `#scream-lisbon`** (see the channel digest, [Evaluation methodology](scream-lisbon-digest.md#evaluation-methodology)). These are the canonical, hand-run evaluation queries — the concrete proof behind the "beat SOTA" claim.
> ⚠️ **Several of these expressions contain copy/paste anomalies** (wrong weight labels in single-model variants, a typo, a port/endpoint mismatch, drift from the stored `sf.json` specs, and a **mangled `checks:` source that points at both `livetruth-latest.eval.jsonl` and an `HLE.jsonl`**). They are reproduced **faithfully as posted**; the problems are tracked in [`docs/ISSUES.md`](ISSUES.md) (I-13 → I-17, I-27). The bugs are **in the source**, not transcription artifacts — don't treat these as bug-free.

**How the harness works.** Each eval is a single url4 expression POSTed to the scoring endpoint:

```
localhost:8080/score?q=<url4-expression>
```

- **`checks:` source** — `https://screamingface.ai/livetruth-latest.eval.jsonl`, expanded per-row with `*`. Each row binds `correct_answer=$item.answer` and the model sees `$item.question`.
- **`consensus`** — one or more model calls (`/claude`, `/codex`, `/gemini`) each weighted, each asked to return a probability distribution as JSON.
- **`normalized:(…)!*'Validate…'`** — a broadcast (`!*`) validation/normalization step that forces the distribution to be non-negative and sum to 1.0.
- **reduce `!'Compute a weighted average…'`** — blends the per-model distributions by source weight and picks the top answer letter.
- **`!/data/check_correct.py`** — compares the consensus answer to `correct_answer`.
- **`;foreach.concurrency=10;foreach.on_error=collect`** — run rows 10-at-a-time; collect (don't abort on) per-row errors.
- **`!/data/calculate_accuracy.py`** — aggregates the per-row checks into `Accuracy: X% ± Y% | n = N`.

**The evaluation matrix.** Same skeleton, varying the model set and whether private data is injected into the model context:

| Variant | Models in consensus | Private data injected? |
|---|---|---|
| Claude baseline | claude only | no |
| Codex baseline | codex only | no |
| Gemini baseline | gemini only | no |
| **Ensemble** (the one in active use) | claude 0.40 / codex 0.30 / gemini 0.30 | no |
| Claude + Private Data | claude only | yes |
| Codex + Private Data | codex only | yes |
| Gemini + Private Data | gemini only | yes |
| Ensemble + Private Data | claude / codex / gemini | yes |

"Private Data" injects `https://screamingface.ai/honest-agi-live-latest.data.html` into each model's context alongside the question. *(Note: this means private/eval data is sent into the model prompt — see privacy issue I-4.)*

### Ensemble — the canonical query we've been working with

```
localhost:8080/score?q=(
 checks:https://screamingface.ai/livetruth-latest.eval.jsonl*(
 correct_answer=$item.answer,
 consensus=(
 normalized:(
 claude:0.40:/claude($item.question)!'Answer this question. If it is multiple choice, return a probability distribution over the answer choices as JSON. Format: {"A": 0.7, "B": 0.2, "C": 0.05,"D": 0.05}. Return only the JSON object.',
 codex:0.30:/codex($item.question)!'Answer this question. If it is multiple choice, return a probability distribution over the answer choices as JSON. Format: {"A": 0.7, "B": 0.2, "C": 0.05,"D": 0.05}. Return only the JSON object.',
 gemini:0.30:/gemini($item.question)!'Answer this question. If it is multiple choice, return a probability distribution over the answer choices as JSON. Format: {"A": 0.7, "B": 0.2, "C": 0.05,"D": 0.05}. Return only the JSON object.'
 )!*'Validate this probability distribution. Ensure all values are non-negative and sum to 1.0. If they do not, normalize proportionally. Return only valid JSON.'
 )!'Compute a weighted average of the distributions in $normalized using source weights claude=0.40, codex=0.30, gemini=0.30. Return the single answer letter with the highest combined probability.'
 )!/data/check_correct.py
 ;foreach.concurrency=10;foreach.on_error=collect
 )!/data/calculate_accuracy.py
```

### Single-model baselines

Each baseline is the ensemble skeleton with **one** model at weight 0.40 in the consensus.

```
# Claude baseline
localhost:8080/score?q=(
 checks:https://screamingface.ai/livetruth-latest.eval.jsonl*(
 correct_answer=$item.answer,
 consensus=(
 normalized:(
 claude:0.40:/claude($item.question)!'Answer this question. If it is multiple choice, return a probability distribution over the answer choices as JSON. Format: {"A": 0.7, "B": 0.2, "C": 0.05,"D": 0.05}. Return only the JSON object.'
 )!*'Validate this probability distribution. Ensure all values are non-negative and sum to 1.0. If they do not, normalize proportionally. Return only valid JSON.'
 )!'Compute a weighted average of the distributions in $normalized using source weights claude=1.0. Return the single answer letter with the highest combined probability.'
 )!/data/check_correct.py
 ;foreach.concurrency=10;foreach.on_error=collect
 )!/data/calculate_accuracy.py
```

```
# Codex baseline  (⚠️ reduce intent still says "claude=1.0" — see ISSUES I-13)
localhost:8080/score?q=(
 checks:https://screamingface.ai/livetruth-latest.eval.jsonl*(
 correct_answer=$item.answer,
 consensus=(
 normalized:(
 codex:0.40:/codex($item.question)!'Answer this question. If it is multiple choice, return a probability distribution over the answer choices as JSON. Format: {"A": 0.7, "B": 0.2, "C": 0.05,"D": 0.05}. Return only the JSON object.'
 )!*'Validate this probability distribution. Ensure all values are non-negative and sum to 1.0. If they do not, normalize proportionally. Return only valid JSON.'
 )!'Compute a weighted average of the distributions in $normalized using source weights claude=1.0. Return the single answer letter with the highest combined probability.'
 )!/data/check_correct.py
 ;foreach.concurrency=10;foreach.on_error=collect
 )!/data/calculate_accuracy.py
```

```
# Gemini baseline  (⚠️ reduce intent still says "claude=1.0" — see ISSUES I-13)
localhost:8080/score?q=(
 checks:https://screamingface.ai/livetruth-latest.eval.jsonl*(
 correct_answer=$item.answer,
 consensus=(
 normalized:(
 gemini:0.40:/gemini($item.question)!'Answer this question. If it is multiple choice, return a probability distribution over the answer choices as JSON. Format: {"A": 0.7, "B": 0.2, "C": 0.05,"D": 0.05}. Return only the JSON object.'
 )!*'Validate this probability distribution. Ensure all values are non-negative and sum to 1.0. If they do not, normalize proportionally. Return only valid JSON.'
 )!'Compute a weighted average of the distributions in $normalized using source weights claude=1.0. Return the single answer letter with the highest combined probability.'
 )!/data/check_correct.py
 ;foreach.concurrency=10;foreach.on_error=collect
 )!/data/calculate_accuracy.py
```

### Private-data variants

Identical to the above, but each model call also receives `https://screamingface.ai/honest-agi-live-latest.data.html` as context, e.g. `/claude(https://screamingface.ai/honest-agi-live-latest.data.html, $item.question)`. The single-model private-data variants (Claude/Codex/Gemini + Private Data) keep the **three-way** weight label `claude=0.40, codex=0.30, gemini=0.30` in their reduce intent despite having only one model in the consensus — see ISSUES I-14. The Ensemble + Private Data variant is the ensemble query above with the data URL prepended to each of the three model calls.

---

*This overview was compiled from the project-knowledge skill, a direct read of the repository on 2026-06-24, the "URL4 MANUAL E2E" canvas, and a direct read of the `#scream-lisbon` channel (May–June 2026, captured in [`scream-lisbon-digest.md`](scream-lisbon-digest.md)). Verified-architecture sections were checked against the live files; status/roadmap (§0) comes from Slack discussion and AI huddle notes and may be imprecise. Code moves — if something here looks wrong, verify against the cited path and update this file.*
