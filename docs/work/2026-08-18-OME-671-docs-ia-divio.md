# OME-671 — public-docs IA restructure (Divio / Diátaxis)

**Date:** 2026-08-18 · **Folds into:** OME-671 / PR #594 · **Actor:** agentic (Irina driving)

## Goal
Restructure the ScreamingFace Client docs around the Divio documentation system:
four separated quadrants — **Tutorials · How-to guides · Reference · Explanation** —
and a complete, role-grouped API Reference (Option A: `sf` namespace + 8 class
groups). Fixes the muddled "Core classes" vs "Modules & types" split and the
incomplete reference (Fusion/Pipeline/Url4 had no reference page).

Plan: `.claude/plans/can-we-checkin-into-warm-tarjan.md`.

## Work
- New reference pages (verified against the client): `api/fusions`, `api/pipelines`,
  `api/url4`, `api/connections`; add `LeaderboardError` to `api/errors`; move
  Connection/ConnectionPanel off `api/clients`.
- Nav rewrite (`src/navigation/sf-client.ts`) into the four Divio sections + Option-A
  reference groups; `learn` → Explanation.
- Guide↔reference dedup; Overview "why" → Explanation.

## Outcome
Structural increment done: sidebar rewritten into Tutorials / How-to guides /
Reference / Explanation; Reference = "The sf namespace" + Classes in 8 role groups;
4 new reference pages (Fusion, Pipeline, Url4, Connections) verified against the
client; Connection/ConnectionPanel moved off the Clients page; Learn → Explanation.
Audits: all 24 nav links resolve; every `sf.__all__` type has exactly one reference
home (0 undocumented); build/prettier/eslint green.

**Remaining (follow-up increment):** guide↔reference dedup (strip duplicate field
tables from the how-to guides), move the Overview "why" narrative into Explanation,
goal-reframe individual guide titles.
