# ScreamingFace V1 — Launch Plan & Team Brief

> **For:** the OpenMined team. **Purpose:** introduce the opportunity, what we're building for V1, how the work splits across the team, the timeline, and what's expected. This is the **single source of truth for who owns what**; other docs link here.
>
> **Companion docs:** the *why/positioning* lives in [`positioning.md`](positioning.md); the *what-exists-today* picture is [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md); the *recent history* is [`scream-lisbon-digest.md`](scream-lisbon-digest.md).
>
> *Names below are normalized from the planning notes; a "(?)" means the spelling/assignment needs confirming. Personal emails are intentionally omitted — ping the owner directly.*

---

## 1. Why this matters

**The goal isn't to win — it's to prove that collective intelligence is a viable path to more capable AI, and to make access to it public.** If we top a leaderboard and stop there, we've missed the point. Success is *other people* reaching SOTA in their own domains, on a network we opened for them.

We start from one fact we've already proven: **an ensemble of models beats any single model** (OpenMined in research; the demo, running locally). What we build on it:

- **Push collective intelligence.** An open home for ensembles — shareable, runnable, leaderboard-ranked url4 recipes — makes "stronger together" the default. Like HuggingFace for models, it works by being about the community, not the company.
- **Keep it public and democratized.** No single company should own the most capable intelligence. We reach SOTA in one domain, then hand everyone the tools (a leaderboard + an SDK) and **subsidized compute** so anyone — researchers without a big budget especially — can reach SOTA in theirs.
- **Build the public network for private information (Wave 2).** The frontier on hard problems is gated behind **private data** models can't see. ScreamingFace is the on-ramp to a network where private knowledge can lift everyone's intelligence *without being surrendered or centralized* — OpenMined's core mission.
- **Counter the concentration of power.** Intelligence shouldn't pool in a handful of labs. The point is to **demonstrate a credible, open, decentralized path to more intelligence — and invite the world onto it.**

Others moving toward ensembles (e.g. OpenRouter) is **validation, not a threat** — it confirms the path is real. Our difference: ours runs **locally, on your own subscriptions, with no middleman on the local path** — open and shared, not metered.

---

## 2. What we're building (V1): two waves

ScreamingFace is the **engine that runs url4** (the human-readable expression of how a prompt fans out across models and reduces to one answer). V1 lands in two narrative waves with a deliberate bridge between them.

> **Where the capability actually comes from.** Ensembling on its own gives *some* lift — but treating that modest gain as the main prize is an **assumption**. The large, reliably-demonstrated jump in capability shows up when two things are true together: **(1) you plug in private data** the models don't already have, and **(2) there's high diversity across the ensemble** — genuinely different knowledge/perspectives, not three near-identical frontier models. (Our own demo shows both: ~27% → ~57.6% once private data is added, and dropping a model from the ensemble costs ~10 points.) **"Private data" is broad** — a specialized/fine-tuned model, a proprietary corpus reached via RAG, or any source the base models can't see. This is exactly why **Wave 1 (ensembles) is the on-ramp and Wave 2 (private data + diversity) is where the real capability story lands.**

### Wave 1 — Ensembles + a shared leaderboard *(eval-first)* — **ships July 1**
Let people **create ensembles, run ensembles, and evaluate ensembles on a shared leaderboard**, backed by:
- **Cached sessions** — don't re-pay to re-ask the same question.
- **Subsidized compute** — an OpenMined-funded provider so researchers can run without burning their own budget.

This is the experiment-and-prove layer. The whole point is: *find SOTA, see it on the board, share the recipe.*

### Wave 2 — SOTA via private data *(SyftSpace)* — **TBD**
The story turns to **private data and private-data access through SyftSpace**: hard eval questions that frontier models miss because they lack the source material, and how feeding in private data closes the gap. This is where ScreamingFace connects to OpenMined's mission.

### The transition (how Wave 1 becomes Wave 2)
**Evaluation first → private data for SOTA.** Concretely:
1. Wave 1: ensembles on public data establish the leaderboard and the baseline.
2. **Bridge:** prove the lift with **fake/public "private" data** (already demonstrated in the demo).
3. Wave 2: the same lift with **real private data via SyftSpace** — the durable, mission-aligned version.

---

## 3. The pillars & how the work splits

Five pillars carry V1. Each component is tagged **W1/W2** and **[P0/P1/P2]** (P0 = needed for the July 1 ship; P1 = fast-follow / Wave-2 enabler; P2 = later).

### Development
| Component | Owner(s) | Wave | P |
|---|---|---|---|
| API gateway *(exists)* | **Sergey** | W1 | P0 |
| Extract & standardize the **url4 engine** | **Ionesio Junior** | W1 | P0 |
| Enhance **caching** (→ "cached sessions") | **Sergey + Dmitry** | W1 | P0 |
| Build the **Python SDK** | **Tauquir Ahmed** | W1 | P0 |
| Build / refactor the **app frontend** | **Tauquir Ahmed** | W1 | P0 |
| Improve the **leaderboard page** | **Dmitry → Filip / Khoa** (handoff) | W1 | P0 |
| **OM-subsidized researcher provider backend** (compute + tokens) | **Dmitry** | W1 | P0 |
| **Cost & speed tracking** | **Sergey + Ionesio** | W1→W2 | P1 |
| **Multi-turn ensemble** issue | **Madhava Jay** | W2 | P1 |
| Pipeline to integrate **SyftSpaces into evaluations** | **Ionesio Junior + Khoa** | W2 | P1 |

### Benchmarks — *team: Siddhant(?), Sameer(?), Khoa*
| Component | Owner(s) | Wave | P |
|---|---|---|---|
| Produce the **first 4 SOTA results** | Benchmarks team | W1 | P0 |
| First SOTA using **fake private data** (the bridge) | Benchmarks team | W1→W2 | P1 |
| First SOTA using **real private data** | Benchmarks team | W2 | P2 |
| Map the **benchmark landscape** (key actors, where published, domain org, what makes a benchmark trustworthy) | **Osam Kyemenu-Sarsah** | W1 | P1 |

### Community / Marketing — *team: Marketing (+ Product)*
| Component | Owner(s) | Wave | P |
|---|---|---|---|
| **Product Hunt launch** (open the tools to everyone) | Marketing | W1 | P0 |
| **"Fusion-Monsters" program** — people who hunt SOTA results and get the subsidized engine | Marketing + Product | W1 | P1 |
| **Blog post** | Marketing | W1 | P0 |
| **Tutorial** (Andrew presents) | Marketing | W1 | P0 |
| **Website** | Marketing | W1 | P0 |
| **Playbook** for announcing future SOTA results (from OM or a Fusion Monster) | Marketing | W1 | P1 |

### Legitimacy / Policy — *team: Policy*
| Component | Owner(s) | Wave | P |
|---|---|---|---|
| Collect **endorsements** ("good for safety / good for China / good for X") | Policy | W1 | P1 |
| Co-write pieces with **Max Katz, Anthony (?), Project Liberty** | Policy | W1 | P1 |
| Build a **pipeline of data contributors** for SyftSpaces (under specific domains) | **Prewitt + Dave Buckley** | W2 | P1 |

### Fundraising
| Component | Owner(s) | Wave | P |
|---|---|---|---|
| Find **cloud providers to sponsor compute** | Fundraising | W1→W2 | P1 |
| Find **funders to sponsor tokens** | Fundraising | W1→W2 | P1 |

---

## 4. Timeline & milestones

- **🚢 July 1, 2026 — V1 Phase 1 (dev) ships:** the Wave-1 product — create/run/evaluate ensembles on the shared leaderboard, with cached sessions and the subsidized provider live.
- **One coordinated invitation (not a staggered trickle).** Dev, Community/Marketing, Policy, and Fundraising go together around the July 1 ship so the invitation is clear and the whole community — researchers and academics especially — can step onto the network at once. We're optimizing for reach and participation, not a land-grab.
- **Wave 2 (private data via SyftSpace) — TBD**, sequenced after evaluation lands; the fake-private-data SOTA result is the bridge that de-risks it.

**What "done" means for July 1:** a new user can install, open the leaderboard, copy/try an ensemble, run an eval locally (cached), see a result on the board, and the subsidized provider is available — end to end, on their own machine.

*(Dates beyond July 1 are intentionally open. Drop them in here and this section is diagram-ready.)*

---

## 5. Risks & honest unknowns

We'd rather name these now than get surprised. None is fatal; all change how we sequence and what we claim.

### R1 — OpenRouter is already here (Fusion / Draco)
**The risk.** OpenRouter ships **Fusion**, a hosted multi-model/ensemble product, and has the benchmark narrative to match ("Fusion beats frontier"); the **Draco** benchmark (`perplexity-ai/draco`) is on our post-demo list specifically to *reproduce* their result. So a well-funded incumbent already owns the plain "ensembles beat single models" story — louder and more convenient (hosted, zero-setup) than us. Our Draco reproduction could also come back showing they're simply ahead.
**Why it's real.** It's their live product, not a rumor; convenience usually wins casual users.
**What we're doing.** Don't compete on the generic ensemble claim — lead where we're actually differentiated: **private data + diversity** (R-thesis in §2), **local / no-middleman**, and **open/community + subsidized compute**. Treat OpenRouter as validation. Run the Draco reproduction **early** so we know where we really stand before we make public claims. *(Owners: Benchmarks; engine — Ionesio.)*

### R2 — Multi-turn + tools asymmetry
**The risk.** Ensembling is cleanest for **single-shot Q&A** — which is exactly what the benchmark demo is. Real coding-CLI work is **multi-turn and tool-using**, and that's where ensembling is hardest: models emit **different tool-call formats**, LiteLLM doesn't cleanly support `tool_calls` ([`ISSUES.md`](ISSUES.md) I-22), and reconciling divergent tool calls + conversation state across an ensemble is unsolved (the multi-turn ensemble issue, owner **Madhava Jay**, P1). So our most credible demo is single-shot, while the daily-driver use people will *actually try* is the weakest part.
**Why it's real.** It's an open engineering problem we haven't solved, and it sits on the main use case.
**What we're doing.** Scope V1 launch claims to **eval/benchmark + single-turn ensembles**; be explicit that multi-turn-with-tools is **in progress (P1)**, not shipped. Don't over-promise the coding-agent loop at launch.

### R3 — Experiment-to-SOTA time (no quick win)
**The risk.** The "come reach SOTA" loop may be **too slow and too expensive** to give newcomers a fast win. Full benchmark runs take **20+ minutes**, hit provider **429s** (I-20) and risk CLI timeouts (I-21); and beating SOTA can take **many trial ensembles** (a combinatorial search). If a first-time user's first experience is a long, costly grind with no payoff, the Product Hunt / "Fusion-Monsters" momentum stalls.
**Why it's real.** The runtime/limit numbers are observed, and SOTA-hunting is genuinely search-heavy.
**What we're doing.** **Caching** + **subsidized compute** cut latency and cost; **seed the leaderboard with a few ready-made SOTA ensembles** so a newcomer's quick win is *remix-and-rerun*, not search-from-scratch; set expectations openly — *remixing is the fast win; topping a board from zero is a marathon.*

---

## 6. Expectations & ways of working

- **Daily build call + dogfood.** We use the tool as our own daily driver; fix what you don't like.
- **High trust, low ceremony.** Merge fast, review informally, show > tell at heartbeat.
- **P0 protects the ship.** If it's not P0, it doesn't get to slip July 1. P1 is fast-follow; P2 is Wave 2+.
- **Workflow:** Asana-backed `SF-{n}` branches, never commit to `main`, PR links the Asana ticket. (See `docs/team-development.md`.)
- **Owners own outcomes, not just tasks** — including the handoffs noted above (e.g. leaderboard: Dmitry → Filip/Khoa).

---

## 7. People (owner directory)

| Name | Pillar(s) |
|---|---|
| **Sergey** Bershadsky | Dev — gateway, caching, cost/speed |
| **Dmitry** | Dev — caching, leaderboard, subsidized provider backend |
| **Ionesio Junior** | Dev — url4 engine, SyftSpaces-in-eval, cost/speed |
| **Tauquir Ahmed** | Dev — Python SDK, app frontend |
| **Filip** / **Khoa** | Dev — leaderboard (handoff); Khoa also Benchmarks + SyftSpaces pipeline |
| **Madhava Jay** | Dev — multi-turn ensemble |
| **Siddhant(?)**, **Sameer(?)**, **Khoa** | Benchmarks |
| **Osam Kyemenu-Sarsah** | Benchmarks — landscape research |
| **Andrew** (Trask) | Community — tutorial; overall narrative |
| **Prewitt**, **Dave Buckley** | Policy — SyftSpace data-contributor pipeline |
| Marketing, Product, Policy, Fundraising | pillar teams (see §3) |
| External: **Max Katz**, **Anthony (?)**, **Project Liberty** | Policy — co-authored pieces |

---

*Drafted from the team's planning notes (June 2026), written for the OpenMined core-team audience. Owners and dates beyond July 1 are living — edit here; this file is the source of truth for the split.*
