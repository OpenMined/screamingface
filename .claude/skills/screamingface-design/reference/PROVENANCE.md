# Provenance of these files

**System:** ScreamingFace Design System (SFDS) **v2.0**
**Source:** `https://brand.screamingface.ai/`
**Version string served at pull time:** `?v=20260731a`
**Pulled:** 2026-07-31 (OME-715)

## The files are VERBATIM

Every file here is byte-identical to the URL it came from. Nothing is hand-edited — not even a
header comment. That is deliberate: it makes the drift check a `cmp`, not a judgement call.

The v1 snapshot (2026-06-11) hand-edited a provenance header into `tokens.css`, which meant the one
question you actually want to answer — "has upstream changed?" — could not be answered mechanically.
Hence this separate file.

| file | bytes | what it is |
|---|---|---|
| `tokens.css` | 22663 | the whole system: 12-step primitive scales, semantic roles, scalars |
| `tokens.json` | 19946 | the source of truth upstream generates `tokens.css` from |
| `style.css` | 42710 | component recipes — buttons, tables, badges, status, checkbox |
| `fonts.css` | 7100 | `@font-face` for IBM Plex Sans/Mono and Parastoo. Self-hosted, no CDN. |

## Drift check

```sh
V=20260731a   # bump to today's date-letter and see if anything moves
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
