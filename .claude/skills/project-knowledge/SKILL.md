---
description: ScreamingFace product & domain knowledge — what the product is, the team, and the key concepts (url4, Enclave, Ensemble, SOTA, Gates). Use for product/domain context. For repo structure, CI, ownership, and the PR/merge process, use the working-in-this-repo skill instead.
user_invocable: true
---

# ScreamingFace — Project Knowledge

## Product

ScreamingFace is an AI ensemble system that routes coding CLI prompts through the best available models (Claude Code, Gemini CLI, Codex, Ollama) to beat SOTA benchmarks. Users install it locally and can share AI credits with friends. Built by OpenMined.

## Team

- **Bennett** — Design lead (branding, visual design for website and app)
- **Sergey** — Server architecture, plugin system (`apps/server/`), devops
- **Kevin** — App backend, url4 protocol specification/parser/editor
- **Kyle** — Frontend development (static website + local app UI)
- **Trask** — Product owner, daily use/testing/requirements

## Key Concepts

- **url4** — DAG-based protocol encoding AI task chains as human-readable URLs
- **Enclaves** — Secure cloud servers running model runners and cache (CPU-based, auditable)
- **Ensemble** — Combining multiple AI models to achieve better accuracy than any single model
- **SOTA** — State of the Art benchmark accuracy scores the system aims to beat
- **Gates** — Cloud UI for token sharing; users create "models" and share access with rate limits

## Tech Stack

- React + Vite, Tailwind CSS, shadcn/ui — frontend
- Recharts / Chart.js / D3 — data visualization
- TypeScript — frontend language
- Next.js — cloud webapp and marketing site
- FastAPI (Python) + uv — plugin-based server (`apps/server/`)

## App Screens

- **Settings** — Configure which AI models are in the ensemble
- **Spend** — View/manage token usage and cost across all models
- **Eval Studio** — Run benchmark evals, duplicate SOTA results with available models
- **Cache/Log** — Browse/search/filter cached AI queries, delete entries, view stats


# ScreamingFace — Target Persona Research Report
### The Technical Developer / AI Benchmark Enthusiast

---

## Who They Are

This is the person who checks Hacker News before checking email. They're a software engineer, ML practitioner, or AI-adjacent developer — likely 25–40, educated to at least a bachelor's level in CS or engineering, working in tech (often at a startup or in a research-adjacent role), and earning well into six figures. While current demographic data shows this space skews male, the actual population of people who care about benchmarks, local models, and token efficiency is meaningfully more diverse — including women engineers, researchers from underrepresented backgrounds, and internationally-based developers who follow cost-efficiency closely. Designing for the realistic full audience, not just the stereotypical one, is both the right call and strategically smart for a tool built under OpenMined's values. They care deeply about **tools**, **efficiency**, and being **early** to things that matter.

They are not a passive consumer of AI. They *run* models. They *compare* benchmarks. They argue in comment threads about whether MMLU is overfitted. They have a Claude subscription and a Gemini API key and they're annoyed that their token budget runs out every week. When they find a tool that genuinely makes them faster, they tell people. When they smell marketing BS, they close the tab in under five seconds.

**Key psychographic traits:**
- Deeply skeptical of hype; responds to *evidence*, not adjectives
- Proud of their toolchain and happy to tweak it
- Motivated by being early — they want to find the next thing before it's mainstream
- Often resource-constrained on tokens despite high technical ability
- Values open source, transparency, and scrappiness
- Politically: skews libertarian-techno-optimist, pragmatically pro-AI

---

## Where They Gather Online

### Primary Homes

**Hacker News** ([news.ycombinator.com](https://news.ycombinator.com))
The most important single destination. This is where the product *has* to survive scrutiny. "Show HN" posts for dev tools live or die here based on whether the claims hold up. The audience is deeply allergic to marketing fluff and actively enjoys poking holes in things. A successful HN thread is the marketing plan.

**r/MachineLearning** ([reddit.com/r/MachineLearning](https://reddit.com/r/MachineLearning))
Over 2.8 million subscribers. High-quality, rigorous, academic-leaning. This is where serious benchmark discussions happen. Getting a post here means reaching researchers and ML engineers who actually care about SOTA claims.

**r/LocalLLaMA** ([reddit.com/r/LocalLLaMA](https://reddit.com/r/LocalLLaMA))
Critical for screamingface specifically. This community obsesses over running models locally, cost efficiency, and benchmarking personal setups. The overlap with screamingface's Ollama integration and local-first approach is near-perfect.

**r/ClaudeAI, r/ChatGPT, r/Aider, r/CursorAI**
Subreddits where developers discuss the exact CLI tools screamingface wraps. These are direct-access communities of the target user.

### Discord Servers
- **Hugging Face Discord** — open-source ML, model sharing, researchers
- **Anthropic's Claude Discord** — Claude power users and API builders
- **OpenAI Discord** — 130k+ members, heavy developer presence
- **AI Village** — security-focused, hackers + AI researchers; relevant for the HN-security-scrutiny crowd

### Other Watering Holes
- **Simon Willison's blog** ([simonwillison.net](https://simonwillison.net)) — The single most trusted independent voice on AI tools. If he wrote about screamingface, adoption would follow.
- **Lobsters** ([lobste.rs](https://lobste.rs)) — Like HN but more CS-focused, invite-only culture
- **Twitter/X** — Still the place where AI researchers announce things and dunk on each other. Accounts like @karpathy, @simonw, @emollick matter here.
- **Kaggle** — Competition and benchmark-focused; highly relevant given screamingface's leaderboard angle

---

## Their Cultural World

**What they read and watch:**
- Simon Willison's blog (power-user AI coverage, no vendor allegiance)
- Andrej Karpathy's posts and videos (deep technical credibility)
- Arxiv papers (they actually read them, or at least skim the abstract and figures)
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

These are products with websites that resonate with this audience. Each is a design reference for screamingface. Note: the tools listed here are drawn directly from the development plan (Claude Code, Gemini CLI, Codex, Ollama) and the broader ecosystem those tools live in — these aren't guesses, they're the exact stack this persona already uses daily.

### [Ollama](https://ollama.com)
The local model runner that screamingface wraps directly. Minimal site — almost no design, and that *is* the design. The single most important element on the page is `curl -fsSL https://ollama.ai/install.sh | sh`. **Lesson: the install command IS the hero image for this audience.** ScreamingFace's own install flow should take this cue directly.

### [Anthropic / Claude Code](https://claude.ai/code)
One of the four core models in the ensemble. The Claude Code landing presence is clean, capability-forward, and developer-respecting. This audience already uses it and trusts it. **Lesson: lean into the Claude/Gemini/Codex brand recognition — these aren't just integrations, they're credibility by association.**

### [Cursor](https://cursor.com)
The current darling of the AI coding world. Dark-mode-forward. Hero shows the actual product in action — no stock photos, no vague promises. They lead with *capability demonstration*, not marketing copy. **Lesson: show, don't tell.**

### [Aider](https://aider.chat)
Direct competitor-adjacent CLI tool. Minimal site. The homepage leads with benchmark scores showing it outperforms competitors. No marketing fluff at all. **Lesson: screamingface's leaderboard chart is the equivalent of Aider's benchmark table — it's the entire argument.**

### [Supabase](https://supabase.com)
"Open source Firebase alternative" — the anchoring framing that made them famous. Dark theme, code snippets front and center, GitHub stars visible. Trusted because the OSS angle is real. **Lesson: anchoring to a known thing works; make any open-source signal loud.**

### [Linear](https://linear.app)
Minimalist power. Sparse design, conversational headline copy, subtle motion showing the product. A benchmark for communicating speed and quality through design alone. **Lesson: negative space is trust for technical audiences.**

### [PostHog](https://posthog.com)
Open-source analytics with a brutalist-adjacent design that leans into its developer identity. Transparent pricing, visible GitHub star count. **Lesson: raw numbers (stars, benchmark scores) build trust faster than words.**

### [SST](https://sst.dev)
Uses a timeline-style "how it works" flow that's more engaging than the typical step-1-2-3. Follows the user's natural journey to the CTA. **Lesson: show the journey, not just features.**

---

## Implications for the ScreamingFace Homepage

Based on all of the above, here's what this persona needs to see to convert:

1. **The benchmark number, above the fold, immediately.** Not "achieves SOTA" — the actual score, vs. the competition. That's the Aider model.

2. **The install command as a hero element.** The curl command isn't a detail — it's the product promise made visual. Treat it like the headline.

3. **No marketing adjectives.** Words like "powerful," "seamless," or "cutting-edge" will cost trust immediately. Replace with specifics.

4. **Transparency signals.** GitHub link, open methodology, visible how-it-works. These are credibility assets, not afterthoughts.

5. **The leaderboard chart as the centerpiece.** This audience reads charts. An interactive, well-labeled chart comparing accuracy-vs-cost across models is more persuasive than any copy.

6. **A step-by-step install flow that's honest about what happens.** They want to know: what gets installed, where, what it calls home to (or doesn't). Don't hide it.

7. **Social proof that grows with the product.** Named endorsements from recognizable researchers or devs aren't available yet — and that's fine. In the early stages, the OpenMined brand, visible GitHub activity, and honest "used by our own team daily" framing carry more weight than a fake quote. As real users accumulate, their words become the asset. For now: GitHub stars, team usage, and benchmark reproducibility *are* the social proof.

---

*Report v1 — March 2026. Prepared for screamingface.ai marketing and UX iteration.*