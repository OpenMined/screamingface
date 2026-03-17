# Persona Audience 1 — The Technical Developer / AI Benchmark Enthusiast
**Type:** External
**Priority:** P0 (primary launch target)

---

## Who They Are

This is the person who checks Hacker News before checking email. They're a software engineer, ML practitioner, or AI-adjacent developer — likely 25–40, educated to at least a bachelor's level in CS or engineering, working in tech (often at a startup or in a research-adjacent role), and earning well into six figures.

The actual population of people who care about benchmarks, local models, and token efficiency is more diverse than the stereotypical picture — it includes women engineers, researchers from underrepresented backgrounds, and internationally-based developers who follow cost-efficiency closely. Designing for the realistic full audience, not the caricature, is both the right call and strategically smart for a tool built under OpenMined's values. Diversity should be present and felt in how we present the product — understated and genuine, never loud or performative.

They are not a passive consumer of AI. They *run* models. They *compare* benchmarks. They argue in comment threads about whether MMLU is overfitted. They have a Claude subscription and a Gemini API key and they're annoyed that their token budget runs out every week. When they find a tool that genuinely makes them faster, they tell people. When they smell marketing BS, they close the tab in under five seconds.

---

## Two Sub-Groups Within This Audience

### Benchmark Doers (smaller, more influential)
These are the people actually running evals, publishing results, and forming the signal. They influence the larger crowd. Reproducibility, open methodology, and verifiable data matter enormously to them. If screamingface can win these people, the rest follows.

### Benchmark Followers (larger, socially motivated)
They track the hype signal — following @karpathy, reading HN, catching discourse on r/MachineLearning. They're not running evals themselves, but they respond to what the Doers validate. They won't install something that smells unproven, but they will install something that their trusted sources have vouched for.

---

## Key Psychographic Traits

- Deeply skeptical of hype; responds to *evidence*, not adjectives
- Proud of their toolchain and happy to tweak it
- Motivated by being early — they want to find the next thing before it's mainstream
- Often resource-constrained on tokens despite high technical ability
- Values open source, transparency, and scrappiness
- **Politically:** Not uniformly libertarian-techno-optimist (that's more specifically a US/Silicon Valley skew). This is a global audience with varied political views — the common thread is pragmatism, not ideology.

---

## How They Interpret Hype and Marketing Signal

They don't like empty hype — but they do need *some* kind of signal. The key is that the signal must be self-aware, verifiable, and grounded. "You can run this yourself" is the gold standard proof.

They read marketing through a few archetypes:

- **The Corporate** — Perfect, high-gloss, polished. They recognize quality but feel kept at arm's length. Inaccessible by design.
- **The Startup with Power** — Popular, scrappy, fast-moving. But this space is full of grifters, so trust must be earned, not assumed.
- **The Individual Robin Hood** — A hero operating at their level: powerful, small, on your side. This is the most aspirational archetype. Screamingface should lean here.

The goal: feel like the smart, principled outsider who built something better than the big players — and can prove it.

---

## Where They Gather Online

### Primary Homes

**Hacker News** — The most important single destination. "Show HN" posts for dev tools live or die here based on whether the claims hold up. A successful HN thread is the marketing plan.

**r/MachineLearning** — Over 2.8 million subscribers. High-quality, academic-leaning. This is where serious benchmark discussions happen.

**r/LocalLLaMA** — Critical for screamingface specifically. Obsessed with running models locally, cost efficiency, and benchmarking personal setups. Near-perfect overlap with screamingface's Ollama integration and local-first approach.

**r/ClaudeAI, r/ChatGPT, r/Aider, r/CursorAI** — Direct-access communities for the exact CLI tools screamingface wraps.

### Discord Servers
- **Hugging Face Discord** — open-source ML, model sharing, researchers
- **Anthropic's Claude Discord** — Claude power users and API builders
- **OpenAI Discord** — 130k+ members, heavy developer presence
- **AI Village** — security-focused, hackers + AI researchers

### Other Watering Holes
- **Simon Willison's blog** — The single most trusted independent voice on AI tools. If he covered screamingface, adoption would follow.
- **Lobsters** — Like HN but more CS-focused, invite-only culture
- **Twitter/X** — Accounts like @karpathy, @simonw, @emollick matter here
- **Kaggle** — Competition and benchmark-focused; highly relevant given the leaderboard angle

---

## Their Cultural World

**What they read and watch:**
- Simon Willison's blog (power-user AI coverage, no vendor allegiance)
- Andrej Karpathy's posts and videos (deep technical credibility)
- Arxiv papers (skim abstracts and figures, sometimes read the whole thing)
- Jeff Geerling's blog/YouTube (hardware, self-hosting, Raspberry Pi culture)
- The Pragmatic Engineer newsletter

**What they love:**
- Open source everything
- Benchmarks with reproducible methodology
- Command line over GUI
- Paying once vs. SaaS subscriptions forever
- The idea of "outsmarting" a bigger company with a clever system
- Saving money without sacrificing quality

**What they hate:**
- Vague claims ("cutting edge AI") without receipts
- Products that phone home or black-box their behavior
- Being marketed to like they're a consumer
- Token limits (deeply personally)
- Hype that doesn't survive scrutiny

**Cultural touchstones:**
- The Bitter Lesson (scaling compute wins in the long run)
- "Open weights" as a value system
- Goodhart's Law applied to AI benchmarks
- The ongoing Claude vs. GPT vs. Gemini wars

---

## Tools They Use (and Love the Landing Pages Of)

These are products with websites that resonate with this audience — design references for screamingface.

**Ollama** — Local model runner screamingface wraps directly. Minimal site — almost no design, and that *is* the design. The install command IS the hero image. ScreamingFace's install flow should take this cue directly.

**Claude Code / Anthropic** — Clean, capability-forward, developer-respecting. Already used and trusted by this audience. Lean into the Claude/Gemini/Codex brand recognition — these aren't just integrations, they're credibility by association.

**Cursor** — Dark-mode-forward. Hero shows the actual product in action. Leads with capability demonstration, not marketing copy. Show, don't tell.

**Aider** — Direct competitor-adjacent CLI tool. Homepage leads with benchmark scores showing it outperforms competitors. No marketing fluff. Screamingface's leaderboard chart is the equivalent — it's the entire argument.

**Supabase** — "Open source Firebase alternative." Anchoring to a known thing works. OSS signal is real and loud.

**PostHog** — Open-source analytics, brutalist-adjacent design, transparent pricing, visible GitHub star count. Raw numbers (stars, benchmark scores) build trust faster than words.

**SST** — Timeline-style "how it works" flow. Follows the user's natural journey to the CTA.

### On Visual Style
**Do not get too close to Linear.** Everyone has already copied that minimal dark aesthetic — it's become corporate by virtue of ubiquity. Screamingface needs to feel like the Robin Hood, not the premium startup. Find a visual voice that's distinct.

---

## Implications for the ScreamingFace Homepage

1. **The benchmark number, above the fold, immediately.** Not "achieves SOTA" — the actual score, vs. the competition. That's the Aider model.

2. **The install command as a hero element.** The curl command isn't a detail — it's the product promise made visual. Treat it like the headline.

3. **No marketing adjectives.** Words like "powerful," "seamless," or "cutting-edge" will cost trust immediately. Replace with specifics.

4. **Transparency signals.** GitHub link, open methodology, visible how-it-works. These are credibility assets, not afterthoughts.

5. **The leaderboard chart as the centerpiece.** This audience reads charts. An interactive, well-labeled chart comparing accuracy-vs-cost across models is more persuasive than any copy.

6. **A step-by-step install flow that's honest about what happens.** They want to know: what gets installed, where, what it calls home to (or doesn't). Don't hide it.

7. **Social proof that grows with the product.** In early stages, the OpenMined brand, visible GitHub activity, and "used by our own team daily" framing carry more weight than a fake quote. GitHub stars, team usage, and benchmark reproducibility *are* the social proof.

---

*Persona Audience 1 — March 2026. Incorporates v1 report content and review updates.*
