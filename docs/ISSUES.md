# ISSUES — open problems to solve for

> A living list of open problems with ScreamingFace — small or big — that we need to solve for. Add freely; keep each item actionable (what's wrong, evidence, who could own it). Move resolved items to the bottom or delete.
>
> **Status of sources:** items marked **[repo]** are verified against the codebase on 2026-06-24. Items marked **[canvas]** come from the **"URL4 MANUAL E2E"** canvas in `#scream-lisbon`. Items marked **[channel]** come from a direct read of `#scream-lisbon` (~2026-05-25 → 2026-06-24), now captured in **[`scream-lisbon-digest.md`](scream-lisbon-digest.md)**; channel-sourced claims drawn from AI huddle-notes are summaries and may be imprecise — verify before acting. The Slack access blocker (formerly I-0) is **resolved** (see Resolved).

| ID | Severity | Area | Issue | Owner |
|----|----------|------|-------|-------|
| I-1 | High | Bug | Port collision: `gemini-frontend` & `ollama-frontend` both default to 9103 | — |
| I-2 | High | Product | No roadmap / phasing lives in the repo | — |
| I-3 | High | Product | Business model (credit sharing / Gates / pricing) undefined | — |
| I-4 | High | Privacy | "What leaves the machine" is undocumented | — |
| I-5 | Med | Docs | `CLAUDE.md` & `README.md` describe a layout that no longer exists | — |
| I-6 | Med | Product | No benchmark numbers / SOTA target captured | — |
| I-7 | Med | Product | Per-app maturity/status is unclear | — |
| I-8 | Med | Config | `sf.json` carries configured-but-inactive plugins | — |
| I-9 | Med | Tech debt | Deprecated intercept plugins still in the tree | — |
| I-10 | Low | Quality | Desktop has no wired-up test script | — |
| I-11 | Low | Config | Inconsistent default model IDs across backends | — |
| I-12 | Low | Docs | `CLAUDE.md` hardcodes a machine-specific plan path | — |
| I-13 | High | Eval | Single-model baselines reduce with wrong weight label (`claude=1.0` for codex/gemini) | — |
| I-14 | Med | Eval | Private-data single-model variants keep the 3-way weight label | — |
| I-15 | Low | Eval | Typo `answeletter` in Claude baseline reduce intent | — |
| I-16 | Med | Eval | Scoring endpoint is `:8080/score` but server runs on `:8000` | — |
| I-17 | Med | Eval | Canvas E2E expressions have drifted from the stored `sf.json` specs | — |
| I-18 | High | Bug | url4 comma-split regression: commas inside `(...)` now parse chunks separately | Sergey |
| I-19 | High | Web | Portal static URLs broke after apex-domain extraction → demo failure | Bennett/Dmitry |
| I-20 | High | Infra | Ensemble evals hit provider 429s; needs backpressure (SF-232) | Sergey |
| I-21 | High | Arch | 20+ min url4 runs risk CLI/front-end timeouts; needs async worker/queue | — |
| I-22 | Med | Eval | `tool_calls` not supported through the LiteLLM interface | — |
| I-23 | Med | Eval | A url4 spec with no grading step silently doesn't compare to ground truth | — |
| I-24 | Med | Product | Scoreboard guardrails: wrong-leaderboard posting, editable provider list, thin user story | — |
| I-25 | Med | Bug | url4 without `$prompt` returns a static (cached) result in CLI → /ensemble | — |
| I-26 | Med | Risk | Provider-auth fragility (Claude P-FLAG, Gemini CLI deprecations) | — |
| I-27 | Low | Eval | `checks:` source line references both `livetruth…eval.jsonl` and `HLE.jsonl` (mangled) | — |
| I-28 | Low | UX | Eval Studio: editing+saving overrides the run URL | Sergey |
| I-29 | Low | Strategy | url4 reimplemented per-project; not a shared library/SDK | — |
| I-30 | Low | Docs | url4 literal-escaping spec undefined (`'a \n b'` vs `'a b'`) | — |
| I-31 | Low | Security | Brand-site password shared in plaintext in `#scream-lisbon` | — |
| I-32 | Med | Eval | Nondeterminism: same models + same context yield different accuracy across runs | — |

---

## Open issues

### I-1 — Port collision between Gemini and Ollama frontends **[repo]**
**Area:** Bug · **Severity:** High
Both `gemini-frontend` and `ollama-frontend` are in the active plugins list, and both listen on **9103** by default — `apps/server/src/screamingface/plugins/gemini_frontend/plugin.py:26` (`listen_port: int = 9103`) and `apps/server/sf.json` (`ollama-frontend.listen_port = 9103`). With both active, one will fail to bind.
**Action:** move one frontend to a distinct default port (and add a startup check that fails loudly on a port clash).

### I-2 — No roadmap / phasing in the repo **[repo]**
**Area:** Product · **Severity:** High
The product plan exists only in `docs/😱 Development Plan.docx`; the plain-text `docs/devplan.txt` that `CLAUDE.md` promises **does not exist**. There is no in-repo roadmap that says what's next or in what order.
**Action:** export/author a living `docs/ROADMAP.md` (current phase, near-term, later). Needs PO (Trask) input.

### I-3 — Business model is undefined in docs **[repo]**
**Area:** Product · **Severity:** High
"Share AI credits with friends" and "Gates" are one-liners. There's no description of how sharing, rate-limiting, quotas, or pricing/monetization actually work.
**Action:** write it down (even a one-pager). Decide owner — likely PO + cloud/Gates owner.

### I-4 — Privacy posture ("what leaves your machine") is undocumented **[repo]**
**Area:** Privacy · **Severity:** High
Built by OpenMined for a privacy-skeptical audience, yet nothing states what data is local-only vs. sent to providers vs. visible to the enclave. Credential encryption is covered; the data-flow/privacy story is not. Concrete instance: the "private data" eval variants inject `honest-agi-live-latest.data.html` directly into each model's prompt (Appendix A of `PROJECT-OVERVIEW.md`) — i.e. private/eval data is sent to third-party providers — and that trade-off is undocumented.
**Action:** add a privacy/data-flow section (and ideally a diagram) covering prompts, datasets, cache, and enclave; state explicitly what the private-data path sends where.

### I-5 — Core docs describe a layout that no longer exists **[repo]**
**Area:** Docs · **Severity:** Med
- `CLAUDE.md` and the dev plan reference top-level `web/`, `app/`, `cloud/`, `brand/`; reality is `apps/{server,desktop,aigateway,scoreboard}` + `web/portal/`. `brand/` does not exist on disk (though it's cited by `CLAUDE.md` and the design skill).
- `README.md` references `apps/web/` (Next.js) and a `packages/` folder that **don't exist**, lists deprecated intercept plugins as "built-in," and says Anthropic auth flows through the macOS keychain — which conflicts with the aigateway encrypted-ORM design.
**Action:** reconcile `CLAUDE.md` + `README.md` with reality (see `docs/PROJECT-OVERVIEW.md` for the verified picture).

### I-6 — No benchmark numbers / SOTA target captured **[repo]**
**Area:** Product · **Severity:** Med
The whole thesis is "beat SOTA," but no doc states the current LiveTruth scores or the target. The *methodology* is now captured (Appendix A of `PROJECT-OVERVIEW.md`, from the URL4 MANUAL E2E canvas) and partial data exists in `docs/results/livetruth-eval-comparison.md`, but the **current numbers vs. SOTA aren't summarized anywhere durable**.
**Action:** surface current vs. SOTA in the overview/roadmap; define the canonical source of truth for scores.

### I-7 — Per-app maturity/status is unclear **[repo]**
**Area:** Product · **Severity:** Med
No "shipped vs. WIP vs. planned" map. Signals suggest early stage (e.g. scoreboard README: "now provides the runnable service shell"; desktop has no test suite).
**Action:** add a status table per app to the overview.

### I-8 — `sf.json` carries configured-but-inactive plugins **[repo]**
**Area:** Config · **Severity:** Med
`apps/server/sf.json` has `plugin_config` blocks for plugins **not** in the active `plugins` array — `claude-backend-api`, `codex-frontend`, `mitmproxy-intercept`. This is confusing (is `/claude` served by `aigw-claude-backend` or `claude-backend-api`?) and risks accidental activation.
**Action:** prune or clearly comment dormant config; document the intended active set.

### I-9 — Deprecated intercept plugins still in the tree **[repo]**
**Area:** Tech debt · **Severity:** Med
`claude_intercept`, `claude_env_intercept`, `mitmproxy_intercept` remain under `apps/server/src/screamingface/plugins/` and are referenced in `README.md`/`sf.json`, despite being officially unmaintained and out of the pipeline.
**Action:** decide delete vs. keep; if keeping, isolate them and stop referencing them as current.

### I-10 — Desktop has no wired-up test script **[repo]**
**Area:** Quality · **Severity:** Low
`apps/desktop/package.json` depends on `vitest` but exposes only a `lint` script — no `test` script, and README confirms "no test suite yet."
**Action:** add a `test` script and a minimal suite for the lifecycle/IPC hooks.

### I-11 — Inconsistent default model IDs across backends **[repo]**
**Area:** Config · **Severity:** Low
`claude-backend-api` defaults to `claude-sonnet-4-6` while `aigw-claude-backend` defaults to `anthropic/claude-sonnet-4-5` (`apps/server/sf.json`). Two `/claude` paths with different default models is a footgun.
**Action:** align defaults (or document why they differ).

### I-12 — `CLAUDE.md` hardcodes a machine-specific path **[repo]**
**Area:** Docs · **Severity:** Low
Planning section points plans/specs at `/Users/sergey/work/openmind/screamingface/docs/superpowers/...` — an absolute path on one machine (and "openmind" misspelled; repo lives elsewhere for other devs).
**Action:** make it a repo-relative path (`docs/superpowers/...`).

### I-13 — Single-model baselines reduce with the wrong weight label **[canvas/channel]**
**Area:** Eval · **Severity:** High
In the URL4 MANUAL E2E canvas, the **Codex** and **Gemini** baseline queries end with `…source weights claude=1.0…` even though their consensus contains only codex / only gemini. The reduce intent names the wrong model. At best it's misleading; at worst it skews the LLM-driven reduction. The Claude baseline correctly says `claude=1.0`.
**Confirmed source:** this is **not a transcription artifact** — Kevin posted the same eight cURLs in `#scream-lisbon` on 2026-06-09, and the Codex/Gemini baselines there literally read `claude=1.0` (see [digest → Evaluation methodology](scream-lisbon-digest.md#evaluation-methodology)).
**Action:** fix each baseline's reduce intent to name its own model (`codex=1.0`, `gemini=1.0`), and prefer a weight-agnostic phrasing for single-model runs.

### I-14 — Private-data single-model variants keep the 3-way weight label **[canvas/channel]**
**Area:** Eval · **Severity:** Med
The "Claude + Private Data", "Codex + Private Data", and "Gemini + Private Data" queries each have a single model in the consensus but still reduce with `source weights claude=0.40, codex=0.30, gemini=0.30`. Same class of copy-paste error as I-13, and likewise present verbatim in Kevin's 2026-06-09 channel post.
**Action:** correct the reduce intent for each single-model private-data variant.

### I-15 — Typo `answeletter` in the Claude baseline **[canvas]**
**Area:** Eval · **Severity:** Low
The Claude baseline reduce intent reads "Return the single **answeletter** with the highest combined probability" (missing space / "answer letter").
**Action:** fix the typo wherever this intent string is templated.

### I-16 — Scoring endpoint port doesn't match the server **[canvas/repo]**
**Area:** Eval · **Severity:** Med
The canvas runs evals against `localhost:8080/score?q=…`, but `apps/server/sf.json` configures the server on **8000** (frontends are 9101/9103, aigateway 9105). It's unclear what serves `/score` on 8080 — a manual/dev setup, a different default, or stale. New contributors can't reproduce an eval from the canvas as-is.
**Action:** document the canonical scoring entry point (host, port, which app/plugin serves `/score`) and reconcile the port.

### I-17 — Canvas E2E expressions have drifted from the stored specs **[canvas/repo]**
**Area:** Eval · **Severity:** Med
The canvas queries use a richer pattern than the `url4-specs` saved in `sf.json`:
- Canvas adds a `normalized:(…)!*'Validate…'` broadcast step; `sf.json`'s `MainOne` has no normalization.
- Scoring scripts are invoked differently: canvas uses bare `!/data/check_correct.py` / `!/data/calculate_accuracy.py`, while `sf.json`'s `ScoredLiveTruth` uses `/python(/data/code/check_correct.py)` / `/python(/data/code/calculate_accuracy.py)` — different paths (`/data/` vs `/data/code/`) **and** different call form.
There is no single source of truth for "the expression we score with."
**Action:** decide whether the canvas or `sf.json` specs are canonical, sync them, and reference the winner from `PROJECT-OVERVIEW.md` Appendix A.

### I-18 — url4 comma-splitting regression inside `(...)` **[channel]**
**Area:** Bug · **Severity:** High
Per Sergey (2026-06-18), after variable interpolation was made stricter, url4 changed how it treats commas inside `(...)`: previously everything inside the parens was treated as one prompt and passed as-is; now a comma **splits the bytes** and each chunk is parsed separately — **including chunks that start with `/` or `http`**. This silently changes the meaning of every `(context, $item.question)` call and is the kind of regression that can flip eval results between runs.
**Action:** define and test the intended comma semantics inside `(...)` (literal prompt vs. argument list); add grammar tests; reconcile with how the demo cURLs pass `(<data-url>, $item.question)`.

### I-19 — Portal static URLs broke after the apex-domain extraction → demo failure **[channel/repo]**
**Area:** Web · **Severity:** High
When the marketing site / apex domain was extracted to a separate web repo and deployed via Cloudflare (Bennett, ~6/17–6/18), the portal's static data URLs (e.g. `https://screamingface.ai/livetruth-latest.eval.jsonl`) started returning broken/404, and **this caused a failure during the demo** (Sergey, 6/18). The fix — **serving static under the scoreboard subdomain** — is now in the repo: `web/portal/main.js` hard-codes `scoreboard.screamingface.ai`, and the scoreboard Helm charts + `apps/scoreboard/DEPLOYMENT.md` make it the public host (`…/livetruth-latest.jsonl`, `…/livetruth-masking.dataset.jsonl`). ⚠️ Note the filenames differ across docs (`livetruth-latest.jsonl` in the scoreboard deploy vs. `livetruth-latest.eval.jsonl` in the eval cURLs) — worth confirming which the harness actually fetches.
**Action:** confirm the canonical static host *and* the exact data filenames the eval expressions use; add a smoke check that those URLs resolve before a demo.

### I-20 — Ensemble evals hit provider 429s; backpressure needed **[channel]**
**Area:** Infra · **Severity:** High
Running the ensemble over a JSONL fans out enough concurrent provider calls to hit **429 rate limits** even at ~32 rows (Sergey, 5/29). Asana **SF-232** tracks reactive backpressure in the aigateway. A caching layer (merged ~6/16) reduces repeat calls but doesn't solve burst limits.
**Action:** land SF-232 backpressure; longer term, smarter rate-limit handling, token pools, and/or proxy rotation (see I-21).

### I-21 — Long url4 runs risk front-end/CLI timeouts; needs async execution **[channel]**
**Area:** Architecture · **Severity:** High
Full-benchmark url4 runs can take **20+ minutes**, which risks exceeding the timeout of the CLI tool / front-end that issued the request (Sergey, 5/29; the team owns neither CLI's timeout). Proposed: a queue/worker model offering **sync and async `/ensemble`** (async returns a `task_id` immediately and the front-end polls). Kevin floated **SSE** as an alternative the CLIs may already expect.
**Action:** decide sync/async vs. SSE; research real per-front-end timeouts; design a keep-alive/worker path before scaling to 1000-question benchmarks.

### I-22 — `tool_calls` unsupported through the LiteLLM interface **[channel]**
**Area:** Eval · **Severity:** Med (post-demo)
LiteLLM (the aigateway's base interface) doesn't support `tool_calls` in the shape SF needs, and different models return different tool-call formats (Sergey/Kevin, 6/17 & 6/23). A judge model could pick the best tool call from multiple responses, but the mechanism needs research; LiteLLM also wasn't designed as a CLI-interface layer.
**Action:** research provider tool-calling contracts (OpenAI vs Anthropic vs OpenRouter); decide whether to extend LiteLLM, add a shim, or change protocol. Explicitly post-demo.

### I-23 — A spec with no grading step silently doesn't grade **[channel]**
**Area:** Eval · **Severity:** Med
Sergey found (6/17) that a url4 spec lacking a check/grade step runs but never compares answers to ground truth — producing "results" that aren't actually scored.
**Action:** validate that scored specs include a `check_correct`/grading node; warn (or fail) when a benchmark spec has no grading step.

### I-24 — Scoreboard publishing guardrails are thin **[channel]**
**Area:** Product · **Severity:** Med
Per the 6/23 huddle: benchmarks are hardcoded in YAML and provider lists are computed from eval runs, but **users could post benchmarks to the wrong leaderboard**, the provider list shouldn't be user-editable, and there's **no detailed user-story documentation** for publishing. Private-data authorization on publish (Sift scope) also needs pre-flight checks + auth prompts.
**Action:** write the publish user story; lock down provider lists; add leaderboard-target validation and a private-data authorization pre-flight.

### I-25 — url4 without `$prompt` returns a static (cached) result **[channel]**
**Area:** Bug · **Severity:** Med
For CLI → `/ensemble` use, a url4 spec that has no `$prompt` variable always returns the same (cached on the second call) result (Sergey/Kevin aligned, 6/5). Combined with the new gateway cache, a `$prompt`-less spec looks "stuck."
**Action:** require/validate `$prompt` for CLI-targeted specs (or document the constraint and surface a clear warning in URL4 Studio).

### I-26 — Provider-auth fragility (Claude P-FLAG, Gemini CLI deprecations) **[channel]**
**Area:** Risk · **Severity:** Med
Mid-demo, **Claude deprecated local auth ("P-FLAG") effective ~June 15** and **Google deprecated the Gemini CLI + client ID**, forcing a scramble to **API-key** mode and a migration to **Antigravity** as the Gemini front-end (6/8, 6/19 huddles). Third-party CLI contracts are weaker than internal APIs and can change without notice.
**Action:** treat provider-auth as a monitored dependency; keep an API-key fallback per provider; track the Antigravity migration to completion.

### I-27 — `checks:` source line references two datasets (mangled) **[channel]**
**Area:** Eval · **Severity:** Low
In Kevin's 6/9 cURLs the source line reads `checks:<https://screamingface.ai/livetruth-latest.eval.jsonl><https://github.com/openmined/HLE.jsonl*(|*(>` — i.e. it points at **both** the LiveTruth eval JSONL **and** an `HLE.jsonl`, with Slack link-mangling. The clean intent is a single `checks:<benchmark>.eval.jsonl*(…)`. Related to the canvas-vs-`sf.json` drift in I-17.
**Action:** establish the one canonical `checks:` source per benchmark and de-mangle the reference in any stored spec/doc.

### I-28 — Eval Studio: editing+saving overrides the run URL **[channel]**
**Area:** UX · **Severity:** Low
"Run locally" always creates a new run, but editing and **saving overrides the URL**, which is confusing (6/18 huddle). Proposed fix: remove the save button so edit-and-rerun creates a new run with a new URL.
**Action:** rework the Studio edit/save/rerun flow as proposed.

### I-29 — url4 is reimplemented per project, not a shared library **[channel]**
**Area:** Strategy · **Severity:** Low
url4 is used across teams but implemented separately per project. Sergey proposed (6/9) extracting a **url4 grammar + interpreter SDK** (python/js/go) so it can be embedded quickly anywhere; Kevin agreed it likely "falls out of the next phase of our work with Irina."
**Action:** scope a standalone url4 parser/SDK; decide languages and ownership in the post-demo phase.

### I-30 — url4 literal-escaping spec undefined **[channel]**
**Area:** Docs · **Severity:** Low
Sergey asked (6/10) whether there's a spec for wrapping literals — is there a difference between `'string data'` and `'string \n data'`? Grammar review was promised but no spec is recorded.
**Action:** document literal/escaping rules in the url4 grammar.

### I-31 — Brand-site password shared in plaintext **[channel]**
**Area:** Security · **Severity:** Low
The `brand.screamingface.ai` password was posted in plaintext in `#scream-lisbon` multiple times. Low-stakes (a brand preview), but poor hygiene if the pattern repeats for anything sensitive.
**Action:** move shared-secret distribution out of channel; rotate if the site ever hosts non-public material.

### I-32 — Eval nondeterminism: same context, different accuracy **[channel]**
**Area:** Eval · **Severity:** Med
Sergey observed (6/18) that the **same models with the same context produced different results** across runs. Expected for sampling LLMs, but it undermines single-run leaderboard numbers and week-over-week comparisons.
**Action:** decide on temperature/seed controls and/or multi-run averaging for published benchmark numbers; document the expected variance band (the methodology already reports `± Y%`).

---

## Resolved

### I-0 — Slack `#scream-lisbon` was not readable by tooling *(resolved 2026-06-24)*
**Area:** Process
The Slack integration originally returned nothing for `#scream-lisbon`. Root cause: the connector was authenticated as `irina@openmined.org`, who **isn't a member** of the channel. Reconnecting the Slack MCP under **`irinam.bejan@gmail.com`** (also in the OpenMined workspace, and a member) exposed it (`C0AL5ER1DLG`). The last ~month of the channel is now captured in **[`scream-lisbon-digest.md`](scream-lisbon-digest.md)**, and the discussion has been triaged into issues **I-18 → I-32** above. Note: Slack **share links** (`join.slack.com/share/...`) can't be resolved via the API — channel access depends on the connected account's membership.
