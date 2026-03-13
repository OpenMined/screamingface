# Personas Directory

This directory contains audience personas and research cohorts that inform how Claude approaches copy, design, features, and positioning across the screamingface project.

## Start Here

**Read `weighting-guide.md` first.** It maps every work context (homepage, /why page, app screens, outreach) to the right audience personas and tells you when to use which files.

## What's In This Directory

### Audience Personas (the core three)
- `persona-audience-1.md` — Technical developers & benchmark enthusiasts (P0, primary launch target)
- `persona-audience-2.md` — AI/society thought leaders, journalists & policy champions (P1)
- `openmined-core-team.md` — OpenMined internal team (pre-launch review only)

### Research Cohorts (reference material)
- `abc-citations/` — Researchers cited in Andrew Trask's thesis at attribution-based-control.ai. Potential peers, co-authors, and validators. Individual profiles indicate whether each person is a peer or Audience 2-aligned.
  - `abc-citations-report.md` — Group analysis and engagement strategy
  - `personas/*.md` — Individual researcher profiles
- `time100-ai/` — TIME's 100 most influential people in AI (2025). Most connected to Audience 2 considerations.
  - `persona-time-100-ai-report.md` — Group analysis organized by orientation
  - `personas/{thinkers,shapers,leaders,innovators}/*.md` — Individual profiles

### Supporting Files
- `weighting-guide.md` — **The routing doc.** Which personas apply to which work context.
- `flatten-headers.lua` — Pandoc filter for document export

## How Personas Are Used

Personas are not marketing artifacts. They are **working context for Claude** — loaded when making decisions about:
- **Website copy and design** — what language resonates, what to emphasize
- **App UX** — what screens matter most, what workflows to optimize
- **Positioning** — how to frame the ensemble value prop for different audiences
- **Outreach** — who to engage, in what order, with what framing

## When to Read What

| Task | Read |
|------|------|
| Any copy/design work | `weighting-guide.md` → relevant audience persona |
| Homepage work | `persona-audience-1.md` (primary), `persona-audience-2.md` (secondary) |
| /why page work | `persona-audience-2.md`, then ABC + Time 100 group reports |
| App screen work | `openmined-core-team.md` (pre-launch) or `persona-audience-1.md` (post-launch) |
| "How would X react?" | Relevant group report → individual profile if needed |
| Positioning question | `weighting-guide.md` → relevant personas + cohort reports |

## Summary Reports (planned)

Digestible rollup reports for the ABC and Time 100 cohorts are in development. These will distill general sentiments and positioning themes from individual profiles. Until those exist, the group-level reports are the starting point.

## Persona File Format

Each audience persona follows this structure:

```
# [Persona Name]
**Type:** Internal | External
**Priority:** P0 (build for now) | P1 (build for soon) | P2 (design for later)

## Who They Are / Identity
## Technical Profile (if applicable)
## Pain Points
## Value Triggers
## Messaging That Resonates
## Messaging That Falls Flat
## Design Implications
```

## Persona Roadmap

| Persona | Type | Priority | Status |
|---------|------|----------|--------|
| OpenMined Core Team | Internal | P0 | Done |
| Audience 1 (Technical Developers) | External | P0 | Done |
| Audience 2 (Thought Leaders/Policy) | External | P1 | Done |
| ABC Citations Cohort | Research | Reference | Done (individual profiles in progress) |
| Time 100 AI Cohort | Research | Reference | Done |
| CLI Power User | External | P0 | Planned |
| Credit-Strapped Developer | External | P1 | Planned |
| Benchmark Enthusiast | External | P1 | Planned |
| Team Lead / Multiplier | External | P2 | Planned |
| AI-Curious Non-Engineer | External | P2 | Planned |
