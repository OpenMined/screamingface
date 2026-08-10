---
ticket: OME-717
stack: repo
status: in_progress
started: 2026-07-31
finished:
---

# OME-717 — Rewrite positioning.md end-to-end to reflect current V1 delivery

## Intent

`docs/positioning.md` (captured June 2026) predates what V1 actually ships: the
`screamingface` Python SDK (`pip install screamingface`), the real `url4` engine
(`packages/url4`), the DRACO reproduction path (rubric grading via a Gemini judge), the
verified scoreboard, subsidized $0-Colab compute, the Fusion Monsters program, and the
August macOS launch. It still frames the product as the Electron/Eval-Studio app on a
"July 1 / two waves" timeline and calls the SDK "just a direction" (ISSUES I-29, now
resolved). Rewrite it end-to-end so the narrative matches delivery while preserving the
durable positioning spine, and keep it honest about what is *not* yet shipped.

## Planned changes

- Rewrite `docs/positioning.md` in full. Keep: A1/A2 audiences, tone rule, four pillars,
  versus-neighbours table, do/don't, the "don't overclaim ensembling — private data +
  diversity is where the gains live" honesty, open questions, sources.
- Add: a "what ships today vs. lands at launch vs. Wave 2" honesty table; a "proof"
  section (demo lift 57.6% vs 27%, DRACO reproduction, reproducible-in-Colab-at-$0,
  verified-not-claimed leaderboard); a constraints/risks section (R1 OpenRouter, R2
  multi-turn+tools, R3 experiment-to-SOTA, I-3 business model, I-4 privacy, I-32
  nondeterminism).
- Refresh each pillar and the neighbours table to current delivery; update the SDK from
  "direction" to shipped (I-29).

## Test plan

Docs artifact — no unit tests. Verification is a grounded read-through:

- Every "what we deliver" claim traces to code (`packages/screamingface`, `packages/url4`,
  `apps/aigateway`, `apps/scoreboard`) or to the Asana launch boards / PROJECT-OVERVIEW.
- No claim asserts something unshipped as shipped (multi-turn+tools, paid business model,
  a *validated* win over OpenRouter Fusion — the SOTA claim is gated/PENDING).
- Internal links resolve; tone rule respected (no marketing adjectives; number + install
  command lead).

## Acceptance

- `docs/positioning.md` reads end-to-end as a current, comprehensive positioning doc.
- Shipped-vs-next split is explicit and honest.
- OME-717 + this ledger + the `docs/tasks/` mirror closed together.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** docs/positioning.md (full rewrite); docs/tasks/2026-07-31-OME-717-positioning-rewrite.md; this ledger.
- **Commits:** none yet — working tree only, left for owner review (never commit to main).
- **Gates:** n/a (docs; no run_gates lane).
- **Follow-on (same ticket):** relisted the **target personas** from the marketing
  document — OpenMined **Newsletter Strategy Deck (July 2026)**, Google Slides
  `1Ty3DHa0nu8VAPXgJjv4AAB5CqnwH3NIqx0uffYt702o`, found via the `Target Audience
  Identification` Asana task. Added a §"Target personas" section (Rahul = A1 primary;
  Helen = A2 secondary) with the deck's tone + "what they want from us," plus the still-open
  expansion candidates (researchers/AI-labs, token-buyers, private-data champion, the "6M
  who saw OpenRouter Fusion") and their open questions.
- **Deviations:** The original doc's persona links (`../personas/*.md`,
  `narrative-funnel-chapter-guide.md`) were **dead on disk**; **resolved** by repointing the
  audience source to the Newsletter Strategy Deck + Asana rather than inventing files. The
  narrative-funnel link remains referenced by name (no file) — left as-is. Not committed
  (working tree only; awaiting owner review + commit decision).
