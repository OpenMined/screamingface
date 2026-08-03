---
ticket: OME-715
stack: repo
status: done
started: 2026-07-31
finished: 2026-07-31
---

# OME-715 — re-sync the screamingface-design skill to SFDS v2

## Intent

`.claude/skills/screamingface-design/reference/` is a snapshot dated **2026-06-11**. The live system
is **SFDS v2.0**, served today as `?v=20260731a`. The skill's own drift rule applies verbatim:
"If they diverge from the live site, the live site / brand repo wins — re-pull and update this
snapshot."

They diverge structurally.

| | snapshot (v1) | live (v2) |
|---|---|---|
| custom properties | **74** | **628** |
| `tokens.css` | 2.5 KB | 22.6 KB |
| color model | flat semantic tokens | 12-step primitive scales + semantic roles, APCA-solved |
| display font | EB Garamond | **Parastoo** |
| wordmark font | Rubik | **IBM Plex Sans** |
| `--gain` | green `#0f7a3d` | **gold** `#ec9f3f` |
| accent | *(none)* | **blue `#4b91f0`** in the app register |
| text scale | 7 sizes | 9 (adds `--text-hero`, `--text-title`) |
| radius | `0` | `0` + `--radius-window: 10px` |
| shadow | none | `--shadow-window`, used exactly once (terminal) |

## Why this blocks the re-skin rather than following it

v2 ships **two registers**. `[data-brand="marketing"]` overrides only the accent-family aliases;
the **app register is the default**, where `--accent` is blue and gold is `--brand`/`--gain`,
"rationed to the win".

The current SKILL.md asserts the opposite for a product surface: that colour means only gain-green /
blind-red / mark-amber, and that EB Garamond carries `h1`. An agent following it would build
something v2 forbids — gold everywhere and a serif headline, against the explicit anti-rule
"never serif in product UI chrome, table cells, or buttons". `OME-716` is exactly that surface, so
the reference has to stop lying first.

## Planned changes

- `reference/tokens.css`, `reference/tokens.json`, `reference/style.css` — re-pull **verbatim**
- `reference/fonts.css` — new in v2 (the site self-hosts; there is no font CDN)
- `reference/PROVENANCE.md` — new. Records the URLs, the version string and the drift check, so the
  files stay byte-identical to upstream and a future check is a diff rather than a judgement call.
  (The v1 snapshot hand-edited a header into `tokens.css`, which made exactly that comparison
  impossible.)
- `SKILL.md` — rewrite the colour table, the type table and the anti-rules; add the register split

## Test plan

Documentation, so the checks are mechanical rather than behavioural:

- each `reference/` file byte-matches the live URL it came from (`cmp`, not eyeballing)
- `SKILL.md` contains no claim contradicted by the live anti-rules — specifically no "gain = green",
  no "EB Garamond", no "Rubik", no "no purple" phrasing that v2 replaced
- the back-compat bridge is documented, since `--ink`/`--line`/`--gain` still resolve and existing
  surfaces depend on them

## Acceptance

- `reference/` verbatim at a recorded version, drift check written down
- `SKILL.md` states the app/marketing register split
- nothing in the repo still reads the v1 semantics as current

## Outcome

- **Four files re-pulled verbatim** and verified by re-fetching and `cmp`-ing, not by eye:
  `tokens.css` (22663), `tokens.json` (19946), `style.css` (42710), `fonts.css` (7100) — all four
  report `identical` against the live URLs at `?v=20260731a`.
- **`SKILL.md` rewritten** against v2. Verified mechanically that no stale v1 claim survives as
  current guidance (`EB Garamond`, `Rubik` → 0 occurrences) and that the load-bearing new concepts
  are present (the register split, Parastoo's display-only scope, gold-as-the-win, `--success` as
  the verified colour, APCA).
- **`reference/PROVENANCE.md` added** with the version string and a copy-pasteable drift check.
  Run at the end of this work: all four identical.

## Deviations from the plan

1. **`reference/starter.html` was DELETED, not re-pulled.** It no longer exists upstream — the URL
   now returns the SPA's `index.html` fallback (161247 bytes, the same byte count as `/`, which is
   how a 404 shows up on this host). The stale v1 copy hardcoded `EB Garamond` and `Rubik`, so it
   was actively teaching the wrong system. A skeleton that contradicts the guide is worse than no
   skeleton. Recorded in `PROVENANCE.md` rather than dropped silently.

2. **Provenance moved OUT of `tokens.css` into its own file.** The v1 snapshot hand-edited a header
   comment into `tokens.css`, which meant the file could never be byte-compared against upstream —
   so the one question worth asking, "has this drifted?", required reading and judging rather than
   running `cmp`. Keeping the copies verbatim makes the check mechanical.

3. **The v1 → v2 `--gain` trap is documented prominently.** Not in the plan because I had not yet
   read the bridge. `--gain` still resolves, but it now resolves to **gold** where v1 had it green.
   Any surface using `--gain` to mean "success" silently changed meaning to "this is the win". That
   is the kind of change that produces a plausible-looking wrong result, so it is called out in
   both `SKILL.md` and `PROVENANCE.md`.

4. **`.pre-commit-config.yaml` now excludes `reference/` from the two rewriting hooks.** Not in the
   plan — found by the commit failing. `end-of-file-fixer` appended a newline to `tokens.json`,
   taking it from 19946 to 19947 bytes and **breaking the `cmp`-against-upstream drift check the
   file exists to support**. A one-byte edit that silently turns "verbatim" into "nearly verbatim"
   is exactly the failure this whole issue is about: the v1 snapshot became un-checkable the same
   way. Vendored third-party content is not ours to format.

## Note for the next reader

`reference/` is now verbatim upstream. **Do not hand-edit these files** — edit `SKILL.md` (our
interpretation) or re-pull (upstream's content). Mixing the two is what made the v1 snapshot
un-checkable.
