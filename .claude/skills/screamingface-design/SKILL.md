---
description: ScreamingFace brand & design system — the single visual law for ALL UI/UX work in this repo (website, app, cloud, demos, charts, components, copy). Use whenever building, styling, or reviewing any frontend surface; choosing colors, type, or spacing; or making a design/layout/visual decision. Overrides shadcn/Tailwind defaults. Parsed from brand.screamingface.ai.
user_invocable: true
---

# ScreamingFace Design System

This is the canonical look-and-rules for everything we ship. The audience is **policy and science leadership, not only developers**, so the surface has to **earn trust at a glance**. One system, applied everywhere — website, Electron app, cloud webapp, demos, charts, and copy.

> **The direction — "infra-retro-modern."** The precision of a developer-infrastructure tool with a terminal-retro backbone: **monospace structure, hairline rules, square corners, true white and true dark.** Color is rationed — it appears only to help the reader follow the story. Retro, not messy. We argue that AI should be *honest*; the surface should feel honest too.

When you touch any UI/UX, follow this skill over framework defaults. The exact tokens and component CSS are in `reference/` — read them when you need precise values.

## The five principles

1. **Evidence over adjectives.** Lead with the number, the run, the source. If we can't back it up, we don't say it.
2. **Structure you can see.** Hierarchy comes from type and rules, not decoration.
3. **Color means something.** Greys carry the page; the accent only marks the thing the reader should understand.
4. **Legible at small sizes.** This holds dense tables and footnotes. Type is chosen for that.
5. **Light and dark are equals.** Both are designed, not one tinted from the other.

## Anti-rules — NOT vibe-coded (hard rules, not suggestions)

The fastest way to look auto-generated in 2026 is to accept the defaults. **Never do the left column. Do the right.**

| NEVER | INSTEAD |
| --- | --- |
| Gradients — **especially blue→purple**. | Flat color fills only. |
| Rounded corners. Radius is `0`. | Square edges + hairline borders. |
| Drop shadows, glows, glassmorphism, blur. | Depth from spacing and rules, not shadow. |
| Gradient or glowing text. | Real type hierarchy; one accent for the story. |
| Emoji as bullets, ✨ decoration. | The 😱 mark, once — never as decoration. |
| **Purple. Any purple.** | The greyscale palette + the one semantic accent. |
| Hero + three feature cards + bento grid. | Left-aligned, document-like, generous space. |
| The default **shadcn / "clean modern SaaS" look**. | Monospace structure; deliberate, defensible choices. |
| Lorem, fake logos, vanity metrics, undefined acronyms. | Real data, real labels, real receipts. |
| Motion to impress. | Motion only where it clarifies. |

**These override shadcn/Tailwind defaults.** When working in the React/Tailwind/shadcn app or cloud webapp: restyle primitives to these tokens (square corners, hairline borders, no shadow, semantic colors) — do **not** ship the stock component look.

## Color — semantic tokens only

Components reference **semantic** tokens (`var(--ink)`, `var(--gain)`…), **never raw hex and never a primitive directly.** The page is **near-monochrome on purpose.** Only two roles carry chromatic meaning:

- **`--gain`** (green) = the model can read the source → correct / SOTA / the win.
- **`--blind`** (red) = guessing without the source → the "before".
- **`--mark`** (😱 amber) = a UI spark only. **Never** use it to encode data.

Everything else is greyscale (`--bg`, `--surface`, `--surface-2`, `--ink`, `--ink-2`, `--ink-3`, `--line`, `--line-2`).

| token | light | dark | role |
| --- | --- | --- | --- |
| `--bg` | `#ffffff` | `#0a0b0d` | page background (true white / true dark) |
| `--surface` | `#f6f6f7` | `#131519` | raised panel / code / hover |
| `--surface-2` | `#efeff1` | `#1a1d22` | second surface |
| `--ink` | `#16181d` | `#e8eaed` | primary text |
| `--ink-2` | `#585d67` | `#9aa0aa` | secondary text |
| `--ink-3` | `#8b909a` | `#686e78` | muted / labels / captions |
| `--line` | `#e6e7ea` | `#20232a` | hairline border |
| `--line-2` | `#d4d6db` | `#2c303a` | stronger divider |
| `--gain` | `#0f7a3d` | `#35d07f` | correct / SOTA / win |
| `--gain-bg` | `#e8f3ec` | `#11241b` | SOTA row / gain note tint |
| `--blind` | `#b23b3b` | `#f0726f` | guessing / before |
| `--blind-bg` | `#f6e7e6` | `#2a1715` | blind tint |
| `--mark` | `#c9821f` | `#e0a23c` | 😱 UI spark — never data |

**Charts comparing many series** use the 8-color categorical palette `--cat-blue, --cat-green, --cat-amber, --cat-rust, --cat-teal, --cat-rose, --cat-brown, --cat-slate` — colorblind-aware, **no purple**, assigned **in that order**, theme-shared, and kept distinct from `--gain`/`--blind`. Full set in `reference/tokens.json` / `reference/tokens.css`.

## Type — four families, strict roles

| family | token | used for |
| --- | --- | --- |
| **EB Garamond** (old-style serif) | `--f-display` | **h1 / display only.** Timeless, credible — deliberately *not* a tech/mono serif. |
| **IBM Plex Sans** | `--f-sans` | body prose, dense small text |
| **IBM Plex Mono** | `--f-mono` | data, labels, code, h2, the rail, chart text |
| **Rubik** | `--f-wordmark` | the wordmark / logo lockup **only** (OpenMined family) |

**Seven sizes, one job each** (one of these maps to everything):

| token | size | role |
| --- | --- | --- |
| `--text-display` | 38px | h1 (Garamond) |
| `--text-metric` | 30px | big stat numbers (Mono) |
| `--text-lead` | 20px | the one opening line (Sans) |
| `--text-body` | 16px | all prose (Sans) |
| `--text-sm` | 13px | captions, tables, climb, buttons |
| `--text-micro` | 12px | chart ticks/labels, rail, footer (Mono) |
| `--text-label` | 11px | ALL uppercase labels: eyebrow, h2, kickers, table headers (Mono) |

All-caps labels use **mono + `--tracking-label` (0.1em)**. Big numbers use `font-variant-numeric: tabular-nums`. Weights are only 400 / 500 / 600.

## Spacing, layout, geometry

- **4px spacing scale**: `--space-1`(4) … `--space-12`(96). Use these for all padding / margin / gap.
- **Column**: `--col` 760px (reading), `--col-wide` 1000px (dense). Content is left-aligned and document-like.
- **Square**: `--radius-none` is `0`. **No exceptions.**
- **Borders**: `--border-hairline` 1px (default), `--border-strong` 2px (emphasis accents, e.g. the left rule on a note).
- **Rail**: a sticky 44px (`--rail-h`) mono header — wordmark, crumbs, theme toggle. See `.rail` in `reference/style.css`.

## Component recipes

Reach for these before inventing anything. Each lives in `reference/style.css`; structures are in the parsed demo/viz pages.

- **`.stats`** — 3-up big-number row. The win number gets `.gain`. Use for the headline metrics ("45% → 91%").
- **`table` + `tr.sota`** — leaderboard of reproducible runs. Mono, `--text-sm`, numeric columns get `.num` (right-aligned tabular-nums). The SOTA/best row is `tr.sota` (gain-bg tint + inset gain bar on the first cell).
- **`.climb`** — staged horizontal-bar progression (label / track / value rows under `.stage-head` group headers). Fill variants: `.base` (frontier alone), `.ens` (ensemble), `.priv` (one model + source), `.sota` (the win). Use to show "why it climbs".
- **`.deltawrap`** — before / `+Δ` / after big-delta panels. `.cell.before .big` is `--blind`, `.cell.after .big` is `--gain`, the `.mid` cell holds the delta. Use for "one thing changed".
- **`figure` + `.svg-*` hooks** — charts (e.g. accuracy×cost Pareto). All chart text is mono/micro. Use the theme hooks (`.svg-ink`, `.svg-line`, `.svg-axis`, `.svg-gain`, `.svg-blind`, `.svg-base`) so SVGs follow the theme. Draw markers **after** lines; circles get a `--bg` halo via `paint-order: stroke`. Caption in `figcaption`.
- **`.note` / `.note.gain`** — callout with a strong left rule + `.kicker` label. `.gain` variant for the positive "what this means" note.
- **`.btn` / `.btn.ghost`** — square mono buttons (solid ink fill / outline ghost), invert on hover.
- **`pre` with `.ok` / `.dim`** — terminal-style command blocks ("run it yourself"). `.ok` = gain, `.dim` = muted.

A full canonical page shell (fonts + tokens + rail + masthead + a `.stats` block + theme toggle) is in `reference/starter.html` — copy it as the skeleton for any new static surface.

## Voice (copy is design too)

Per OpenMined: **concise, credible, helpful.** Write to be useful, not to sound impressive.

| do | don't |
| --- | --- |
| Lead with the outcome, then how it works | Overclaim or speculate |
| Show receipts — numbers, links, names | Buzzwords / corporate jargon |
| Plain language; define acronyms once | Fear-based messaging |
| Center the reader and the outcome | Center ourselves |

**Titles must pass four tests:** can you visualize it; is it falsifiable; could anyone else say it (if yes, too generic); is it true. Draft 5–10 before choosing.

## Self-check before you finish

Run this against your own output — every "yes" in the left list is a violation to fix:

- [ ] Any **purple** anywhere?
- [ ] Any gradient, drop shadow, glow, blur, or glassmorphism?
- [ ] Any **rounded corner** (radius ≠ 0)?
- [ ] Color used for anything **other than** gain (green), blind (red), or the 😱 mark (amber)?
- [ ] A **raw hex** or a primitive token where a semantic token belongs?
- [ ] **EB Garamond** used anywhere but an h1? Mono used for a big display headline?
- [ ] Lorem / fake logos / vanity or placeholder metrics / undefined acronyms left in?
- [ ] Did you verify **both light and dark**? (They are co-equal — check the toggle.)
- [ ] Is depth coming from shadow instead of spacing + hairlines?
- [ ] Is the layout a hero + 3-cards + bento, or the stock shadcn "clean SaaS" look?

## Source & drift

Canonical source: **`brand.screamingface.ai`** (password `letmein`) and the external **`screamingface-brand`** repo. The files in `reference/` (`tokens.json`, `tokens.css`, `style.css`, `starter.html`) are a **snapshot dated 2026-06-11**. If they diverge from the live site, the live site / brand repo wins — re-pull and update this snapshot.
