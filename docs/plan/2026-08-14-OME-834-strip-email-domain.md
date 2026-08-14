# OME-834 — Implementation plan

Spec: `docs/spec/2026-08-14-OME-834-strip-email-domain.md` · Ledger:
`docs/work/2026-08-14-OME-834-strip-email-domain.md`

Two files of production code. RED before GREEN.

## Step 1 — RED

`tests/unit/scores/test_schemas.py` — the serializer, parametrised over spec §3's table, including
the two edge cases that are easy to get wrong: `@openmined.org` must not become `""`, and
`a@b@openmined.org` splits on the last `@`.

`tests/unit/test_leaderboard_routes.py` — the leaderboard route and the per-spec history both return
the local part.

`tests/unit/test_scores_routes.py` — `GET /v1/scores/{id}` too, **and the D2 guarantee**: after
submitting, read the row back from the database and assert it still holds the full address. That is
the assertion that stops a future "simplification" from stripping on write.

## Step 2 — GREEN

`scores/schemas.py`: a `_serialize_submitter` returning the local part per §3, plus
`SubmittedBy = Annotated[str | None, PlainSerializer(..., when_used="json")]`. Apply to
`ScoreSchema` and `LeaderboardEntry`.

`routes/leaderboard.py`: the same type on `RankedLeaderboardEntry` and `HistorySubmission`.

`when_used="json"` is deliberate — `_ranked_entry` splats `entry.model_dump()` in python mode and
must keep receiving the stored value.

## Step 3 — gates

`run_gates.py scoreboard --base origin/main`, then a live probe against a freshly migrated database:
submit a full email, confirm all three read paths show the local part and the row still holds the
domain.

## Risks

- **`ScoreSubmission` must not be touched.** It carries the value *inbound*; stripping there would
  write the truncated form to the database and silently become D2's rejected option.
- The SDK decodes `submitted_by` into `LeaderboardEntry`; its tests may assert full addresses. Check
  `packages/screamingface` before assuming this is scoreboard-only.
