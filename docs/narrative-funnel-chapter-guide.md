# Narrative Funnel — Chapter Guide

**Internal Reference, screamingface team**
**March 2026**

---

## Overview

screamingface does not launch as a product. It launches as a story — a narrative funnel that campaigns about the problem before introducing the solution. The goal is to create real value for technical developers (Persona 1) by giving them tools and data they actually need, and to bring them with us through a progression from awareness to tool to community to private data infrastructure.

**Key principle:** Each chapter is ongoing content production, not a single release. Chapters keep feeding even as later ones start. Think of them as taps you turn on — water flows downhill, and you don't stop pouring from the top just because some of it has reached the bottom.

**Note:** The OpenMined internal team enters at Chapter 4. Chapters 1–3 are public-facing only.

---

## Table of Contents

**Chapter1, Pre-release, Market Blindness**
Highlight how opaque the AI market is — live dashboards, pricing mechanics, daily accuracy drift

**Chapter2, Pre-release, Wasted Resources**
Pivot from "you don't know" to "you're getting a bad deal" — wrong tools, hidden costs, wasted accuracy

**Chapter3, Pre-release, Ensembles Are Inconvenient**
Observe that ensembles beat individual models, but deploying them is a pain

**Chapter4, Alpha, Authentic Tool**
First scrappy release of screamingface CLI — sideshow on leaderboard site, grows into main feature

**Chapter5, Alpha, Community Can Win**
Community-created ensembles, shared url4s, collaborative leaderboard improvement

**Chapter6, Beta, Coming of Age**
Press coverage, endorsements, institutional credibility — polish starts to make sense

**Chapter7, Private Data, Market Blindness (Private Data)**
AI hallucinations from lack of paywalled/private information — new leaderboards prove the gap

**Chapter8, Private Data, Wasted Resources (Private Data)**
Hallucinations cost time, money, accuracy — quantify the waste

**Chapter9, Private Data, Inconvenient (Private Data)**
Getting private data into AI is hard, clunky, insecure

**Chapter10, Gamma, Authentic Data Gates**
Data proxies that make private data queryable without centralizing it — connects to OpenMined's core mission

---

## Pre-Release: The Problem Campaign

### Chapter 1 — Market Blindness

**Thesis:** People don't know what they're buying when they use AI tools. The intelligence market is completely opaque.

**Target audience:** Persona 1 (technical developers, CLI power users)

**The problem we're highlighting:**
- AI pricing is opaque. Subscription plans don't tell you how many tokens you get — it just cuts off some days.
- Model quality changes constantly. Anthropic and others fiddle with models daily, but benchmarks are published once and treated as permanent.
- No two tokens are the same value. Claude tokens and ChatGPT tokens have different capabilities, different costs, different accuracy profiles — and those profiles shift.
- People don't want tokens — they want problems solved. Cost-per-solution is the real metric, and nobody tracks it.
- Companies benefit from this opacity. Anthropic adjusts token allotments (likely larger off-peak, smaller on-peak) without disclosure. This is a feature, not a bug, from their perspective.

**Content types:**
- **Tweets/blog posts (earliest):** Trask as individual. "I ran a script today and it seems like Claude Code is changing its price day to day. Here's yesterday vs. today. Huh." Observational, not adversarial.
- **Live dashboards:** Stock-chart style. What is the real price per million tokens on Claude Code right now? Updated continuously. What is today's accuracy on HumanEval if you download Claude Code right now? Not a fixed benchmark — a live ticker.
- **Leaderboards:** Daily accuracy scores across models on representative tasks. Not one-time evaluations — continuous monitoring that shows how scores drift over time.
- **Blog posts:** "How does the pricing mechanism at Claude Code actually work?" Deep dives on cache behavior (queries within 5 minutes are free, after that you pay again), token budget mechanics, hidden dynamics.

**Web properties:**
- Starts as a side page of Trask's personal blog + a tweet. "Hey, I noticed this thing."
- First static site is literally just the leaderboard — a single page showing live market data. That's all.
- May eventually become the screaming face brand ("I've been interested in this conversation for a while. I've moved it to a website called screamingface and we're working on it with some folks at OpenMined.")

**What success looks like:**
- 50–1,000 people in a core group who come to us for market intelligence on AI tools
- People viewing us as a source of useful insights, not an authority figure
- The algorithm starts associating OpenMined/Trask with this conversation
- A mild amount of controversy — "they were hiding it from you, we're telling you the truth"

**Connects to Chapter 2:** Once people can see the market, the natural next question is: "Am I getting a bad deal?"

**Staffing note:** May eventually want at least one person whose ongoing job is creating market blindness content — new leaderboards, new surprises, keeping the tap running even as later chapters start.

---

### Chapter 2 — Wasted Resources

**Thesis:** Now that you can see the market, you realize you're getting a bad deal. You're wasting money, time, and accuracy.

**Target audience:** Persona 1

**The problem we're highlighting:**
- You're using the wrong tool for the wrong task. Model X is better at task A, Model Y is better at task B, but you're using one for everything.
- Hidden pricing mechanics mean you're throwing away value. (Cache expiry, token budget resets, peak/off-peak pricing differences.)
- Accuracy varies by task type and by day. The model you're paying premium for might be underperforming on the specific thing you need today.
- Three dimensions of waste: **money** (paying more than necessary for the accuracy you get), **time** (using more tokens/attempts than necessary), **capability** (getting worse results than possible for your spend).

**Content types:**
- Specific surprises. "Did you know that if you wait 6 minutes between queries you just paid for your entire context window again?"
- Comparative analyses. "For this common task, here's what each model costs you per correct answer."
- Productivity content. "How to maximize overnight token productivity" — bridge from productivity hack to how-it-works-under-the-hood to here's-why-it-matters.
- Continue feeding Chapter 1 content (new leaderboards, new market data).

**Web properties:**
- Additional leaderboards on the existing site focused on cost-per-accuracy comparisons
- Blog posts with specific "gotcha" findings

**What success looks like:**
- People feel the problem personally — "I'm being taken for a ride"
- Demand building for a better way to spend on AI tools
- The funnel is wide here — we want eyeballs in this problem space, not tight conversion

**Connects to Chapter 3:** "OK, I'm wasting resources. What would a better approach look like?"

**Important note from Trask:** The funnel should be wide. Don't over-align every piece of content to ensembles. The main thing is people coming to us for the conversation. Some content may wander into side journeys if it means more impressions. Ensembles are a general solution to multiple problems — we don't need to telegraph it yet.

---

### Chapter 3 — Ensembles Are Inconvenient

**Thesis:** Ensembles outperform individual models. The data proves it. But deploying them is a pain.

**Target audience:** Persona 1

**What we're introducing:**
- Observation (not pitch) that ensembles beat individual models. The leaderboard data should make this obvious — ensembles sit above the Pareto frontier on accuracy-vs-cost charts.
- This is us stating a fact, not releasing a product. "We didn't invent this. We're observing that it's true."
- The natural conclusion from the chart: "How do I deploy this?" We don't answer that question yet. We let it sit.

**Content types:**
- Leaderboard updates showing ensemble results alongside individual models
- Blog posts: "We ran X models as an ensemble on Y benchmark. Here's what happened."
- The chart should scream it without us having to say it — individual models clustered below, ensembles above the frontier
- Overnight productivity angle: "If you don't care about latency and want to wake up to the right answer, a powerful ensemble that's slower but more accurate makes a lot of sense."

**Web properties:**
- Ensemble results added to existing leaderboard site
- The leaderboard is now showing something that creates demand for a solution

**What success looks like:**
- People are asking "How do I deploy an ensemble?" without us prompting them
- The community is primed for a convenient solution
- We've created demand without pitching anything

**Connects to Chapter 4:** "I wish it was easier to add an ensemble to my CLI." Enter screamingface.

---

## Alpha: Product Release

### Chapter 4 — Alpha Authentic Tool

**Thesis:** Here's a scrappy tool that solves the ensemble problem. We felt it too. Try it.

**Target audience:** Persona 1 (external) + OpenMined internal team (separate track converges here)

**What this is:**
- First release of the screamingface CLI tool
- Starts as a **sideshow** on the leaderboard site — "If you wanted to actually try this, here's where you go do that." A blog post, a side link. Not the main feature yet.
- Grows into the main feature over days/weeks as community interest builds
- The preceding chapters did the pitching. This page doesn't need to sell the problem.

**Website style (the "Dolly Parton effect"):**
- White background, plain text, minimal content
- Possibly single page, possibly no scrolling needed
- Tool language, not marketing language — "an app that makes your CLI smarter"
- No sales pitch. Assumes demand already exists from chapters 1–3.
- "Substance over style" — think academic professor website, early-stage open source project
- Internal team should feel like insiders, not outsiders. If it's too polished, it signals "you're being marketed to." If it's scrappy, it signals "you're part of this."
- Don't dress it down so much it looks suspicious — find the sweet spot
- NOT vibe-coded grad student random aesthetic. NOT fully polished product page. Somewhere original.

**Style reference dials (from Trask):**
1. 1995 web nostalgia
2. Vibe-coded aesthetic
3. 8-bit / retro
4. "Bennett originality magic" — if you only do the first three, you're positioning next to things that already exist. Need something unique.

**Content on the page:**
- What it is (one line)
- Install command
- What it does (brief)
- GitHub link
- That's roughly it

**Internal team messaging:**
- Trask communicates context via Slack, not on the website itself
- Internal team gets the alpha authentic tool version — scrappy, unfinished, "we built this over the weekend, try it out"
- Risk: without context, it's not immediately obvious how this links to OpenMined's mission. Trask's message addresses this: "This is a marketing strategy for our bets. Ensembles build community → community is the entry point for private data conversation."

**What success looks like:**
- Internal team can walk through the product flow from the website
- External users (who came through chapters 1–3) find the tool as a natural next step from the leaderboards
- Word of mouth does the heavy lifting. No ad spend, no launch event.

**Connects to Chapter 5:** "This ensemble is great. What if we all shared our best configurations?"

---

### Chapter 5 — Community Can Win

**Thesis:** If we all work together, we can find the best ensembles for every task. People helping people.

**Target audience:** Persona 1 (growing community)

**What this is:**
- Community-created ensembles. People discover, test, and share ensemble configurations.
- Shared url4s — human-readable URLs encoding specific ensemble setups that anyone can try.
- Collaborative leaderboard improvement — the community collectively pushes the frontier.
- The product becomes about the community, not about screamingface. Like HuggingFace — "it never became about Hugging Face, it's always about the people uploading to help each other out."

**Content types:**
- Community-submitted ensemble configs on the leaderboard
- "Here's what the community found this week" roundups
- Featured url4s — interesting ensemble configurations people have shared
- User stories, community spotlights

**What the product does here:**
- Upload your own url4s
- Investigate different ensemble combinations
- Compare community-submitted ensembles against commercial models
- Grassroots "looking out for ourselves" against providers who are taking us for a ride

**What success looks like:**
- The community is self-sustaining — people submit ensembles without prompting
- The product is valued because of the community, not just the tool
- The narrative shifts from "screamingface is a tool" to "screamingface is where people help each other get better AI for less money"

**Connects to Chapter 6:** Community traction attracts attention from press, institutions, bigger players.

**Staffing note:** Samir may be a natural fit as a "community can win" lead — getting the research community to contribute ensembles, publish papers, keep screamingface at SOTA.

---

### Chapter 6 — Beta / Coming of Age

**Thesis:** This is real now. The community proved it. Institutions and press are paying attention.

**Target audience:** Persona 1 + beginning of Persona 2 (thought leaders, journalists, policy)

**What this is:**
- The product matures. More serious design, more features, more stability.
- Endorsements from recognized players — featured in Wired, discussed by Karpathy, etc.
- Institutional credibility. "Used by X researchers. Cited in Y papers."
- This is where polish starts to make sense — the community signal is the authenticity proof, not the scrappy website.

**Content types:**
- Press coverage, interviews, podcast appearances
- Case studies from community usage
- Research papers co-authored with community members
- The website can now be more polished because authentic signal (community activity, GitHub stars, press coverage) provides the credibility that design previously couldn't

**What success looks like:**
- Press coverage in outlets Persona 1 reads (Hacker News front page, Simon Willison's blog, Wired)
- Institutional adoption — research labs, companies using it internally
- The brand is established enough to support the private data pivot

**Connects to Chapter 7:** "OK, ensembles are great for public models. But what about all the information AI can't access?"

**Staffing note:** Coming of age likely needs someone focused on press/journalist relationships, getting features, playing the media game.

---

## Private Data Cycle (Repeat)

The same three-chapter problem campaign repeats, but now focused on private data instead of public model selection.

### Chapter 7 — Market Blindness (Private Data)

**Thesis:** AI tools hallucinate because they lack access to private, paywalled, and proprietary information. You don't know how much accuracy you're losing.

**Target audience:** Persona 1 + Persona 2

**The problem we're highlighting:**
- AI models don't know about today's news behind paywalls
- They don't have access to private scientific journals, proprietary databases, internal docs
- They hallucinate when asked about information they don't have — and users can't always tell
- New leaderboards prove this: test models on questions that require paywalled/private information, watch them fail

**Content types:**
- New leaderboard category: "How well does your AI do on questions requiring private data?" (news accuracy, scientific accuracy behind paywalls, etc.)
- Blog posts: "Your AI is lying to you about [specific domain] because it can't read [specific paywalled source]"
- The Karpathy framing: LLMs are the "cognitive core" — good at reasoning, bad at being encyclopedias. The intelligence is in the data, the model is more of a formatting layer. (Don't say the quiet part loud. Let the data suggest it.)

**What success looks like:**
- People realize their AI tools have a massive blind spot
- Demand building for better data access
- Sets up the same emotional progression as chapters 1–3 but for a different problem

---

### Chapter 8 — Wasted Resources (Private Data)

**Thesis:** Hallucinations cost you time, money, and accuracy. You're paying for AI that's confidently wrong about things behind paywalls.

**Target audience:** Persona 1 + Persona 2

**The problem we're highlighting:**
- Every hallucination costs you something — time to verify, time to redo, wrong decisions made on bad information
- You're relying on a model for intelligence, but the intelligence is actually in the data it references — and it doesn't have the good data
- Quantifiable waste: "X% of responses on [domain] contain hallucinations that would be eliminated with access to [source]"

**Content types:**
- Hallucination rate comparisons: with vs. without access to private data sources
- Cost-of-hallucination analyses
- Continue feeding chapters 1–3 and 7 content

---

### Chapter 9 — Inconvenient (Private Data)

**Thesis:** Getting private data into AI is hard. Existing solutions are clunky, insecure, or vendor-locked.

**Target audience:** Persona 1 + Persona 2

**What we're introducing:**
- The observation that private data access would solve the accuracy problem, but doing it is a pain
- Privacy concerns, security concerns, format concerns, access concerns
- Sets up demand for a convenient, secure solution

**Connects to Chapter 10:** "What if there was a way to give your AI access to private data without giving up control of it?"

---

### Chapter 10 — Gamma / Authentic Data Gates

**Thesis:** Here's a tool that lets you plug private data into your AI ensemble securely. Same scrappy energy as the original tool launch.

**Target audience:** Persona 1 + Persona 2 + institutions

**What this is:**
- Data proxies / data gates — mechanisms for making private data queryable by AI without copying it or centralizing it
- Sergei's "Second Brain" framing: it's your personal knowledge base that AI can query. (Underneath: it's files in a folder that others could pay to query against, but frame it as personal empowerment, not marketplace.)
- This is where screamingface connects directly to OpenMined's core mission: secure computation across siloed data, attribution-based control, the whole thesis.

**Connection to ABC thesis:**
- Deep Voting (Chapter 2 of ABC): source-specific parameters stay separate until prediction time. Users weight which sources they trust. Providers can withdraw contributions.
- Network-Source AI (Chapter 3 of ABC): data owners enable some uses without enabling others. No copies leave the owner's control.
- Credit sharing as the bridge: a developer sharing tokens with a friend is structurally the same pattern as a training data contributor receiving compensation when their data influences output.

**What success looks like:**
- The community that was built through chapters 1–9 now has a tool that connects to OpenMined's deeper mission
- "Gateway drug" thesis proves out — ensemble community naturally evolves into private data / attribution community
- The bets across OpenMined (Network Source AI, BioVault, Creators subnet, etc.) can plug into screamingface's leaderboards and demonstrate their value

---

## Key Principles (Cross-Chapter)

1. **Observational, not persuasive.** We don't invent problems or pitch solutions. We collect data and display it. People follow the natural incentives.

2. **The Dolly Parton effect.** "It takes a lot of money to look this cheap." Intentional scrappiness signals authenticity. Polished = outsider. Scrappy = insider.

3. **Chapterapters are taps, not releases.** Each chapter starts producing content and keeps producing. Chapter 1 content continues even when we're deep into chapter 5. Staffing should reflect this — dedicated people per chapter, not one team context-switching.

4. **Individual → organization → independent brand.** Content starts from Trask as a person, transitions to OpenMined, then to screamingface as its own thing. Individuals are more authentic than companies.

5. **Git history is part of the performance.** Work in private repos. Push intentional history to public. The commit log tells a story too.

6. **Community forward.** The product is never about us. It's about people helping people. Like HuggingFace — the platform is the stage, the community is the show.

7. **The truth is on our side.** We don't have to persuade anyone. We just have to get the obfuscation out of the way and let people chase the natural incentives.

8. **Don't say the quiet part loud.** "AI is a formatting layer, intelligence is in the data" — if you state it directly, people reject it. Show the data and let them arrive at it themselves.

---

## Competitive Awareness

Engagement opportunities in the market blindness / ensemble space should be flagged to Trask. Example: a LinkedIn post about someone open-sourcing an ensemble tool (Code Fleet) — these are not threats, they're co-marketing. For chapters 1–3, there's no competitiveness. We want the conversation happening around us. Engage, don't compete.

---

## Timeline Estimate

Chapters 1–5 represent "a couple of months of work at least, if we're really cooking hard" (Trask, March 2026). The private data cycle (7–10) is further out and depends on how the first cycle lands.

---

*Derived from team huddle, March 17, 2026. Participants: Trask, Kyle, Bennett, Kevin.*
*Reference: narrative-funnel-screamingface-url4-abc.md, persona-audience-1.md, website-copy.md*
