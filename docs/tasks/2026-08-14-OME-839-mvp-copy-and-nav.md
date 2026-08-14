---
id: OME-839
linear_url: https://linear.app/openmined/issue/OME-839/adopt-the-leaderboard-mvp-masthead-nav-and-landing-copy
status: In Progress
priority: P2
labels: [scoreboard, agentic, autonomous]
created: 2026-08-14
milestone: "🏆 Week 3 · Subsidized compute, $0 Colab & a verified board"
---

# Adopt the leaderboard-mvp masthead nav and landing copy

Irina's request (2026-08-14 DM): implement the `brand.screamingface.ai/leaderboard-mvp` copy more
faithfully, and add the top-right `benchmarks` / `github` / `docs` links.

Adopted: the three nav links, the fusion definition as the lead, the benchmark-picker sentence, and
the footer wordmark.

Deferred to `OME-770` / `OME-771`: roughly half the mockup's landing copy asserts capabilities that
do not exist (a reproducible/unverified legend, a reproducible-SOTA medal, a cost-vs-accuracy chart).
Adopting it would republish the exact claims `OME-820` withdrew two review rounds ago. The mockup's
footer line naming `leaderboard.screamingface.ai` is not adopted either — that host has no DNS
record and the data is not mock.

Sequencing: touches the same three HTML files as `#588`, which is unmerged; `#588` lands first and
this rebases.

Ledger: `docs/work/2026-08-14-OME-839-mvp-copy-and-nav.md` ·
Spec: `docs/spec/2026-08-14-OME-839-mvp-copy-and-nav.md` ·
Plan: `docs/plan/2026-08-14-OME-839-mvp-copy-and-nav.md`
