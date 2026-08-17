---
ticket: OME-839
stack: scoreboard
status: in_review
started: 2026-08-14
finished: 2026-08-15
---

# OME-839 — adopt the leaderboard-mvp masthead nav and landing copy

## Intent

Irina, 2026-08-14 DM: implement the copy from `brand.screamingface.ai/leaderboard-mvp` more
faithfully, and add the top-right `benchmarks` / `github` / `docs` links — *"quick changes, but I
suspect it would make a difference for testers"*.

The two surfaces already share `fonts.css`, `tokens.css` and `style.css`, so this is copy and three
anchors, not a redesign.

## Decisions locked (2026-08-14)

| # | Decision | Choice |
|---|---|---|
| D1 | Adopt only the copy that is **true today** | Owner decision. About half the mockup's landing copy asserts capabilities that do not exist, and adopting it would republish the exact claims `OME-820` withdrew at `@HupBaHa`'s request over two review rounds. Deferred to `OME-770` / `OME-771`, which is when each becomes true. |
| D2 | `benchmarks` points at `index.html#benchmarks`, **not** `benchmark.html` | The mockup links bare `benchmark.html`, which works there because its board is hardcoded mock data. On live, `benchmark.js:283` calls `P.requireParam("id")`, so a bare link renders an error state. `index.html` *is* the benchmark catalogue, so it is the honest target. Verified rather than copied. |
| D3 | `.rail-link` goes in `portal.css` | It is **not** in the vendored `style.css` (grepped) — it lives in the mockup's own `board.css`. `portal.css` is the extension file, and its header rule is token-vars only, no raw values. |
| D4 | Footer: wordmark only | The mockup's right-hand cell reads *"leaderboard.screamingface.ai · MVP preview · mock data"*. That host has **no DNS record** (verified: `dig` empty, `curl` exit 6), and this data is not mock. Adopting the wordmark and dropping that line. |
| D5 | Headline left alone | The mockup's *"Fusions, ranked and reproducible."* claims reproduction the board cannot back. The live *"Results you can rerun, not just read."* is honest about what is actually on offer — a re-runnable recipe. Flagged for Irina rather than changed unilaterally, since brand voice is hers. |

## Planned changes

- `apps/scoreboard/portal/portal.css` — `.rail-link` (extension; matches the mockup's rules,
  token vars only).
- `apps/scoreboard/portal/index.html` — the three nav links; lead → the fusion definition; an
  anchorable `id` on the Benchmarks heading plus the picker sentence; footer wordmark.
- `apps/scoreboard/portal/benchmark.html`, `spec.html`, `data.html` — the same three nav
  links and footer.

## Test plan

No logic changes, so this is verified by rendering, not by assertions:

- Every portal page shows the three links, and each resolves (`index.html#benchmarks`, the GitHub
  repo, `docs.screamingface.ai`).
- Adopted copy matches the mockup verbatim.
- **No copy this change introduces claims reproduction, verification status, or cost** — the
  `OME-820` invariant. Note the scope: `index.html`'s `.note` block still carries the
  *"Verified means OpenMined independently reproduced the run"* text. That block is `#588`'s to
  remove and is untouched here; duplicating it would collide with two rounds of review.
- Rendered at desktop and mobile widths, measured in Chrome (getBoundingClientRect, not eyeballed):
  the rail must not overflow and no rail item may overlap the fixed theme toggle.

## Acceptance

- The three links appear on all three pages and resolve.
- The adopted copy is verbatim.
- Nothing this change adds claims verification, reproduction or cost.
- Full gates green.

## Outcome

Status: **DONE** (2026-08-14)

- **Actual files** (4, all as planned):
  - `apps/scoreboard/portal/portal.css` — `.rail-nav` / `.rail-link`
  - `apps/scoreboard/portal/index.html` — nav · lead · `id="benchmarks"` + picker sentence · footer
  - `apps/scoreboard/portal/benchmark.html`, `spec.html` — nav · footer
- **Gates:** `run_gates.py scoreboard --base origin/main` — ALL GREEN (append-only, ruff check,
  ruff format, pyright, pytest ≥80% cov). No Python touched; no test added — this is copy and CSS,
  and the portal has no DOM-rendering harness (its JS tests cover pure logic only).

### What the rendering check caught that the diff did not

Adopting the mockup's CSS verbatim was wrong, in both directions, because the two rails differ in
one detail the markup does not show: **here the theme toggle is `position: fixed`**
(`style.css:58` — it pins itself because the rail's sticky is defeated by the page's overflow-x
clipping), so it consumes no flex space. Measured, "◐ light" is 55px wide:

| Width | Symptom with the mockup's CSS | After |
|---|---|---|
| 1200px | the mockup's 32px end margin left `docs` **overlapping the toggle by 23px** | 25px gap |
| 375px | the rail wraps (`style.css:667`) and **`github` landed under the toggle** | links on their own row, no overlap |

Fix: group the anchors in a `.rail-nav` container — `--space-11` reserves the toggle's footprint on
desktop, `flex: 0 0 100%` moves the group to its own wrapped row on mobile. Verified on all three
pages at 1200px and 375px, light and dark, plus `.rail-link` color = `--ink-2` in both themes
(identical to the crumbs).

### Deviations from the plan

1. **`.rail-nav` container added**, not the three bare anchors the plan described — forced by the
   collision above. `.rail-link--end` and the mockup's `620px` per-link margin were both dropped;
   neither is needed once the group owns its own row.
2. **`.rail-link.here` not adopted.** Nothing sets it — the crumbs already carry the active state.
   Dead CSS.
3. **Both external links checked live**, which the plan only implied: `docs.screamingface.ai` 200
   (Cloudflare, `172.67.172.6`), the GitHub repo 200. Worth doing — the footer line this change
   *declined* to adopt names `leaderboard.screamingface.ai`, which still has no DNS record at all.
4. **"Inside, you can tab across all benchmarks" was verified before adoption**, not assumed:
   `benchmark.html:34` has `#benchmark-tabs` and `benchmark.js:258` renders the strip across every
   benchmark. True on live, not just in the mockup.

### Found, not fixed — out of scope

**`spec.html`'s crumbs collide with the theme toggle below ~400px.** At 375px the three-level trail
(`portal / leaderboard / spec`) reaches x=326 while the fixed toggle starts at x=300. Confirmed
**pre-existing**: hiding `.rail-nav` and re-measuring reproduces it, so this change neither causes
nor worsens it. Both sides are vendored CSS. Not touched here; it wants its own ticket.

## Review pass (2026-08-15) — two findings, both valid, both mine

| Finding | Verified how | Verdict |
|---|---|---|
| The `benchmarks` link parks its target under the rail | measured after `scrollIntoView()` in Chrome | **valid — the link this ticket adds does not work properly** |
| `data.html` is a fourth portal page and has no nav | `curl` on dev returned 200; reached from `main.js:280` | **valid — the ticket and PR both claimed "every portal page"** |

### The anchor lands under the masthead

I verified the `#benchmarks` target *existed* and never verified where it *lands*. The rail is sticky
at `top: 0` and its JS re-pins it as `fixed` once scrolled past (`style.css:44`), so a bare fragment
jump parks the heading beneath it. Measured: heading top at **y=7**, rail bottom at **y=44** — 37px
of a 57px heading hidden, with `scroll-margin-top: 0px` and no `scroll-padding` anywhere in the
vendored CSS.

Fixed with one additive rule, `html { scroll-padding-top: calc(var(--rail-h) + var(--space-4)) }`,
which covers every future in-page anchor rather than only this one, and reuses the same token the
rail's height uses so the two cannot drift. After: heading top **y=63**, rail bottom y=44 — **19px
clearance, 0px obscured**.

### The fourth page

`data.html` renders a published JSONL file. It is reached from the index's "Dataset" links
(`main.js:280`), it is live (`leaderboard.dev.screamingface.ai/data.html` → 200), and I never looked
past the three pages the mockup has. Both the ticket and the PR body claimed the nav appears on every
portal page; that was false until now. Nav and footer wordmark added; verified at 1200px (25px gap to
the toggle, no overlap) and 375px (nav on its own wrapped row, no overflow).

Worth keeping: "I changed the three files the design mocks up" is not the same as "I changed every
page that ships". The check is `ls *.html`, not the mockup's sitemap.

**Gates:** all green.
