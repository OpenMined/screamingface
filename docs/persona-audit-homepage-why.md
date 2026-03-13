# Persona Audit: Homepage & /why Page
**Date:** March 2026
**Reviewed against:** Persona Weighting Guide (personas/weighting-guide.md)

---

## Homepage (/)
**Primary audience:** Audience 1 — Technical Developers & Benchmark Enthusiasts
**Secondary audience:** Audience 2 — Thought Leaders & Policy Champions

---

### What Audience 1 Would Like

**The hero works.** "SOTA on your laptop." is direct, provable, and avoids marketing adjectives. The persona says this audience "closes the tab in under five seconds" on BS — this headline survives that test.

**"Skeptical?" is exactly right.** Linking immediately to benchmark scores and inviting them to "run the evals yourself" mirrors the Aider homepage pattern the persona specifically calls out. Self-verifiable claims are the gold standard for this audience.

**The install command as a visual element.** The terminal-style block with `curl -fsSL https://screamingface.ai/install | sh` follows the Ollama pattern the persona identifies as a design reference. The install command IS the product promise.

**The 3-step install flow is honest.** "Nothing is uploaded during setup," "reads your PATH and existing configs," "we route every prompt to whichever model scores best" — this tells them what happens without hiding anything. The persona demands this transparency.

**"No new workflow. No new subscription."** Hits two pain points directly: tool-switching friction and subscription fatigue.

**GitHub link in nav and as secondary CTA.** Open source signal is prominent. The persona says GitHub visibility is a credibility asset, not an afterthought.

**Reproducibility footnote under the chart.** "These scores are reproducible. Evaluation code is open source — run it yourself." This is trust currency for Audience 1.

---

### What Audience 1 Would Dislike or Question

**The benchmark data is placeholder.** The chart literally says "placeholder data" in a badge. This audience reads charts — the chart IS the argument. Placeholder data makes the entire SOTA claim unverifiable, which is the one thing this audience won't tolerate. This is the highest-priority fix on the homepage.

**The model names look dated.** "Claude 3.5 Sonnet," "GPT-4o" — Audience 1 tracks model versions obsessively. If these aren't the current best versions, the chart loses credibility. They'll wonder if the ensemble was tested against straw men.

**Only one benchmark.** The persona's "Benchmark Doers" sub-group wants to see methodology across multiple evals, not just one. A single HLE chart is a start, but this audience will want more before they're convinced. At minimum, acknowledge that more benchmarks exist and are coming.

**The "Why open matters" section is misplaced for this audience.** Privacy, Copyright, Hallucination, Bias, Value Alignment, Democracy — these are societal stakes, which is Audience 2 messaging. Audience 1 cares about: does it work, how fast is it, and what does it cost. This section reads like it's talking to someone else, and it is. It's fine as a bridge to /why, but it shouldn't be the penultimate section before the email capture. It cools down the developer momentum built by the install flow.

**No cost or token information anywhere.** The persona specifically says this audience is "resource-constrained on tokens despite high technical ability." The credit-sharing feature — arguably the most broadly resonant element per the Time 100 report — isn't mentioned at all. The dev plan says Week 2 adds an accuracy-vs-cost graph. That's good, but even before the graph, some mention of token efficiency or credit sharing would land.

**No speed information.** The dev plan says "works better, not noticeably slower." That reassurance matters. Ensembling implies latency overhead — Audience 1 will immediately wonder about it. Addressing it proactively (even briefly) prevents a common objection.

**No explanation of how routing works.** "We route every prompt to whichever model scores best on the task" is the one-liner, but Audience 1 will want to know: how? Is it a classifier? Majority vote? Bandit? The persona says they're proud of their toolchain and want to understand what they're running. A "How it works" section (even 2-3 sentences + a link) would earn trust.

**The collaborators section is all fake.** Placeholder logos with fabricated descriptions (ArXiv paper, HuggingFace blog, Wired press) are worse than no social proof for this audience. They will check these links. Fake social proof destroys trust instantly. The persona says: in early stages, "OpenMined brand, visible GitHub activity, and 'used by our own team daily'" carry more weight than fabricated quotes. Show what's real, even if it's small.

**No GitHub stars or activity signal.** PostHog shows star count. Supabase shows contributor count. Raw numbers build trust faster than words for Audience 1.

---

### What Audience 2 Would Think (secondary lens)

The homepage isn't for them, and that's correct. The "Why open matters" section and "Read about the societal stakes →" link is the bridge to /why. That works.

However: if an Audience 2 person lands on the homepage directly (via a link from a journalist or colleague), the developer-heavy framing might lose them before they find the bridge. Consider whether the /why link should be more prominent — perhaps in the nav, not just buried in a section near the bottom.

---

### Suggested Changes — Homepage

| Priority | Change | Rationale |
|----------|--------|-----------|
| **Critical** | Replace placeholder benchmark data with real scores | The chart is the entire argument. Placeholder data makes the SOTA claim empty. |
| **Critical** | Remove or honestly label the collaborators section | Fake social proof is worse than none. Show real signals (GitHub activity, team usage, OpenMined brand) or remove until real collaborations exist. |
| **High** | Add cost/token mention | Credit sharing and token efficiency are missing entirely. Even a line in the hero subhead or a new section. |
| **High** | Add a "How it works" section (brief) | Routing logic needs at least a high-level explanation. Audience 1 wants to understand what they're running. |
| **High** | Update model names to current versions | Dated model names undermine the benchmark credibility. |
| **Medium** | Add speed reassurance | "Not noticeably slower" or actual latency data. Addresses a predictable objection. |
| **Medium** | Move "Why open matters" below email capture or make it lighter | It breaks developer momentum. The /why link can be a simpler bridge without the full stakes grid. |
| **Medium** | Add /why to the nav | Audience 2 visitors who land on homepage need to find the /why page quickly. Currently only linked near the bottom. |
| **Low** | Add GitHub activity signal | Star count, contributor count, or recent commit activity. Raw social proof for Audience 1. |
| **Low** | Tease additional benchmarks | "HLE is one of N benchmarks we've tested. Full leaderboard coming soon." |

---

## /why Page
**Primary audience:** Audience 2 — Thought Leaders, Journalists & Policy Champions
**Reference cohorts:** ABC Citations, Time 100 AI

---

### What Audience 2 Would Like

**"An open letter" framing.** Editorial, principled, institutional. The persona says this page should "feel different from the developer homepage" and it does. The tone shift is right.

**The 2-year window argument.** Urgency without alarmism. "We are in a narrow window" is the core message for this audience, and it's the opening line. The stat callout ("~2 yrs") makes it visual and concrete.

**The government digitization analogy.** The persona specifically says "History rhymes — the digitization analogy is legible and non-technical." This section nails it. Public records, libraries, civic data → vendor lock-in. The parallel is clear and doesn't require technical literacy.

**"The proof exists" with link back to homepage.** Good bridge. Audience 2 needs to know this isn't theoretical, but they don't need the technical details on this page.

**attribution-based-control.ai link.** Gives serious readers a place to go deeper. The persona identifies this as the intellectual anchor for the policy case.

**"Get involved" targeting researchers, journalists, and policy advocates.** The right CTA for the right audience. It asks for participation, not just an email.

**OpenMined attribution.** Institutional backing matters to this audience more than Audience 1.

---

### What Audience 2 Would Dislike or Question

**The stakes grid is too thin.** The same 6 one-liners appear on both the homepage and /why page. On the homepage (Audience 1 secondary), they're fine as a quick bridge. On this page (Audience 2 primary), they're inadequate. This audience needs substance: Privacy isn't just "institutions contribute data while keeping full control" — it's the data sovereignty question that Carissa Véliz wrote a book about, that Latanya Sweeney has spent her career on. Each of these deserves 2-3 sentences, or at least a more developed treatment than a single line.

**"Democracy: Strength from everything the free market builds together."** This is the wrong frame for Audience 2. These are people who think about public goods, institutional coordination, and democratic governance — not free market dynamics. Policy advocates, journalists covering AI power, and civil society researchers are often explicitly skeptical of "free market" framing. This bullet might actively alienate part of the primary audience. Consider: "Democratic oversight of AI requires infrastructure that no single company controls."

**No names, institutions, or coalition signals.** The persona says Audience 2 engagement goals include "collect logos" and "gather collaborators." The collaborators grid shows the same placeholder logos as the homepage. For Audience 2, seeing institutional affiliations — universities, civil society orgs, policy institutes — is critical. Even listing "We're in conversation with researchers at [institutions]" would be more credible than fabricated partnerships.

**No explanation of what OpenMined is.** "Built by OpenMined" assumes name recognition. Audience 2 may not know OpenMined. One sentence — "OpenMined is a nonprofit building open-source tools for privacy-preserving AI" — would ground the credibility claim.

**"Get involved" is just an email form.** The persona explicitly says this audience wants: "co-author something, join a call, sign a letter." An email field is the lowest-effort engagement. Consider listing specific ways to participate, even if the email form is the actual mechanism. Frame it as collaboration, not subscription.

**The email capture uses homepage copy.** "Early access, benchmark drops, and open beta updates" is developer language (Audience 1). Audience 2 doesn't care about benchmark drops. They care about: coalition updates, policy briefs, co-authorship opportunities, events.

**No author or signatory.** It says "An open letter" but doesn't say from whom. Is this from Andrew Trask? From OpenMined as an organization? Open letters have signatories. Audience 2 will notice this absence — they work in a world where who signs something matters as much as what it says.

**No mention of policy frameworks Audience 2 already tracks.** The EU AI Act, GDPR, executive orders on AI — these are the reference points for this audience. The page makes the public infrastructure argument without connecting it to the regulatory landscape they already navigate.

---

### What the ABC Cohort Would Notice

The ABC report identifies four entry narratives — each championed by different people in the cohort. The /why page currently uses **one** narrative (democracy/public infrastructure) and touches the others only in the stakes grid one-liners. The doors that are missing or underdeveloped:

| Narrative | ABC Champions | Currently on /why page |
|-----------|---------------|----------------------|
| Democracy & public infrastructure | Pasquale, Summerfield, Dafoe, Garfinkel | Yes — this is the main argument |
| Privacy & data rights | Schneier, Véliz, Dwork | One-liner only ("Institutions contribute data while keeping full control") |
| Control & safety | Russell, Bengio | Not addressed |
| Copyright & attribution | Samuelson, Gabriel | One-liner only ("Creator attribution rights survive model training") |

The ABC Group 1 (Governance Architects — Dafoe, Garfinkel) would find this page sympathetic but would want evidence that the governance properties claimed for the ensemble are real. The "proof exists" section points to benchmarks, not governance audits.

The ABC Group 2 (Public Intellectuals — Schneier, Véliz, Pasquale, Russell, Summerfield) would each have a specific question that this page doesn't answer:
- **Schneier:** Does open routing actually distribute power if the underlying models are still proprietary?
- **Véliz:** What does screamingface itself collect? What's the data flow?
- **Pasquale:** Does this substitute for regulation or complement it?

---

### What the Time 100 Cohort Would Notice

The Time 100 report's Group 4 (Critical Evaluators — ~20 people) would surface three gaps:

1. **Safety evaluability:** Dynamic routing across models with different safety profiles makes the ensemble harder to formally evaluate. This isn't addressed.
2. **Privacy and data flow:** What flows to which APIs, under what retention policies? Not answered.
3. **Content policy:** Whose content policy governs the ensemble when models disagree? Not addressed.

The Time 100 report also notes that the **credit-sharing story is the most broadly resonant feature** across all five groups — more than benchmarks. It doesn't appear on the /why page at all. For Audience 2, credit sharing could be framed as "resource democratization" — a different angle than the developer cost-savings pitch, but potentially powerful.

---

### Suggested Changes — /why Page

| Priority | Change | Rationale |
|----------|--------|-----------|
| **Critical** | Expand the stakes grid or replace with developed paragraphs | 6 one-liners are too thin for the primary audience. Each stake needs real substance on this page. |
| **Critical** | Fix "Democracy" framing — remove "free market" language | Actively alienates part of the primary audience. Reframe around public goods and democratic governance. |
| **High** | Add an author/signatory to the open letter | Open letters need a "from." Audience 2 cares deeply about who stands behind a claim. |
| **High** | Differentiate the email capture copy for this page | "Benchmark drops" is Audience 1 language. Audience 2 wants coalition updates, co-authorship, policy briefs. |
| **High** | Expand "Get involved" with specific participation paths | "Co-author a piece," "join our research calls," "add your organization's name." Not just an email field. |
| **High** | Add one sentence explaining what OpenMined is | Audience 2 may not know. One line of institutional context. |
| **Medium** | Remove or replace placeholder collaborators | Same problem as homepage but worse here — Audience 2 evaluates institutional credibility through partnerships. |
| **Medium** | Connect to existing policy frameworks | EU AI Act, GDPR, executive orders — reference the landscape this audience already works in. |
| **Medium** | Open more "doors" per the ABC cohort entry narratives | Currently only the democracy/infrastructure narrative is developed. Privacy, safety, copyright each deserve a paragraph or their own section. |
| **Medium** | Mention credit sharing as resource democratization | The Time 100 report says this is the most broadly resonant feature. Frame it for Audience 2. |
| **Low** | Address the "proprietary models" question | Schneier and others will ask: is "open routing" meaningful when the models are proprietary? Acknowledging the limitation builds credibility. |
| **Low** | Add data flow transparency note | What screamingface itself collects and sends. Audience 2 (and the ABC technical validators) will ask. |

---

## Cross-Page Issues

| Issue | Pages Affected | Note |
|-------|---------------|------|
| Stakes grid is identical on both pages | Homepage + /why | Homepage version is fine as a bridge. /why version needs to be substantially expanded for its primary audience. |
| Collaborators section is placeholder on both | Homepage + /why | Different fix per page: homepage should show real dev signals (GitHub, team usage); /why should show institutional/research affiliations. |
| Email capture is identical on both | Homepage + /why | Copy should differ by audience: developer language on homepage, coalition/policy language on /why. |
| No /why link in homepage nav | Homepage | Audience 2 visitors who land on homepage can't find /why easily. |
| Content system (default.ts) exists but page.tsx hardcodes content | Homepage | Some copy is in the content system, some is hardcoded in page.tsx. If the multi-audience system is still planned, this should be consistent. |

---

*Audit conducted March 2026 against persona-audience-1.md (P0), persona-audience-2.md (P1), abc-citations-report.md, and persona-time-100-ai-report.md. Use the persona weighting guide to confirm audience targeting before implementing changes.*
