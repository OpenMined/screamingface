# OME-839 — Implementation plan

Spec: `docs/spec/2026-08-14-OME-839-mvp-copy-and-nav.md` · Ledger:
`docs/work/2026-08-14-OME-839-mvp-copy-and-nav.md`

Copy and three anchors. No logic, so verification is by rendering.

## Step 1 — `portal.css`: `.rail-link`

Match the mockup's own rules (`board.css:27-30`, plus its `620px` margin rule), using token vars
only per `portal.css`'s header rule. `.rail-link--end` carries the right margin so nothing sits
under the toggle glyph.

## Step 2 — the three links, on all three pages

Insert before the toggle in each `.rail`. `github` and `docs` are external:
`target="_blank" rel="noopener"`. `benchmarks` → `index.html#benchmarks` (spec §3).

## Step 3 — `index.html` copy

- lead → the fusion definition;
- `id="benchmarks"` on the Benchmarks heading so the nav link lands;
- the picker sentence beneath it;
- footer wordmark.

## Step 4 — verify by rendering, not reading

Serve the portal locally and check in Chrome at ~1200px and ~420px:

- the three links present and resolving on all three pages;
- the rail does not wrap or overlap the toggle at mobile width;
- **grep the rendered HTML** for `verif`, `reproduc`, `cost`, `SOTA` — the `OME-820` invariant. Three
  previous passes missed a stale claim by reading the diff instead.

## Step 5 — gates, ledger, commit, PR

`run_gates.py scoreboard --base origin/main`.

## Risks

- **`#588` touches the same three files** and is unmerged; the overlap on `index.html`'s lead is real.
  It should land first. Adopting the mockup's lead preserves `#588`'s honesty fix, since the mockup's
  lead makes no verification claim — so the rebase is a text conflict, not a semantic one.
- `.rail-link` is new CSS in an extension file that forbids raw values. Use token vars.
