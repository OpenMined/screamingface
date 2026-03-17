# ABC Thesis Citations — Expanded Cohort Analysis (v2)
**Date:** March 2026
**Source:** https://attribution-based-control.ai/ — thesis by Andrew Trask

---

## Summary

This report extends the original 13-persona ABC citations cohort (v1) with 11 additional researchers from the thesis reference list, bringing the total to **24 personas**. The expansion was driven by an audit of the full thesis citation list against the project's two target audiences:

- **Audience 1** — Technical developers and AI benchmark enthusiasts (primary launch target)
- **Audience 2** — AI/society thought leaders, journalists, and policy champions

The new personas were prioritized in two tiers based on alignment with these audiences, public reach, and relevance to screamingface's core claims.

---

## What Changed from v1

The original cohort focused on researchers with the closest intellectual relationship to Trask's thesis — co-authors, direct technical contributors, and policy/legal thinkers whose frameworks the thesis explicitly builds on. The v2 expansion adds two new categories:

1. **Frontier lab leaders** (Amodei, LeCun, Hinton, Sutskever) — People who run or built the companies and models that screamingface routes through. Their reactions matter not as endorsements but as adversarial stress tests: if screamingface's architecture survives their objections, it's credible.

2. **Cryptographic foundations** (Goldwasser, Shamir, Micali, Gentry, Yao) — The inventors of the mathematical primitives the ABC thesis depends on: zero-knowledge proofs, secret sharing, secure multi-party computation, fully homomorphic encryption. Their validation carries weight with the technical community and with grant-makers funding privacy-preserving infrastructure.

3. **Ensemble theory originators** (Freund, Schapire) — The inventors of AdaBoost and formal boosting theory, from which screamingface's "deep voting" concept descends. Their assessment of whether screamingface constitutes a real ensemble (vs. adaptive model selection) is a definitional question the project needs to answer.

---

## How the Expanded Cohort Divides

### Original Groups (v1 — 13 personas)

| Group | Members | Function |
|-------|---------|----------|
| **1 — Governance Architects** | Dafoe (P1), Garfinkel (P3) | Co-authors; institutional design |
| **2 — Public Intellectuals** | Schneier (P2), Véliz (P4), Pasquale (P5), Russell (P6), Summerfield (P8) | Amplification; narrative framing |
| **3 — Legal & Attribution** | Samuelson (P7), Gabriel (P9) | Copyright; values alignment |
| **4 — Technical Validators** | Bengio (P10), Dwork (P11), Papernot (P12), McMahan (P13) | Privacy math; federated learning |

### New Groups (v2 — 11 personas)

| Group | Members | Function |
|-------|---------|----------|
| **5 — Frontier Lab Leaders** | Amodei (P14), LeCun (P15), Hinton (P16), Sutskever (P17) | Adversarial validation; competitive positioning |
| **6 — Cryptographic Foundations** | Goldwasser (P18), Shamir (P19), Micali (P20), Gentry (P21), Yao (P24) | Formal verification of privacy claims |
| **7 — Ensemble Theory** | Freund (P22), Schapire (P23) | Definitional validation of ensemble architecture |

---

## Group 5 — Frontier Lab Leaders (Amodei, LeCun, Hinton, Sutskever)

**Who they are:** The people who built, run, or left the companies whose models screamingface routes through. Amodei runs Anthropic (Claude). LeCun leads AI research at Meta (LLaMA). Hinton left Google to warn about AI risk. Sutskever left OpenAI to build safe superintelligence. Together they represent four distinct positions on the AI safety/openness spectrum — and four distinct objections to the ensemble concept.

**Their orientation to screamingface:** Each arrives through a different tension:

- **Amodei** sees ensemble routing as architecturally defeating the safety controls he's building into Claude. If no single provider controls the inference pipeline, who enforces constitutional constraints?
- **LeCun** would champion the open routing layer but reject the safety framing. He wants screamingface sold on capability and openness, not governance and risk.
- **Hinton** would find decentralization compelling but worry that making frontier AI more accessible accelerates the timeline to uncontrollable systems.
- **Sutskever** would view the ensemble as clever engineering at the wrong level of abstraction — a governance patch on systems that need architectural redesign.

**What they bring:** Not endorsement — pressure testing. If screamingface's claims survive the objections of the people who actually build and govern frontier models, the credibility gain is enormous. These four also represent the competitive landscape: their reactions predict how the labs will respond to ensemble routing as it grows.

**Audience fit:** Primarily Audience 2 (Amodei, LeCun, Hinton as public voices on AI power), with Sutskever bridging to Audience 1 (technical hero credibility).

---

## Group 6 — Cryptographic Foundations (Goldwasser, Shamir, Micali, Gentry, Yao)

**Who they are:** Five Turing Award winners (or equivalent) who invented the mathematical primitives the ABC thesis depends on. Goldwasser and Micali co-invented zero-knowledge proofs. Shamir invented secret sharing and co-invented RSA. Gentry solved fully homomorphic encryption. Yao invented secure multi-party computation. Their work is not analogous to screamingface's architecture — it is the literal foundation.

**Their orientation to screamingface:** Narrow, formal, and unforgiving. Each would evaluate screamingface against the security definitions their field has established:

- **Goldwasser** asks: is the verification end-to-end? Can a user cryptographically confirm correct routing?
- **Shamir** asks: what prevents an adversarial provider from reverse-engineering the routing strategy from the queries it receives?
- **Micali** asks: does the routing layer constitute genuine distributed consensus, or does it reintroduce a trusted intermediary?
- **Gentry** asks: are the privacy guarantees cryptographically enforced, or do they depend on trusting the orchestrator?
- **Yao** asks: does the architecture satisfy formal MPC security definitions under composition?

**What they bring:** If screamingface passes their scrutiny, the credibility with researchers, policymakers, and grant-makers is definitive. These are the people whose names appear in the theorems that the privacy claims rest on.

**Audience fit:** Crossover. Audience 1 respects them as technical authorities; Audience 2 recognizes their names as institutional validators.

---

## Group 7 — Ensemble Theory (Freund, Schapire)

**Who they are:** The co-inventors of AdaBoost and formal boosting theory. Their 1997 paper proved that weak learners, combined correctly, can match or beat any single strong learner — the theoretical result that screamingface's "deep voting" concept descends from.

**Their orientation to screamingface:** Interested but precise. Both would immediately distinguish between what screamingface does (routing queries to the predicted best model) and what boosting does (training a weighted combination with provable error reduction at each round). The original boosting proof depends on access to each learner's error profile and the ability to reweight examples — neither of which applies to opaque commercial APIs. They'd respect empirical SOTA results but push hard on whether the ensemble has formal guarantees or is brittle model selection.

**What they bring:** Definitional clarity. The question "is this really an ensemble?" is not academic — it determines whether screamingface's core claim (combining models beats any single model) has theoretical backing or is an empirical observation that could collapse with the next model update. Freund and Schapire are the two people most qualified to answer it.

**Audience fit:** Audience 1. The benchmark-running, eval-obsessed technical audience will immediately recognize the boosting lineage and care whether the theory holds.

---

## Updated Entry Narratives

The v1 report identified four entry narratives. The expanded cohort adds two more:

- **Control & safety** (Russell, Bengio, Hinton, Sutskever): "No single company should control AI inference — and the competitive race between them is itself a risk."
- **Privacy & data rights** (Schneier, Véliz, Dwork, Goldwasser, Shamir, Gentry, Yao): "Distributing queries across providers is structural privacy — but only if the cryptographic guarantees are real."
- **Copyright & attribution** (Samuelson, Gabriel): "The ensemble tracks attribution — which matters for the legal and values questions courts and ethicists are actively fighting over."
- **Democracy & power** (Pasquale, Summerfield, Dafoe, Garfinkel): "AI monoculture is a democratic infrastructure problem and this is a concrete technical intervention."
- **Open vs. closed** (LeCun, Amodei): "Should AI capability be distributed openly or controlled centrally? Screamingface forces the question by doing both simultaneously."
- **Ensemble validity** (Freund, Schapire, Papernot): "Does combining models actually work in the formal sense — and if so, why?"

---

## Updated Validation Sequence

The v1 sequence was: **validate → co-author → amplify.**

The expanded cohort adds a preliminary step:

**stress-test → validate → co-author → amplify**

1. **Stress-test** (Groups 5, 7) — Engage frontier lab leaders and ensemble theorists first. Their objections will reveal the weaknesses screamingface needs to address before seeking formal validation. Amodei's safety objection, LeCun's framing objection, and Freund/Schapire's definitional objection are the three hardest questions. Answer them first.

2. **Validate** (Groups 4, 6) — Technical validators and cryptographic foundations. Dwork, Papernot, McMahan from v1, plus Goldwasser, Shamir, Micali, Gentry, Yao. Formal review and audit. If the privacy math and ensemble claims survive, the credibility is locked in.

3. **Co-author** (Groups 1, 3) — Governance architects and legal/attribution specialists. Joint papers, policy briefs, public statements.

4. **Amplify** (Group 2) — Public intellectuals with reach. Schneier blogs, Russell lectures, Véliz writes, Pasquale testifies, Summerfield advises UKASI. Once there's something validated to point to, they amplify it.

---

## Personas by File

```
personas/abc-citations/
  abc-citations-report.md       ← v1 report (original 13)
  abc-citations-report-v2.md    ← this file (expanded to 24)
  personas/
    — v1 (original cohort) —
    allan-dafoe.md               P1  — GovAI / DeepMind
    bruce-schneier.md            P2  — Harvard Kennedy / EFF
    ben-garfinkel.md             P3  — GovAI
    carissa-veliz.md             P4  — Oxford Ethics in AI
    frank-pasquale.md            P5  — Cornell Tech + Law
    stuart-russell.md            P6  — UC Berkeley CHAI
    pamela-samuelson.md          P7  — UC Berkeley Law
    chris-summerfield.md         P8  — Oxford / DeepMind / UKASI
    iason-gabriel.md             P9  — DeepMind AGI & Society
    yoshua-bengio.md             P10 — Mila / U Montréal
    cynthia-dwork.md             P11 — Harvard
    nicolas-papernot.md          P12 — U Toronto / CAISI
    brendan-mcmahan.md           P13 — Google Research

    — v2 Tier 1 (frontier lab leaders + crossover) —
    dario-amodei.md              P14 — Anthropic
    yann-lecun.md                P15 — Meta AI / NYU
    geoffrey-hinton.md           P16 — U Toronto (emeritus)
    ilya-sutskever.md            P17 — Safe Superintelligence Inc.
    shafi-goldwasser.md          P18 — MIT / Weizmann / Duality

    — v2 Tier 2 (cryptographic foundations + ensemble theory) —
    adi-shamir.md                P19 — Weizmann Institute
    silvio-micali.md             P20 — MIT / Algorand
    craig-gentry.md              P21 — TripleBlind (ex-IBM)
    yoav-freund.md               P22 — UC San Diego
    robert-schapire.md           P23 — Microsoft Research
    andrew-yao.md                P24 — Tsinghua IIIS
```

---

## Remaining Citations Not Yet Profiled

The full thesis cites approximately 90+ unique works. The 24 profiled personas cover the individuals most relevant to screamingface's Audience 1 and Audience 2 strategies. Remaining citations fall into categories that are useful for narrative but not for engagement personas:

- **Historical/deceased figures** — Ostrom (commons governance), Simon (bounded rationality), Hayek (knowledge in society), Bernays (propaganda), Wells (World Brain), Licklider (human-computer symbiosis), Anderson (imagined communities)
- **Foundational but tangential** — Chomsky (linguistics), Dunbar (anthropology), Granovetter (network theory), Page/Brin (PageRank)
- **Journalists cited for reporting** — Grynbaum, O'Brien, Samuel, etc. (cited for coverage, not as thought leaders)
- **Institutional/government citations** — EU Commission, IEEE, Access Now, Montreal Declaration, etc.

These are available for narrative framing (e.g., "Ostrom's commons framework applies directly to federated AI infrastructure") but do not require individual persona files.

---

*Research conducted March 2026. Based on publicly available information and the attribution-based-control.ai thesis reference list. Individual personas are synthesized from research and should be treated as informed approximations, not direct quotes or verified positions.*
