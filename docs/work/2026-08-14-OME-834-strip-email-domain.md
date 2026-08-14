---
ticket: OME-834
stack: scoreboard
status: in_progress
started: 2026-08-14
finished:
---

# OME-834 — publish only the local part of a submitter's email

## Intent

Irina, 2026-08-14: *"since we do not have usernames yet and you have access to the email, can we
strip @… from the email (i.e trask@openmined.org → trask)? I am just afraid we're exposing folks to
bot spam"*.

Measured before deciding where: the full addresses are already public **in the API, without auth** —
`GET /v1/leaderboard/hle` returns `200` with `"submitted_by": "filip.boltuzic@openmined.org"`. A
harvester reads JSON, so stripping in `portal/main.js` would not have addressed the request at all.

## Decisions locked (2026-08-14)

| # | Decision | Choice |
|---|---|---|
| D1 | Layer | **Read DTOs.** One change point covers the portal, the SDK notebook view and any future consumer. Owner decision. |
| D2 | Storage untouched | `Score.submitted_by` keeps the full email, so OpenMined can still contact a submitter and audit the mesh-verified identity behind a score (`OME-404`). Stripping on write was rejected as irreversible. |
| D3 | Mechanism | One annotated type with a `PlainSerializer`, applied to every read DTO — the pattern `RunCostUsd` already uses, so the four DTOs cannot drift. `when_used="json"` only, because `_ranked_entry` splats `entry.model_dump()` in python mode. |
| D4 | Non-emails pass through | In `authMode: disabled` this field is client-supplied free text. A value without `@` is returned unchanged rather than mangled. |
| D5 | Split on the LAST `@` | The domain is what follows the final `@`. If the local part would be empty (`@openmined.org`), return the original — never emit `""`, which would read as a missing submitter. |
| D6 | Two limits stated, not hidden | **Collisions:** `trask@openmined.org` and `trask@gmail.com` both render `trask`; with external testers on arbitrary domains the board would attribute two people identically. **Not anonymisation:** `filip.boltuzic` still names a person and `first.last@` is guessable. This defeats naive scrapers and must not be described as more. |

Safe by construction: `submitted_by` is deliberately excluded from `content_hash` (`OME-391`), so
nothing here can affect dedup, and the field is a key for nothing else.

## Planned changes

- `apps/scoreboard/src/scoreboard/scores/schemas.py` — the serializer + annotated type, applied to
  `ScoreSchema` and `LeaderboardEntry`.
- `apps/scoreboard/src/scoreboard/routes/leaderboard.py` — the same type on `RankedLeaderboardEntry`
  and `HistorySubmission`.
- Tests under `apps/scoreboard/tests/unit/`.

No portal change: it renders whatever the API returns.

## Test plan

RED first:

- `trask@openmined.org` → `trask`; `filip.boltuzic@openmined.org` → `filip.boltuzic`.
- No `@` (`tester`) → unchanged (D4). `None` → `None`. `""` → `""`.
- `@openmined.org` → unchanged, never `""` (D5).
- `a@b@openmined.org` → `a@b` (split on the last `@`, D5).
- All three read paths strip: leaderboard, per-spec history, `GET /v1/scores/{id}`.
- **The stored row still holds the full email** — the D2 guarantee, asserted against the database
  rather than the response.

## Acceptance

- All three read paths return the local part only.
- The database row keeps the full address.
- Submitting a full email still works; a non-email value is untouched.
- Full gates green.

## Outcome

- **Actual files:** as planned — `scores/schemas.py` (serializer + `SubmittedBy`, applied to
  `ScoreSchema` and `LeaderboardEntry`), `routes/leaderboard.py` (`RankedLeaderboardEntry`,
  `HistorySubmission`), tests in `tests/unit/scores/test_schemas.py`,
  `tests/unit/test_leaderboard_routes.py`, `tests/unit/test_scores_routes.py`. **No portal change** —
  it renders whatever the API returns.
- **Gates:** `run_gates.py scoreboard --base origin/main --skip-append-only` → ruff check ✓,
  ruff format ✓, pyright ✓, pytest --cov ✓. **176 passed, 2 skipped.**
- **Live probe** (fresh migrated database, full email submitted):

  | Path | Published |
  |---|---|
  | `POST /v1/scores` | `trask` |
  | `GET /v1/scores/{id}` | `trask` |
  | `GET /v1/leaderboard/{id}` | `trask` |
  | per-spec history | `trask` |
  | domain present in any payload | **none** |
  | database row | `trask@openmined.org` |

  The last two rows are the point: the exposure is closed on the wire and the audit trail survives.

### Deviations

1. **`ScoreSubmission` deliberately untouched.** It carries the value inbound; trimming there would
   have written the truncated form to the database and silently become the option D2 rejected. Pinned
   by `test_the_database_still_holds_the_full_address`.
2. **One prior test adapted, owner-approved.** `test_post_score_with_identity_header_stores_header_email`
   asserted the response equalled the full address. Escalated per sdlc rule 5. Its purpose — the
   header beats the request body — still holds, because the body claimed `someone-else`. Rather than
   only changing the expected string, it now also asserts the stored row holds the full address,
   which is what the test's own name claims and the response alone never verified. The gate run used
   `--skip-append-only`.
3. **My first RED failed for the wrong reason.** I built `ScoreSchema` with `run_cost_usd=None`, but
   this branch is off `origin/main` where that field does not exist yet — it is in the unmerged #582 —
   so `extra="forbid"` rejected it and all seven tests errored instead of three failing on the
   assertion. Caught by reading the error. **Consequence for sequencing:** when #582 merges, this
   branch rebases and those two constructors need `run_cost_usd` adding back.
4. **Verified no other consumer pins a full address.** The SDK's `researcher@example.com` occurrences
   are its own request fixtures and constructed objects, not assertions against a live response, so
   `packages/screamingface` needed no change.
