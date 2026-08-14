# OME-839 — adopt what the mockup says that we can stand behind

Status: approved (owner, 2026-08-14) · Stack: scoreboard

## 1. Problem

The live portal and `brand.screamingface.ai/leaderboard-mvp` share the same design system, so they
already look like one product. What differs is **content**: the mockup names the product's core term,
offers three navigation links, and explains how to move around the board. The live portal does none
of that — it has only a theme toggle in the rail and never defines "fusion".

Irina asked for the mockup's copy "more faithfully", and specifically for the three links, expecting
them to matter for the tester cohort.

## 2. Why "faithfully" cannot mean "verbatim"

Roughly half the mockup's landing copy describes capabilities that do not exist:

| Mockup copy | Reality |
|---|---|
| `REPRODUCIBLE` — *"Ran on shared compute… Anyone can re-run it and get the same score."* | nothing re-runs submissions; `OME-414` unstarted, unstaffed |
| *"the top **reproducible** result is the current SOTA (the one place gold appears)"* | medal descoped to `OME-771` |
| *"The chart shows what accuracy each dollar of run-cost buys."* | no chart, no cost data; `OME-770` pass 2 blocked |
| `FUSIONS` / `REPRODUCIBLE` / `BEST REPRODUCIBLE` columns | no verification signal exists |
| footer *"leaderboard.screamingface.ai · MVP preview · mock data"* | that host has **no DNS record**; the data is not mock |

`OME-820` spent two review rounds removing precisely these claims from this portal, at the reviewer's
request, after they were found to contradict the rendered UI. Re-adding them as "copy fidelity" would
undo that.

So the rule is: **adopt the copy that is true now; the rest lands with the ticket that makes it true.**

## 3. Contract

Adopted:

- Masthead: `benchmarks` · `github` · `docs`, right-aligned before the theme toggle, on every page.
- Lead: *"A fusion is one or more models scored on a public benchmark."*
- Benchmarks section: *"Pick a benchmark to open its leaderboard. Inside, you can tab across all
  benchmarks."*
- Footer: the wordmark cell.

Two adaptations, both because the mockup is backed by mock data and we are not:

- **`benchmarks` targets `index.html#benchmarks`.** The mockup links bare `benchmark.html`; on live,
  `benchmark.js` requires an `id` query parameter and renders an error state without one. The landing
  page is the catalogue, so it is the correct target.
- **The footer's second cell is dropped**, not reworded — its three claims are a nonexistent
  hostname, a preview label, and "mock data".

Not adopted: the headline. *"Fusions, ranked and reproducible."* asserts reproduction; the live
*"Results you can rerun, not just read."* claims only what the board delivers. Left for Irina to
decide, since brand voice is hers.

## 4. The invariant this must not break

**No portal copy may claim reproduction, verification status, or cost** until the owning ticket lands.
`OME-820` established this and it has already been broken twice by edits that looked unrelated.
Verification is a grep of the rendered output, not a reading of the diff.

## 5. Acceptance

- Three links on all three pages, each resolving.
- Adopted copy verbatim.
- No verification or cost claim in any portal HTML.
- Rail does not wrap or collide with the toggle at mobile widths.
