---
ticket: OME-716
stack: aigateway-ui
status: done
started: 2026-07-31
finished: 2026-07-31
---

# OME-716 — re-skin the admin console on ScreamingFace Design System v2

## Intent

Owner reversal. `OME-707` vendored the **OpenMined Design System** on the reasoning that internal
operator tooling wears the parent brand. Owner: _"I was wrong giving you openmind design."_ The
console moves to **SFDS v2**. The two systems contradict each other on radius, shadows, gradients
and colour semantics, so this is a replacement, not a merge.

## Getting the register right IS the job

SFDS v2 ships two registers. `[data-brand="marketing"]` overrides **only** the accent-family
aliases; the **app register is the default**. An admin console is a technical product surface:

| role | app register | used here for |
|---|---|---|
| `--accent` | **blue** `#4b91f0` | every interaction — buttons, links, focus |
| `--brand` / `--gain` | gold | **nothing.** Gold is "rationed to the win"; there is no win here. |
| `--success` | green | account active |
| `--danger` | red | deactivate, delete profile |
| neutrals | `--bg`/`--surface`/`--surface-2`/`--border`/`--text`/`--text-2` | everything else |

The naive reading of "make it ScreamingFace" is gold everywhere plus a serif headline. Both are
v2 **anti-rules**. A correct re-skin of this surface is mostly neutral with blue interaction, and
the acceptance test asserts zero gold rather than trusting me.

## An accessibility note that gets BETTER

The OMDS build carries six comments working around contrast, e.g. _"green-600 text on this surface
is 3.2:1 and fails AA at 14px, so hover moves the underline instead of the label"_. Those existed
because OMDS exposes palette steps and leaves the contrast maths to the caller.

v2 is **APCA-solved and exposes the answer**: `-text-low` targets Lc 75, `-text-high` Lc 90. So the
workarounds are replaced by simply using the right rung. Where a v1 comment says "cannot colour this
text", v2 has a token for exactly that.

## Planned changes

- `src/brand/` — replace the three OMDS files with SFDS v2 `tokens.css`; new `README.md`
- `src/app/globals.css` — rewritten against v2 roles (671 lines)
- `src/app/accounts/[id]/detail.module.css`, `credentials/new/form.module.css` — same
- `src/app/layout.tsx` — fonts Inter/Rubik → IBM Plex Sans/Mono
- `stylelint.config.mjs` — retarget the token-file exemption
- `apps/aigateway-ui/CLAUDE.md` — currently states OMDS is design law and explicitly says *not* the
  screamingface-design skill; that is now exactly backwards
- a test asserting the register rules hold

## Preserve — each has a test

`OME-709`'s four fixes must survive:

1. theme switch defaulting to **dark**, applied pre-paint by the served `theme-init.js` (no flash)
2. full-bleed, **no `max-width` anywhere** (owner decision)
3. search button aligned to its input (`flex-wrap: nowrap` + `flex: 0 1 20rem`)
4. the "New tenant" `<dialog>` centred — **v2's reset will strip `margin: auto` the same way OMDS's
   did**, so the fix must be re-applied, not assumed

## Test plan

- existing 181 tests still pass (they assert behaviour, not colour, so they should be untouched)
- new: the rendered CSS contains **no gold token reference** (`--brand-`, `--gain-`) — asserted
- new: no `border-radius` other than 0, and no `box-shadow` (v2 anti-rules), asserted over the
  app's own CSS
- `lint:css` still blocks raw colour, retargeted at the new token file — including the shorthand
  bypass (`border: 1px solid rgb(...)`) that the OMDS gate originally missed
- browser: both themes, all three pages, dialog open/close

## Acceptance

- no OMDS token remains anywhere
- `run_gates.py aigateway-ui` green
- the four `OME-709` behaviours hold
- zero gold, zero serif, zero radius, zero shadow — asserted not eyeballed
- light and dark both verified

## Outcome

- **Gates:** `run_gates.py aigateway-ui` green. **218 tests**, up from 181 — 35 of the new ones are
  `design-system.test.ts`, plus two the re-skin exercised.
- **No OMDS token remains.** Swept for every one of the 39 distinct tokens the old CSS referenced;
  zero hits. The remaining textual mentions of "OMDS" are historical comments explaining why v2 is
  better at a particular thing.

- **Measured in a real browser, both themes, not eyeballed:**

  | | dark | light |
  |---|---|---|
  | `data-theme` | `dark` (default preserved) | `light` after toggle |
  | body background | `rgb(5,7,11)` = v2 `--bg` | `rgb(252,253,255)` = v2 `--bg` |
  | **gold painted** | **0 elements** | **0 elements** |
  | rounded corners | 0 | 0 |
  | shadows | 0 | 0 |
  | serif elements | 0 | 0 |
  | `main` width vs viewport | 1920 / 1920 | 1920 / 1920 |
  | `data-brand` | `null` — app register, not marketing | `null` |

  The gold check is the load-bearing one: `--gain-solid` **resolves** to `#e2a35b`, so the token is
  present and correct — and nothing on the page paints with it.

- **All four `OME-709` behaviours re-verified after the re-skin:** theme defaults to dark and the
  switch flips the document; layout is full-bleed; the search input and its button are **3px** apart
  on the vertical (aligned); the dialog opens **centred on both axes**, with `margin: auto`
  re-applied because v2's reset strips it exactly as OMDS's did.

## Deviations from the plan

1. **`base.css` is written, not vendored.** The plan said "replace the three OMDS files". Upstream's
   `style.css` is 42 KB of the brand site's own stylesheet — `.rail`, `.masthead`, `.stats`,
   `.climb`, `.logo-band`, the fusion gradient, the leaderboard table. Almost none applies to an
   admin console, and the parts that do are already this app's `.ui-*` primitives. Vendoring it
   would ship ~40 KB of leaderboard CSS that also competes with the app's own classes. Only
   `tokens.css` is vendored; `base.css` is a small element-defaults layer that adds no values.

2. **Parastoo is not loaded at all.** Planned as a straight font swap. It is v2's display face and
   is display/marketing-only — "never serif in product UI chrome, table cells, or buttons" — and
   this console has no display type, so loading it costs bytes for a face nothing may use.
   `--f-display` is aliased to Plex Sans so a stray reference degrades correctly instead of falling
   back to a system serif.

3. **Two hardcoded font stacks were found and removed.** `detail.module.css` set
   `Consolas, Monaco, "Andale Mono", "Ubuntu Mono", monospace` in two places. A font stack is
   invisible to the colour gate, so it had survived the whole OMDS build. `design-system.test.ts`
   now asserts every `font-family` is a `--f-*` token.

4. **`theme.test.tsx` was NOT updated**, though its title still says "OMDS tokens". The
   append-only test gate refused the edit (sdlc rule 5: changing a prior test is a Confidence-Gate
   decision). The assertion is correct and unchanged — only the title string is stale. Reverted
   rather than argued with, and recorded here so it is a known cosmetic wart, not a silent one.

5. **`.pre-commit-config.yaml`** — no change needed here, but note `OME-715` excluded the vendored
   reference from the rewriting hooks for the same reason this app's `tokens.css` must not be
   reformatted.

## Two things worth keeping

**v2 made the accessibility story simpler, not harder.** The OMDS build carried six comments
working around contrast ("green-600 text is 3.2:1 and fails AA at 14px, so hover moves the underline
instead of the label"). v2 is APCA-solved and exposes the answer as `-text-low` (Lc 75) /
`-text-high` (Lc 90), so those workarounds are gone: links can simply *be* the accent colour, and
`--accent-contrast-text` states what is legible on a fill rather than leaving it to a judgement
call.

**A dev-server artefact cost time and was not an app bug.** Browsing `127.0.0.1:9107` while Next
serves `localhost` trips its cross-origin dev-resource block, which silently prevents the client
bundle loading — so React never hydrates, the theme switch is dead and the dialog will not open,
with **no console error**. On `localhost` everything works. Worth knowing before diagnosing a
"broken" client component.
