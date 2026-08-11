---
title: Leaderboard v1 — landing page, benchmark catalog, benchmark page shell
status: proposed
created: 2026-08-11
author: Filip Boltuzic + Claude (Sonnet 5)
related:
  - OME-768 (this unit)
  - OME-769 (fills the shell's submissions table — separate unit)
  - OME-770 (cost/Pareto — separate unit)
  - OME-771 (reproducible toggle — separate unit)
  - OME-772 (leaderboard-mvp design gap feedback — the field-availability findings below reuse it)
  - screamingface-design skill (SFDS v2 — reference/ holds the verbatim current system)
---

# Leaderboard v1: landing page + benchmark catalog + benchmark page shell — spec

## Context

Irina scoped OME-768 this morning (2026-08-11) as the first of four leaderboard-v1 tickets
(768/769/770/771), following up on the OME-772 design-gap feedback. `apps/scoreboard/portal/`
already has a working `index.html` (catalog landing, live-wired stat counters) and
`benchmark.html` (per-benchmark shell) — this unit is a completion + design-system migration, not
a from-scratch build.

Separately, Bennett Farkas flagged (2026-08-07, #scream-dev) that the live dev portal is "consuming
a slightly dated design system" and showing a stray OM-affiliation mark, offering to push a fix
himself (never followed up). Confirmed by inspection: `apps/scoreboard/portal/tokens.css` is a
hand-vendored copy of `screamingface-brand@c9673b3` — the SFDS **v1** snapshot (EB Garamond
display font, Rubik wordmark, `--gain` resolves to green, ~20 custom properties, fonts loaded from
the Google Fonts CDN). The `screamingface-design` skill's `reference/` directory mirrors the
current **v2** system verbatim (628 tokens, Parastoo display font, `--gain` resolves to **gold**,
self-hosted `fonts.css`, marketing/app register split). Doing the v1→v2 migration inside this unit
— rather than as a separate ticket — is a judgment call: OME-768 already touches every file the
migration touches, and shipping the new shell on the old system would just create the same drift
Bennett already flagged, one release later.

## Decisions locked (2026-08-11)

| # | Decision | Choice |
|---|---|---|
| D1 | Design-system version | **Migrate to SFDS v2** as part of this unit. Replace `tokens.css`/`style.css`/`fonts.css` with byte-identical copies of `.claude/skills/screamingface-design/reference/*`, per that skill's own drift-check convention. |
| D2 | Register | **Marketing** (`data-brand="marketing"` on `<html>`) — the skill states explicitly: "leaderboard... marketing register", gold accent. This is not the app/product register scoreboard's admin-style surfaces might otherwise default to. |
| D3 | Font delivery | **Self-hosted**, via v2's `fonts.css`. Drop the `fonts.googleapis.com` `<link>` tags in `index.html`/`benchmark.html` — v2 does not use the Google Fonts CDN. |
| D4 | Data source | **Scoreboard's own API** (`GET /v1/benchmarks`, `GET /v1/leaderboard/{id}`) — already live, already what `data.js`/`benchmark.js` call today. OME-768's ticket text says "pull... from the SF engine"; read as loose phrasing for "the backend," not the separate `screamingface-engine` component, since no such catalog endpoint exists there and scoreboard's already serves this. **Flagged to Irina for a one-line confirmation before merge**, not blocking spec approval. |
| D5 | Scope boundary vs. OME-769 | The per-benchmark table ships **empty** (structure only) in this unit — rows, ranking, and the SOTA medal are OME-769's job. Don't pre-build submission-row rendering here even though it's tempting once the shell exists. |
| D6 | Benchmark scope | **Resolved 2026-08-11, same morning.** Keelan self-filed `OME-775` (register DRACO/IFEval/**HealthBench** — one more than this ticket's original scope — in scoreboard; its own acceptance criteria names OME-768 directly) and `OME-776` (scoreboard's `{benchmark_id}` path routes don't survive slash-containing canonical IDs like `draco/lite` — a real risk given this unit's tab strip/deep-linking/count-fetch all hit that route). Both set as `blockedBy` on OME-768. This unit's code stays generic (renders whatever `/v1/benchmarks` returns, never hardcodes an id) — full end-to-end verification with real data waits on both landing, not just OME-775. |
| D7 | `--gain` usage | Anywhere the current v1 portal code uses `--gain` to mean "success" (verified-style green), migrate to `--success-*` per the v1→v2 bridge note — do not let it silently flip to gold. |
| D8 | Empty state — zero benchmarks | Landing shows an explicit empty-state message ("No benchmarks registered yet"), not a blank table or an infinite loading spinner. Reuses the existing `#benchmark-status` live-region pattern already in `index.html`, re-skinned to v2. |
| D9 | Empty state — unknown `?id=` | `benchmark.html` shows a "Benchmark not found" state with a link back to the landing catalog — not a broken/blank shell, not a silent redirect. |
| D10 | Error state — API failure | Distinct from both loading and empty: a retry-affordance error state on network/5xx, reusing the same live-region pattern as D8/loading rather than a third bespoke mechanism. |
| D11 | Landing "# submissions" | No aggregate endpoint exists (confirmed, OME-772). Computed client-side: for each of the (currently 2-3) benchmarks, fetch `GET /v1/leaderboard/{id}` and count `entries.length`. Acceptable N+1 at today's benchmark count; revisit if the catalog grows past a handful. |
| D12 | Bennett's OM-affiliation mark | **Found, not just flagged**: every portal page's footer carries `<span>😱 screamingface, built by ... OpenMined</a></span>`. Matches Bennett's own words elsewhere ("ScreamingFace will have its own branding... as a unique project") — this is a deliberate de-branding, not a bug fix. Remove that span from `index.html`/`benchmark.html`'s `.foot` (leaderboard-facing pages only, this unit's scope); leave the GitHub link. |

## Open questions — route back to the team

- **"Subtitle" mapping** — the ticket says catalog rows show name/subtitle/#submissions, but
  nothing on `Benchmark` is explicitly a subtitle. Best guess is `description`, but this is
  Irina's/design's call, not ours to assume silently — **ask her directly** before building the
  row template.
- ~~**DRACO/IFEval registration ownership**~~ — resolved, see D6 (`OME-775`/`OME-776`, Keelan).
- **D4's "SF engine" wording** — one-line Slack confirmation with Irina before merge, not before
  starting (low risk either way; scoreboard's API is the only live source that matches the rest
  of the ticket's acceptance criteria).
- **Bennett's OM-affiliation mark** — resolved, see D12. Confirmed there's no separate design
  asset to consult either (Bennett authored the `screamingface-design` skill/`brand.screamingface.ai`
  itself — that *is* his design, not a proxy for it).

## Out of scope

- Submission-row population, ranking, SOTA medal (OME-769).
- Cost column, Pareto marks/chart (OME-770).
- Reproducible/All toggle, status column (OME-771).
- Any change to `apps/scoreboard`'s Python backend or API contracts — this unit is portal-only.
