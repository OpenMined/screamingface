---
ticket: OME-769
stack: scoreboard
status: in_progress
started: 2026-08-12
finished:
---

# OME-769 — Leaderboard: fill the submissions board (ranked rows, core columns, SOTA medal)

## Intent

Turn the per-benchmark board shell that `OME-768` landed into the real ranked submissions table:
rows ordered by accuracy, an in-cell accuracy bar, an author column, and a SOTA medal on the top
**reproducible** entry — with a mark slot that reserves space on every row so names stay aligned
when `OME-770` adds frontier marks. Cost and the Reproducible/All toggle stay out (OME-770/771).

Three of the ticket's requested columns cannot be built from the current API and are handled by
rendering the structure without fabricating data — see Decisions.

## Decisions locked (2026-08-12)

| # | Decision | Choice |
|---|---|---|
| D1 | Row order | Accuracy desc — already the shell's default sort state; keep it and keep the existing sortable headers. |
| D2 | SOTA definition | **Top accuracy among `verified_by_openmined === true` entries**, isolated in a `pickSota()` pure function. Today's board marks *every* row tied at max accuracy regardless of verification, which contradicts the ticket ("top reproducible fusion") — so this is a behavior fix, not just an addition. **But note the definition is not settled** (see D11): `verified_by_openmined` is the only reproducibility signal the Scoreboard API exposes, while `OME-771` intends to source it from the SF engine instead. Keeping the decision inside one pure function means that swap is a one-function change, not a rewrite. |
| D3 | Mark slot | A fixed-width leading slot in the Name cell, rendered on **every** row — medal on the SOTA row, an empty spacer otherwise — so `OME-770`'s frontier mark can drop in without shifting names. **⚠️ Superseded during implementation — see Outcome deviation 2:** the in-cell slot was built, measured, and found to break the very alignment it existed for (the enhanced badge is wider than its text form, so the slot grew on the SOTA row). Shipped as its own table column instead, which meets the stated goal structurally. |
| D4 | SOTA medal visual | **Vendor the animated wave-mark, with the text form as the baseline.** Correcting an earlier wrong assumption: the assets are real and fetchable from the design origin (`brand.screamingface.ai/wave-mark.js`, 3.2 kB; `assets/mark/sf-mark-wave.webp`, 24.5 kB — both OpenMined's own work, no third-party licence), and the gold↔blue pulse is **pure CSS that needs no JS at all**. Vendor both files, same pattern as OME-768's fonts. Built as **progressive enhancement, not graceful degradation**: the badge renders plain text `SOTA` by default (correct + pulsing with zero JS), and only after the webp successfully decodes do we swap the `O` for `canvas.wave-mark` and call the script's own `window.SFWave.init()` (exposed precisely for dynamically-rendered canvases). **WHY that direction:** the documented markup is `"S"` + canvas + `"TA"`, so a canvas that fails to draw renders `S TA` with a gap — a naive fallback is worse than no enhancement. Any failure (404, decode error, no canvas, no JS, blocked script) leaves the text baseline untouched. |
| D5 | Accuracy cell | Reuse the vendored `.score-cell` / `.score-track` / `.score-fill` recipe (`style.css:395–409`) — it exists precisely for a number-plus-bar table cell. Replaces today's bare percent text. Bar width is accuracy relative to the max on screen. |
| D6 | **`Name` column** | **Keep the existing `Spec` header**, holding `spec_id`, and hang the mark slot off that cell. No name/title field exists on `Score` or in `LeaderboardEntry` (the same gap `OME-772` catalogued), so labelling the column "Name" would promise a human-readable name and deliver a technical key — the label/data mismatch `@HupBaHa` rejected on OME-768's "Submissions" column. Note in Linear as needing a real name field. |
| D7 | **`Models` column** | **Not built as "Models".** The payload carries only `ran_with_providers` (provider names) and the free-text `url4_expression`; per-member model names do not exist, and `providers.length > 1` is not a valid fusion/solo test (a provider is not a model). Keeping the existing accurate **Backends** column rather than labelling provider data "Models" — that would repeat the mislabelling `@HupBaHa` correctly rejected on `OME-768`'s "Submissions" column. Needs a backend field first. |
| D8 | **Accuracy range whisker** | **Not built.** No min/max/stddev/CI field exists anywhere in the schema, and `correct_questions` is not even exposed on the leaderboard entry. The Accuracy cell markup is structured so a whisker can be added later without reflowing the cell. |
| D9 | Summary strip | **Keep all three existing stats** (`Best accuracy` / `Specs shown` / `Verified rows`) and **add** a reproducible-qualified SOTA stat. No "fusion count": distinguishing a fusion from a solo model is not derivable from the payload (see D7), and `Specs shown` already carries the entry count honestly. The existing stats stay so they fill in naturally as the backend grows. Cheapest-run stat stays out (needs cost — `OME-770`). |
| D11 | **"Reproducible" is not yet a settled definition — verified 2026-08-12** | Re-checked after an earlier claim of mine ("no medal until `OME-414` ships, which is unassigned") turned out wrong on three counts. Corrected picture: (a) `OME-414` **is** assigned (Stephen) — the "no named operator" line is stale prose in its description, not the assignee field; (b) verification does **not** need `OME-414` to ship — `ScoreStore.mark_verified()` already exists and is tested (`store.py:311`, `test_store.py:213`), so entries can be flipped verified today by code/DB access, only an API route is missing; (c) the caching work is the enabler and is live — `OME-767` (Urgent) already has its **"zero cost verifiable re-execution"** design box ticked, with implementation tickets (`OME-777`/`781`/`782`) in review. **The load-bearing find:** `OME-771` states reproducible status is *"fetched from SF engine (have we run this URL4 before) — might need a separate ticket on Ionesio's side"*, and defines a three-way status (reproducible / third-party imported / self-reported). So the cache is intended to *be* the reproducibility signal, and the richer status model belongs to `OME-771`, not here. This unit therefore uses the only signal the Scoreboard API actually has, and does not attempt the engine lookup or the three-way status. |
| D12 | Cost is closer than previously recorded | The X-ray sheet now lists `OME-303` (real USD cost) as **"PR, not merged"** (scope trimmed: final cost only, no streamed cost), not "Not started" as an earlier pass of mine reported. Doesn't change this unit — cost stays out per the ticket — but it means `OME-770` is far less blocked than previously assumed. |
| D10 | Testing | Rendering decisions extracted as **pure functions** (SOTA selection, ordering, bar width) so they are unit-testable without a DOM; behavior verified manually in Chrome. `apps/scoreboard` has **no JS test harness at all** (no `package.json`, no vitest) — standing one up means a new toolchain, CI lane, and card-gate changes, i.e. the repo's "adding a new component" checklist. Filed as its own ticket rather than folded in here. |

## Planned changes

- `apps/scoreboard/portal/benchmark.js` — extend `COLUMNS` with an Author column; replace the bare
  accuracy text with the `.score-cell` recipe; add the mark-slot + medal rendering; fix SOTA
  selection to require `verified_by_openmined`; extend `renderSummary`. Extract `pickSota()`,
  `orderRows()`, `barWidth()` as pure, side-effect-free helpers.
- `apps/scoreboard/portal/portal.css` — mark-slot sizing/spacer and any medal chrome not already in
  the vendored recipes. **No edits to `style.css`/`tokens.css`** (byte-identical vendored copies).
- **Vendored (new, per D4):** `apps/scoreboard/portal/wave-mark.js` and
  `apps/scoreboard/portal/assets/mark/sf-mark-wave.webp`, copied verbatim from
  `brand.screamingface.ai` (upstream serves the script as `wave-mark.js?v=20260717`; record that
  version). Plus the `<script src="wave-mark.js" defer>` tag on `benchmark.html`.
- `apps/scoreboard/portal/benchmark.html` — summary-strip nodes if the existing three don't cover
  SOTA + fusion count.
- `docs/tasks/2026-08-12-OME-769-submissions-board.md` — the mirror.
- Carried in (separate commit, not part of this unit's feature work):
  `docs/tasks/2026-08-11-OME-768-...md` — close its stale `status: todo` frontmatter now that
  `OME-768` is merged and Done.

## Test plan

- **Pure-function tests first (RED):** `pickSota()` — no entries; no verified entries (⇒ no medal at
  all, not "fall back to unverified"); a single verified entry; ties at max verified accuracy;
  a higher-accuracy *unverified* entry that must NOT take the medal (the D2 invariant). These tests
  pin the *invariant* ("only a reproducible entry may wear the medal"), not the current *source* of
  that signal — so when `OME-771` re-sources it per D11, the tests stay valid and only the
  predicate inside `pickSota()` changes.
  `orderRows()` — accuracy desc, stable for ties. `barWidth()` — zero, max, and a mid value; guards
  against divide-by-zero when the max is 0.
- No backend/API change in this unit, so `apps/scoreboard`'s pytest suite is a regression check
  only — re-run and expect unchanged counts.
- Manual/visual in Chrome, against a locally seeded benchmark with a deliberate mix: verified and
  unverified entries, a tie at top accuracy, one row with no `url4_expression`, one with a null
  `submitted_by`, and the zero-entry case (must keep `OME-768`'s empty shell intact).
- Light + dark theme; confirm names stay left-aligned across medal and spacer rows.
- **Wave-mark fallback (D4), tested by breaking it on purpose:** the badge must read `SOTA` with the
  pulse intact when the webp is unreachable — verify by renaming the asset / blocking the request in
  DevTools, and confirm the rendered text is `SOTA` and never `S TA`. Also confirm the enhanced path
  actually engages when the asset loads (canvas present, `data-wave-init` set, no console errors),
  and that `prefers-reduced-motion` yields a single static frame rather than a loop.

## Acceptance

- Rows ranked by accuracy; the medal sits on the top **verified** entry and nowhere else.
- Non-SOTA rows render a spacer so the Name column aligns — verified by measuring the rendered
  text offset, not by eyeballing.
- Author renders (`submitted_by`, em-dash when null); accuracy shows value + bar; url4 copy still
  works; `OME-768`'s empty-state shell still renders when a benchmark has no scores.
- Summary strip shows reproducible SOTA + fusion count.
- No fabricated data: no column claims to show models, and no whisker is drawn.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** As planned, plus two beyond it —
  `apps/scoreboard/portal/leaderboard-logic.js` (the pure decisions),
  `apps/scoreboard/tests/portal/leaderboard-logic.test.js` (14 tests),
  `apps/scoreboard/portal/wave-mark.js` + `assets/mark/sf-mark-wave.webp` (vendored per D4),
  and edits to `benchmark.js` / `benchmark.html` / `portal.css`.
- **Gates:** `run_gates.py scoreboard --base origin/main` → append-only ✓, ruff check ✓,
  ruff format ✓, pyright ✓, pytest --cov ✓. ALL GATES GREEN.
  `node --test tests/portal/leaderboard-logic.test.js` → 14 passed, 0 failed.
- **Verification:** seeded a deliberate mix — `unverified-top` at 0.99 (unverified),
  `verified-mid` at 0.62 (marked verified via the DB), `low-no-extras` at 0.15 with a null
  author. Measured in Chrome, not eyeballed:
  - **D2 invariant holds:** the 0.99 unverified row carries no medal; the 0.62 verified row
    does. Summary reads `Best accuracy 99.0%` beside `SOTA (reproducible) 62.0%`.
  - **D3 alignment holds at 297px across all three rows**, including with the enhanced badge
    present, and again in the fallback state.
  - **D4 fallback proven by breaking it:** with the webp removed (404) the badge reads
    `SOTA`, no canvas is injected, `data-mark-enhanced` is never set, and alignment survives.
    With the asset present the canvas paints (30×30, `data-wave-init="1"`).
  - Null author renders an em-dash; OME-768's empty shell still renders (9 headers, 0 rows,
    no stray badge); page body never scrolls horizontally.
- **Deviations:**
  1. **A JS test harness was feasible after all, so this unit is properly TDD'd.** D10 assumed
     tests needed a new toolchain; Node 24 ships `node:test`, so the RED tests were written
     first against **zero** new dependencies — no `package.json`, no vitest. The tests were
     mutation-checked (inverting `isReproducible` fails exactly the 3 guarding tests). The
     follow-up ticket therefore narrows from "stand up a harness" to "wire
     `node --test tests/portal/` into `scoreboard-tests.yml` + the sdlc card's gate list",
     which is why it is still not wired into CI here.
  2. **The mark went into its own column, not a span inside the spec cell.** OME-769 words it
     as "a spacer for non-SOTA rows so names stay aligned"; an in-cell fixed-width slot was
     built first and **failed that very goal** — the enhanced badge (`S` + canvas + `TA`)
     renders wider than its text form, so the slot grew on the SOTA row and pushed that name
     ~64px right of the others, and it also stole width from `.cell-wrap`'s 192px cap and
     wrapped long spec names onto two lines. A column cannot drift for either reason. The
     ticket's stated purpose is met; its literal "spacer" mechanism is not.
  3. **The `Questions` column was removed** (owner-approved). Adding Author + the mark column
     pushed the table from exactly-fitting to 1205px inside a 958px container, putting the
     url4 copy button — the board's primary action — behind a horizontal scroll. Questions is
     absent from OME-769's column list and still shown on each spec's detail page.
  4. **The table still overflows by ~134px and I flagged this rather than trim further.**
     Dropping Questions recovered 113px, less than the ~247px needed. `.wrap.wide` is already
     the design system's widest container (`--col-wide: 1000px`), and the remaining width is
     genuine content (a 19-character author email, a full timestamp). The overflow is
     correctly contained — `.table-wrap { overflow-x: auto }` scrolls, the page body does not,
     and Run Locally is reachable — so this is the system's sanctioned behavior for a wide
     table, not a break. `OME-771` replaces the Verified column with a Status column and may
     reclaim the difference.
  5. **`renderClimb` was changed beyond the ticket's scope, to prevent a self-contradiction.**
     Its "sota" gradient fill keyed off the raw maximum accuracy, so once the table's medal
     became reproducible-only the chart would have painted the unverified top row in the win
     colour while the table withheld the medal from it — one story colour asserting two
     different things on the same page. It now reads from the same `L.isSota`.
  6. **`prefers-reduced-motion` was verified by reading the vendored source, not by running
     it.** `wave-mark.js` documents the contract and implements it
     (`if (reduced.matches) { still(); return; }` — one static frame, no loop), and the file is
     byte-identical to upstream, but the available tooling cannot emulate the media query, so
     this is a source-level check rather than an observed one.
  7. Rendering beyond these pure functions remains covered only by manual verification —
     unchanged from OME-768 and the reason deviation 1's follow-up matters.


## Review round 2 (PR #569 — @HupBaHa, 2026-08-12)

Five findings, all verified against the code before acting; all five valid.

**P1 — the SOTA medal could name the wrong reproduced winner. Descoped (owner decision).**
`entries` is built by `RowNumber().over(spec_id).orderby(accuracy DESC, submitted_at DESC)` — one
row per spec, verification never consulted. A spec holding a verified 0.80 and an unverified 0.90
returns only the 0.90, so the verified run is invisible to any client and the medal could badge a
lower verified spec, or none. Working through the fix showed a **second** problem the reviewer's
suggested server-computed SOTA field would not solve: if the winner is a row the table does not
contain, there is no truthful row to badge. `OME-771` filters the pool in the *query*, making the
verified run a real row — the medal moves there. Removed with it: the reproducible-SOTA stat, the
`.badge-sota` rendering, `enhanceSotaMark`, and the vendored `wave-mark.js` +
`assets/mark/sf-mark-wave.webp`. `sotaAccuracy`/`isSota` are retained and still tested, carrying an
`AIDEV-NOTE` explaining why they are not yet called.

**Findings 2 and 4 were resolved *by* the descope, not patched separately.** `.stats` is
`repeat(3,1fr)` above 620px with border rules assuming three cells, so the fourth stat produced a
3+1 layout with "Verified rows" alone at one-third width; and both `summary-best` and
`summary-sota` carried `.gain`, painting two different numbers as the win. Dropping the fourth stat
fixed both at once — verified: `statCount: 3`, `gainCount: 1`.

**Finding 3 — `--text-xs` does not exist.** The scale is `--text-2/-body/-display/-hero/-label/
-lead/-metric/-micro/-sm/-title`. The rule became dead code with the badge and was removed. **This
is the same failure mode as the `--accent` bug found in PR #558** — a plausible-looking token name
used without grepping the token list. The lesson is procedural, not local.

**Finding 5 — missing SDLC artifacts.** Accurate, and worse than stated: this ledger's own
"Planned changes" listed `docs/tasks/2026-08-12-OME-769-submissions-board.md` and it was never
created, while `OME-768` shipped all three artifacts. Added `docs/tasks/`, `docs/spec/`, and
`docs/plan/` for this unit, with a provenance note recording that the decisions were made before
implementation but originally lived only in this ledger.

**Row highlight reworded rather than removed (spec D12).** The gold row now marks the highest
accuracy on screen and says `(highest accuracy)`; the previous
`(state of the art, independently reproduced)` was false whenever the leader was unverified —
which is the live state of the dev board. `renderClimb` keys off the same raw maximum, so the two
agree.

**Self-inflicted bug caught by re-testing:** the bulk deletion that removed `enhanceSotaMark` also
removed `renderAccuracyCell`, which sat between it and `renderBody`. That threw and left the whole
table hidden. Restored; found only because the board was re-driven in Chrome after the edit rather
than assumed correct.

**Post-descope verification:** wrap visible, 2 rows, `statCount: 3`, `gainCount: 1`,
`anyBadge: false`, gold row = `unverified-top` with `(highest accuracy)`, bars `100%`/`62.6%`, no
`wave-mark` request, table overflow reduced 134px → 72px. JS tests 14/14. All gates green.
