**Goal:** Migrate `apps/scoreboard/portal/`'s landing (`index.html`) and per-benchmark shell
(`benchmark.html`) from the vendored SFDS v1 system to the current v2 marketing register, and add
the missing structural pieces (subtitle + submission count on catalog rows, a benchmark tab
strip, `?id=` deep-linking already exists) per OME-768's acceptance criteria. Reuse everything
already built (`main.js`'s fetch/status/format helpers, `benchmark.js`'s existing per-benchmark
render) rather than rewriting working code.

**Architecture:** No build tooling added — the portal stays plain HTML/CSS/JS, `window.ScorePortal`
namespace pattern unchanged. `main.js` gains the catalog row's subtitle/count fields and a new
`renderTabStrip` helper shared by `index.html` (not shown there) and `benchmark.html` (shown,
highlights the active benchmark).

**Tech Stack:** No dependency changes. `apps/scoreboard`'s Python/API side is untouched — this
unit is portal-only per spec's "Out of scope."

**Source:** `.claude/skills/screamingface-design/reference/{tokens,style,fonts}.css` (the v2
system to migrate to) and the current `apps/scoreboard/portal/*` files (already read in full).

## Task 1 — Design-system migration (spec D1–D3, D7, D12)

- Replace `apps/scoreboard/portal/tokens.css`, `style.css` with byte-identical copies of
  `.claude/skills/screamingface-design/reference/tokens.css`, `style.css`. Add `fonts.css` (new
  file, same source) — the portal has none today (fonts come from the Google Fonts CDN instead).
- In `index.html`, `benchmark.html`: remove the `fonts.googleapis.com` `preconnect`/`stylesheet`
  `<link>` tags; add `<link rel="stylesheet" href="fonts.css">` before `tokens.css` (v2's own load
  order per `PROVENANCE.md`: fonts → tokens → style).
- Add `data-brand="marketing"` to `<html>` in both files.
- Remove the `<span>😱 screamingface, built by ... OpenMined</a></span>` from `.foot` in both
  files (D12) — keep the GitHub link.
- Audit `portal.css` for any `--gain` usage meaning "success" (D7) — `.badge-verified` (line 48)
  is the one hit; change to `--success` / `--success-bg` equivalents. Re-check after the tokens
  swap that `--success-*` roles actually exist in v2 (per skill: they do — `--success` role table).
- Manual check, both themes: no v1-only class (`.climb`, `.stats`, etc.) breaks visually under v2
  tokens — the skill lists these as leaderboard-appropriate, so they should carry over, but v2's
  primitive scale is different (12-step vs flat) and needs a visual pass, not just a token swap.

## Task 2 — Landing catalog row: subtitle + submission count (spec D6 partial, D11)

- `main.js::benchmarkRow(b)` — add a subtitle line under the name using `b.description`
  (provisional — flagged to Irina, see Linear comment; easy to swap the field if she says
  otherwise, this is one line).
- `main.js::initIndex()` — after fetching `/v1/benchmarks`, for each benchmark also fetch
  `GET /v1/leaderboard/{id}` and read `entries.length` for the submission count (D11). Render
  alongside the row (new `<td>` or folded into the existing row — table structure change, keep
  the existing `id`/`dataset`/`leaderboard-link` columns, this is additive).
- `index.html` — add the new column header to `#benchmark-table`'s `<thead>`.

## Task 3 — Benchmark tab strip (the one genuinely new UI piece)

- New shared helper in `main.js`: `renderTabStrip(container, benchmarks, activeId)` — one tab per
  registered benchmark (whatever `/v1/benchmarks` returns; do not hardcode DRACO/IFEval per spec
  D6), linking to `benchmark.html?id=<id>`, active tab marked via `aria-current="page"` +
  `data-brand="marketing"`-appropriate styling (no ad-hoc colors — token roles only).
- `benchmark.html` — add the tab-strip container in the `masthead`, above the title; `benchmark.js`
  fetches `/v1/benchmarks` (in addition to its existing `/v1/leaderboard/{id}` call) to populate it
  and calls `renderTabStrip` with `state.benchmarkId` as active.
- Deep-linking (`?id=`) already works via `benchmark.js`'s existing `P.requireParam("id")` — no
  change needed there, just confirm the new tab strip's links preserve it.

## Task 4 — Empty/error states (spec D8–D10)

- D8 (zero benchmarks) and D10 (API failure) are **already implemented** in `main.js::initIndex()`
  (`showEmpty`/`showError` calls exist) — verify wording matches the spec's intent, no functional
  change expected.
- D9 (unknown `?id=`) — `benchmark.js` already calls `describeError(err, { notFound: "Benchmark
  not found." })` on a 404 from `/v1/leaderboard/{id}`. Add a link back to `index.html` in that
  error message (currently plain text, no link) — the one real gap against D9's "not a silently
  broken shell" intent.

## Task 5 — Close-out

- No backend tests affected — re-run `apps/scoreboard`'s pytest suite as a regression check only
  (no assertions expected to change).
- Manual pass: light + dark theme, DRACO/IFEval absence handled gracefully (empty catalog is a
  real possible state right now, not just a spec exercise), `?id=` deep-link + reload, tab strip
  keyboard-navigable.
- Post the three open questions (subtitle mapping, DRACO/IFEval ownership, "SF engine" wording) as
  a Linear comment on OME-768 before requesting review — implementation proceeds with the
  provisional choices noted above regardless of when Irina answers.
