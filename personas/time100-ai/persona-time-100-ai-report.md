# Time 100 AI 2025 — Cohort Analysis
**Date:** March 2026
**Source list:** https://time.com/collections/time100-ai-2025/

---

## About This Cohort

TIME's 100 most influential people in AI 2025 spans frontier lab CEOs, academic researchers, policy officials, labor advocates, artists, roboticists, a pope, and an anonymous jailbreaker. It skews Western and institutional — meaningful representation from Africa, Asia, and Latin America exists, but primarily through figures who engage with global institutions rather than ground-level communities. What the list reveals about AI's current moment: power is concentrated but contested. The builders have the most resources, the safety researchers have the most urgency, the policy officials have the most uncertainty, and the critical theorists have the most patience.

---

## Methodology

**Source material:** TIME 100 AI 2025 individual profiles, supplemented by web research for each person covering their public statements, published research, organizational work, and known positions on AI development, safety, and policy. Research conducted March 2026.

**Approach:** For each person, we built a quick persona answering four questions: Who are they and what is their lens on AI? What is their relationship to AI tools — are they a builder, researcher, critic, regulator, or user? How would they likely react to screamingface specifically? And what is the key tension or open question between their worldview and screamingface's value proposition?

**Framing:** Reactions to screamingface are synthesized from each person's known positions and public record. They are informed approximations, not verified statements or direct quotes. No one on this list was contacted. These are directional reads useful for positioning and prioritization, not for attribution.

**Coverage:** All 100 people were researched. Thinkers (25) and Shapers (27) received full individual persona files. Leaders (23) and Innovators (24) received individual files for the most relevant subset; others were summarized in group notes where domain overlap with screamingface was minimal.

**Limitations:** The list's Western-institutional skew mirrors screamingface's own current positioning — both have the same blind spot about ground-level developer communities in the Global South, which is worth noting as the product matures.

---

## How This Cohort Divides

The 100 people on this list fall into five groups based on their orientation toward AI and their relationship to a tool like screamingface.

---

### Group 1 — Technical Practitioners (~15 people)

**Who they are:** Researchers, benchmark methodologists, open-source builders, and developer-tools practitioners who engage with AI at the systems level. These are people who have built models, run evals, read documentation, and have strong opinions about evaluation design. They tend toward intellectual honesty over institutional loyalty. They're early adopters who move technical culture — when they endorse something, other practitioners notice.

**How they think about AI:** Through the lens of evidence, reproducibility, and what actually works. They're skeptical of hype (they've seen too many overpromised benchmarks) but genuinely curious about new approaches. They care about methodology as much as outcomes. Open-source is a value, not just a preference — it means they can check the work.

**Their orientation to screamingface:** Natural fit. This is the audience the product was built for and the group most likely to evaluate it rigorously, adopt it early, and become credible advocates. The benchmark story resonates immediately; the open-source architecture earns trust. If the claims hold up to their scrutiny, their endorsement carries weight precisely because they're not easy to impress.

**Notable individuals:**

- **David Ha (Sakana AI)** — His founding thesis at Sakana — small collaborative models outperform monolithic large ones — is the ensemble argument. The deepest intellectual alignment on the list.
- **Edwin Chen (Surge AI)** — Built training data infrastructure for Anthropic, OpenAI, and Google. The most technically credible evaluator of screamingface's benchmark claims. His judgment on whether the methodology is sound would carry significant weight.
- **Jared Kaplan (Anthropic)** — Co-author of Scaling Laws. Would push on the deepest technical question: is ensemble routing a new scaling axis, or just picking the winner from a fixed pool?
- **Pliny the Liberator** — The most adversarial lens in this group. Would immediately probe the routing layer as an attack surface. Either a critical vulnerability finder or the fastest red-teaming partnership available — depending on how the relationship is handled.
- **Alan Descoins (Tryolabs)** — 15 years of production AI deployments. Would test screamingface against real client workloads, not synthetic benchmarks. The most calibrated production skeptic on the list.

---

### Group 2 — Infrastructure & Capital (~10 people)

**Who they are:** Hardware executives, platform-layer CEOs, and large-scale investors who operate at the compute, chip, and capital layer. They think in GPU clusters, power contracts, sovereign funds, and chip architectures. They track developer adoption as a leading indicator for compute demand, but they don't engage with individual developer tools as strategic priorities.

**How they think about AI:** At the infrastructure level — who controls the physical substrate, who builds the platforms that developers depend on, and what compute economics look like at scale. They're bullish on AI broadly and largely agnostic about which software layer wins, provided the underlying hardware and platform businesses capture value. They have long time horizons and high tolerance for volatility.

**Their orientation to screamingface:** Commercially positive, tactically indifferent. More inference demand is good news at their level. The Ollama angle (local inference on edge hardware) is genuinely interesting for chip companies whose thesis is that AI moves to the device — it's directionally aligned. But screamingface is too far up the stack to occupy their attention.

**Notable individuals:**

- **Cristiano Amon (Qualcomm)** — Strongest interest in this group. His entire thesis is that edge AI on Snapdragon wins; the Ollama integration in screamingface (route to local models on-device when available) is exactly the developer experience he'd want to exist. Most likely in this group to mention screamingface publicly.
- **Jensen Huang (Nvidia)** — Structurally positive: more model calls = more GPU demand. Indifferent to which software orchestrates it.
- **Andy Jassy (Amazon)** — Would note that AWS Bedrock already does multi-model routing at enterprise scale and wonder why developers wouldn't just use Bedrock. Represents the "enterprise already solved this" objection screamingface needs an answer for.

---

### Group 3 — Domain Practitioners & Creative Thinkers (~30 people)

**Who they are:** The largest and most diverse group — educators, artists, roboticists, healthcare AI builders, defense technologists, domain-specific scientists, film editors, and music producers. They work in AI, but in highly specialized contexts: protein folding, autonomous flight, dolphin vocalization, drug discovery, power grid optimization. General-purpose developer CLIs aren't part of their workflow.

**How they think about AI:** Through the lens of their specific domain. They tend to be more grounded about AI's actual capabilities than techno-optimists — they've spent years dealing with the gap between AI's promises and its performance in high-stakes or creative contexts. They care about real-world validation, domain specificity, and the human relationships that AI either supports or disrupts. Many are deeply mission-driven and somewhat skeptical of efficiency-maximization as an end in itself.

**Their orientation to screamingface:** Warm, curious, not personally engaged as users. They'd appreciate the open-source ethos and democratization framing — these resonate broadly across people who work on AI for social good, global access, and creative expression. Some connect philosophically (Rick Rubin on the "punk rock" ethos of not needing to pick a model; Refik Anadol on the aesthetics of data flows; Denise Herzing on AI making the previously impossible suddenly possible). But screamingface's primary use case — developer coding productivity — doesn't intersect with their work.

**Notable individuals:**

- **Rick Rubin** — The most unexpected resonance in this group. His "AI is the punk rock of coding" framing maps directly onto screamingface's pitch: you don't need to know which model is best, you just have the idea and the ensemble figures out the rest. His public enthusiasm for Anthropic and vibe-coding would make him a natural evangelist for a general audience.
- **Benjamin Rosman (Witwatersrand / Deep Learning Indaba)** — Represents the global-access perspective from inside the sympathetic camp. His work building ML communities across 47 African countries means his endorsement of screamingface as a genuinely global tool would be contingent on the Ollama integration being first-class and the tool working in bandwidth-constrained environments.
- **Regina Barzilay (MIT)** — The most likely actual user in this group. She writes research code and cares more about reliability than speed — specifically whether ensembles reduce hallucination rates on specialized scientific tasks.

---

### Group 4 — Critical Evaluators (~20 people)

**Who they are:** Safety researchers, AI governance experts, labor advocates, critical theorists, privacy scholars, and journalist-analysts. They engage with AI seriously and often more rigorously than the builders — but through the lens of what could go wrong, who gets harmed, and what the clean UX obscures. They're not opposed to new AI tools; most would see genuine value in screamingface. But they ask the questions that optimistic builders miss.

**How they think about AI:** As a sociotechnical system with embedded choices about who benefits and who bears risk. They read technical documentation as policy documents and press releases as political ones. They're interested in accountability, transparency, and the gap between stated values and actual architecture. Many have spent years watching AI products make well-intentioned promises that turned out to be difficult to deliver — they have calibrated skepticism.

**Their orientation to screamingface:** Substantive engagement with real pushback. They'd identify the gaps that are genuinely unanswered — content policy across models, safety evaluability, data flow and privacy, training data provenance — and push until those questions have real answers. If screamingface can satisfy this group, the product becomes significantly more defensible in policy, enterprise, and press contexts. These are not adversaries; they're the people who make products better by asking hard questions early.

**Notable individuals:**

- **Heidy Khlaaf (AI Now Institute)** — Wrote the Codex safety evaluation framework. Would argue that dynamic routing across models with different safety profiles makes systematic safety evaluation harder, not easier. The routing logic itself needs formal evaluation — this is a specific, actionable gap.
- **Latanya Sweeney (Harvard)** — Would surface the multi-API privacy exposure more rigorously than anyone: what flows to which APIs, under what retention policies, per routing decision? She'd know what a proper data flow documentation looks like and push until it exists.
- **Ed Newton-Rex (Fairly Trained)** — Would push on training data provenance for each model in the ensemble. Open-source routing doesn't change the copyright and licensing questions embedded in the underlying models. He'd want Fairly Trained certification for the whole stack.
- **Joanne Jang (OpenAI)** — Raises the most practically urgent unanswered question: whose content policy governs the ensemble? If Claude, Gemini, and an unconstrained Ollama model are all in the routing pool, what happens when a prompt reaches the most permissive model?
- **Marius Hobbhahn (Apollo Research)** — Asks whether the routing layer is a new attack surface for AI scheming. Can a prompt manipulate routing logic to preferentially select a less safety-restricted model? He'd want to run Apollo evaluations on the routing logic itself.
- **Karen Hao (journalist / "Empire of AI")** — Would frame screamingface as a story about AI power distribution — probably favorably, but with the sharp question: is "open source" meaningful when every model being routed is proprietary?

---

### Group 5 — Strategically Positioned (~10 people)

**Who they are:** Executives and investors whose commercial positions depend on model loyalty and frontier model differentiation. They've built moats around specific AI models — through API relationships, product integrations, portfolio stakes, or policy influence — and screamingface's core premise challenges those moats.

**How they think about AI:** Commercially. They track developer tool adoption closely because developers drive long-term platform stickiness. They're sophisticated about AI capabilities but their primary frame is competitive positioning: who wins, who loses, and where value accumulates in the stack. They're not ideological about open vs. closed; they're practical about what protects their business model.

**Their orientation to screamingface:** Professional curiosity on the surface; competitive calculation underneath. They'd evaluate screamingface primarily as a signal — what does the routing data reveal about their model's relative performance, and does the "no single model wins" narrative hurt their positioning? They wouldn't attack it publicly, but they wouldn't champion it either. The most aligned individuals in this group are those whose models are likely to win routing decisions (Liang Wenfeng / DeepSeek, Mark Zuckerberg / Llama) — for them, screamingface is free distribution.

**Notable individuals:**

- **Sam Altman / Fidji Simo / Chris Lehane (OpenAI)** — Three faces of the same institutional wariness. Altman: intellectually curious, strategically cautious. Simo: would ask whether OpenAI should build this natively into the API tier. Lehane — a political operative paid to protect OpenAI's "frontier model superiority" narrative — would be the most strategically wary; the ensemble premise directly challenges the story he's paid to tell.
- **Liang Wenfeng (DeepSeek)** — Strongest positive interest in this group. DeepSeek's open-weights, efficiency-first models are natural ensemble candidates; screamingface routing to DeepSeek-R1 validates the model and builds adoption. He'd be genuinely interested.
- **Joshua Kushner (Thrive Capital)** — The purest financial lens. His largest bets (OpenAI, Cursor) depend on frontier model providers capturing durable value. The ensemble-as-commodity narrative is structurally adverse to his portfolio thesis.

---

## What This Means for screamingface

### The core audience is right, and it's influential

The Technical Practitioners group — the people who would actually evaluate and endorse screamingface — are exactly the right early audience. They're not the most famous names on this list, but they're the ones who move technical culture. Their endorsement is trusted precisely because they're not easy to impress.

### The credit-sharing story is the most broadly resonant feature

Across all five groups, the single element that provokes genuine curiosity from the widest range of people is the credit-sharing mechanism — not the benchmark claims. Economists (Korinek), creator-rights advocates (Srivastava, Newton-Rex), identity researchers (Blania), attribution experts (Parsons), and labor advocates (Murphy) each see it differently, but it catches attention in a way that "beats SOTA on HLE" doesn't for non-developers. Lead with credits in press, policy, and partnership conversations.

### Three gaps will surface repeatedly from credible voices

**Safety evaluability:** Dynamic routing across models with different safety profiles makes the ensemble harder to formally evaluate than any single model. Khlaaf, Hobbhahn, Ilott, Russell, and Jang would each arrive at this independently.

**Privacy and data flow:** What flows to which APIs, under what retention policies, per routing decision? Unanswered publicly, and it blocks enterprise adoption and policy endorsement.

**The model roster is a geopolitical statement:** The default ensemble (Claude, Gemini, Codex) is US-centric. Xue Lan, Liang Wenfeng, Tijani, Ingabire, Singh, and Chappaz would each notice. Adding DeepSeek-R1 and Mistral as first-class routing options would broaden the coalition substantially.

### Open-source is necessary but not sufficient

Ed Newton-Rex, Milagros Miceli, Paola Ricaurte Quijano, and Karen Hao would each note, from different angles, that open-source routing doesn't resolve training data provenance, embedded power dynamics, or cultural assumptions in the models being routed. These aren't fatal critiques — they're the sophisticated "yes, and" that an honest product team should be able to answer.

---

## Personas by File

Individual persona files are organized in:

```
personas/time100-ai/
  report.md              ← this file
  personas/
    thinkers/            ← 25 individual files
    shapers/             ← 27 individual files
    leaders/             ← selected individual files
    innovators/          ← selected individual files + remaining-innovators.md
```

---

*Research conducted March 2026. Based on publicly available information, TIME 100 AI 2025 profiles, and secondary sources. Individual personas are synthesized from research and should be treated as informed approximations, not direct quotes or verified positions.*
