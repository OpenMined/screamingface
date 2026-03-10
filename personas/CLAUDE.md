# Personas Directory

This directory contains user personas that inform how Claude approaches design, copy, features, and prioritization across all parts of the screamingface project (website, app, cloud).

## Purpose

Personas are not just marketing artifacts. They are **working context for Claude** — loaded when making decisions about:
- **Website copy and design** — what language resonates, what to emphasize on the homepage
- **App UX** — what screens matter most, what workflows to optimize
- **Feature prioritization** — what to build next based on who we're serving
- **Onboarding flows** — what assumptions we can make about technical ability
- **Messaging and positioning** — how to frame the ensemble value prop for different audiences

## Persona Types

We maintain personas at two levels:

### 1. Internal Personas (who's building and dogfooding)
These represent the team and close collaborators who use screamingface daily. They inform the "Week 1" experience — the product must work for these people first before it works for anyone else.

### 2. External Personas (who we're launching to)
These represent target users at various stages of the product's growth. They inform marketing, onboarding, and feature decisions as we expand beyond internal use.

## How to Use Personas

When Claude is working on a task, reference the relevant persona:
- "Write homepage copy targeting the **CLI Power User**"
- "Design the spend screen for the **Credit-Strapped Developer**"
- "What would the **OpenMined Core Team** need from the eval studio?"

Personas should be referenced in CLAUDE.md files within each package (web/, app/, cloud/) to guide context-specific work.

## Persona File Format

Each persona file follows this structure:

```
# [Persona Name]
**Type:** Internal | External
**Priority:** P0 (build for now) | P1 (build for soon) | P2 (design for later)

## Identity
Who they are in 2-3 sentences. Role, context, motivation.

## Technical Profile
- Tools they use daily
- Technical comfort level
- Operating systems / environments

## Relationship to AI Coding Tools
How they currently use AI in their workflow. What's working, what's frustrating.

## Pain Points
What problems screamingface solves for them. Be specific.

## Value Triggers
What would make them say "I need this." The moments that drive adoption.

## Messaging That Resonates
Language, framing, and proof points that land with this persona.

## Messaging That Falls Flat
What to avoid. Jargon, framings, or promises that don't connect.

## Design Implications
How this persona affects UI/UX decisions across website, app, and cloud.

## Key Quotes (real or synthesized)
Representative statements that capture their mindset. Source from Slack, interviews, or synthesis.
```

## Persona Roadmap

| Persona | Type | Priority | Status |
|---------|------|----------|--------|
| OpenMined Core Team | Internal | P0 | Done |
| CLI Power User | External | P0 | Planned |
| Credit-Strapped Developer | External | P1 | Planned |
| Benchmark Enthusiast | External | P1 | Planned |
| Team Lead / Multiplier | External | P2 | Planned |
| AI-Curious Non-Engineer | External | P2 | Planned |

### Planned Persona Descriptions

**CLI Power User** — A developer who already uses 2+ AI coding CLIs (Claude Code, Gemini, Codex) daily. They're productive but annoyed by context-switching between tools and inconsistent quality. They want one interface that's always the best answer. This is the Day 1 external user.

**Credit-Strapped Developer** — Someone who hits API rate limits or budget caps regularly. They've done the mental math on what each provider costs. The "share credits with friends" feature is their entry point. Token economics matter to them.

**Benchmark Enthusiast** — Follows AI leaderboards, runs their own evals, cares about measurable quality. The SOTA claim is what gets them in the door. They want to verify it themselves via the Eval Studio.

**Team Lead / Multiplier** — Manages a small engineering team. Interested in screamingface as a way to give their team better AI without 5 different subscriptions. The "Gates" token sharing feature is their unlock.

**AI-Curious Non-Engineer** — Interested in AI tools but not deeply technical. Could be a designer, PM, or researcher. The ensemble concept intrigues them but they need it to be dead simple. Important for viral growth but not a launch target.
