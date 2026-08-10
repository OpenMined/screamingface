# ScreamingFace — Positioning

> **Internal reference.** The canonical product-narrative / messaging doc: how we frame the ensemble value prop versus OpenRouter and HuggingFace, the four pillars the team converged on, and — as of the August 2026 launch — what we can actually *say* because it ships. When a claim touches product state, this doc defers to what's real.
>
> **Audiences (named target personas — marketing's *Newsletter Strategy Deck*, July 2026; relisted in §"Target personas"):** **Rahul — the concerned AI developer (A1, P0)** is primary; the local / no-middleman / run-it-yourself framing is his. **Helen — the political mover (A2, P1)** is secondary; the "decentralized AI, SOTA as an open invitation, subsidized compute" framing is hers. Complements the [`narrative-funnel-chapter-guide.md`](narrative-funnel-chapter-guide.md) (the *when/sequence*), the [`screamingface-v1-launch-plan.md`](screamingface-v1-launch-plan.md) (owners + the launch gates), and [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md) / [`ISSUES.md`](ISSUES.md) (verified shipped state).
>
> **Tone rule (A1):** no marketing adjectives ("powerful," "seamless," "cutting-edge"). Lead with specifics and evidence. **"You can run this yourself"** is the gold-standard proof — and, as of V1, it's literally true: `pip install screamingface`.
>
> **Aligned to delivery:** 2026-07-31 (OME-717). Companion of record for "what's shipped": `PROJECT-OVERVIEW.md`.

---

## One-line positioning

**ScreamingFace is the engine that runs model ensembles locally — the place to find, prove, and share state-of-the-art model ensembles, with no middleman taking a cut of every call.**

The execution artifact is **url4** (a human-readable context/DAG expression); the engine that runs it is **ScreamingFace** — now shipping as the **`screamingface` Python package** wrapping the **`url4` engine**; the public surface that ranks and *verifies* results is the **leaderboard**.

**Where the capability actually comes from (don't overclaim ensembling).** Ensembling alone yields a *modest* intelligence bump — treating that as the headline is an assumption this audience will call. The strong, demonstrated gain comes from **private data + high model diversity** together: feed in knowledge the base models lack, across an ensemble whose members are genuinely different (not three near-identical frontier models). "Private data" is broad — a **specialized/fine-tuned model**, a **private corpus via RAG**, or any source the models can't already see. The honest claim is: *ensembling is the mechanism; private data and diversity are where the real gains live* — which is why the private-data wave (§"Two waves") is the payoff, not a footnote.

---

## Target personas

Two named personas from marketing's **Newsletter Strategy Deck (July 2026)** anchor V1 messaging — a primary developer and a secondary policy mover. Design every asset for one of them; the `A1`/`A2` shorthand used elsewhere in this doc maps to these.

### Rahul — the concerned AI developer *(Primary · A1)*

- 31, London; builds backend systems for a fast-scaling SaaS. Hacker News before email; the person tagged in **r/LocalLLaMA** for a second opinion on whether a benchmark number is real "or just a good README." Runs local models against GPT-5-class systems on a **token budget that never quite stretches**.
- Believes he shouldn't have to hand his data to someone else's cloud to get real use from a model. The one coworkers quietly pull aside before pasting something sensitive into a chatbot; actually reads the privacy policy.
- Quietly scared the good guys are falling behind — that compute and funding are consolidating to three or four companies. Conviction that decentralization is right **stopped being enough; he needs proof it's viable.**
- **Earns his trust:** a number he can run himself · a person actually fighting this (not posting about it) · a sign that open/local is *gaining ground*, not holding a principled losing position.
- **Wants from us:** to believe the fight is live and he's *in* it; when he's the only one asking where his data goes, give him numbers/tools/frameworks he can check himself; show who else is really in this fight (real people and projects, not talking points) — receipts, and let him check the work.

### Helen — the political mover *(Secondary · A2)*

- 56, career civil servant; three decades in public-infrastructure policy. Little social following, but authority, influence, and a network that picks up the phone. Cut her teeth digitizing public libraries / health records / civic archives; watched agencies that moved too slowly get permanently outpaced.
- Believes the public sector has **~two years** before large AI companies close off (or absorb) the paths that let open systems compete. Wants public alternatives that actually work, **funded as a public good** — not a favor from private industry.
- **Has:** institutional power to move public investment + the historical memory of how narrow the window is. **Lacks:** visible, credible proof and co-signers.
- **Wants from us:** the case in plain language (no CS degree); proof it's running, working, and real before she puts her name on it (something to hand a skeptical committee, journalist, or colleague); people to build with (co-authors, institutions, a coalition); urgency framed honestly — *solvable if we move now,* not a panic.

**Throughline (both), from the deck's positioning:** *"where the proof and the case meet"* — reproducible, verifiable evidence explained plainly enough that a policy advisor doesn't need a CS degree to trust it, and rigorously enough that a benchmark obsessive doesn't roll their eyes.

**Tone (from the deck):** precise not promotional · honest and grounded · authoritative without arrogance · urgent not alarmist · principled not preachy · confident not defensive. (Consistent with the A1 tone rule: no marketing adjectives, lead with the number.)

**Expanding / under discussion** *(`Target Audience Identification`, not yet final — do not treat as locked):* Researchers & AI Labs (added Jul 6); **price/quality/speed-sensitive AI users** — developers building AI into their product, and the people who decide how a firm buys tokens for its employees; a Wave-2 **private-data champion** (working name "lab / internal-institutional champion"); and the raw reach target — *"people talking about OpenRouter's model fusion / the ~6M who saw it."* Open questions the team still owns: is the token-buyer covered by "researchers"? what do we call the private-data champion? is "developers & benchmark enthusiasts" too narrow / not quite right?

---

## What ships today vs. what lands at launch (honesty first)

Lead every external claim from the left column. The launch runs on three gates — **public SOTA claim → Python client (Aug 7) → macOS app, open to everyone (Aug 14)** — so several pillars are *arriving*, not *arrived*. Say which.

| ✅ Shipped & working now | 🚀 Landing across the August launch | 🔒 Wave 2 (next) |
|---|---|---|
| `pip install screamingface` — Python SDK/client: BYOK → compose `Model`/`Fusion` recipes → run a benchmark → read the url4 → read the gain | **Public SOTA claim + verified board** — reproduce a benchmark in **Colab at $0** on OpenMined-subsidized compute (gate 1) | **Private data via SyftSpace** — the durable, mission-aligned version of the lift |
| The **`url4` engine** (`packages/url4`) — compiles a recipe to a url4 expression, runs the ensemble, grades | **Python client external release** (gate 2, Aug 7) — notebooks + SDK public, auth-before-submit | Real private-data partnerships (data-contributor pipeline) |
| **DRACO** benchmark reproduction — rubric-graded (Gemini judge), the "ensembles vs frontier" check | **macOS 1-click app** (gate 3, Aug 14) — managed engine, "open to everyone" | Multi-turn + tool-using ensembles (research; owner-tracked) |
| **Local AI gateway** (`apps/aigateway`, LiteLLM) — your own subscriptions/keys, encrypted, no OS keychain | **Fusion Monsters** program — SOTA-hunters get the subsidized engine (pilot → public) | Windows / Linux (post-launch: Win ~Aug 14, Linux ~Aug 21) |
| **Verified scoreboard** (`apps/scoreboard`) — ranks are **re-run-verified, never self-claimed** | More benchmarks in SF — Healthbench, IFEval, MedX, GDPval, ContractEval, … | A defined paid business model (credit-sharing / Gates / Sift Hub — see I-3) |
| Notebooks — `00_quickstart`, `09_reproduce_a_result` | | |

**Explicitly not shipped — do not imply otherwise:** multi-turn/agentic tool-using ensembles (single-shot eval is our credible surface — R2); a *validated* win over OpenRouter Fusion (the public SOTA claim is **gated on validation**, PENDING); a paid/monetization model (I-3).

---

## The proof (lead with this for A1)

For A1 the hero is a number plus an install command, and the killer move is **reproducibility**:

- **The lift is real and measured.** In the private-data demo: **~57.6% with private data vs ~27% without** (~30-point lift); dropping one model from the 3-model ensemble costs **~10 points**. (Different runs on different sets — a progression, not one canonical number; and eval is nondeterministic — I-32.)
- **We check ourselves in public before we claim.** **DRACO** (`perplexity-ai/draco`) is our reproduction of OpenRouter's "Fusion beats frontier" claim on a public research benchmark, rubric-graded. We run it **early and honestly** — it could come back showing a competitor is simply ahead (R1). The public SOTA claim ships only after validation lands.
- **You can run it yourself, for $0.** `pip install screamingface`, compose an ensemble, reproduce DRACO in a **fresh Colab at $0** on OpenMined-subsidized compute. Leaderboard ranks are **re-run-verified**, so a number on the board means someone re-ran it — not that someone claimed it.

This is the whole argument: *an ensemble, a reproducible url4 recipe, and a leaderboard that verifies.*

---

## From positioning to plan (the two waves)

Delivered in two launch waves — full owner split, gates, and timeline in **[`screamingface-v1-launch-plan.md`](screamingface-v1-launch-plan.md)**:

- **Wave 1 (the August launch)** carries **pillar 2** ("the hub for ensembles") and **pillar 3** ("SOTA as an open invitation + subsidized compute") on the **local / no-middleman** foundation of pillar 1 — i.e. create/run/evaluate ensembles on a **verified** leaderboard, with subsidized compute and the `screamingface` SDK + macOS app.
- **Wave 2 (next)** carries the **private-data-for-SOTA** story (SyftSpace) — the deepest expression of pillar 3 and the bridge to OpenMined's mission.
- **The transition** mirrors the funnel: prove SOTA on public data → bridge with fake/public "private" data (already demonstrated) → real private data via SyftSpace. Keep pillar 1's "no middleman" scoped to the **local path** as the subsidized-compute / Sift-Hub economics land.

---

## The four pillars

### 1. Like OpenRouter's ensembles — but local, and no middleman

OpenRouter routes prompts to multi-model / ensemble answers through a hosted broker. Our difference is *where the work happens and who gets paid*:

- **It runs locally**, against the user's own model subscriptions / keys (via the local AI gateway) — not through a hosted broker.
- **We're not cutting a check as the middleman.** There's no per-call margin skimmed off the local ensemble path.

**Why it lands (A1):** this audience values pay-once over rent-forever, distrusts black boxes that phone home, and loves out-smarting a bigger player with a clever local system (the "Robin Hood" archetype). "Runs on your machine, on your own subscriptions" is exactly their proof posture.

**Keep it honest.** The *no-cut* claim is specifically about **local ensemble execution**. The broader business model is still being defined ([`ISSUES.md`](ISSUES.md) I-3) and *does* include money flows — a planned reverse proxy to monetize SF endpoints via Sift Hub, credit-sharing/Gates, and **subsidized compute** (pillar 3). Say **"no middleman on the local path,"** not "free forever." Also be precise on privacy: the private-data eval path *sends data into model prompts* (I-4) — scope any "your data stays local" language to what's actually local.

**On OpenRouter specifically:** ensemble tools in this space are **co-marketing, not enemies** — their existence validates that ensembles matter. Engage, don't attack. OpenRouter's own "Fusion beats frontier" framing is, usefully, our argument (and our DRACO reproduction target).

### 2. The hub for ensembles — *"HuggingFace, but for ensembles"*

HuggingFace is the hub for **models**; ScreamingFace is the hub for **ensembles** — shareable, runnable, leaderboard-ranked **url4 recipes**.

**Why it lands:** an instantly-legible analogy to a thing both audiences respect, and it sets the ambition (a community platform, not just a CLI). It's already the team's stated end-state: per the narrative funnel, *"it never becomes about ScreamingFace — it's always about the people uploading ensembles to help each other."*

**Now real, not aspirational.** The unit you share and discover is the **url4 recipe** (the way the HF unit is the model/dataset), and the machinery to make it first-class now exists: the `screamingface` SDK composes and runs recipes, the engine emits the exact url4, and the leaderboard ranks **verified** submissions. The **Fusion Monsters** program is the community engine on top — SOTA-hunters who reproduce, remix, and submit verified wins.

### 3. SOTA as an open invitation — with subsidized compute

> *"We reached SOTA in this domain. We invite others to reach SOTA in other domains — and we'll subsidize the compute."*

This reframes the leaderboard from a scoreboard we own into **an open challenge we host and verify**. We proved the method in one domain (the private-data news benchmark); now we hand others the tools to do it in theirs and lower the cost barrier with subsidized compute.

**How others actually reach SOTA (set the expectation honestly):** not by stacking more near-identical frontier models, but by bringing **private data the base models can't see** + **a diverse ensemble** — where "private data" can be a specialized/fine-tuned model, a private corpus via RAG, or any proprietary source. The invitation is really *"bring your domain's private data and your diverse stack; we'll host the proof and subsidize the compute."* This is also why a domain expert can top a board a generic ensemble can't.

**What it implies we ship — the tools to find/prove SOTA (now real):**
- **A verified leaderboard** — the public surface where SOTA is found, proven, contested, and **re-run-verified** (ranks are earned, not claimed). Accuracy today; accuracy-vs-cost is the direction.
- **An SDK** — `pip install screamingface`, so reaching/measuring SOTA isn't locked to our app; others embed the ensemble engine in their own domain and stack. (This is the extracted url4 library — [`ISSUES.md`](ISSUES.md) I-29, now **resolved/shipped** as `packages/url4` + the SDK, no longer "a direction.")
- **Subsidized compute** — reproduce a benchmark in Colab at $0 on OpenMined-funded compute; the **Fusion Monsters** program routes the subsidized engine to the people hunting SOTA.

**Why it lands:** for A1, an open invitation + reproducible methodology + "you can top the leaderboard" is catnip (the Kaggle/Aider instinct). For A2, "no single entity should own SOTA; we're funding others to reach it" is the decentralized-AI, public-good story — democratize access to intelligence, not win a market — and **subsidized compute** is a concrete commitment, not an ethics platitude.

### 4. ScreamingFace is the engine that runs the context (url4)

url4 is the human-readable expression of *how a prompt fans out across models, with what context and weights, and how the results reduce to one answer*. **ScreamingFace is the execution engine for url4** — parse, resolve, dispatch, ensemble, grade.

**Why it matters:** it cleanly separates the **artifact** (url4 — portable, shareable, the thing on the leaderboard) from the **engine** (ScreamingFace — what you install to run it). That separation is what makes pillars 2 and 3 possible: you can share a url4 the way you share a model, and run it anywhere the engine exists — locally, in a notebook, or in the managed app.

**Now real:** the engine is shipped code (`packages/url4`), wrapped by the `screamingface` SDK; a benchmark run compiles to a single url4 expression the tool shows you and you can copy.

---

## Versus the neighbors (at a glance)

| | **OpenRouter** | **HuggingFace** | **ScreamingFace** |
|---|---|---|---|
| Unit | API routing to models | Models & datasets | **Ensembles (url4 recipes)** |
| Where it runs | Hosted broker | Hosted / download | **Locally, on your own subscriptions** (+ subsidized compute) |
| Who's paid per call | OpenRouter (margin) | — | **No middleman on the local path** |
| Public surface | Pricing / routing | Model hub | **Verified SOTA leaderboard + SDK** |
| How you get it | API key | `pip install` / download | **`pip install screamingface`** (+ macOS app at launch) |
| The pitch | "We route for you" | "The hub for models" | **"Find, prove & share SOTA ensembles — locally, verified"** |

*(Framing, not a teardown. OpenRouter and HF are reference points the audience already trusts; we define ourselves in their vocabulary, not against them.)*

---

## Messaging do / don't

**Do**
- Lead with the **number** (the SOTA/benchmark score vs. the field) and the **install command** (`pip install screamingface`) — those are the hero, not a tagline (A1).
- Say **"you can run this yourself"** and mean it — link the reproducible methodology and the $0-Colab path.
- Emphasize **verified, not claimed** — the leaderboard re-runs submissions; that's a trust asset this audience will respect.
- Use the **HuggingFace-for-ensembles** analogy; it does a lot of work in one line.
- For A2, frame SOTA-invitation + subsidized compute as a **public-good / anti-concentration** move, anchored to attribution-based-control.ai.

**Don't**
- Don't claim "free / no middleman" flat-out — scope it to the **local ensemble path** (the business model isn't feeless — I-3).
- Don't attack OpenRouter — they validate the category (engage, don't compete); DRACO is a reproduction, not a diss.
- Don't claim we've **beaten** Fusion until validation lands — the public SOTA claim is gated (PENDING); "reproducing / measuring against" is the honest verb until then (R1).
- Don't over-promise the **coding-agent loop** — multi-turn + tool-using ensembles aren't shipped; scope launch claims to eval / single-turn ensembles (R2).
- Don't imply **private data stays on your machine** on the current path — the eval path sends data into prompts (I-4); the "never leaves" story is Wave 2 (SyftSpace).
- Don't drown A2 in benchmark/token mechanics without the societal frame, and don't hit A1 with mission-speak without the receipts.

---

## Honest constraints & risks (name them; they change what we claim)

- **R1 — OpenRouter is already here (Fusion / DRACO).** A well-funded incumbent owns the plain "ensembles beat single models" story, hosted and zero-setup. Our differentiation is **private data + diversity**, **local / no-middleman**, and **open/community + subsidized compute + verification**. DRACO reproduction runs early so we know where we stand before we claim.
- **R2 — Multi-turn + tools asymmetry.** Ensembling is cleanest for single-shot Q&A (our benchmark demo). Real coding-CLI work is multi-turn and tool-using — models emit different tool-call formats, and reconciling them across an ensemble is unsolved. Scope V1 claims to **eval + single-turn**; multi-turn-with-tools is in progress, not shipped.
- **R3 — Experiment-to-SOTA time.** Full runs are long and search-heavy; a newcomer's first experience can be a costly grind. Mitigations: **subsidized compute** + **seed the board with ready-made SOTA ensembles** so the quick win is *remix-and-rerun*, not search-from-scratch. Set expectations openly: *remixing is the fast win; topping a board from zero is a marathon.*
- **Privacy posture (I-4).** State plainly what the private-data path sends where; don't over-claim locality.
- **Nondeterminism (I-32).** Same models + same context can yield different accuracy across runs; published numbers carry a variance band (`± Y%`) — don't sell single-run precision.
- **Business model undefined (I-3).** Keep "no middleman" scoped to the local path until the credit-sharing / Gates / Sift-Hub model is written down.

---

## Open questions to resolve

- **What exactly is subsidized, for whom, and funded how?** (Ties to the Gates / credit-sharing / Sift-Hub model — I-3; and to the Fusion Monsters compute budget.)
- **Where "no middleman" stops being true** — document the local path vs. the hosted/Sift-Hub paths so the claim stays precise as the business model lands.
- **A2 front door** — this positioning is A1-first (Rahul); the A2 version (Helen) needs the editorial, non-technical treatment her persona calls for (separate gated site).
- **The multi-turn / coding-agent story** — when (if) it ships, how do we position it without undercutting the eval-first credibility?
- **Announcement shape** — split (SOTA claim + product) vs combined; how hard to lean on the "release a fusion model like a frontier model" playbook (the marketing playbook's open question).

---

## Sources

Captured from team discussion (June 2026) and aligned to delivery on 2026-07-31 against the Asana launch boards (`scream-dev` / `scream-sota` / `scream-marketing` / `scream-fusion-monsters`), the shipped code (`packages/screamingface`, `packages/url4`, `apps/aigateway`, `apps/scoreboard`), and [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md) / [`ISSUES.md`](ISSUES.md) / [`screamingface-v1-launch-plan.md`](screamingface-v1-launch-plan.md) / [`scream-lisbon-digest.md`](scream-lisbon-digest.md). Target personas (Rahul, Helen) relisted from marketing's **Newsletter Strategy Deck (July 2026)** and the `Target Audience Identification` Asana task; message sequence per the narrative funnel. Messaging here is *positioning*, not verified product state — when a claim touches what's shipped, check `PROJECT-OVERVIEW.md` / `ISSUES.md`.
