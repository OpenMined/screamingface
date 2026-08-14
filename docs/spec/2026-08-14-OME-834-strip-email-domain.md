# OME-834 — the board must not publish harvestable email addresses

Status: approved (owner, 2026-08-14) · Stack: scoreboard

## 1. Problem

Since `OME-404`, a submission's `submitted_by` is the mesh-verified email from the Cloudflare Access
identity header. The leaderboard publishes it verbatim, and the read API is **public and
unauthenticated**. Measured on dev:

```
GET https://leaderboard.dev.screamingface.ai/v1/leaderboard/hle  →  200
  "submitted_by": "filip.boltuzic@openmined.org"
  "submitted_by": "stephen@openmined.org"
```

Every submitter's address is therefore machine-readable by anyone. With external testers about to
submit, that is a live spam exposure created by us.

## 2. Why the portal is the wrong layer

`portal/main.js`'s `formatSubmitter` renders the value as-is, so a one-line change there would make
the page look right. It would not help: **a harvester reads the JSON, not the HTML.** Fixing only the
portal would have satisfied the request as phrased while leaving the exposure intact — the kind of
fix that is worse than none, because it looks done.

The strip belongs where every consumer is served: the **read DTOs**.

## 3. Contract

| Input | Output | Why |
|---|---|---|
| `trask@openmined.org` | `trask` | the request |
| `filip.boltuzic@openmined.org` | `filip.boltuzic` | dots in the local part survive |
| `tester` (no `@`) | `tester` | in `authMode: disabled` this is client-supplied free text, not necessarily an email |
| `a@b@openmined.org` | `a@b` | the domain is what follows the **last** `@` |
| `@openmined.org` | `@openmined.org` | an empty local part would render as a missing submitter; keep the original instead |
| `" @openmined.org"` | unchanged | **a BLANK local part is the dangerous case** — see §3a |
| `"Team A @ OpenMined"` | unchanged | free text containing `@` is not an address |
| `user@github` | unchanged | a handle, not a public address (no dotted domain) |
| `null` | `null` | absent stays absent |
| `""` | `""` | unchanged |

### 3a Revision after review (2026-08-14) — gate on address shape, not on "@"

The first implementation trimmed whenever `@` appeared and guarded the result with
`local or value`. Two holes, both verified:

* `" @openmined.org"` yields `" "`. That is **blank, not empty**, so the guard missed it — and the
  SDK's `_text` (`_scoreboard/leaderboards.py:445`) rejects blank-after-strip, raising
  `LeaderboardError` for the **entire board**. One poisoned row would break every SDK client's read.
  In the default `authMode: disabled` this field is unvalidated free text, so that value is
  reachable.
* `"Team A @ OpenMined"` yielded `"Team A "`, contradicting the pass-through rule above.

The rule is now: trim only what looks like **one address** — no whitespace anywhere, a non-blank
local part, and a dotted domain. Everything else passes through untouched.

**Storage is untouched.** `Score.submitted_by` keeps the full address. OpenMined must still be able
to contact a submitter and audit which verified identity produced a score, which stripping on write
would destroy irreversibly.

Applied via one annotated type shared by `ScoreSchema`, `LeaderboardEntry`,
`RankedLeaderboardEntry` and `HistorySubmission` — the pattern `RunCostUsd` established, after that
same four-DTO duplication caused two separate defects.

## 4. What this does not do

**It is not anonymisation.** `filip.boltuzic` still identifies a person, and `first.last@openmined.org`
is trivially reconstructed for anyone who knows the domain convention. This raises the cost of naive
scraping; it does not protect identity. Nobody should describe it as privacy.

**It collides.** `trask@openmined.org` and `trask@gmail.com` both render `trask`. The board attributes
credit, so two testers on different domains would be indistinguishable. Acceptable only because this
is explicitly a stopgap — the request opens *"since we do not have usernames yet"*. A real username
field (`OME-772` records its absence) is the actual fix.

## 5. Safe by construction

`submitted_by` is deliberately excluded from `content_hash` (`OME-391`), so this cannot affect dedup,
and the field is not a key for anything else.

## 6. Acceptance

- All three read paths return the local part only.
- The stored row still holds the full address — asserted against the database, not the response.
- Submitting a full email still works; a non-email value passes through unchanged.
- Full gates green.
