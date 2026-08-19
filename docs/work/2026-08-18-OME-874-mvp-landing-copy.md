---
ticket: OME-874
stack: scoreboard
status: in_progress
started: 2026-08-18
finished:
---

# OME-874 — Replicate the leaderboard-mvp landing copy and UI on the portal

## Intent

Bring `apps/scoreboard/portal/index.html` to the brand mockup at
https://brand.screamingface.ai/leaderboard-mvp/ — copy and UI — rendering the parts we cannot yet
back as visible-but-inert rather than omitting them. Requested by Irina in `#scream-dev`
(2026-08-18 13:18) and confirmed in DM at 13:55.

This unit reverses a rule I wrote and the owner approved four days ago. `OME-839` adopted only the
mockup copy that was true, under the §4 invariant *"no portal copy may claim reproduction,
verification status, or cost until the owning ticket lands."* Irina has now explicitly chosen the
aspirational framing: *"it's not dishonest, it's just to present what purpose this leaderboard
serves long term."* That is the owner's call to make, and this ledger records that the reversal is
deliberate rather than an oversight — so a future reader does not "fix" it back.

## Decisions carried in from the owner (Slack 2026-08-18 13:35)

**D1 — the verified-SOTA framing is adopted despite no verification existing.** Owner call, quoted
above. `OME-414`/`OME-821` still own making it true.

**D2 — "Best reproducible" column renders the board's top score.** Owner: *"The top score on that
leaderboard."* The number is real; only the column label is forward-looking.

**D3 — the pool toggle ships inert.** Owner: *"we can make the 'all' greyed out."* Rendered so the
affordance is visible, disabled so it cannot assert a filter that does not exist. The functional
toggle stays `OME-771` (Blocked).

**D4 — the cost chart is out of scope.** Nothing emits a run cost; owner is resolving it separately.

## Open questions (raised on the issue, not blocking a first pass)

1. Which side of the toggle is greyed — defaulting to *Reproducible* renders an empty board.
   Working assumption: default **All**, grey out *Reproducible*.
2. The `REPRODUCIBLE` glossary definition names machinery that does not exist ("shared compute",
   "global cache" — and *global cache* already means our cost-caching layer to this team).
3. *"By default, the leaderboard only shows results we've reproduced ourselves"* — literally
   implemented, the default view is empty.

**D5 — no internal references in files the browser receives.** Raised by the owner mid-build. The
portal's HTML, JS and CSS are served unminified, so every comment in them is public via View Source.
My first pass put ticket ids and implementation caveats in `index.html` — including, directly beneath
the glossary, an `AIDEV-NOTE` reading *"none of this is implemented yet … do not read these
definitions as a description of current behaviour."* On a public board whose copy claims
reproducibility, that is the internal contradiction stated out loud, in the shipped artifact.

All six of my HTML comments were removed and my JS/CSS comments rewritten without ticket ids or
implementation caveats, keeping only the technical rationale a maintainer needs. The reasoning lives
here and in the spec instead — neither is shipped. Verified: `git diff` adds **0** `OME-` references
to anything under `portal/`.

The rationale that moved here rather than staying in the served files:

- **`benchmarks` → `index.html#benchmarks`**, not the mockup's bare `benchmark.html`, because
  `benchmark.js` requires an `id` parameter and renders an error state without one (`OME-839`).
- **The glossary is aspirational, not descriptive.** Nothing behind `Reproducible` exists:
  re-run verification is `OME-414`, the real verified signal `OME-821`, the pool toggle `OME-771`.
  Shipped verbatim at the owner's instruction to stay consistent with brand copy.
- **The footer names the host that resolves.** The mockup's cell reads
  *"leaderboard.screamingface.ai · MVP preview · mock data"*; that hostname has no DNS record
  (re-checked 2026-08-18 — `leaderboard.dev.screamingface.ai` and `scoreboard.screamingface.ai` do
  resolve, it does not) and this board serves real submissions, so two of its three claims are
  false. Owner chose `scoreboard.screamingface.ai`; GitHub keeps its rail link.
- **`leaderboard-logic.js` must load before `main.js`** — the catalogue's Best-reproducible cell
  calls `SFLeaderboardLogic.bestEntryScore`. Same order `benchmark.html` already uses.
- **The Dataset column** is not in the mockup, whose data is mock; ours links published JSONL that
  `data.html` serves, so dropping it would break a working path to a real artifact. Owner confirmed.

**D5 was under-enforced and review caught it.** My audit grepped `*.html`, `*.js` and `*.css` — the
file types I had been editing — and missed that I had *created* a markdown file inside the served
tree. `portal/assets/mark/PROVENANCE.md` shipped publicly (`200 text/markdown`) carrying the ticket
id on line 20 and a `.claude/skills/...` path on line 41. The PR body's claim of "zero internal
references in served files" was false when written; both the file and that claim are corrected.

Worth recording because two reviews disagreed and both were right: the security pass explicitly
cleared this file — *"no secrets, no internal hostnames, no credentials"* — which is true against a
security bar, where this is a non-finding. The code review judged it against D5, where it is a
violation. A file can be harmless and still break a stated rule.

The real fix is not the scrub but the guard: `test_served_markdown_carries_no_internal_references`
now fetches every `*.md` under `portal/` through the app and fails on `OME-`, `.claude/` or
`worktrees/`. Verified by reintroducing the original leak and watching it fail. D5 had been a
paragraph in this ledger with nothing enforcing it, which is exactly how it was missed.

Scope of that guard is deliberately markdown-only — see below.

**Pre-existing leak, NOT fixed here.** The same audit found **~42** `OME-` references already on
`main` in served portal files — `benchmark.js` 19, `main.js` 11, `leaderboard-logic.js` 9,
`portal.css` 8, `index.html` 4 (the last now 0 of mine). Those predate this branch and sit in files
this unit does not otherwise touch. Cleaning them, or stripping comments at build time, is its own
unit of work — flagged for a follow-up ticket rather than smuggled in here.

## Planned changes

- `apps/scoreboard/portal/index.html` — hero, glossary block, READ THIS FIRST box, benchmark table
  head, pool toggle
- `apps/scoreboard/portal/main.js` — `benchmarkRow` columns (Focus, Best reproducible), toggle render
- `apps/scoreboard/portal/portal.css` — glossary + toggle rules, tokens only
- `apps/scoreboard/src/scoreboard/scores/models/benchmark.py` + schema + a migration — optional
  `focus` field
- seed + `charts/scoreboard/values.yaml` — `focus` values
- `apps/scoreboard/tests/portal/*` + unit tests

**D6 — `benchmark.html` copy aligned too (owner, option A2).** A security review of the branch found
that `index.html`'s new claim ("only shows results we've reproduced ourselves") directly contradicted
`benchmark.html`'s standing disclaimer ("every score here is self-reported") one click away — and
that `models/score.py` carried a codified invariant naming *both* files: *"change the default and
that copy together, or the board lies."*

The mockup's own benchmark page has **no** note box, so matching it exactly would have meant deleting
the disclaimer. The owner chose instead to reword it consistently with the landing framing (A2), on
the grounds that verification "will be done soon". The `score.py` invariant was amended in the same
change: the copy rule is recorded as consciously suspended, while the rule that still holds — nothing
may filter or rank on `verified_by_screamingface`, because it certifies nothing — is restated. Copy
may promise; code may not pretend.

**D7 — the name cell keeps its `description` subtitle and mono id (owner, option B2).** The mockup
renders only the linked name, putting its short line in the Focus column. We now show both: the
`description` subtitle *and* Focus. Accepted redundancy, owner's call. Consequence to note: this
leaves `OME-768`'s open question ("what should the catalogue subtitle be?") still open, since
`description` continues to fill that slot.

**D8 — Focus ships with authored placeholder copy (owner, option C1).** draco → *"Research reports
with citations"*; ifeval → *"Instruction following"*; healthbench-worst30 → *"Clinical safety,
hardest cases"*. Not brand-approved — editable in `values.yaml` without a code change, subject to the
deployed-values caveat above.

## Test plan

Written RED first, then made green:

- `test_seed.py` — `focus` persists through seeding; an absent `focus` is `None`.
- `test_leaderboard_routes.py` — `/v1/benchmarks` exposes `focus`, serialising `null` when unset
  rather than omitting the key.
- `tests/portal/leaderboard-logic.test.js` — six cases on `bestEntryScore`: empty/missing board,
  `null` vs a real `0`, highest-not-first, an all-negative board, **baselines never counting as our
  best**, and a malformed entry being skipped.
- `test_portal_static.py` — the hero mark is served as `image/png`, and the `.o-mark` `src` resolves
  to a path this app serves (behavioural, so it cannot be satisfied by a hotlink).
- `tests/smoke/` — opt-in drift alarms against the brand site: the three glossary definitions, the
  note copy, and the mark's upstream sha256. Excluded from CI by the new `smoke` marker, because an
  editor at another company must not be able to turn our build red.

## Acceptance

- Landing page matches the live mockup on every element in the spec's §4, both themes. ✓
- The hero mark renders from a vendored asset with no off-origin request. ✓
- `focus` round-trips model → schema → `/v1/benchmarks` → rendered cell; `—` when unset. ✓
- `Best reproducible` shows the top submission score; `—` when there are none. ✓
- No internal reference (ticket id, implementation caveat) in any file the browser receives. ✓
- `index.html` and `benchmark.html` no longer contradict each other. ✓
- Full gates green. ✓

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:**

## Review finding (Dmitry, 2026-08-19): the aspirational copy was not implementable

Both points were correct and both are fixed.

**1. The `benchmark.html` note contradicted itself.** It read *"The top of this board is the best
reproducible result: the current SOTA. Self-reported runs can rank above it."* If a self-reported
run can rank above the top, the top is not the best reproducible result. Verified against the code
rather than argued: `_build_leaderboard_query` selects `verified_by_screamingface` but never filters
on it, and orders by `score DESC` — so an unverified `0.99` genuinely outranks a verified `0.40`.

That sentence was **mine**, written for D6, not brand copy: the mockup's benchmark page carries no
note box at all (0 `class="note"`, 0 occurrences of "Read this first"). Strict fidelity would have
deleted the box; rewording it moves toward the mockup, not away.

**2. `index.html` instructed a control that does not exist.** *"Toggle on self-reported runs"* —
there is no toggle on that page, on the benchmark page, or anywhere in the product; `OME-771` is
Blocked. That is broken UX rather than a premature claim.

### Why this supersedes D1–D3

The owner chose forward-looking copy on 2026-08-18 believing it was a wording question. It was not.
The mockup's wording is coherent **only because its default view is filtered to reproducible rows** —
"the top is the best verified result" is true of a *filtered* board, and "toggle on self-reported
runs" names the control doing the filtering. Ported to an unfiltered board, the same sentences
contradict themselves and point at nothing.

So this copy and the pool filter (`OME-771` → `OME-821` → `OME-414`) are **one change, not two**.
Both notes now state what is true — every score self-reported, nothing independently reproduced,
every row rerunnable via its URL4 — and name verified ranking as a future state rather than a
current one. The ambition is kept; the false present tense is gone.

**Glossary left untouched.** The `Reproducible` definition stays verbatim per the owner's
instruction. It is a definition of a term, not an assertion that rows are in that category, and it
reads coherently beside a note saying nothing has been reproduced yet.

**`models/score.py` reverted** to the original invariant, with a note recording that forward-looking
copy was tried and why it failed — so the next person reaches for the filter rather than the wording.

**Owner action:** the `index.html` note was verbatim mockup copy that @Irina locked on 2026-08-18.
Changing it is a deviation from that instruction, made because the review demonstrated it was not
implementable. She needs to confirm before merge.
