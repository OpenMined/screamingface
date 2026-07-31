---
description: ScreamingFace brand & design system (SFDS v2) — the single visual law for ALL UI/UX work in this repo (website, leaderboard, scoreboard, studio, admin consoles, demos, charts, copy). Use whenever building, styling, or reviewing any frontend surface; choosing colors, type, or spacing; or making a design/layout/visual decision. Overrides shadcn/Tailwind defaults. Parsed from brand.screamingface.ai.
user_invocable: true
---

# ScreamingFace Design System

**SFDS v2.0** — the canonical look-and-rules for everything we ship. The audience is **policy and
science leadership, not only developers**, so the surface has to **earn trust at a glance**. One
system, applied everywhere — website, leaderboard, scoreboard, studio, admin tooling, demos, charts,
and copy.

> **The direction — "infra-retro-modern."** Developer-infrastructure precision with a terminal-retro
> backbone: **mono structure, hairline rules, square corners, true white and true dark.** Colour is
> rationed — it appears only to help the reader follow the story. We argue that AI should be
> *honest*; the surface should feel honest too.

The exact tokens and component CSS are in `reference/`; **`reference/PROVENANCE.md` records the
version and a copy-pasteable drift check.** Those files are verbatim copies of the live system, so
they are the answer, not a paraphrase — read them when you need precise values.

## READ THIS FIRST — the two registers

v2 ships **two registers**, and picking the wrong one is the single most likely way to get a surface
confidently wrong.

| register | how | `--accent` is | use for |
|---|---|---|---|
| **app** | **the default** — nothing to set | **blue** `#4b91f0` | product UI: studio, admin consoles, dashboards, forms, tables |
| **marketing** | `data-brand="marketing"` on the root | **gold** `#ec9f3f` | leaderboard, landing pages, brand surfaces |

`[data-brand="marketing"]` overrides **only** the accent-family aliases. Everything else — neutrals,
success, danger, type, spacing — is identical in both.

**In the app register, gold is not the accent.** Gold is `--brand`/`--gain`, and it is *rationed to
the win*: the leading leaderboard row, the SOTA counter. A product surface with no "win" in it — an
admin console, a settings page — should contain **no gold at all**. It is mostly neutral with blue
interaction.

If you find yourself painting a product surface gold because "gold is the ScreamingFace colour",
stop. That is the marketing register leaking into a place the system deliberately kept quiet.

## The five principles

1. **Evidence over adjectives.** Lead with the number, the run, the source.
2. **Structure you can see.** Hierarchy from type and rules, not decoration.
3. **Colour means something.** Neutrals carry the page; colour marks the thing that matters.
4. **Legible at small sizes.** This holds dense tables and footnotes.
5. **Light and dark are equals.** Both designed, not one tinted from the other.

## Anti-rules — hard rules, not suggestions

| NEVER | INSTEAD |
| --- | --- |
| Serif in product UI chrome, table cells, or buttons. | Plex Sans. Parastoo is **display/marketing only**. |
| Mono at display size. | Mono for data, labels, IDs, receipts. |
| More than two font families on one surface. | Pick two and hold the line. |
| Rounded corners. Radius is `0`. | Square edges + hairline borders. `--radius-window` (10px) is terminal chrome **only**. |
| Drop shadows on components. | Depth from the seam, not blur. `--shadow-window` is used exactly **once** (the terminal window). |
| Gradients. | The one sanctioned gradient is `--fusion-grad`, on the leading leaderboard row only. |
| Fake small-caps or stretched type. | Real weights: 400 / 500 / 600. |
| Caps typed into repeating labels. | Sentence case + a coloured square for state. Caps only via CSS `text-transform`, on tiny labels. |
| Recolouring, boxing, or redrawing the 😱 mark. | System emoji exactly as shipped. |
| Recolouring or distorting a model provider's logo. | As shipped — see `assets/model-logos/`. |
| Text carrying a gradient, a solid step, or a non-text role. | Contracted text roles only (machine-linted upstream). |
| Cycling status colours as chart series. | The `--data-*` categorical palette, in fixed order. |
| The stock shadcn / "clean modern SaaS" look. | Mono structure; deliberate, defensible choices. |

**These override shadcn/Tailwind defaults.** Restyle primitives to these tokens — do not ship the
stock component look.

## Colour — semantic roles, never raw values

Components reference **semantic** roles, never a hex and never a primitive step directly. Each role
carries a full ladder: `-bg-subtle`, `-component`, `-component-hover`, `-component-active`,
`-border-subtle`, `-border`, `-border-strong`, `-focus-ring`, `-solid`, `-solid-hover`, `-text-low`,
`-text-high`, `-contrast-text`, `-text`.

| role | light solid | dark solid | means |
|---|---|---|---|
| `--accent` | `#4b91f0` blue | `#75affe` | **interaction** — buttons, links, focus (app register) |
| `--brand` | `#ec9f3f` gold | `#e2a35b` | brand presence; constant across surfaces |
| `--gain` | `#ec9f3f` gold | `#e2a35b` | **the win** — SOTA, leading row. Rationed. |
| `--success` | `#64e47d` green | — | verified, reproduced, healthy, active |
| `--warning` | `#efbd41` | — | needs attention |
| `--danger` | `#ff0325` red | — | destructive, failed, blocked |
| `--info` | `#4b91f0` | — | neutral notice (same family as accent) |

Neutrals: `--bg` (page floor) · `--surface` (panels, sealed by `--border`) · `--surface-2` (wells,
inputs, tracks, sealed by `--border-strong`) · `--border`, `--border-2` · `--text`, `--text-2`.
Plus `--focus` for the ring.

**Green ≠ gold.** Green marks *verified*; gold marks *the win*. They are not interchangeable.

**Contrast is engineered on APCA**: `-text-low` targets Lc 75, `-text-high` Lc 90. Use the ladder
rather than picking whichever step looks right.

**Charts** use the `--data-*` categorical palette (azure, green, rose, orange, … — **no purple**) in
fixed order, with 5-step ramps for magnitude. Triple-encode (hue + marker shape + direct end-label)
so colour-blind readers never lose the thread. Never conflate series colour with status colour.

### v1 → v2 bridge — one trap

`tokens.css` still resolves the v1 names (`--ink`, `--ink-2`, `--ink-3`, `--line`, `--line-2`,
`--gain`, `--gain-bg`, `--blind`, `--blind-bg`, `--mark`, `--cat-*`), so v1 surfaces keep working.

**But `--gain` now resolves to GOLD, where in v1 it was green.** A v1 surface using `--gain` to mean
"success" is now saying "this is the win". Migrate those to `--success-*`.

## Type — three families, strict roles

| family | token | used for |
| --- | --- | --- |
| **Parastoo** (500 display) | `--f-display` | **hero/display only, marketing only.** Never in product chrome, tables or buttons. |
| **IBM Plex Sans** (400/500/600) | `--f-sans` | load-bearing UI, body, dense data, **and the wordmark** |
| **IBM Plex Mono** (500/600) | `--f-mono` | data, labels, receipts, IDs, code, chart text |

Nine sizes, one job each: `--text-hero` (clamp 44–76, Parastoo) · `--text-display` 38 (Parastoo) ·
`--text-metric` 30 (Mono) · `--text-title` 24 · `--text-lead` 20 · `--text-body` 16 · `--text-sm` 13
· `--text-micro` 12 (Mono) · `--text-label` 11 (Mono).

Weights: 400 body/data · 500 emphasis, buttons, active nav · 600 sans titles · 500 display.
All-caps labels are mono + `--tracking-label`. Mono enforces
`font-variant-numeric: tabular-nums slashed-zero` — tabular keeps columns aligned, the slashed zero
disambiguates `0` from `O` in run IDs and receipts.

**A product surface uses two families: Plex Sans and Plex Mono.** That is the whole palette.

## Spacing, layout, geometry

- **4px scale**: `--space-1` (4) … `--space-12` (96). All padding/margin/gap.
- **Columns**: `--col` 760px (prose), `.band` 1140px (specimens, galleries). `--col-wide` 1000px
  survives from v1.
- **Square**: `--radius-none` is `0`. `--radius-window` (10px) is terminal chrome only.
- **Borders**: `--border-hairline` 1px default, `--border-strong` 2px. A border is one step stronger
  than the fill it seals.
- **Elevation reads from the seam, not blur.** Ground → `--bg`; Panel → `--surface` + `--border`;
  Inset → `--surface-2` + `--border-strong`; Float → `--shadow-window`, terminal only.

## Component recipes

Reach for these before inventing anything; all live in `reference/style.css`.

- **Buttons** — `.btn` base, then `.btn--primary` (accent-solid fill, contrast text), `.btn--sec`
  (accent outline, transparent fill), `.btn--link` (underline, no box), plain `.btn` (ink fill).
  `.sm` matches input height.
- **`table` + `th`/`td`** — hairline rows, tabular figures. The SOTA row takes `--gain` (gold) —
  **leaderboards only**; an admin table has no SOTA row.
- **`.badge`** — `.badge--ok` / `.badge--bad`, plus `.badge-verified` (green ✓, trust) and
  `.badge-sota` (gold, leaderboard only).
- **`.markbox`** — row-level ✓/✗ square, 16px (`.sm` 14px), `--ok`/`--bad` variants.
- **`.checkbox` / `.checkbox-box`** — the one toggle: drawn square, accent fill + geometric check.
- **`.status`** — inline square signal; the off-state word drops to a whisper tone.
- **`.kicker`** — mono, uppercase, 0.14em tracking, `--gain-text-low`.
- **`.note`** — callout with a strong left rule.
- **`.lead`, `.meta`, `.mono`, `.faint`, `.eyebrow`, `.kv`** — text roles.
- **`.rail` / `.masthead`** — sticky 44px (`--rail-h`) mono header.

Leaderboard-only, do not reach for on a product surface: `.stats`, `.climb`, `.deltawrap`,
`.badge-sota`, `.o-mark`, `.fusion-flow`, `.logo-*`.

## Icons

**Remix Icon** (Apache-2.0), self-hosted — no CDN. Sizes 16/20/24, default 24 (`--ic`).
Fill-based (`fill="currentColor"`): set the colour, the icon follows.

## Voice and capitalisation

Concise, credible, helpful. Lead with the outcome; show receipts; plain language; centre the reader.

| case | where | rule |
|---|---|---|
| **Sentence case** | default — buttons, titles, body, tooltips, labels, errors | first word capitalised |
| **UPPERCASE** | eyebrows, section labels, table headers, kickers | mono, tracked, ≤3 words, **CSS `text-transform` only — never typed** |
| **lowercase** | code, SDK/API names, env vars, IDs, receipts | match real casing |
| **As-branded** | proper nouns | ScreamingFace · OpenMined · benchmark names |

All-caps costs dyslexic readers 13–18% reading speed, and typed caps reach screen readers as caps —
hence CSS-only, tiny labels only.

**Titles must pass four tests:** can you visualise it; is it falsifiable; could anyone else say it
(if yes, too generic); is it true.

## Self-check before you finish

Every "yes" on the left is a violation:

- [ ] Wrong **register** — gold accent on a product surface, or blue on marketing?
- [ ] **Gold anywhere it isn't "the win"?**
- [ ] Serif in chrome, a table cell, or a button? Mono at display size?
- [ ] More than two families on this surface?
- [ ] Any **rounded corner** outside terminal chrome? Any shadow outside the terminal window?
- [ ] Any gradient that isn't `--fusion-grad` on a leading row?
- [ ] A **raw hex**, or a primitive step where a semantic role belongs?
- [ ] `--gain` used to mean "success"? (v1 habit — it is gold now; use `--success-*`.)
- [ ] Typed ALL-CAPS instead of CSS `text-transform`?
- [ ] Lorem / fake logos / placeholder metrics / undefined acronyms?
- [ ] Did you verify **both light and dark**?

## Source & drift

Canonical source: **`brand.screamingface.ai`** and the external **`screamingface-brand`** repo. The
system renders live from `tokens.json`, so the site never drifts from itself.

`reference/` holds **verbatim** copies — see **`reference/PROVENANCE.md`** for the version string
and a copy-pasteable drift check. If they diverge, **the live site wins**: re-pull and update this
file in the same change.
