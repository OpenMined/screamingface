---
ticket: OME-834
stack: scoreboard
status: in_review
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

## Review pass (2026-08-14) — two findings, both valid, both mine

| Finding | Verified how | Verdict |
|---|---|---|
| `" @openmined.org"` publishes `" "`, and the SDK rejects blank text | ran `_publish_submitter`; read `leaderboards.py:445` | **valid, and the worst blast radius found anywhere today** |
| `"Team A @ OpenMined"` publishes `"Team A "` | same | valid — contradicted my own D4 |

### Why the first one matters more than its size

`_text` is `if not isinstance(value, str) or not value.strip(): _invalid(...)`. A single space passes
my `local or value` guard (it is truthy) and then fails the SDK's blank check, so **one row with a
leading space in the submitted email would raise `LeaderboardError` for every SDK client reading that
whole board**. `authMode: disabled` is the chart default, and this field is unvalidated free text
there, so the value is reachable — not theoretical.

### The fix

Gate on address shape rather than the presence of `@`: no whitespace anywhere, non-blank local part,
dotted domain. Verified behaviour after the change:

| Input | Output |
|---|---|
| `trask@openmined.org` | `trask` |
| `filip.boltuzic@openmined.org` | `filip.boltuzic` |
| `a@b@openmined.org` | `a@b` |
| `tester`, `""`, `None` | unchanged |
| `@openmined.org`, `" @openmined.org"`, `"\t@openmined.org"` | unchanged |
| `"Team A @ OpenMined"`, `"me @ openmined.org"` | unchanged |
| `user@github` | unchanged — a handle, not a dotted-domain address |

Spec §3a records the revision.

### Deviation

My original guard, `local or value`, tested for *empty* when the hazard was *blank*. The lesson is
narrow and worth keeping: for a field that another service validates with `.strip()`, an emptiness
check is not the same as a blankness check.

## Review pass 2 (2026-08-15) — one finding, valid, and it undid the point of the change

| Finding | Verified how | Verdict |
|---|---|---|
| Surrounding whitespace defeats the strip entirely — `"trask@openmined.org "` publishes the full domain | ran `_publish_submitter` over a padded matrix | **valid, P1: it re-opens the exposure this PR exists to close** |

### What went wrong

Review pass 1 fixed a blank *local part* by rejecting **all** whitespace. That is a wider rule than
the hazard required, and the extra width lands exactly on the failure case: an address with padding
is still an address, and refusing to trim it publishes the domain. Two passes, each fixing one half
of "what counts as one address", each breaking the other half.

The distinction that was actually needed: **surrounding** whitespace is noise, **internal**
whitespace is what proves free text. Strip first, then require no whitespace in the remainder.

Reachable, not theoretical: `ScoreSubmission.submitted_by` is `str | None = None` — no strip, no
constraint — and in `authMode: disabled` (the chart default) it is client-supplied free text. The
authenticated path was never affected; `identity_from_headers` strips (`cloudflare_identity.py:68`).

### Verified after the fix

| Input | Published |
|---|---|
| `trask@openmined.org `, ` trask@openmined.org`, `\ttrask@openmined.org\t` | `trask` |
| `  filip.boltuzic@openmined.org  ` | `filip.boltuzic` |
| `@openmined.org`, `" @openmined.org"`, `"  @openmined.org  "` | unchanged — never blank |
| `Team A @ OpenMined`, `user@github`, `tester`, `""`, `None` | unchanged |
| `a@b@openmined.org` | `a@b` |

RED first: the four padded cases failed for the right reason before the fix, and the padded
blank-local case passed throughout, proving the §3a guarantee survived.

### Residual, escalated — and the owner closed it

`"me @ openmined.org"` still published in full under pass 2's rule. Escalated rather than changed
unilaterally, because trimming it reverses §3's pass-through decision. See review pass 3.

**Gates:** all green.

## Review pass 3 (2026-08-15) — the owner answered the question under all three passes

Three passes had argued about *what whitespace means*. The owner settled what the FIELD means:
**`submitted_by` is an identity, not a display name.**

Two facts I gathered while framing the question made the "protect team names" defence untenable, and
they contradicted my own earlier framing:

* the Client SDK **never sends this field** — `_submission()` in `_scoreboard/leaderboards.py` omits
  it entirely, so free-text submitters are a use case nobody has;
* the only real values anywhere are two rows on dev, both clean addresses.

I had used a hypothetical to justify leaving a real leak open. Recording that, because the failure was
in the *reasoning*, not the code.

### The rule got simpler, not more baroque

Remove all whitespace, then require a non-empty local part and a **dotted domain**. The dot — not the
whitespace — is now what keeps free text safe, which is a narrower and more honest test:

| Input | Published |
|---|---|
| `trask@openmined.org`, padded variants | `trask` |
| `"me @ openmined.org"`, `"filip.boltuzic @ openmined . org"` | `me`, `filip.boltuzic` |
| `"Team A @ OpenMined"`, `"me @ github"`, `user@github` | unchanged — undotted domain |
| `@openmined.org` and every padded form | unchanged, never blank |
| `tester`, `""`, `None` | unchanged |

RED first: exactly the three address-shaped cases failed; the two free-text cases passed before and
after, which is the evidence that the dotted-domain test — not the whitespace test — is doing the work.

### One prior expectation removed

`("me @ openmined.org", "me @ openmined.org")` was deleted from the parametrize list. It was added by
this same PR one pass earlier and it **encoded the leak the owner just closed**, so keeping it would
have pinned the bug. Not a weakening: it is replaced by the opposite assertion.

### Accepted cost, stated plainly

Free text whose right-hand side contains a dot is truncated — `"Contact: trask @ openmined.org
please"` publishes `Contact:trask`. It loses formatting; it leaks nothing.

### Follow-up filed

`OME-840` — validate the address on the write path so this stops being a read-time guess. `#602` is
its blocker. Mirror at `docs/tasks/2026-08-15-OME-840-validate-submitter-on-write.md`.

**Gates:** all green.
