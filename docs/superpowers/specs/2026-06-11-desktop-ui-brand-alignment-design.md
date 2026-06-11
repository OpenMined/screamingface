# Design Spec — Align Desktop App UI to the screamingface-design Skill

- **Ticket:** SF-268 — https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215639975551466
- **Date:** 2026-06-11
- **Status:** Design (awaiting review) → implementation plan to follow
- **Branch:** `SF-268-desktop-ui-brand-alignment`

## Context

We just shipped the `screamingface-design` skill (SF-267, `.claude/skills/screamingface-design/`), a fully-tokenized "infra-retro-modern" brand system parsed from `brand.screamingface.ai`: square corners (radius 0), hairline 1px borders, flat fills (no gradients/shadows/blur), near-monochrome with **only** green `--gain` / red `--blind` / amber `--mark` as meaningful accents, **no purple**, EB Garamond for h1 only, IBM Plex Sans for body, IBM Plex Mono for data/labels.

The desktop app (`apps/desktop/`, Electron + React 19 + Vite + Tailwind v4 + shadcn/ui) predates the skill and visibly violates it: an OpenMined dark palette (gold `#f8c073`, **violet** `#6976ae`), `--radius: 0.5rem` (≈120 `rounded-*` usages), `shadow-*` on cards/tabs, gradient utilities, and the wrong fonts (Inter / Rubik / Sometype Mono). The skill explicitly forbids "the default shadcn / clean modern SaaS look," which is roughly what the app looks like today.

**Goal:** bring the desktop app into conformance with the brand system, incrementally — foundation first, then the shared primitives, then screen by screen — so each step is a small, independently verifiable PR.

## Scope

**In scope (SF-268):** `apps/desktop/` only.
- Rebrand to the brand **dark** tokens; the app stays **dark-only** for now.
- Foundation (tokens, fonts, radius, chart palette, gradients) → the 7 shared `components/ui/` primitives → the four screens (Settings, Spend/Dashboard, Eval Studio, Cache/Log).

**Out of scope (future tickets):**
- `web/portal/` (vanilla CSS leaderboard/receipts) and root `index.html` (marketing) — separate follow-up.
- A full **light** theme for the app (brand says light & dark are co-equal; deferred to keep this increment small).
- Functional/behavioral changes. This is a visual-conformance effort, not a refactor or feature work.

## Target & current state

**Target:** the rules and tokens in `.claude/skills/screamingface-design/` (`SKILL.md`, `reference/tokens.css`).

**Current foundation files (verified):**
- `apps/desktop/src/renderer/src/globals.css` — `@theme inline {}` maps shadcn semantic vars → Tailwind utilities (`--color-*`, `--font-*`, `--radius-*`); a `.dark {}` block holds the actual values; an `@layer utilities {}` block defines `.gradient-gold/-teal/-violet/.text-gradient-gold`.
- `apps/desktop/src/renderer/index.html` — `<html class="dark">`, a Google-Fonts `<link>` (Inter/Rubik/Sometype Mono), and an inline boot-screen `<style>` (`body { background:#14121a; font-family: Inter }`, boot heading in Rubik).
- `apps/desktop/src/renderer/src/components/ui/` — 7 primitives: `button.tsx`, `card.tsx`, `badge.tsx`, `tabs.tsx`, `input.tsx`, `resizable.tsx`, `toaster.tsx`, consumed across ~40 files and all four screens.
- Screens (`views/`): `SettingsView.tsx`, `DashboardView.tsx` (Spend), `EvalStudioView.tsx`, `SessionsView.tsx` (Cache/Log), plus `components/{eval,server,session}/` and `components/rjsf-theme.tsx`.

## Approach (chosen: C — cascade, then clean, then widgets)

The shadcn primitives reference CSS variables that Tailwind's `@theme inline` exposes as utilities (`bg-background`, `border-border`, `rounded-md`, `text-destructive`…). Because of this indirection, **redefining the variables in one place recolors and de-rounds the whole app without touching component code.** We exploit that for leverage, then clean up what tokens can't reach, then refine per screen.

Rejected alternatives:
- **A (variable remap only):** fast but leaves literal `shadow-*`/`rounded-*`/font-role issues in the primitives.
- **B (new token layer + rewrite primitives to brand var names):** most literal to the skill's "semantic tokens only" rule, but high churn and fights shadcn conventions for little visual gain.

C = A's cascade **plus** B's cleanup, but only for the 7 primitives, sequenced by leverage.

### Token mapping (brand dark → shadcn vars, in `globals.css` `.dark`)

| shadcn var | current | → brand (dark) | brand token |
| --- | --- | --- | --- |
| `--background` | `#14121a` | `#0a0b0d` | `--bg` |
| `--foreground` | `#fcfcfd` | `#e8eaed` | `--ink` |
| `--card` / `--popover` | `#1e1b26` | `#131519` | `--surface` |
| `--card-foreground` / `--popover-foreground` | `#fcfcfd` | `#e8eaed` | `--ink` |
| `--secondary` / `--muted` / `--accent` | `#2a2633` | `#1a1d22` | `--surface-2` |
| `--muted-foreground` | `#8a8699` | `#9aa0aa` | `--ink-2` |
| `--secondary/accent-foreground` | `#fcfcfd` | `#e8eaed` | `--ink` |
| `--border` / `--input` | `#2e2a3a` | `#20232a` | `--line` |
| `--primary` | `#f8c073` (gold) | `#e0a23c` | `--mark` (amber spark) |
| `--primary-foreground` | `#1a1720` | `#0a0b0d` | `--bg` |
| `--ring` | `#f8c073` | `#e0a23c` | `--mark` |
| `--destructive` | `#cc677b` | `#f0726f` | `--blind` |
| `--radius` | `0.5rem` | `0` | `radius.none` |
| `--radius-2xl` (in `@theme`) | `999px` | `0` | square everywhere |
| `--chart-1..5` | gold/orange/teal/**violet**/red | `--cat-blue, --cat-green, --cat-amber, --cat-rust, --cat-rose` | categorical (no purple) |

Add a `--gain` (`#35d07f`) variable for the brand's "correct/SOTA" green (shadcn has no native success role); use it where the app signals success/active. Keep `--blind` (mapped via `--destructive`) for negative/guessing states. `--mark` (amber) is UI-only, never data.

> Decision: map `--primary` → `--mark` (amber). Rationale: shadcn's `--primary` drives default buttons/focus, which are UI chrome — the brand's amber spark is the correct "UI accent, not data" role. Data meaning (gain/blind) is applied explicitly per widget, never via `--primary`.

### Fonts

- `index.html` `<link>`: replace the Google-Fonts families with **EB Garamond** (500;600), **IBM Plex Sans** (400;500;600), **IBM Plex Mono** (400;500;600) — matching the skill's loader.
- `globals.css` `@theme inline`: `--font-sans: "IBM Plex Sans"…`, `--font-heading: "EB Garamond"…`, `--font-mono: "IBM Plex Mono"…`.
- `index.html` boot `<style>`: `background:#0a0b0d`, body font IBM Plex Sans, boot heading EB Garamond.
- **Role discipline:** EB Garamond is for **h1/display only**; everything else is Plex Sans (prose) or Plex Mono (data, labels, code, table headers). Enforced per widget in the screen increments, not globally.

## Increments (each = one small, verifiable PR under SF-268)

Each increment ends with the app launched and the relevant surface visually checked against the skill's **self-check** (no purple, no gradient/shadow/rounded, color only for gain/blind/mark, Garamond h1-only, both… here dark-only).

1. **Foundation.** Edit `index.html` (fonts + boot styles) and `globals.css` (`.dark` value remap, `--radius:0`, `--radius-2xl:0`, chart palette → brand categorical, **delete the gradient utilities**, add `--gain`). *Outcome:* whole app recolors to brand dark, square corners, brand fonts — with zero component edits. Grep confirms no remaining `gradient-*` utility definitions.

2. **The 7 primitives.** `components/ui/*`: remove residual literal `rounded-*` and `shadow-*` classes (replace shadow with hairline `border-border` where separation is needed); confirm `badge`/`tabs`/`button` read square; apply font roles (mono for badges/labels, sans for button text). *Outcome:* cascades to all four screens; grep shows `shadow-`/`rounded-[^n]` count drop to ~0 in `ui/`.

3. **Settings** (`SettingsView.tsx`, `rjsf-theme.tsx`). Status dots → gain/blind/ink-3; plugin sections as hairline-bordered rows; form inputs square; labels in mono caps; h1 in Garamond.

4. **Spend / Dashboard** (`DashboardView.tsx`, `components/server/*`). Cards → flat surface + hairline (no shadow); server-status indicators → gain/blind; control buttons square; logs panel in mono. Consider the brand `.stats` 3-up pattern where metrics are shown.

5. **Eval Studio** (`EvalStudioView.tsx`, `components/eval/*`). `EvalQuestionsTable` → brand table (mono, `--text-sm`, tabular-nums, right-aligned numerics, gain/blind ✓/✗); resizable handles → hairline; SOTA/best row in `--gain-bg`; dialogs square.

6. **Cache/Log** (`SessionsView.tsx`, `components/session/*`). Session cards → flat + hairline; status badges → gain/blind/ink-3 (square, mono); dialogs and the session-type selector squared; shared `ServerLogs` already covered by #4.

7. **Verify & close.** Launch the app (single instance — close any running dev app first), screenshot all four screens, run the skill self-check per screen, fix stragglers (hardcoded hex, stray `purple/violet/indigo`, `rounded`, `shadow`, gradient) found by a final grep sweep.

## Things tokens can't fix (explicit cleanup, tracked across increments)

- Literal `shadow-*` utilities on components (must be removed in TSX) — primarily `card.tsx`, `tabs.tsx`.
- Gradient utilities + any `gradient-*`/`text-gradient-gold` usages in TSX (e.g. a violet gradient in `SessionsView`).
- The violet `--chart-4` and any hardcoded `#6976ae`/`violet`/`indigo`/`purple`.
- Hardcoded hex colors in TSX that bypass tokens — replace with semantic utilities.
- `--radius-2xl: 999px` and `rounded-full` (e.g. `badge`) — square per brand.

## Verification

- **Run:** `cd apps/desktop && npm run dev` (one instance only; close any running dev app first per project rule).
- **Per increment:** screenshot the affected surface; check against the skill self-check (`.claude/skills/screamingface-design/SKILL.md` → "Self-check before you finish"). Dark theme only for SF-268.
- **Grep gates:** after #1–#2, `rg -n "gradient|shadow-|rounded-(?!none)|#[0-9a-fA-F]{3,6}|violet|indigo|purple"` over `apps/desktop/src/renderer/src` trends toward zero (residuals justified or ticketed).
- **Build:** `npm run build` stays green.
- No behavioral regressions: each screen's controls still function (manual smoke per screen).

## Risks / open questions

- **Base-ui/CVA defaults** may inject radius/shadow outside our class lists; if a primitive still renders rounded after #2, pin it explicitly. (Low risk; verified in the run step.)
- **Contrast** of brand dark `--ink-2`/`--ink-3` on `--surface` for dense tables — verify legibility in #5; nudge to `--ink` if needed (no token invention).
- **Light theme** deliberately deferred; the `@theme`/`.dark` split keeps a future `:root` light block easy to add.
- **`--gain` introduction:** a non-shadcn variable; ensure it's declared in `.dark` and (later) any `:root` so a future light theme doesn't break.

## Summary

This spec covers visual conformance of `apps/desktop/` in **dark mode only**, applied incrementally: foundation (tokens/fonts/radius/palette) → the 7 shared primitives → the four screens → verify. Web portal, marketing site, and a full light theme are explicit follow-up tickets.
