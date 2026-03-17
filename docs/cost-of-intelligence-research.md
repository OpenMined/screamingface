# Cost of Intelligence — Market & Audience Research

**Date:** 2026-03-16
**Supporting research for:** `docs/cost-of-intelligence-exploration.md`

---

## 1. Existing Landscape — Who Tracks AI Model Performance + Cost?

### Benchmark-Only Platforms (No Cost Data)

**Chatbot Arena / LMSYS**
- Head-to-head human preference rankings via blind voting
- 2M+ community votes, widely cited
- No cost dimension whatsoever — pure capability ranking
- Style: academic, utilitarian, research-focused

**Hugging Face Open LLM Leaderboard**
- Open-source model accuracy across standardized benchmarks
- Community-driven, massive participation
- No cost data — purely about which open model performs best

**Scale Labs SEAL**
- Enterprise-focused evaluation benchmarks
- Private evaluations, B2B oriented
- No public cost comparison

**LiveBench**
- Frequently updated benchmark with contamination-resistant questions
- Academic rigor, monthly refreshes
- Benchmark-only, no pricing layer

### Cost + Performance (Partial Integration)

**Artificial Analysis** (artificialanalysis.ai)
- **Closest competitor to the proposed direction**
- Tracks 410+ models across providers
- Shows: quality scores, pricing, speed (TTFT, tokens/sec), context window
- Has a "Quality vs Price" scatter plot
- **But**: Model-centric, not problem-centric. Shows "Model X costs Y per million tokens and scores Z on MMLU." Does NOT show "Solving a coding problem at 90% accuracy costs $X."
- Missing the synthesis that Andrew is proposing

**Vellum**
- Shows pricing alongside benchmark scores in parallel columns
- Side-by-side comparison tool
- Not a unified cost-per-accuracy metric; just two data points next to each other

**OpenRouter**
- Aggregates 300+ models across 60+ providers
- Shows pricing per model
- Has an auto-router that optimizes for cost/quality
- **Infrastructure layer**, not a public dashboard or analytical tool

### Cost Infrastructure (Behind-the-Scenes)

**Not Diamond**
- Routes queries to optimize cost/accuracy/latency per input
- The infrastructure version of what Andrew wants to make visible
- Not a public-facing dashboard

**Epoch AI**
- Tracks training costs across 3,200+ models historically
- Training cost ≠ inference cost per task
- Research-oriented, not real-time

**SemiAnalysis**
- Infrastructure TCO analysis (GPU costs, data center economics)
- Supply-side costs, not demand-side "what does it cost to solve X?"

### The Gap

**Nobody publishes a live, task-specific cost-per-accuracy tracker.**

The pieces exist:
- Benchmark scores (many sources)
- API pricing (published by every provider)
- Cost-efficiency analysis (scattered blog posts, Twitter threads)

But nobody has synthesized them into: **"For problem type X, at accuracy threshold Y%, here's what each model costs, and here's how that's changed over time."**

This is the gap Andrew identified.

---

## 2. The Financial Markets Analogy

### Why It Works

The "stock prices for intelligence" metaphor does several things:

1. **Makes the abstract tangible.** "AI capability" is vague. "$0.47 per correct answer on college math" is concrete.

2. **Creates urgency through movement.** Static benchmarks are published once and forgotten. Prices that move daily create ongoing relevance, return visits, and news cycles.

3. **Implies a market.** Where there are prices, there are buyers, sellers, and market dynamics. This naturally raises questions about who sets prices, whether they're fair, and whether competition is working.

4. **Is universally legible.** You don't need to understand MMLU or HLE to understand "this costs more than that." Cost is the universal metric.

### Precedents: Financial UX Applied to Non-Financial Data

**Levels.fyi**
- Made opaque tech compensation data transparent
- Uses stock-market-style charts (total comp over time, by company, by level)
- Built massive adoption (10M+ annual visitors) because it exposed data people wanted but couldn't get
- **Direct parallel**: "What does a senior engineer make at Google?" → "What does it cost to solve a coding problem with Claude?"
- Key lesson: the data was always theoretically available (Glassdoor, etc.) but Levels.fyi SYNTHESIZED it in a way that was immediately useful

**Our World in Data**
- Each visualization tells a self-contained, shareable story
- Charts get embedded in articles, tweets, presentations globally
- Not "financial UX" per se, but proves that data-dense visualizations can go viral when they answer a question people care about
- Key lesson: make every chart embeddable and self-explanatory

**Electric Capital Developer Report**
- Annual report on crypto developer activity
- Became THE authoritative reference that everyone in the industry cited
- Created a brand (Electric Capital) out of being the data source
- Key lesson: being the definitive source of a metric IS the brand

**CoinMarketCap / CoinGecko**
- Applied financial UX (tickers, sparklines, 24h change, market cap) to crypto
- Built massive audiences that pre-dated any product or tool
- Key lesson: the dashboard IS the product for many users; the tool comes later

### Design Implications

From these precedents, the cost-of-intelligence dashboard should:
- Show price MOVEMENT, not just current prices (sparklines, % change)
- Be organized by what users care about (problem type, not model)
- Make every visualization shareable/embeddable
- Update frequently enough to be worth revisiting
- Cite methodology transparently (the "how we calculate this" is as important as the data)

---

## 3. Audience-Specific Appeal

### For Audience 1 (Developers) — "Finally, the data I've been collecting manually"

From the persona doc:
- **Token-constrained** (key psychographic) — cost is deeply personal
- **Skeptical of hype** — data-driven decisions are their default
- **Love benchmarks** — but frustrated that benchmarks don't include cost
- **Already comparing informally** — in Reddit threads, blog posts, Twitter. A dashboard formalizes what they're already doing.

**What they'd do with it:**
- Use it to choose which API to call for specific tasks
- Share charts on HN, Reddit, Discord when debating models
- Run the crowdsourcing script to contribute (they love open data projects)
- Eventually install the ensemble tool to get the cost-efficiency the dashboard proves

**The persona doc literally says:** "An interactive, well-labeled chart comparing accuracy-vs-cost across models is more persuasive than any copy." Direction B puts this front and center.

**HN launch potential:**
- "Show HN: We built a live tracker for the real cost of AI intelligence"
- This is exactly the kind of novel data + clean visualization that gets HN front page
- Simon Willison would likely cover it (he writes about AI cost/efficiency regularly)

### For Audience 2 (Policy/Thought Leaders) — "Who controls the price of intelligence?"

From the persona doc:
- Care about **power concentration** — a cost dashboard makes concentration visible
- Need **non-technical framing** — "cost" is universally understood; "benchmark accuracy" isn't
- Want something **concrete** — not ethics platitudes, but actual data
- Need **shareable artifacts** — for op-eds, policy briefs, slide decks

**What they'd do with it:**
- Embed charts in policy papers and presentations
- Ask "why does Company X charge 10x more for the same capability?"
- Connect it to market concentration arguments
- Use it as evidence in the "public investment in AI" argument
- Share it as "something everyone should see"

**The bridge to the 2-year window:**
"Right now, 3-4 companies set the price of intelligence. Watch these prices move. Watch who controls them. In two years, you won't have the choice to route around them. This is the window to build public alternatives."

That's 100x more powerful than "Deep Voting is a new architecture for trust-based AI."

### For the ABC Cohort — "This is the governance metric we've been missing"

- **Allan Dafoe / Ben Garfinkel** (GovAI/DeepMind) — Would immediately recognize "cost of intelligence" as an AI governance metric. This is the kind of data their research programs need.
- **Bruce Schneier** — Would write about market concentration implications. Cost data is security data (dependency on concentrated providers = systemic risk).
- **Carissa Véliz** — Would connect to her arguments about data value and exploitation. "Your data trained these models. Here's what companies charge for the intelligence your data created."
- **Pamela Samuelson** — Would connect to copyright/compensation arguments. Cost data provides the economic foundation for "who gets paid when AI uses your data?"

### For the Time 100 — "The feature they actually care about"

The Time 100 report's key finding: **credit-sharing is the most broadly resonant feature** — more than benchmarks.

Cost-of-intelligence is the foundation for the credit-sharing story:
1. "Here's what intelligence costs" (dashboard)
2. "Here's how to get it cheaper" (ensemble)
3. "Here's how to share those savings with your team" (credit sharing)

Without the cost framing, credit sharing is an abstract feature. With it, credit sharing is the obvious next step.

---

## 4. Viral Potential

### What Makes Data Visualizations Go Viral in Tech

Based on precedents (Our World in Data, Levels.fyi, Electric Capital, various HN front-pagers):

1. **Novel data** — Something nobody has seen before. "The cost to solve a coding problem dropped 43% this month" is novel.

2. **Self-contained stories** — Each chart should answer a question on its own, without needing the surrounding page. Embeddable = shareable.

3. **Regular updates** — One-time publications get one moment. Regularly-updated data creates ongoing relevance and repeat visits. Price movement = daily stories.

4. **Controversy potential** — Data that challenges assumptions generates discussion. "GPT-4o is 3x more expensive than the ensemble for the same accuracy" is inherently controversial.

5. **Community ownership** — Crowdsourced data creates community investment. People share things they helped build.

6. **Methodology transparency** — In the developer audience, HOW you calculated matters as much as what you found. Open methodology = trust = shares.

### Specific Viral Scenarios

- **"The price of coding intelligence dropped 60% in 6 months"** → HN front page, dev Twitter, newsletter coverage
- **"It costs $4.72 to solve a college-level math problem at 95% accuracy"** → Mainstream tech press, policy citations
- **"The ensemble costs 40% less than any single model for the same accuracy"** → Direct product conversion
- **"Company X just raised prices on reasoning tasks by 200%"** → Controversy, discussion, Audience 2 amplification
- **Weekly "State of Intelligence Pricing" report** → Newsletter-worthy, journalist-friendly

---

## 5. Deep Voting Connection

The bridge from cost-of-intelligence to Deep Voting/ABC is natural:

**Phase 1**: "We show you what intelligence costs."
**Phase 2**: "We show you how to get it cheaper (ensemble)."
**Phase 3**: "We show you WHERE that intelligence comes from (attribution)."

The financial metaphor extends:
- Cost-of-intelligence = the price ticker
- Deep Voting = the audit trail (like "who holds this stock?" in financial markets)
- Attribution-Based Control = the regulatory framework (like SEC requirements for transparency)

For Audience 2, this sequence is powerful:
1. "You can see what intelligence costs" (transparency)
2. "You can choose which sources you trust" (agency)
3. "The people whose data created this intelligence can be compensated" (justice)

Each phase builds on the previous one. Direction B starts at phase 1 — which is the most universally compelling entry point.

---

## 6. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Dashboard is interesting but doesn't convert to product users | Medium | High | Design the ensemble row as the hero — every chart should show the ensemble winning on cost-efficiency |
| Artificial Analysis adds problem-centric view first | Low | Medium | They're model-centric by DNA; pivoting is hard. Speed to market matters. |
| Data quality/accuracy challenges | Medium | Medium | Open methodology, community verification, conservative claims |
| "Just a dashboard" perception from Benchmark Doers | Medium | Low | Crowdsourcing script gives them something to DO, not just look at |
| Pricing data changes faster than we can track | Low | Medium | Automated pipeline from public API pricing pages |
| Legal issues with publishing comparative pricing | Very Low | Medium | All data is publicly available; comparison is editorial, not commercial |

---

## 7. Key Design References

For the dashboard design:

- **bitcoinwisdom.io** — Andrew's direct reference. Data-dense, real-time, financial-feeling.
- **Levels.fyi** — Clean data visualization of information people desperately want.
- **Our World in Data** — Each chart tells a story. Embeddable. Shareable.
- **Artificial Analysis** — Closest in content. Study what they do well (comprehensive data) and what they miss (problem-centric view).
- **Supabase dashboard** — For the screamingface aesthetic: warm, light, data-dense but not overwhelming.
- **PostHog** — Open-source analytics with personality. Transparent methodology displayed proudly.

**What NOT to reference:**
- Bloomberg Terminal (too complex, too dark, too financial-bro)
- CoinMarketCap (too crypto-coded, alienates non-crypto audiences)
- Generic dashboard templates (too corporate)

The sweet spot: **warm, light, data-dense, personality-forward, and problem-centric.**

---

*Research compiled 2026-03-16. Sources include web research, persona analysis, competitive landscape review, and Slack conversation context.*
