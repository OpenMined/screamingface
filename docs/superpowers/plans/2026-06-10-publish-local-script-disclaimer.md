# Plan: don't redact local-script refs on publish — flag + disclaim instead

**Status:** plan for review (not yet ticketed/implemented)
**Origin:** Publishing ScoredLiveTruth showed a `/data/<redacted>` variant because the redaction regex over-matches. `/data/code/*.py` scripts aren't *private data* — they're a **local dependency**: the spec is readable but not reproducible without those files.

## Decisions (confirmed with user)
1. **Reference + disclaimer** (not source-bundling): keep the script paths verbatim in the published expression, flag the submission as needing local scripts, and show a "contact the author to reproduce" disclaimer on the scoreboard. Do **not** publish the script source.
2. **Keep the "Run Locally" link + warning badge** on script-dependent scoreboard entries (don't suppress it).

## The two `/data/` kinds (the core distinction)
| ref | meaning | treatment |
|---|---|---|
| `/data/<16-hex>` | content-addressed **private blob** (`sha256(data)[:16]`, `data_store/storage.py:36`) — local-only, can leak data | **redact** (unchanged) |
| `/data/code/<name>.py` | **local script** served by python-runner from config (`python_runner/plugin.py:67`) — portable logic, not secret | **keep text, flag as local dependency, disclaim** |

## Today's contract (what changes ride on)
- Desktop payload (`use-publish-score.ts`): `{ benchmark_id, spec_id, url4_expression, submitted_by, ran_with_providers, client }`.
- Scoreboard `ScoreSubmission` (`apps/scoreboard/.../scores/schemas.py:45`) + output `ScoreSchema` (`:119`) carry the same — no dependency field.
- Web portal `spec.js` builds "Run Locally" from `url4_expression`, and already has a "hide button + quiet note" pattern.
- Redaction lib: `lib/url4-redaction.ts` `DATA_REF_RE = /\/data\/[A-Za-z0-9_./-]+/` (over-broad).

## Changes

### 1. Desktop — redaction lib (`lib/url4-redaction.ts`)
- Split detection:
  - `findPrivateBlobRefs(expr)` → matches **only** `/data/<16-hex>` (`/\/data\/[0-9a-f]{16}\b/g`). Drives the existing **sanitize/redact** flow (`hasLocalDataRefs`/`sanitizeDataRefs` repointed here).
  - `findLocalScriptRefs(expr)` → matches `/data/code/...(.py)` script paths. Drives the **disclaimer** flow (never redacted).
- Add unit tests (`url4-redaction.test.ts`): code paths are NOT flagged as private; hash blobs still are; a spec with both is handled.

### 2. Desktop — publish dialog (`components/eval/PublishToLeaderboardDialog.tsx`)
- The redaction warning + sanitize/expose checkboxes now key off **private blobs only**.
- When `findLocalScriptRefs` is non-empty: show a distinct, non-destructive notice — *"This spec references local scripts (check_correct.py, …) that only exist on your machine. The expression is published as-is; others will need these scripts to reproduce it."* — with a single acknowledgment checkbox (no redaction). The scripts list is sent on the submission.
- `expressionToPublish` keeps script paths verbatim; only private blobs are sanitized when chosen.

### 3. Desktop — publish payload (`hooks/use-publish-score.ts`)
- Add `local_script_refs: string[]` (the `findLocalScriptRefs` result) to `PublishInputs` and the POST body.

### 4. Scoreboard service (`apps/scoreboard`)
- `ScoreSubmission` (`scores/schemas.py`): add `local_script_refs: list[str] = []` (validated, bounded length).
- Persist it (`scores/store.py` + model/migration per scoreboard conventions — check whether it uses aerich or generate_schemas).
- `ScoreSchema` / leaderboard output: include `local_script_refs` so the web can render the disclaimer.

### 5. Web portal (`web/portal/spec.js`, styles)
- For entries with non-empty `local_script_refs`: render a **warning badge** ("Requires local scripts") with a tooltip listing the scripts and *"contact the author to reproduce."*
- **Keep** the "Run Locally" link, annotated with the same warning (per decision 2).

## Test plan
- Desktop: redaction-lib unit tests (above); PublishToLeaderboardDialog test — script-dependent spec shows the acknowledgment (not the redact checkbox), private-blob spec still shows redact, payload includes `local_script_refs`.
- Scoreboard: submission round-trips `local_script_refs`; output includes it.
- Web: (if tested) badge renders when refs present.

## Sequencing
1. Redaction lib + tests (pure, isolated).
2. Desktop dialog + payload.
3. Scoreboard contract (schema + store + output) + tests.
4. Web portal badge.
Each layer is independently shippable; desktop can land first (extra payload field is ignored by an older scoreboard), but the disclaimer only appears once scoreboard+web land.

## Out of scope
- Bundling/publishing the script **source** (explicitly rejected — "talk to author").
- Auto-resolving/serving the scripts to other users.
- Any change to how private `/data/<hash>` blobs are handled (unchanged).

## Open questions
- Scoreboard migration mechanism (aerich vs generate_schemas) — confirm before the schema add.
- Badge wording/placement on the leaderboard row vs the spec detail page.
