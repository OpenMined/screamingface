# src/brand — vendored OpenMined Design System

Copied from [`OpenMined/brand.openmined.org`](https://github.com/OpenMined/brand.openmined.org)
per that repo's "Using in a project" instructions.

- **Upstream commit:** `af7d344318d4b0afb4493393c1b2ced52ac9facb` (2026-07-08) —
  also recorded in `brand-version.txt`, which is the audit trail.
- **What was copied:** `src/tokens/` only — `tokens.css`, `global.css`, `typography.css`.
- **What was not:** `src/components/`. Those are `.astro` files and this is a React app; the
  primitives are reimplemented in `src/components/` as React (OME-708). The token files are
  plain CSS custom properties and port unchanged.

`tokens.css` is the single place literal palette values may live. Everywhere else references a
token via `var(--…)` — enforced by `stylelint.config.mjs`, which fails CI on any raw hex, named
color, or `rgb()`/`hsl()` literal on a color property.

## Documented divergence

One edit was made to the copied files, sanctioned by upstream's rule that *"any edits to files in
`src/brand/` are intentional project-specific divergence — document what changed and why."*

**Font family names are aliased to CSS variables.** Upstream hardcodes `'Inter'` and `'Rubik'`
(20 occurrences across `global.css` and `typography.css`) and loads them with a `<link>` to Google
Fonts. This app loads them through `next/font/google`, which self-hosts the files at build time
and exposes them as generated CSS variables — it cannot publish a font under a chosen family name.
So every `'Inter'` became `var(--font-inter)` and every `'Rubik'` became `var(--font-rubik)`; the
variables are bound in `src/app/layout.tsx`.

This is strictly closer to upstream's own stated intent than the `<link>` it replaces —
`typography.css` carries a TODO to *"replace with self-hosted woff2 files per Decision #18 before
production."* Self-hosting also matters here specifically: this console is internal tooling behind
Cloudflare Access, and a third-party font request from an admin page is both a leak and a failure
mode.

## Re-syncing

Pull the newer upstream `src/tokens/`, re-apply the font aliasing above, update
`brand-version.txt`, and re-run `npm run lint:css`.
