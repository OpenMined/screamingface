# OME-874 — replicate the leaderboard-mvp landing page

Status: **draft, awaiting owner approval** · Stack: scoreboard

## 1. Problem

`OME-839` adopted only the part of `brand.screamingface.ai/leaderboard-mvp` that was true at the
time, under a §4 invariant forbidding any portal copy that claims reproduction, verification or
cost. Irina has now asked for the full landing page, and confirmed the aspirational framing is
wanted: *"it's not dishonest, it's just to present what purpose this leaderboard serves long term."*

This spec defines what "fully replicate" means concretely, because the mockup and our page differ in
more places than the copy — and because **the mockup itself has drifted from the screenshot Irina
circulated**, so "the mockup" needs pinning to one artifact.

## 2. Source of truth

The live page fetched 2026-08-18: `https://brand.screamingface.ai/leaderboard-mvp/` plus its
`board.css?v=20260806b`. Two differences from the screenshot shared in Slack, both resolved in
favour of the **live page**, since that is what Irina linked:

| | Screenshot | Live page |
|---|---|---|
| Glossary rows | 4 — adds **Reports** ("extra scores… imported from third-party platforms") | **3** — Reproducible · Unverified · Solo model |
| Read-this-first | *"Treat this as a public scoreboard, not a trust oracle…"* | *"By default, the leaderboard only shows results we've reproduced ourselves…"* |

The live version of the note is the stronger claim of the two. Flagged in §6.

## 3. What the mockup needs that we do not have

- **`.defs`** — no CSS rule exists anywhere; it is a bare hook. The glossary is styled entirely by
  the existing `.kv` role.
- **`.dt-repro`** — one declaration, `color: var(--success-text-low)`. Green, because the system
  reserves green for *verified* and gold for *the win*. One new rule in `portal.css`.
- **`.o-mark`** — already in our vendored `style.css`, but it is an **`<img>`**, not the emoji.
  The system comment is explicit: *"Never set the raw OS emoji inside display type — its glyph box
  word-spaces the letters apart and dips below baseline like a descender (kerning audit
  2026-07-17)."* So the hero requires vendoring `sf-mark-640.png` into `portal/assets/mark/`
  (app-local; no external hosts).
- **`focus`** — no such field on `Benchmark`. New nullable column + migration + seed.
- **`.rail-link--end`** — one margin rule.

## 4. Contract

### Adopted verbatim
- Eyebrow `Leaderboard`; `<h1>` `Fusi<img class="o-mark">ns, ranked and reproducible.`
- The 3-row `<dl class="kv defs">` glossary, exact wording.
- The `Read this first` note, exact wording.
- The `.btn` CTA *"Get started with ScreamingFace →"* → `docs.screamingface.ai`.
- Table head `Benchmark · Focus · Fusions · Best reproducible · Open`.

### Adapted, with reasons
- **`benchmarks` still targets `index.html#benchmarks`.** The mockup links bare `benchmark.html`;
  on live, `benchmark.js` requires an `id` parameter and renders an error without one. Carried
  forward unchanged from `OME-839`.
- **The stats strip stays.** The mockup has none, but ours shows three real live counts. The mockup
  predates them; deleting true data to match a mock is not fidelity.
- **The Dataset column stays**, appended before `Open`. The mockup never had one because its data is
  mock; ours links published JSONL artifacts that `data.html` serves. Removing it would break a
  working path to real artifacts. **Owner question in §6.**
- **The footer's second cell stays dropped.** `leaderboard.screamingface.ai` has no DNS record and
  our data is not mock — both claims in that cell are false. Carried forward from `OME-839`.

### Not adopted
- No pool toggle on this page. The live mockup's landing page has **no toggle control** — the
  `Read this first` text refers to one that lives on the benchmark page. This removes the overlap
  with `OME-771` that the issue anticipated; nothing inert needs rendering here.

## 5. Data

**`Best reproducible` needs no new endpoint.** The page already issues
`/v1/leaderboard/{id}?top=200` per benchmark to count submissions (a documented, accepted N+1 at
today's catalogue size). That payload carries ranked entries, so the top score is
`entries[0].score` — read from a response we already have. The column renders `—` for a benchmark
with no submissions.

Scope note: the value is the top **submission** score, not `max(entries ∪ baselines)`. Baselines are
imported reference numbers with no submitter, and the mockup's own glossary calls them a separate
kind; ranking them into a "best" figure would let a third-party import present as our best result.

**`focus`** — `CharField(max_length=120, null=True)`, mirroring how `revision` was added in
`OME-775`: nullable, no backfill, seeded through `values.yaml`. Legacy demo entries stay `null` and
render `—`.

## 6. Owner decisions

**RESOLVED (owner, 2026-08-18, on the issue).**

1. **The `Reproducible` glossary row ships verbatim** — *"must keep definition to be consistent with
   copy."* So *"Ran on shared compute and stored on the global cache. Anyone can re-run it and get
   the same score"* goes in unchanged, including the "global cache" clause. Recorded here because
   **that phrase already names our cost-caching layer** (`OME-305`/`OME-306`): a reader inside the
   team will take it for that feature. Deliberate, not an oversight.
2. **The pool toggle greys out *Reproducible***, leaving *All* active — the reading that avoids an
   empty default. **No toggle exists on this page**, so this decision does not apply to this unit;
   it is recorded for whoever builds the benchmark-page control (`OME-771`). See §4 "Not adopted".
3. **`Read this first` ships verbatim too**, by the same consistency argument as (1). The
   empty-board worry raised earlier does **not** apply here: this page renders a benchmark
   *catalogue*, not leaderboard rows, so the sentence is prose about the benchmark pages and filters
   nothing on the landing page.

**STILL OPEN — proceeding on the recommendation, reversible in one edit:**

4. **Dataset column** — kept (§4). The mockup has none because its data is mock; ours links real
   published JSONL that `data.html` serves, so dropping it breaks a working path to real artifacts.
5. **`Focus` values** are copy, not data we hold. Shipping as placeholders for owner edit: draco →
   *"Research reports with citations"*; ifeval → *"Instruction following"*; healthbench-worst30 →
   *"Clinical safety, hardest cases"*. Column renders `—` for anything unset.

## 7. Invariants

- Marketing register (`data-brand="marketing"`) — gold accent. Verified in light **and** dark.
- No raw hex; semantic roles only. No rounded corners outside terminal chrome; the one shadow is
  `.note`'s terminal window. No gradient but `--fusion-grad` on a leading row.
- `.o-mark` is an image, never the raw emoji, and never outside Parastoo display type.
- All-caps only via CSS `text-transform`; never typed.
- Portal assets stay app-local under `portal/`; no external host is introduced.
- `PUBLIC_ARTIFACTS`/`FORBIDDEN_ARTIFACTS` in `src/scoreboard/portal.py` still gate every new file
  the portal serves — the vendored mark must be reachable, forbidden paths still 404.

## 8. Acceptance

- Landing page matches the live mockup for every element in §4, in both themes.
- The hero mark renders from a vendored asset with no network request off-origin.
- `focus` round-trips: model → schema → `/v1/benchmarks` → rendered cell; absent → `—`.
- `Best reproducible` shows the top submission score per benchmark; `—` when there are none.
- Portal JS tests green; scoreboard gates green.
