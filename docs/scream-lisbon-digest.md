# `#scream-lisbon` — Channel Digest (last ~month)

> **What this is.** A curated digest of the private Slack channel **`#scream-lisbon`** (`C0AL5ER1DLG`) — the working channel for the ScreamingFace demo team. It captures decisions, progress, results, open problems, and post-demo direction so the project docs don't have to depend on a single pasted canvas anymore.
>
> **Source & scope.** Compiled **2026-06-24** from a direct read of the channel covering **~2026-05-25 → 2026-06-24**: all top-level messages plus the substantive discussion threads and the daily AI **huddle-notes** docs (6/8–6/23). Channel permalink: `https://openmined.slack.com/archives/C0AL5ER1DLG`.
>
> **Trust notes.** Huddle notes are **AI-generated meeting summaries** and are explicitly flagged "some information may be inaccurate" — claims sourced from them are attributed inline (e.g. "(6/19 huddle)") and should be treated as leads, not gospel. Some new-teammate names are transcription-approximate. Problems surfaced here are tracked in [`ISSUES.md`](ISSUES.md); the verified architecture lives in [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md).
>
> **This is a factual record, not our narrative.** Competitive phrasing quoted below (e.g. "OpenRouter moving in on the opportunity") is *what was said in-channel*, captured as history — not how we frame the mission. The team-facing narrative and goals (collective intelligence, public AI, democratizing access, the public network for private information) live in the **[V1 launch plan](screamingface-v1-launch-plan.md)** and **[positioning](positioning.md)**.

---

## TL;DR

- The team's **North Star for June** was a **working benchmark-eval demo for Max Katz to run locally** — originally "before June 19th," handed off via Andrew. The demo's whole argument: **including the private source data that a benchmark was built from measurably improves model accuracy.**
- The demo **happened** (week of June 19) and by **6/23 main was stable** with the scoreboard wiring tested. **300+ PRs** have shipped into SF (6/22).
- **Headline result (6/19 huddle):** with private data **57.6%** vs. without **27%** — ~30 points. Dropping Gemini from the 3-model ensemble costs ~10 points. (Earlier ad-hoc runs showed 36.4→48.5 and 45→100 on smaller/specific sets — see [Results](#results--accuracy-signal).)
- Two **provider auth shocks** hit mid-demo: **Claude deprecated local auth ("P-FLAG") ~June 15** and **Google deprecated the Gemini CLI + client ID** → forcing **API-key** mode and a migration to **Antigravity** as the Gemini front-end.
- **Post-demo pivot is large:** ScreamingFace becomes central to the **Q3 mission**; the team is adding engineers and leaning toward a **CLI terminal-overlay** product (Tmux-style) with **3 install presets (cheap / fast / accurate)**, a **Node.js backend rewrite to drop the Python dependency**, and new **HuggingFace + OpenRouter** backends.

---

## Who's in the channel

| Handle | Name | Role (per channel) |
|---|---|---|
| `U0AHQUV2FLG` | **Kevin McDonough** | App backend + url4; de-facto demo lead / requirements owner |
| `U0AKGUU3F51` | **Sergey Bershadsky** | Server, desktop, devops/packaging; most prolific contributor |
| `U0B2A9MS2SZ` | **Dmitry** | Backend, scoreboard/portal, API-key + Antigravity work |
| `U6AUHSDA5` | **Bennett Farkas** | Design lead; brand system + marketing site |
| `U6AN4BFML` | **Andrew Trask** | Product/founder; presents demo to Max, sets vision |
| `U0191FVFKRP` | **Irina Bejan** | Joined 6/5; architecture/governance, "next phase" lead |
| `U012TUX76TB` | **Ronnie Falcon** | Head of product; network/AI-unification |
| `U0334RMEBFY` | **Siddhant Rai** | Joined 6/19; engineer (OpenRouter/tool-calling, local models) |

**Inbound (named in huddles, spellings approximate):** Enizio, Arena, Sadan/Sadat (benchmark automation + private-data hosting), Stephen (benchmark automation). Per the 6/23 huddle, Andrew committed **2–5 engineers** to the Q3 push.

---

## The June demo (for Max Katz)

**Goal (Kevin, 6/8):** *"deliver a working demo before June 19th."* For a ~1000-question benchmark, **local runtimes < 24h are acceptable** (Andrew explicitly OK with long runtimes; speed is not the point — accuracy is). The demo is **local-only**: leaderboard → copy a context URL → configure endpoints → run eval in Eval Studio → publish results (6/18 huddle).

### The 11-step benchmark E2E user story (Kevin, 6/8) — verbatim-faithful

1. User visits `screamingface.ai/honest-agi-live`.
2. Sees an **Accuracy vs. Cost** chart of baseline eval metrics (frontier models vs. the latest benchmark, **no private data**) plus any user-published runs.
3. Sees an interesting published **URL4 cURL ensemble using private data** that out-performs the baseline; clicks for a detail panel.
4. Clicks **"try this ensemble"** — the cURL is copied to the clipboard for the SF Eval Studio.
5. The **ScreamingFace Electron app** opens to **Eval Studio** with the cURL loaded.
6. Clicks **"Run Benchmark Eval"** to run locally (<24h for 1000–1100 questions via OAuth).
7. Eval metrics from the local run (on the user's own subscription) appear in Eval Studio.
8. User **tweaks the ensemble** (add/remove models, add Python scripts for online learning model selection) and re-runs.
9. Gets **SOTA results** beating the pulled-down ensemble.
10. Clicks **"Share on ScreamingFace.ai"** to publish ensemble + results.
11. The chart shows a **new point** (Accuracy vs. Cost) from the user's run.

*Notes Kevin attached:* re-run prior weeks' best cURLs on each new weekly benchmark; allow comparing weeks; a selected ensemble may reference models the user hasn't installed (step 5).

### How the demo actually got scoped down

- **Accuracy only (1-D leaderboard) for the demo**; 3-D (accuracy/speed/cost) is the long-term goal (Trask: *"short term, 1d is fine. long term 3d is required"*). Cost is a **stretch goal** — would require collecting token usage across the gateway execution tree, and adding a cheaper OpenRouter/local model to actually show savings.
- **CLI interaction is *not* the demo focus** — Max likely has Claude Code installed; the demo centers on the **portal + Eval Studio + private-data** story. If CLI isn't shown, the CLI front-ends don't even need installing (6/18 huddle).
- Demo data made **public** to dodge auth work (see [private data](#private-data-the-core-argument)).

---

## Progress timeline (late-May → late-June)

- **5/29:** Ensemble-over-JSONL testing hits **429 rate limits**; backpressure ticket **SF-232** filed. Flagged risk: 20+ min url4 runs may exceed front-end CLI timeouts → need async/worker model (post-demo backlog).
- **6/2–6/5:** Architecture diagrams + project **Glossary** posted (Irina/Sergey); Irina **joins the channel 6/5**. Claude front-end reworked to **return the ensemble result into the CLI directly (no proxying)**. Alignment: a url4 spec **needs `$prompt`** for CLI→/ensemble use or it returns a static (cached) result.
- **6/8:** The **11-step E2E user story** and the *"demo before June 19th"* goal posted. Claude **local-auth deprecation (June 15)** surfaces → plan to move to **API keys**.
- **6/9:** Kevin posts the **8 evaluation cURLs** (baselines + ensemble + private-data variants) — see [Evaluation methodology](#evaluation-methodology). Private-data approach defined: **inject the data URL as the first arg to each model call**. Caching layer in the gateway proposed to avoid re-querying identical questions.
- **6/10:** Bennett ships a **tokenized brand system** at `brand.screamingface.ai` (3 directions + a live demo comparison). Sergey embeds **Monaco editor with a url4 plugin** (autocomplete/highlighting), adds Studio settings + publishing. 32 questions ran in ~20 min.
- **6/11:** Parallel workstream kicked off — the **Slack→Claude productivity bridge** (dog-food before July 4). See [Post-demo directions](#post-demo--strategic-directions).
- **6/12:** **Eval Studio → Scoreboard/portal publish** working. Sergey builds a **temporary fake-private-data plugin** ("to be destroyed after the demo") and demonstrates accuracy lift from injected context.
- **6/15:** **~2K tests** guarding against drift. Claude local-auth deprecation day.
- **6/16:** Core **cache** merged to main. Token-**cost** feature research begins (pricing owned by the gateway). Post-demo priorities named: **Draco benchmark** + **tool-calling**.
- **6/17:** url4 **comma-separated context+question** syntax nailed down for the demo; bug found: a spec with **no grading step** doesn't compare to ground truth.
- **6/18:** Bennett extracts the apex domain to a **separate web repo (Cloudflare)** → **portal breaks**, `screamingface.ai/livetruth-latest.eval.jsonl`-style URLs 404 → **caused a demo failure**. Static is being **moved under the scoreboard subdomain**. Sergey makes **variable interpolation stricter** (introducing the comma-split behavior change).
- **6/19:** **Demo / pre-flight huddle** with Max-demo planning. Gemini-CLI-deprecation blocker handled via API key + Antigravity. Benchmark-metadata design (filename + ID + signature hash). **Siddhant Rai joins.**
- **6/20:** Sergey floats **"reframe ScreamingFace"** (CLI overlay idea) with visuals; shares a Rust overlay PoC.
- **6/22:** **300+ PRs** shipped; desktop fixes in main.
- **6/23:** **Main is stable; scoreboard wiring tested manually and works.** Post-demo huddle sets the Q3 roadmap (overlay, refactor, new backends). New static home: **`scoreboard.screamingface.ai`**.
- **6/24:** Sergey shares a **Golang/Bubbletea** overlay PoC (live-updating, resizable alongside Claude).

---

## Evaluation methodology

The canonical eval is a single url4 expression POSTed to `localhost:8080/score?q=<expr>`, expanded per-row over the benchmark JSONL, scored by Python. Kevin's 6/9 list is the **source of truth** for the eight variants:

| Variant | Models in consensus | Private data injected? |
|---|---|---|
| Claude / Codex / Gemini baselines | one model each | no |
| **Ensemble** (the working one) | claude 0.40 / codex 0.30 / gemini 0.30 | no |
| Claude / Codex / Gemini + Private Data | one model each | yes |
| **Ensemble + Private Data** | all three | yes |

The full cURLs are reproduced in **[`PROJECT-OVERVIEW.md` Appendix A](PROJECT-OVERVIEW.md#appendix-a--evaluation-curl-reference-livetruth)**. Things to know from the channel source:

- **The `checks:` source line is link-mangled** in Slack and reads `checks:<…/livetruth-latest.eval.jsonl><…github.com/openmined/HLE.jsonl*(|*(>` — i.e. it references **both** the LiveTruth eval JSONL and an `HLE.jsonl`. The clean intent is `checks:<benchmark>.eval.jsonl*(…)`. Tracked as a drift/format issue.
- **Copy-paste weight bugs are real and originate here:** the Codex and Gemini *baselines* still reduce with `source weights claude=1.0`, and the single-model *private-data* variants keep the 3-way `claude=0.40, codex=0.30, gemini=0.30` label. (Tracked as `ISSUES` I-13 / I-14.)
- **Two private-data plumbing styles** were floated: a single data URL prepended to each model call (`/claude(<data-url>, $item.question)`), or a **per-row `$item.source`** pointer (Kevin's alternative). The fill-in-the-blank demo runs used a simpler `!'…single most likely short answer…'` intent and `/python(/data/code/check_correct.py)` rather than the JSON-distribution form.
- **JSON reliability:** ~3–4% of eval rows come back as non-JSON; LiteLLM normalizes "text+json" down to json. Trask's call: bad answers should be **rejected, not corrected** (acceptable for demo).
- **Structured output idea (Sergey, 6/9):** define a **dynamic function-tool / JSON schema** (`f('…') -> /data/schema`) so model output is guaranteed JSON instead of prompt-coerced. Deferred post-demo.

### Private data — the core argument

- The benchmark's **private source documents** are the "private data." Including them in each frontier model's context is what produces the accuracy lift the demo is built to show (Kevin, 6/8–6/9).
- For the demo, **the private data was made public** (served as static files) so **no auth was needed**. The general case needs a real **external-connectivity + auth plugin** (HTTP basic / JWT per-domain, later FTP/SSH) — **explicitly deferred** (Kevin: *"Not yet the auth piece for data sources"*).
- Source documents live in the **private benchmarks repo** (below); examples are weekly `output_artifacts/raw_data/<date>/*.txt` Atlantic-style articles. Sergey's `/private/<uuid>` resource maps to one of these files.

---

## Results / accuracy signal

These are **different runs on different sets** over time — read as a progression, not one canonical number:

| Date | Source | Without context | With private data/context | Notes |
|---|---|---|---|---|
| 6/12 | Sergey (ad-hoc) | 36.4% | 48.5% | Emulated context; 6 questions intentionally given direct answers to prove the path works |
| 6/16 | Dmitry | 45% | 100% | Small/specific set |
| 6/19 | Demo huddle | 27% | **57.6%** | ~30-pt lift; the headline demo number |

Also: **dropping Gemini** from the 3-model ensemble costs **~10 points** with or without private data (6/19). **Nondeterminism observed:** same models + same context produced different results across runs (6/18) — worth understanding before trusting single-run numbers.

---

## Open problems & risks (raised in-channel)

Cross-referenced to [`ISSUES.md`](ISSUES.md):

- **url4 comma-splitting regression** — after stricter interpolation (6/18), commas inside `(...)` split the contents into separately-parsed chunks (including `/`- and `http`-prefixed ones) instead of treating the whole as one prompt. Changes how context+question must be passed.
- **Portal static URLs broken** — apex-domain extraction to the web repo / Cloudflare broke `screamingface.ai/*.jsonl` links and **caused the demo failure** (6/18); static moving under `scoreboard.screamingface.ai`.
- **Backpressure / 429** — ensemble evals fan out enough to hit provider rate limits (SF-232).
- **Long-run timeouts** — 20+ min url4 runs risk front-end CLI timeouts; needs async worker + queue (sync/async modes) or SSE; possibly proxy swarm + token pools later.
- **`tool_calls` unsupported via LiteLLM** — different models return different tool-call formats; a judge model could pick the best; needs research. Post-demo.
- **No grading step** — a spec without a check/ground-truth step silently doesn't grade (6/17).
- **Scoreboard guardrails** — benchmarks hardcoded in YAML; provider list computed from eval runs and should **not** be user-editable; risk of posting to the wrong leaderboard; thin user-story docs (6/23).
- **Comparison semantics** — runs are grouped by **benchmark ID**, not by url4; different private-data sets on the same benchmark are intentionally comparable (resolved understanding, 6/12).
- **`$prompt` requirement / caching collision** — a CLI cURL without `$prompt` returns a static cached result.
- **Provider-auth fragility** — Claude local-auth + Gemini CLI deprecations show third-party contracts are weaker than internal APIs and need monitoring.
- **Brand-site password shared in plaintext** in-channel (`letmein`) — hygiene.

---

## Post-demo / strategic directions

- **CLI terminal overlay (the likely next product).** A Tmux-style overlay that runs Claude (or any CLI) underneath with a ScreamingFace UI on top for **switching model/ensemble live**. Endorsed as **simpler than the desktop app** and closer to the developer workflow (6/23). PoCs: **Rust** (6/23) then **Golang + Bubbletea** (6/24), both well-received by Trask.
- **3 install presets.** Next release: install → pick **cheap / fast / accurate** coding preset (each maps to an ensemble) → launch a session and code. ~**2–4 week** target for a first basic CLI tool.
- **Backend rewrite + simpler install.** Drop the **Python server dependency**, rewrite backends in **Node.js** (Go floated longer-term), keep **Electron over Tauri** (stronger community, consistent Chrome runtime). Install must require **no Python/Conda** to avoid support burden.
- **New backends (priority order):** finalize demo → finish **Antigravity** (Gemini replacement) → **HuggingFace** backend (their API, no local download) → **OpenRouter** backend → **tool-calling**.
- **Cost/pricing in the gateway.** Token-cost owned by the AIGateway (hardcoded price lists initially: free=0, keyed=price list); cost = token usage summed across the gateway execution tree; **Envoy** floated as a higher-load gateway base vs. OpenRouter.
- **url4 as a standalone library/SDK** (python/js/go) instead of per-project reimplementations — "falls out of the next phase with Irina."
- **Draco benchmark** (`perplexity-ai/draco`, ~100 rows) to reproduce **OpenRouter Fusion** results, post-demo.
- **Local models:** LM Studio + **Qwen3-Coder-30B** (128k ctx) via OpenAI-shaped endpoints; interest in integrating LM Studio.
- **Slack→Claude productivity bridge (parallel bet).** Trigger on @mentions/DMs → a **dynamic router** runs a chosen url4 spec against a personal "second brain" (Syft resource) + **guardrailing rules** and replies with an ensemble result. Uses **personal tokens (not an org bot)** for viral, person-to-person adoption; dog-food before **July 4**. Governance debate: **semantic** (who/relationship/request-type, social-graph-based — Trask) vs. **hard MCP/folder restrictions** as a trust primitive (Irina), plus a likely **deterministic governance-policy layer**; url4 as a **semantic firewall language**. OpenMined principle reaffirmed: **raw source data never leaves the user's machine; synthesize first, then triage by role.**
- **Sift / PySift integration (3 points):** AIGateway as the unified LLM layer; a reverse proxy to **monetize SF endpoints via Sift Hub**; **private-data access from Sift Hub inside url4** (transparent pre-flight auth for users with Sift access).
- **Market signal:** Trask flags **OpenRouter moving in on the opportunity** (6/14) and shares early user signal on X; `0xNyk/council-of-high-intelligence` noted as a related project (6/20).

---

## Key links & artifacts

- **Private benchmarks repo:** `github.com/OpenMined/screamingface-benchmarks` — weekly benchmark content, a `-latest` pointer, eval metrics vs. frontier models (no private data), and source docs under `output_artifacts/raw_data/<date>/`.
- **Brand system:** `brand.screamingface.ai` (pw shared in-channel) — tokenized design system, 3 directions, live demo comparison.
- **Scoreboard / portal:** new home `scoreboard.screamingface.ai` (e.g. `…/benchmark.html?id=livetruth`, `?id=hle`); old `screamingface.ai/portal/`. Data files: `livetruth-latest.eval.jsonl`, `honest-agi-live-latest.data.html`, `livetruth-masking.dataset.jsonl`.
- **Benchmark identity (design):** filename + **benchmark ID** (e.g. `honest-agi-live-W24`) + **signature/content hash**; ID added per-question in the eval JSONL.
- **Repo docs:** architecture diagrams (`docs/architecture/`, by Irina: overview, app↔server, auth-flow) and the project **Glossary** (the canvas this team posted on 6/5, mirrored as `docs/GLOSSARY.md`).
- **Asana:** backpressure **SF-232**; the API-token ticket (`…/task/1215507593465846`).
- **Overlay PoCs:** `sf-overlay-poc.zip` / `sf-cli.mov` (Rust), `sf-poc-go.zip` / `sf-cli-go.mov` (Go).

---

*Compiled 2026-06-24 from `#scream-lisbon`. Huddle-note–sourced claims are AI-summarized and may be imprecise — verify against the channel or the cited repo path before acting. When this digest and the code disagree, trust the code and update this file.*
