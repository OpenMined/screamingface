---
title: Open vs. closed frontier statistics — spec
status: resolved — ready for docs/plan/ (§4, §6 resolved 2026-07-17; further resolved
  2026-08-06 against real production data + review — §4 mixed-provider rule, registry
  staleness, cross-system drift; §6 tie-breaking, baseline timing, frontier scope;
  new §9 manual override, §10 pre-launch cleanup)
created: 2026-07-16
resolved: 2026-07-17 (extended 2026-08-06)
author: Filip Boltuzic + Claude
ticket: OME-323
related:
  - https://linear.app/openmined/issue/OME-323/ome-323-open-vs-closed-frontier-statistics-main-page-screamingfaceai
  - https://linear.app/openmined/issue/OME-428/ome-428-openrouter-support-in-the-ai-gateway — source of the §4 classification precedent
  - OME-391 (dedup + write-path protection), OME-322 (baseline import) — prior scoreboard units this builds on
---

# Open vs. closed frontier statistics — spec

## 1. Context

OME-323: *"Show how much of the frontier is held by open, reproducible stacks vs.
proprietary ones — backed by real entries, not mock data."* This is one of the two
frontier-visualization tickets (alongside OME-324, 2D/3D charts) that deliver the
plan's headline claim — from Irina's 4-6 week plan video: *"an ensemble of models
beats the best score a single model can get... not only prove it, but create a
machinery through which we can enable a lot of researchers... to obtain the same
result in a repeatable way."* The Week 3 milestone frames this as evidence *"the
verified leaderboard [becomes] a headline about how much frontier open reproducible
stacks now hold."*

**Done when** (per the ticket): the open-vs-closed split reflects real leaderboard
contents — not mock data.

## 2. Current state (as-built, verified against the codebase)

- `Score` (submissions): `benchmark_id`, `spec_id`, `url4_expression`,
  `ran_with_providers: list[str]` (provider name strings, e.g. `["openai",
  "anthropic"]`), `accuracy`, `verified_by_openmined`. **No field indicates whether a
  submission is "open" or "closed."**
- `Baseline` (imported single-model reference scores, OME-322): `model_name`
  (free-text, e.g. `"GPT-5.2"`), `source` (`"lmarena"` / `"artificial_analysis"`),
  `accuracy`. **No field indicates openness either.**
- Nothing in this codebase currently encodes "open weights," "reproducible recipe,"
  or "proprietary" for any model or provider — this is genuinely new, not a gap in an
  existing mechanism.

## 3. Goals

- Compute, from real board data (submissions + baselines), what share of the
  accuracy frontier for a benchmark is held by "open" entries vs. "closed" ones.
- Expose this as data the scoreboard portal (and, later, the separate marketing
  site — see §7) can render as a headline stat.
- Ground truth must be **real leaderboard contents**, never mock/hardcoded numbers.

## 4. Classification — resolved: Option A, seeded from real AI Gateway policy

**Decision (2026-07-17):** Option A — a provider/model registry — seeded from a
concrete, current precedent rather than invented from scratch. Irina Bejan's
2026-07-17 comment thread on `OME-428` (OpenRouter support in the AI Gateway)
states the org's actual policy: *"we'll likely use HuggingFace for all open weight
models where we can"* — HuggingFace-routed models are open, OpenRouter/direct
commercial-API models (Anthropic, OpenAI, Google/Gemini) are closed. This mirrors
the same OR-vs-HF provenance split the (separate, not-in-this-repo)
`screamingface-benchmarks` repo already uses for panel-call routing (2026-07-13
benchmarking deck, slide 38: "Split routing by provenance — closed models via
OpenRouter, open-source via HuggingFace").

Filip confirmed this is sufficient sign-off — no separate OME-323 comment thread
was needed given the OME-428 precedent already reflects the product owner's stance.

**Implementation shape:**

- A small static registry (e.g. `scoreboard/classification/openness.py` or a YAML
  config, not a DB column) mapping provider name / model name pattern → `open` |
  `closed`. Deterministic and unit-testable, per the original Option A framing.
- Classify `Score` rows by `ran_with_providers` (provider name strings).
- Classify `Baseline` rows by `model_name` pattern-matching (e.g. `gpt-`, `claude-`,
  `gemini-` → closed; HF-style org/model names — `llama`, `mistral`, `qwen`,
  `deepseek`, etc. — → open).
- **Fail-closed default**: an unrecognized provider/model counts as closed, not
  open. A public "how much of the frontier is open" claim must not default-credit
  the open side for things it can't actually verify.
- **Mixed-provider fusion rule, resolved (2026-08-06):** a `Score` naming multiple
  providers in `ran_with_providers` is classified **closed if any single provider is
  closed** — open only when every named provider is open. Conservative by design: a
  fusion that leans on even one closed model must not get credited as open. (This
  wasn't actually specified in the original §4 text — it was an implementation
  assumption surfaced and confirmed explicitly during follow-up review, not a change
  of a prior decision.)
- **Registry staleness, resolved (2026-08-06):** the fail-closed default above is
  permanent — new models will keep shipping faster than the registry can track them,
  and every one of those defaults to "closed" until someone updates the list, quietly
  understating "open" in the meantime. That default direction stays (safer than the
  alternative), but staying silent about it doesn't: every unrecognized
  provider/model name encountered at classification time must be logged (or
  otherwise surfaced, e.g. via a metric), so staleness is a visible signal an
  operator can act on, not silent, permanent drift.
- **Cross-system drift, resolved (2026-08-06):** ship scoreboard's own registry now
  rather than wait for AI Gateway's `hosted_shared` classification (OME-428/OME-394)
  to land — that work doesn't exist yet and blocking on it has no defined end date.
  To keep the two from silently diverging once it does land, add a note directly to
  OME-428 and OME-394 themselves (not only here) pointing at scoreboard's registry
  and this ticket, so whoever implements AI Gateway's own classification sees the
  dependency in their own ticket, not buried in a scoreboard doc they'd have no
  reason to read.

<details>
<summary>Original candidate options (kept for record)</summary>

This was the crux of the spec — everything else follows from it. Three candidate
approaches were considered, not mutually exclusive:

**Option A — provider/model registry (static, curated).**
Maintain a small lookup (e.g. a JSON/YAML file in the repo, or a DB table) mapping
known provider names / model name patterns to `open` or `closed`. E.g. `openai`,
`anthropic`, `google` → closed; `meta-llama`, `mistral`, self-hosted/HuggingFace
model names → open. Simple, deterministic, no new submission-time fields — but
someone has to build and maintain the registry, and it can misclassify anything not
in the list (fails open or closed by default? — another decision).

**Option B — self-reported at submission time.**
Add an `is_open` (or similar) field to `ScoreSubmission`/`Baseline` import, set by
whoever submits/imports. Simple to implement, but trustworthiness is the same
problem `verified_by_openmined` already exists to solve for accuracy — an
unauthenticated or unverified claim of "open" is not evidence.

**Option C — infer from the recipe itself.**
"Reproducible recipe" (the ticket's own parenthetical) might mean something
stricter than "uses an open-weight model" — e.g. a `url4_expression` is only
"open" if every provider/model it references is independently runnable without a
proprietary API key. This is the most rigorous reading of the ticket text, but
requires the classification logic to actually parse/understand `url4_expression`
provider references, which is more machinery than A or B.

**My read (2026-07-16, pre-resolution):** Option A (a small curated registry) is the
simplest path to something real and correct today, and can be tightened later (e.g.
combined with C) without changing the stat's shape. But this is exactly the kind of
call that shouldn't be assumed — flagging for an explicit decision before any
plan/implementation.

</details>

## 5. Scope (resolved per §4, §6)

- Classify each `Score` (by its `ran_with_providers`) and each `Baseline` (by its
  `model_name`) as open or closed, via the §4 registry.
- Compute, per benchmark: the running-best accuracy over time (walking
  `submitted_at` order per §6) and, at each point, whether the entry holding that
  position is open or closed — yielding both the *current* split and the
  *time-series trend*.
- Expose via a new read endpoint (e.g. `GET /v1/leaderboard/{benchmark_id}/frontier`
  or folded into the existing leaderboard response) returning the current split +
  supporting counts + the trend series, so the portal (and any future external
  consumer) can render it.
- Render it somewhere on the scoreboard portal (exact placement TBD in the plan).

## 6. "The frontier" — resolved: trend over time, not a single snapshot

**Decision (2026-07-17):** Option (c) — a trend over time — settled by re-reading the
ticket's own text, not a separate ambiguity to resolve: OME-323's description says
"Compute the frontier share **+ trend** from real board data." That's explicit scope,
not implied wording to interpret.

`Score` already has `submitted_at`, so this is buildable: per benchmark, walk
submissions (and baseline import events) ordered by time, track the running-best
accuracy, and tag whether the entry holding that "current best" position at each
point was open or closed. The output is a time series of frontier-holder
classification changes, plus the current split, not just a single instantaneous
number.

This is a materially bigger scope than a top-1 snapshot (the original draft's option
(a)) — the plan should size for it accordingly rather than deliver (a) and call the
ticket done.

**Tie-breaking, resolved (2026-08-06):** an exact accuracy tie is not an improvement —
the existing frontier holder keeps that position until a *later* entry strictly beats
it, not merely matches it. This isn't theoretical: the real production leaderboard
already has two submissions tied at 100% accuracy (11 questions each) at the time this
was checked, so the trend computation will hit this case immediately on real data, not
eventually.

**Baseline timing, resolved (2026-08-06):** a `Baseline`'s `imported_at` records when
someone ran the import command, not when that model was actually current in the real
world — it cannot be trusted as a point on the real-world timeline, and treating it as
one would let a late import scramble the trend's chronology. Baselines still count
toward the *current* open/closed split (§5), but are **excluded from the time-series
trend** — only real `Score` submissions, whose `submitted_at` is genuine, drive the
trend.

**Frontier scope, resolved (2026-08-06):** "the frontier" is the single best score
across *all* specs within a benchmark, matching this spec's own literal wording ("per
benchmark") — not scoped per-`spec_id` the way the existing leaderboard's own ranking
is. This accepts a known gaming risk (an unusually easy or narrow spec could dominate a
benchmark's whole frontier) as a non-goal for this unit, mitigated over time by human
oversight and `verified_by_openmined`, not by this feature.

## 7. Non-goals (explicitly out of scope for this unit)

- Rendering this on the actual `screamingface.ai` marketing homepage — that site
  lives in a separate repo (`screamingface-web`) this session doesn't have access to.
  This unit exposes the data; wiring it into that homepage is a follow-up for
  whoever owns that repo.
- Retroactively classifying/backfilling existing `Baseline`/`Score` rows with the
  *registry's* classification does not require a migration or backfill (the registry
  is a code-side lookup evaluated at read time, not a stored column) — this still
  holds. It's distinct from the new `openness_override` column (§9), which is an
  explicit, opt-in correction mechanism added by this unit, not a backfill of the
  registry's own output.
- Syncing the classification registry with whatever AI Gateway ends up encoding for
  `hosted_shared` routing (OME-428/OME-394) — resolved in §4 as "ship now, cross-link
  the dependency in their tickets," not this unit's job to implement.
- Real score/claim verification for the public claim — §4's classification only
  answers "which provider/model," never "is the claimed accuracy true." Resolved
  (2026-08-06): ship as-is. Unverified and even anonymous submissions affect this stat
  exactly the same way they already affect the rest of the leaderboard today —
  tightening that is a separate, much larger, already-unowned effort (see OME-404's
  own D6 for the precedent of scoping verification out of an adjacent unit), not
  something this unit blocks on.
- OME-324 (2D/3D frontier charts) — related but separate ticket/unit.

## 8. Acceptance criteria

- The open-vs-closed split and the trend-over-time series (§6) are computed from
  real `Score`/`Baseline` rows, with no mock/hardcoded numbers in the code path.
- Classification approach (§4 registry) is deterministic and testable (unit tests
  cover known open/closed cases, the fail-closed default for unrecognized
  providers/models, and the frontier trend computation itself).
- Exposed via the scoreboard's own API/portal; marketing-site integration explicitly
  deferred (§7).
- A mixed-provider `Score` is classified closed-if-any-provider-is-closed (§4).
- Every unrecognized provider/model name encountered is logged/surfaced, not
  silently absorbed into the "closed" default (§4).
- The frontier trend never moves the holder on an exact accuracy tie — only on a
  strict improvement (§6).
- Baselines are included in the current open/closed split but excluded from the
  time-series trend (§6).
- `openness_override` (§9) is respected by the classification path when set on a
  row, and ships with its migration in this same unit.
- Known non-real rows already in production (§10) are removed before this feature's
  first real computation, so day-one numbers aren't contaminated by test data.

## 9. Manual classification override — resolved: add a per-row override field

**Decision (2026-08-06):** classification is code-driven by default (§4), but a
specific row's automatic classification must be correctable without a code deploy —
e.g. a genuinely open model whose name doesn't yet match any registry pattern. Add an
optional `openness_override: "open" | "closed" | null` column to both `Score` and
`Baseline` (`null` = defer to the §4 registry; a set value wins outright). This is a
schema change and ships with its migration in the same implementation unit, per this
repo's Stack rule S1 — it is the one place this spec now requires a migration; §7's
"no migration needed" note still holds for the registry/classification logic itself,
which remains a pure code-side lookup.

## 10. Pre-launch data cleanup (operational, not code scope)

**Decision (2026-08-06):** the live production database already contains at least
one non-real row — the smoke-test submission documented in `DEPLOYMENT.md`'s own
example (`spec_id: score-007-smoke`, `ran_with_providers: ["smoke"]`, submitted by
`score-007`), confirmed present via a direct query against
`https://scoreboard.screamingface.ai` on 2026-08-06. This and any other known junk
rows must be manually deleted from production **before** this feature computes its
first real public number — a one-time operational cleanup, not a code change, but
recorded here so it isn't forgotten before launch. This is a direct write against
shared production data — requires explicit confirmation before executing, separate
from this spec.
