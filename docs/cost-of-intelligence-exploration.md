# The Real Cost of Intelligence — Direction Exploration

**Date:** 2026-03-16
**Author:** Bennett (with Claude)
**Context:** Andrew's DM thread proposing a pivot to the v1 launch strategy — launching screamingface first as a cost-of-intelligence tracker before the full ensemble product ships.

---

## The Proposal (Andrew's Words)

> "we should start by just creating leaderboards that measure AI models by how much they cost to solve problems at a certain level of accuracy"
>
> "v1 should be a website that looks/feels like bitcoinwisdom.io but for every type of intelligence imaginable"
>
> "live updating market prices for different kinds of intelligence"
>
> "stock prices for intelligence is such a sexy idea that it's a really good way to get people's attention"
>
> "the nice thing being that we can create a following much earlier, long before we have a working product"

Andrew also proposed that people would run a local script to help crowdsource the cost data — making it participatory, not just a static dashboard.

---

## Direction A: Current ("SOTA on Your Laptop")

### The Pitch
The models you already use (Claude Code, Gemini CLI, Codex, Ollama) combined into an ensemble that consistently outscores any one of them. No new workflow. No new subscription.

### What the Website Does
- Hero: "SOTA on your laptop" + 😱 emoji
- Leaderboard chart: HLE benchmark accuracy (ensemble vs. individual models)
- Install command: `curl -fsSL https://screamingface.ai/install | sh`
- /why page: Deep Voting + 2-year window argument for policy audience
- Email capture for beta access

### Core Value Proposition
**Performance**: The ensemble beats every individual model on benchmarks.

### What Ships First
The full product — Electron app, microservices, ensemble routing, eval studio. The website is a marketing front for the tool.

### Blockers
- Benchmark data is placeholder (chart literally says "placeholder data")
- Ensemble routing needs to actually work and prove the SOTA claim
- Electron app + 8 microservices need to be built
- Collaborators section is fabricated
- The SOTA claim is the ENTIRE argument — if it doesn't hold, there's nothing

---

## Direction B: Proposed ("The Real Cost of Intelligence")

### The Pitch
Every AI benchmark measures accuracy. Every pricing page shows cost per token. Nobody shows what actually matters: **how much does it cost to solve a specific problem at a specific level of accuracy?**

### What the Website Does
- Hero: Live, updating cost-per-accuracy dashboard (think bitcoinwisdom.io meets AI benchmarks)
- Rows organized by **problem type** (coding, reasoning, medical QA, math, writing) not by model
- Columns show: models ranked by cost-efficiency for that task, with price movement over time
- Ensemble data included from day one — proving that model combinations beat single models on cost-efficiency
- Crowdsourced: users run a local script to contribute cost data
- Every chart is embeddable and shareable

### Core Value Proposition
**Transparency + Economics**: You deserve to know what intelligence actually costs — and that no single model gives you the best deal.

### What Ships First
A website. Just a website. No Electron app, no microservices, no routing. A compelling data visualization that builds a following, then the product comes later.

### Blockers
- Need real benchmark + pricing data (but this is more achievable than building the full product)
- Need the crowdsourcing script
- Need a data pipeline that keeps prices current
- Need enough problem categories to be interesting

---

## Side-by-Side Comparison

| Dimension | Direction A (SOTA) | Direction B (Cost of Intelligence) |
|---|---|---|
| **What ships first** | Full product (app + site) | Website only (data viz) |
| **Time to v1** | Weeks to months | Days to weeks |
| **Core claim** | "The ensemble beats every model" | "Nobody is showing you the real cost" |
| **Proof required** | Working ensemble + real HLE scores | Benchmark data + API pricing (public data) |
| **Audience hook** | Performance (beat SOTA) | Economics (save money, see truth) |
| **Viral mechanism** | HN launch of a tool | Embeddable charts, daily price changes, controversy |
| **Community before product** | No — need product to prove claim | Yes — dashboard builds following pre-product |
| **Revenue story** | Tool adoption → credit sharing | Audience → tool adoption → credit sharing |
| **Risk** | SOTA claim doesn't hold, or takes too long to prove | Dashboard is interesting but doesn't convert to product users |
| **Ensemble narrative** | "It wins benchmarks" | "It gives you the best price for the intelligence you need" |
| **Defensibility** | Open source tool (can be cloned) | First-mover on framing + community data (harder to clone) |

---

## Persona Analysis: How Each Audience Responds

### Audience 1 — Technical Developers & Benchmark Enthusiasts (P0)

**Direction A reaction:**
"Show me the benchmark. If it's real, I'll try it. If it's placeholder, I'm gone."
- This audience WILL install and test — but only if the claim is verifiable on day one
- The current placeholder data is a credibility killer; this audience closes tabs in 5 seconds
- The install-command-as-hero is strong for this group
- Risk: if ensemble doesn't actually beat SOTA, the entire pitch collapses

**Direction B reaction:**
"Oh interesting, I've been wondering about this. Let me see the data."
- This audience is **token-constrained** (key psychographic trait) — cost-efficiency is deeply personal
- They already compare models informally; a dashboard that does it rigorously earns trust
- The crowdsourcing angle appeals: they love contributing to open datasets
- Embeddable charts get shared on HN, r/LocalLLaMA, r/MachineLearning
- "Stock prices for intelligence" is the kind of framing that generates HN front-page threads
- **Key advantage**: Direction B doesn't require them to change their workflow or install anything to engage. Lower barrier = larger initial audience
- Risk: if it's just a pretty dashboard, the "so what?" question comes fast. Need a clear bridge to the tool.

**Verdict for Audience 1: Direction B is STRONGER for initial engagement.** Direction A is stronger for conversion but requires the full product to exist first. Direction B can start building the audience TODAY while the product is being built.

### Audience 2 — AI/Society Thought Leaders & Policy (P1)

**Direction A reaction:**
"I don't understand benchmarks and I don't code. What does this have to do with the 2-year window?"
- The /why page does important work here, but it's disconnected from the homepage
- Deep Voting framing resonates but (per Trask's own feedback) some claims are premature
- This audience needs something they can point to and share with other non-technical people

**Direction B reaction:**
"Wait — who controls the price of intelligence? And why isn't anyone tracking this?"
- "The Real Cost of Intelligence" is **immediately legible** to non-technical people
- It reframes AI competition in economic terms that policy people understand
- The framing naturally raises questions about market concentration, pricing power, and public alternatives
- "Right now, 3-4 companies set the price of intelligence and nobody is watching" — that's a policy story
- Connects directly to the 2-year window: "Look at how prices are moving. Look at who controls them."
- Embeddable charts work in op-eds, policy briefs, and presentations
- **Key advantage**: Direction B gives Audience 2 something THEY can use and share, not just something they have to explain to others

**Verdict for Audience 2: Direction B is DRAMATICALLY stronger.** It makes the invisible visible. Cost-of-intelligence is the policy bridge that the current /why page is trying to build but can't because it's grounded in technical concepts (Deep Voting, ensemble routing) that don't translate.

### ABC Cohort — Peers & Validators

**Direction A reaction:**
- Technical validators (Dwork, Papernot, McMahan) would want to audit the ensemble methodology
- Public intellectuals (Schneier, Véliz) wouldn't engage until there's a societal narrative

**Direction B reaction:**
- Governance architects (Dafoe, Garfinkel at GovAI/DeepMind) would recognize "cost of intelligence" as an **AI governance metric** — this is the kind of data they wish existed
- Public intellectuals would share the charts and write about the framing
- Legal/attribution specialists (Samuelson) would connect it to the value-of-data arguments they already make
- The bridge to Deep Voting/ABC is natural: "We show you what intelligence costs. Next, we'll show you where it comes from."

**Verdict for ABC: Direction B creates engagement opportunities that Direction A doesn't.**

### Time 100 AI Cohort

The Time 100 report's key finding was that **credit-sharing is the most broadly resonant feature across ALL groups** — more than benchmark claims. Direction B directly leads with cost/economics, which is the foundation for the credit-sharing story.

- Technical Practitioners would evaluate the data rigorously and cite it
- Critical Evaluators would use it to make arguments about pricing power and market concentration
- Domain Practitioners (healthcare, art, education) care about cost because they're budget-constrained
- The "stock prices for intelligence" metaphor is novel enough to generate coverage

**Verdict for Time 100: Direction B is significantly more shareable and quotable.**

---

## The Market Gap (Research Findings)

### What Exists Today

| Platform | What It Tracks | What's Missing |
|---|---|---|
| **Artificial Analysis** | Cost + benchmark performance for 410+ models | Model-centric (not problem-centric). Shows "Model X costs Y and scores Z" but not "Solving this problem costs $X" |
| **Chatbot Arena (LMSYS)** | Head-to-head human preference rankings | No cost data at all |
| **Scale Labs / SEAL** | Enterprise-focused eval benchmarks | No cost dimension |
| **Hugging Face Open LLM Leaderboard** | Open-source model accuracy | No cost data |
| **Vellum** | Pricing + benchmarks as parallel columns | Not integrated; no "cost per unit of accuracy" metric |
| **Not Diamond** | Routes queries to optimize cost/accuracy/latency | Infrastructure, not a public dashboard |
| **Epoch AI** | Historical training costs across 3,200+ models | Training cost, not inference cost per task |

**The gap:** Nobody publishes a live, task-level, "what does it cost to solve X at Y% accuracy" tracker. The pieces exist separately — benchmark data on one site, pricing on another — but nobody has synthesized them into the metric that actually matters.

### The Financial Markets Analogy Works

**Precedents for applying financial UX to non-financial data:**

- **Levels.fyi** — Made opaque compensation data transparent with stock-market-style visualizations. Built massive adoption because it gave people data they desperately wanted but couldn't get. Directly analogous: "What does intelligence cost?" is the "what does a senior engineer make at Google?" of AI.

- **Our World in Data** — Generates viral charts because each one tells a self-contained, shareable story. A cost-of-intelligence chart that shows the ensemble beating individual models on cost-efficiency would be exactly this kind of shareable artifact.

- **Electric Capital Developer Report** — Became THE authoritative reference for crypto developer activity. Everyone cited it. A cost-of-intelligence dashboard could become the authoritative reference for "how much does AI really cost?"

- **BitcoinWisdom.io** (Andrew's direct reference) — Data-dense, real-time, financial-feeling. The UX pattern (price tickers, time-series charts, comparison tables) is immediately legible and creates a sense of live, dynamic data.

### Why This Would Go Viral

1. **Novel data**: Nobody is showing this. First-mover advantage on the framing.
2. **Daily newsworthiness**: Prices change every time a model updates or a provider adjusts pricing. Static benchmarks are one-time events; cost-of-intelligence is an ongoing story.
3. **Embeddable**: Every chart can be embedded in blog posts, tweets, newsletters, presentations.
4. **Controversial**: "Did you know it costs $4.72 to solve a college-level math problem at 95% accuracy?" — that's a headline.
5. **Participatory**: Crowdsourced data means the community owns it.
6. **Both audiences**: Developers share it because it's useful. Policy people share it because it's alarming.

---

## The Bridge: How Direction B Leads to the Product

Andrew's insight: "the ensemble becomes more about making it so you can continuously calibrate/optimize that cost, and exceed the max capability."

The narrative arc:

1. **Phase 1 (Dashboard)**: "Here's what intelligence costs. Isn't it interesting? Isn't it concerning?"
2. **Phase 2 (Insight)**: "Did you notice the ensemble row always wins on cost-efficiency? That's because combining models is always cheaper than relying on one."
3. **Phase 3 (Tool)**: "Want that cost-efficiency for yourself? One command: `curl -fsSL https://screamingface.ai/install | sh`"

The dashboard IS the top of the funnel. It builds the audience, establishes the brand, proves the core insight (ensembles win on cost-efficiency), and creates natural demand for the tool.

---

## What Changes, What Stays

### Stays the Same
- 😱 brand identity
- OpenMined gold design system
- The ensemble as the core technical advantage
- /why page for policy audience (actually gets stronger)
- Open source ethos
- The install command and CLI tool (becomes Phase 2)
- Credit-sharing feature (becomes the natural next step: "now share that cost-efficiency with your team")

### Changes
- **Homepage hero**: "SOTA on your laptop" → "The real cost of intelligence" (or similar)
- **Centerpiece**: Static benchmark chart → Live cost-per-accuracy dashboard
- **Primary metric**: Accuracy → Cost-per-accuracy
- **What ships first**: Full product → Dashboard website
- **Engagement model**: "Install this" → "Explore this data, then install this"
- **Data source**: Internal benchmarks → Crowdsourced + public API pricing
- **Update cadence**: Static → Live/daily
- **Shareability**: Low (it's a product page) → High (every chart is a shareable artifact)

### Gets Stronger
- **Audience 2 engagement**: Cost is legible; benchmarks aren't
- **Community building**: People contribute data, not just consume
- **HN/viral potential**: Novel data + embeddable charts + controversy
- **Time-to-launch**: Website only, no product dependency
- **Credit-sharing pitch**: "We showed you what intelligence costs. Now save money on it."
- **Deep Voting bridge**: "We show what intelligence costs. Next: where it comes from."
- **The 2-year window argument**: "Watch these prices. Watch who controls them. That's the window closing."

### Gets Weaker (Risks)
- **"SOTA on your laptop" as a singular tagline** — diffused, but not lost (it becomes the Phase 2 pitch)
- **Product urgency** — if the dashboard is compelling on its own, will people care about the tool?
- **Benchmark Doers** — the most technical sub-group of Audience 1 may see a dashboard as "not a real product"
- **Competitive moat** — a dashboard is easier to clone than a working ensemble tool

---

## Design Direction: What This Would Look Like

### Concept: "The Intelligence Ticker"

**Header**: Minimal. 😱 screamingface logo, nav links (Dashboard, About, GitHub, /why).

**Hero**: No big headline. Instead, a live-feeling data visualization fills the viewport — rows of problem categories with real-time-ish cost data, model rankings, and sparkline price movement. Think Bloomberg Terminal meets Our World in Data meets bitcoinwisdom.io, but in screamingface's warm/light aesthetic.

**Below the fold**:
- "What is this?" — brief explainer of the cost-per-accuracy metric
- "How we calculate it" — methodology transparency (crucial for Audience 1 trust)
- "The ensemble always wins" — callout showing that model combinations consistently beat single models on cost-efficiency
- "Contribute data" — crowdsourcing CTA with script
- "Get the tool" — bridge to the ensemble installer
- "Why this matters" → /why page

**Individual problem pages**: Click into "Coding" and see detailed model comparison, cost history, accuracy thresholds, ensemble configurations. Deep, explorable data.

**Embeddable widgets**: Every chart has a "Share" button that generates an embed code or a direct link to a static image. Optimized for Twitter cards, blog embeds, and slide decks.

### Visual Feel
- **Not** dark/hacker/financial (avoid the crypto bro aesthetic)
- **Yes** warm, light, data-dense but readable — screamingface's existing gold + light aesthetic
- The data is the design. No hero images, no illustrations. Just the numbers, well-presented.
- Sparklines in gold. Ensemble rows highlighted. Everything else neutral.
- Sometype Mono for all data. Rubik for headings. Inter for body.
- Responsive: mobile shows simplified cards per problem type; desktop shows the full ticker.

---

## Recommendation

**Direction B is stronger for v1 launch.** Here's why:

1. **It can ship NOW.** The current site has placeholder data and no working product. Direction B needs benchmark data + API pricing — both publicly available — and a compelling visualization. That's a website sprint, not a product sprint.

2. **It builds audience before product.** Andrew said it himself: "we can create a following much earlier, long before we have a working product." The dashboard is the following-builder.

3. **It serves BOTH audiences from day one.** Direction A requires the /why page to do heavy lifting for Audience 2. Direction B naturally speaks to both: developers see cost-efficiency data, policy people see market concentration data. Same dashboard, different takeaways.

4. **It makes the ensemble pitch inevitable.** If every chart shows that model combinations beat single models on cost-efficiency, the natural question is "how do I get that?" — and that's the product.

5. **It's more defensible as a brand.** "The place where you find out what intelligence costs" is a category-defining position. "Another CLI tool that combines AI models" is a feature.

6. **It connects to everything downstream.** Credit sharing ("save on those costs with friends"), Deep Voting ("where does that intelligence come from?"), the 2-year window ("watch who controls those prices").

### The Sequence

```
Week 1-2: Ship the dashboard with public data (benchmarks + pricing)
Week 2-3: Add crowdsourcing script + ensemble data
Week 3-4: Add embeddable widgets + /why page integration
Week 4+:  Bridge to the tool ("Want this cost-efficiency? Install screamingface.")
```

**Direction A isn't wrong — it's Phase 2.** The "SOTA on your laptop" pitch is the conversion story. Direction B is the acquisition story. You need both, but B comes first.

---

## Open Questions

1. **What's the name of the metric?** "Cost per accuracy point"? "Price of intelligence"? "Intelligence cost index"? The framing matters enormously.

2. **How do we handle the ensemble data?** Do we show "Ensemble (😱)" as a row from day one with our own data? Or wait until users crowdsource it?

3. **What problem categories to start with?** Coding is obvious. Math, reasoning, medical QA? Need categories that have established benchmarks AND that people care about the cost of.

4. **Crowdsourcing mechanics**: What does the local script actually measure? How do we aggregate? How do we prevent gaming?

5. **Relationship to existing players**: Artificial Analysis is closest. How do we position relative to them? (Answer: they're model-centric, we're problem-centric. Different question, different answer.)

6. **Does the /why page change?** The Deep Voting framing is separate from cost-of-intelligence. Do they merge? Or does /why remain the ABC-grounded societal argument while the homepage becomes the cost dashboard?

7. **Andrew said "purely marketing site where people can crowdsource the cost of AI programming tools"** — does he see this as a separate site from screamingface.ai, or as the new screamingface.ai homepage?

---

*This document is an exploration, not a decision. Bring it to the team for discussion.*
