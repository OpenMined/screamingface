# Plan: SF-268 — Align Desktop App UI to the screamingface-design Skill

## Context

We shipped the `screamingface-design` skill (SF-267, `.claude/skills/screamingface-design/`) — a fully-tokenized "infra-retro-modern" brand system: square corners (radius 0), hairline borders, flat fills (no gradients/shadows/blur), near-monochrome with **only** green `--gain` / red `--blind` / amber `--mark` as meaningful accents, **no purple**, EB Garamond (h1 only) / IBM Plex Sans (body) / IBM Plex Mono (data·labels). The desktop app (`apps/desktop/`, Electron + React 19 + Vite + Tailwind v4 + shadcn/ui) predates it and visibly violates it (OpenMined gold+**violet** palette, `--radius:0.5rem`, shadows, gradients, Inter/Rubik/Sometype Mono). The skill literally forbids "the default shadcn / clean modern SaaS look," which is roughly today's app.

**Outcome:** bring `apps/desktop/` into brand conformance, **dark-only**, incrementally — foundation → shared primitives → screen by screen — each step a small, independently verifiable PR. Design spec (approved): `docs/superpowers/specs/2026-06-11-desktop-ui-brand-alignment-design.md`.

**Scope.** In: `apps/desktop/` visual conformance, dark theme. Out (separate tickets): `web/portal/`, root `index.html` marketing, a full **light** theme, any behavioral/refactor change.

## Approach (C — cascade, then clean, then widgets)

shadcn primitives reference CSS vars that Tailwind's `@theme inline` exposes as utilities (`bg-background`, `border-border`, `rounded-*`, `text-destructive`…). Redefining those vars in **one** file recolors + de-rounds the whole app with zero component edits. Verified: `rounded-lg/md/xl` in the primitives all resolve through `--radius`, so `--radius:0` squares buttons/inputs/cards automatically. Then hand-fix only the **non-token literals** tokens can't reach, then refine per screen.

## Increment 1 — Foundation (one PR)

**Files:** `apps/desktop/src/renderer/src/globals.css`, `apps/desktop/src/renderer/index.html`.

**`globals.css` `.dark {}` — remap values to brand dark tokens** (values from `.claude/skills/screamingface-design/reference/tokens.css`):

| var | → value | brand role |
| --- | --- | --- |
| `--background` | `#0a0b0d` | bg |
| `--foreground` | `#e8eaed` | ink |
| `--card`, `--popover` | `#131519` | surface |
| `--card-foreground`, `--popover-foreground` | `#e8eaed` | ink |
| `--secondary`, `--muted`, `--accent` | `#1a1d22` | surface-2 |
| `--secondary-foreground`, `--accent-foreground` | `#e8eaed` | ink |
| `--muted-foreground` | `#9aa0aa` | ink-2 |
| `--border`, `--input` | `#20232a` | line |
| `--primary`, `--ring` | `#e0a23c` | mark (amber) |
| `--primary-foreground` | `#0a0b0d` | bg |
| `--destructive` | `#f0726f` | blind |
| `--radius` | `0` | square |
| `--chart-1..5` | `#4e79a7 #59a14f #d6a13c #b4574a #cf5d7a` | brand categorical (no purple) |
| add `--gain` | `#35d07f` | success/active (also add to sidebar mappings if used) |

Also update the `@theme inline {}` block: `--radius-2xl: 999px` → `0`; fonts → `--font-sans: "IBM Plex Sans", system-ui, sans-serif`, `--font-heading: "EB Garamond", Georgia, serif`, `--font-mono: "IBM Plex Mono", ui-monospace, monospace`. Map `--color-gain: var(--gain)` so a `bg-gain`/`text-gain` utility exists. Update the sidebar token block to brand values too (mirrors the main map).

**Delete** the `@layer utilities { .gradient-gold/.gradient-teal/.gradient-violet/.text-gradient-gold }` block. Update the dark scrollbar color `#2e2a3a` → `var(--line)`.

**`index.html`:** swap the Google-Fonts `<link>` to `EB+Garamond:wght@500;600`, `IBM+Plex+Sans:wght@400;500;600`, `IBM+Plex+Mono:wght@400;500;600` (mirror the skill loader). In the boot `<style>`: `body { background:#0a0b0d; font-family:"IBM Plex Sans",system-ui,sans-serif }`, boot heading → EB Garamond.

**Outcome / check:** whole app recolors to brand dark, square, brand fonts, no gradient utilities, no violet. `rg "gradient-(gold|teal|violet)|#6976ae|#f8c073"` over `src/renderer` → 0 definitions.

## Increment 2 — The 7 primitives (one PR)

`apps/desktop/src/renderer/src/components/ui/*`. Fix only the **non-token literals** (the rest squared via Increment 1):

- **badge.tsx** — `rounded-4xl` → `rounded-none`. Use `font-mono` for badge text (labels). Map `default` variant off `--primary`(amber) is fine for UI chips; status badges get gain/blind explicitly in the screen increments.
- **tabs.tsx** — remove `group-data-[variant=default]/tabs-list:data-active:shadow-sm` (drop the shadow; the existing `after:` underline + bg change carries active state). `rounded-lg`/`rounded-md` already → 0.
- **resizable.tsx** — grip `rounded-xs` → `rounded-none`.
- **card.tsx** — replace `ring-1 ring-foreground/10` with `border border-border` (true hairline) and keep square; `CardFooter` `bg-muted/50` → `bg-muted`.
- **button.tsx**, **input.tsx** — verify square after foundation (token-derived); no literal fixes expected. Confirm in the run step.
- App-wide `rounded-full` (status dots, avatars — never token-derived, always 9999px): handle per screen increment (default: square per the skill; flag any deliberate exception).

**Outcome / check:** `rg "rounded-(full|xs|sm|md|lg|xl|2xl|3xl|4xl)|shadow-" components/ui` → only token-derived (now-0) classes remain; no literal radius/shadow.

## Increments 3–6 — Screens (one PR each)

Reuse the primitives; apply brand semantics + font roles. Each ends with the app launched and that screen checked against the skill self-check (dark only).

3. **Settings** — `views/SettingsView.tsx`, `components/rjsf-theme.tsx`. Status dots → `--gain`/`--blind`/`--ink-3` (square); plugin sections as hairline-bordered rows; inputs square; section labels mono-caps; h1 Garamond. Note the `SettingsView.tsx:424` "red→…→violet" comment/color ramp — replace any violet ramp with the brand categorical/gain scale.
4. **Spend / Dashboard** — `views/DashboardView.tsx`, `components/server/*`. Cards flat surface + hairline (no ring/shadow); server status → gain/blind; control buttons square; logs in mono. Use the brand `.stats` 3-up pattern where metrics show.
5. **Eval Studio** — `views/EvalStudioView.tsx`, `components/eval/*`. `EvalQuestionsTable` → brand table (mono, `text-sm`, tabular-nums, right-aligned numerics, gain/blind ✓/✗); best/SOTA row in `--gain-bg`; resizable handles hairline; dialogs square.
6. **Cache/Log** — `views/SessionsView.tsx`, `components/session/*`. Session cards flat + hairline; status badges → gain/blind/ink-3 (square, mono); session-type selector + dialogs squared; shared `ServerLogs` already covered by #4.

## Increment 7 — Verify & close (one PR)

Launch the app (single instance — close any running dev app first), screenshot all four screens, run the skill self-check per screen, fix stragglers found by a final sweep: `rg -P "rounded-(?!none)|shadow-|gradient|violet|indigo|purple|#[0-9a-fA-F]{6}" apps/desktop/src/renderer/src` → justified/zero. `npm run build` green.

## Verification

- **Run:** `cd apps/desktop && npm run dev` (one instance only, per project rule). Dark theme only.
- **Per increment:** screenshot affected surface; check against `.claude/skills/screamingface-design/SKILL.md` → "Self-check before you finish" (no purple/gradient/shadow/rounded; color only for gain/blind/mark; Garamond h1-only; mono for data/labels).
- **Grep gates:** after #1–#2, anti-rule sweep over `apps/desktop/src/renderer/src` trends to zero (residuals justified). Use ripgrep `-P` for the `(?!none)` lookahead.
- **Build:** `npm run build` stays green; manual smoke that each screen's controls still function (no behavioral regression).

## Process / workflow notes

- Branch `SF-268-desktop-ui-brand-alignment` (already created); spec already committed there. Each increment = its own commit; group into one or a few PRs as the user prefers. Asana permalink in each commit body; no `Co-Authored-By`.
- Plan/spec live under `docs/superpowers/` per project rules; on approval this plan is copied to `docs/superpowers/plans/2026-06-11-desktop-ui-brand-alignment-plan.md`.
- Open decisions to confirm during execution (low-risk): `rounded-full` status dots → square vs small exception; base-ui/CVA may inject radius outside class lists (pin explicitly if a primitive still renders rounded); `--ink-2`/`--ink-3` contrast on `--surface` in dense tables (nudge to `--ink` if needed, no token invention).
