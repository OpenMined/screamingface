# Provenance of these files

**System:** ScreamingFace Design System (SFDS) **v2.0**
**Source:** `https://brand.screamingface.ai/`
**Version string served at pull time:** `?v=20260807`
**Pulled:** 2026-08-07 — re-sync; drift found against the 2026-07-31 pull (`tokens.css`,
`tokens.json`, `style.css` all moved; `fonts.css` unchanged)

## The files are VERBATIM

Every file here is byte-identical to the URL it came from. Nothing is hand-edited — not even a
header comment. That is deliberate: it makes the drift check a `cmp`, not a judgement call.

The v1 snapshot (2026-06-11) hand-edited a provenance header into `tokens.css`, which meant the one
question you actually want to answer — "has upstream changed?" — could not be answered mechanically.
Hence this separate file.

| file | bytes | what it is |
|---|---|---|
| `tokens.css` | 22874 | the whole system: 12-step primitive scales, semantic roles, scalars |
| `tokens.json` | 20133 | the source of truth upstream generates `tokens.css` from |
| `style.css` | 52302 | component recipes — buttons, tables, badges, status, checkbox |
| `fonts.css` | 7100 | `@font-face` for IBM Plex Sans/Mono and Parastoo. Self-hosted, no CDN. |

## Drift check

```sh
V=20260807   # bump to today's date-letter and see if anything moves
for f in tokens.css tokens.json style.css fonts.css; do
  curl -sS "https://brand.screamingface.ai/$f?v=$V" | \
    cmp -s - ".claude/skills/screamingface-design/reference/$f" \
    && echo "  $f  identical" || echo "  $f  DRIFTED"
done
```

Any `DRIFTED` line means re-pull and re-check `SKILL.md` against the live guide — **the live site
wins**, always.

The live page links exactly three stylesheets, in this order: `fonts.css`, `tokens.css`,
`style.css`. If that list changes, this file is out of date too.

## What changed from the 2026-07-31 pull to 2026-08-07

`tokens.css`: nested-scope selector added so `[data-brand="marketing"]` resolves both when set on
the themed root itself *and* when set on a surface nested inside a dark page (a marketing section
embedded in a dark product page).

`tokens.json`: two `$description` fixups only, no value changes — wordmark note now says Rubik was
retired 2026-07-15 (already reflected in `SKILL.md`); caps-label note clarifies **h2 is no longer a
label** — it's a sans display heading, not part of the mono caps-label role.

`style.css` — real component changes, not just comments:

- **Caps-label role** unified: mono, weight **500** (was 600/semibold), one tracking, and now
  includes `.kv dt`. h1/h2 display headings corrected to `--weight-display` (500) — semibold was
  itself drift from a 2026-07-16 decision.
- **`--ink-2` contrast** raised APCA Lc 60 → 75 (2026-07-17) — `SKILL.md` already documented Lc 75,
  so no doc change needed there.
- **`.badge-verified`** grew a drawn check-glyph (`::before`, masked SVG) instead of relying on
  surrounding markup for the icon.
- **New product-register components**: `.field`/`.field.dd` (labeled inline control incl.
  dropdown), `.tabs`/`.tab` (segmented control), `.th-sort` (sortable column header), `.model-ico`
  (monochrome provider-logo mask), `.score-cell`/`.score-track`/`.score-fill` (leaderboard score +
  comparison band, with `.grad` = the one sanctioned fusion-gradient fill).
- **`.btn`**: padding widened (`space-3` → `space-4`), gained a hover-inverts-to-outline state, and
  a `.ghost` (muted outline) variant. Added a `.lg` size tier alongside the existing `.sm`.
  **`.btn--sec.gain` (gold secondary button) was retired** — gold must not enter the product
  register; the marketing register already defaults its outline tier to gold, and in marketing the
  button *font* now flips to sans (mono stays the data instrument).
- **`.climb .row`** grid switched from a fixed 210px label column to a `minmax()` column so it
  compresses in narrow containers instead of starving the bar.
- **`.deltawrap .cell.before .big`** recolored from the raw `--blind` (danger) token to `--ink-2` —
  "before" is a neutral no-signal state, not an error.
- Focus rings on `.signup`/`#gate` inputs now use `--accent-solid` instead of `--ink` (focus is
  always the accent, per the interaction ladder).

None of the above are covered in `SKILL.md`'s Component recipes section yet except where noted —
see the section for what was added there in this sync.

## Removed in this sync

**`starter.html`** — deleted. It no longer exists upstream (the URL now returns the SPA's
`index.html` fallback), and the stale v1 copy hardcoded `EB Garamond` and `Rubik`, both of which v2
replaced. A skeleton that contradicts the system is worse than no skeleton.

## What changed from v1 (2026-06-11)

| | v1 | v2 |
|---|---|---|
| custom properties | 74 | **628** |
| colour model | flat semantic tokens | 12-step primitive scales + semantic roles, APCA-solved |
| display font | EB Garamond | **Parastoo** |
| wordmark font | Rubik | **IBM Plex Sans** |
| `--gain` | green `#0f7a3d` | **gold** `#ec9f3f` |
| accent | none | **blue `#4b91f0`** (app register) |
| text scale | 7 sizes | 9 (adds `--text-hero`, `--text-title`) |
| radius | `0` only | `0` + `--radius-window: 10px` |
| shadow | none | `--shadow-window`, used exactly once (the terminal window) |

`tokens.css` carries a **v1 → v2 back-compat bridge**, so `--ink`, `--ink-2`, `--ink-3`, `--line`,
`--line-2`, `--gain`, `--gain-bg`, `--blind`, `--blind-bg`, `--mark` and the `--cat-*` series all
still resolve. Existing surfaces written against v1 names will not break — but note that
**`--gain` now resolves to gold, not green**, so a v1 surface using it to mean "success" is now
saying something different. Prefer the v2 names in new work.
