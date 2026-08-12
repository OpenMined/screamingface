---
ticket: OME-768
stack: scoreboard
status: done
started: 2026-08-11
finished: 2026-08-11
---

# OME-768 — Leaderboard v1: landing page + benchmark catalog + benchmark page shell

## Intent

Rebuild `apps/scoreboard/portal/index.html` (benchmark catalog landing) and `benchmark.html`
(per-benchmark shell) to render entirely from the live API, scoped to the first two benchmarks
(DRACO, IFEval), with tab strip + `?id=` deep-linking — and, in the same unit, migrate the portal
off its vendored SFDS **v1** design system onto the current **v2** marketing register. This is
the fix for Bennett Farkas's 2026-08-07 flag ("consuming a slightly dated design system... should
not have the OM affiliation in the lower left") — the portal's `tokens.css` is confirmed a hand
copy of `screamingface-brand@c9673b3` (v1: EB Garamond, Rubik, `--gain` green), not the live v2
system the `screamingface-design` skill mirrors (628 tokens, Parastoo, gold `--gain`, self-hosted
fonts). Submission-row population (OME-769), cost (OME-770), and the reproducible toggle
(OME-771) are explicitly out of scope — this unit ships the shell only.

## Planned changes

- `apps/scoreboard/portal/tokens.css`, `style.css`, `fonts.css` — replace vendored v1 copies with
  the current v2 files (byte-identical to `.claude/skills/screamingface-design/reference/*`, per
  that skill's own drift-check convention).
- `apps/scoreboard/portal/index.html` — landing page: benchmark catalog rows (name, subtitle,
  submission count) from the live API; drop the Google-Fonts CDN `<link>` (v2 self-hosts via
  `fonts.css`); apply `data-brand="marketing"` (leaderboard is the marketing register per SFDS
  v2).
- `apps/scoreboard/portal/benchmark.html` — per-benchmark shell: tab strip across registered
  benchmarks, title/subtitle from live metadata, empty table structure ready for OME-769; `?id=`
  deep-linking.
- `apps/scoreboard/portal/data.js` / `benchmark.js` — updated to the (unchanged) `GET
  /v1/benchmarks` / `GET /v1/leaderboard/{id}` contracts; no backend changes.
- `apps/scoreboard/portal/portal.css` — reconciled against v2 component recipes
  (`reference/style.css`) rather than hand rules layered on v1 tokens.

## Test plan

- No backend/API changes in this unit — `apps/scoreboard`'s existing pytest suite is unaffected;
  re-run as a regression check only.
- Manual/visual: landing renders benchmark catalog live (no mock data); DRACO + IFEval tabs
  render via the shell; `?id=DRACO` and `?id=IFEval` deep-link correctly; light + dark theme both
  checked (SFDS v2 self-check list); no v1 token (`EB Garamond`/`Rubik`/green `--gain`) remains
  reachable in rendered output.
- No `--gain` used to mean "success" (v1 habit) anywhere touched — migrate any such use to
  `--success-*`.

## Acceptance

- Landing + DRACO + IFEval (+ HealthBench) boards render entirely from the live API (OME-768's own
  acceptance line). **Getting them actually registered upstream is not this unit's job** (see spec
  D6) — tracked as real blockers `OME-775` + `OME-776` (Keelan, filed 2026-08-11), not just a
  standing wish. This unit's own code stays generic and doesn't block on either landing.
- Tabs + `?id=` deep-linking work.
- Reasonable empty/error states: zero benchmarks, unknown `?id=`, and API failure each show their
  own explicit state (spec D8–D10) — never a blank or silently-broken shell.
- Portal visually matches the current SFDS v2 marketing register (gold accent, Plex Sans/Mono
  only, no rounded corners/shadows/gradients outside the sanctioned ones) — resolves Bennett's
  dated-design-system flag as a side effect of this unit, not a separate ticket.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** As planned — `tokens.css`/`style.css`/`fonts.css` replaced with byte-identical
  copies of `.claude/skills/screamingface-design/reference/*`; `index.html`/`benchmark.html`
  rebuilt on the live API with tab strip + `?id=` deep-linking; `portal.css` reconciled against v2
  component recipes. One addition beyond the plan: `assets/fonts/*.woff2` (20 files) — the plan
  assumed the font binaries existed somewhere reachable; they didn't (see Deviations).
- **Commits:**
  - `65d275cc` — feat(scoreboard): rebuild leaderboard portal shell on SFDS v2
  - `e4d3acef` — fix(scoreboard): point the active tab underline at a defined accent token
  - `bfd2aa3c` — fix(scoreboard): address portal review findings before merge
  (the first sha was `927a784b` pre-rebase onto origin/main)
- **Gates:** `uv run .claude/scripts/run_gates.py scoreboard --base origin/main` → append-only ✓,
  ruff check ✓, ruff format ✓, pyright ✓, pytest --cov=scoreboard --cov-fail-under=80 ✓ (167
  passed, 2 skipped). ALL GATES GREEN.
- **Manual/visual verification:** ran the app locally (fresh migrated DB, seeded `draco`/`ifeval`
  via `scoreboard.seed`) and drove it through Chrome DevTools: zero-benchmarks empty state (D8),
  unknown-`?id=` state (D9), tab strip + deep-linking, per-benchmark empty-submissions state, and
  light/dark theme all verified working. No `--gain`-as-success usage found remaining (D7).
- **Deviations:**
  1. **Font binaries were never vendored anywhere in the repo** — neither here nor in
     `screamingface-design`'s own `reference/` (a pre-existing gap from OME-715, not introduced by
     this unit). `fonts.css`'s `@font-face` rules 404'd on all 20 files; the SFDS v2 migration was
     visually inert (system-font fallback) despite the CSS/HTML side being complete. Root-caused via
     the skill's own `PROVENANCE.md` drift-check convention — the files are self-hosted directly off
     `brand.screamingface.ai/assets/fonts/*.woff2` (confirmed reachable, HTTP 200 on all 20) — pulled
     and vendored into `apps/scoreboard/portal/assets/fonts/`. Not fixed in `screamingface-design`'s
     own `reference/` — out of this unit's scope (portal-only), flagged for a follow-up there.
  2. **Subtitle → `description` field mapping is still only provisional**, per spec's own open
     question — Keelan confirmed the "SF engine" wording and benchmark-registration ownership
     (OME-775/776) in `OME-768`'s comments, but Irina has not yet confirmed the subtitle mapping.
     Shipping with the provisional choice per the spec's own instruction not to block on it; flag if
     it needs to change.
  3. Verified against `draco`/`ifeval` seeded locally, not the real upstream registration — that
     depends on OME-775 (register DRACO/IFEval/HealthBench) + OME-776 (slash-containing benchmark
     ID routing), both still Backlog and set as `blockedBy` on this ticket. This unit's code stays
     generic (renders whatever `/v1/benchmarks` returns) so it doesn't block on either landing.
  4. **`portal.css` now carries one deliberate override, breaking its own header rule**
     ("Extends — never overrides — tokens.css + style.css"). `style.css` ships
     `.rail { position: relative }` + a `.rail.stuck` variant its own comment documents as
     JS-toggled; this portal supplies no such listener, so the rail scrolled away while the
     `position: fixed` toggle stayed pinned. Restored `position: sticky` locally rather than
     implementing the `.stuck` scroll-listener + spacer, because that is new untested behavior and
     this unit is under a merge deadline. The system-faithful fix wants its own ticket; the override
     carries an `AIDEV-NOTE:` saying so and to drop the block when that lands.

## Review round (post-PR, pre-merge)

Ran the `code-review` skill against PR #558; 11 findings, all spot-verified before acting.
**Fixed in `bfd2aa3c`** (detail in that commit message): stale vendored copy vs. the reference
(the most serious — it falsified spec D1 *and* the PR body's own "byte-matched" claim), the
sticky-rail/floating-toggle regression, the misleading "Submissions" column header, an empty
`.tabstrip` painting a stray rule, a `.then`-shaped rejection handler that could strand the page
on "Loading…", the OM affiliation mark surviving on `spec.html`/`data.html`, and a missing OFL
license for the vendored fonts.

**Deliberately deferred, with reasons:**
- *Catalog blocks on N leaderboard fetches before painting any row* — real, but inert at today's
  benchmark count, and OME-769 rewrites this exact code path. Doing it there beats rushing a
  render-then-fill refactor under a deadline.
- *Spec D10 promised a retry affordance on the API-failure state; it ships as static text* —
  genuine gap against the spec, small, follow-up.
- *`encodeURIComponent` on slash-containing benchmark IDs still 404s* — already tracked as
  OME-776 (`blockedBy` on this ticket); nothing to change here.
