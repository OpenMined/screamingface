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
| `"trask@openmined.org "` | `trask` | surrounding whitespace is noise — see §3b |
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

### 3b Second revision after review (2026-08-15) — strip the padding first

§3a over-corrected. Rejecting **all** whitespace also rejected an address that merely carries
padding, so one trailing space published the full domain — the exact exposure this change exists to
close, defeated by a space:

```
"trask@openmined.org "   ->  "trask@openmined.org "   # domain published
" trask@openmined.org"   ->  " trask@openmined.org"   # domain published
```

Reachable, not theoretical: `ScoreSubmission.submitted_by` is `str | None = None` with no strip and
no constraint, and in `authMode: disabled` — the chart default — it is client-supplied free text. The
authenticated path is safe; `identity_from_headers` already calls `.strip()`
(`cloudflare_identity.py:68`).

The distinction §3a actually needed is **surrounding** whitespace (noise) versus **internal**
whitespace (proof the value is free text). So: strip, then require the remainder to hold no
whitespace at all. This cannot resurrect §3a's hazard — after stripping, an empty local part is
empty rather than blank, so `"  @openmined.org  "` still passes through untouched instead of
publishing `"  "`.

### 3c Third revision (owner decision, 2026-08-15) — the field is an identity

§3b left `"me @ openmined.org"` passing through in full, on the §3 rule that internal whitespace
means free text. A harvester just normalises that back into a working address, so the leak was real.

The owner settled the question sitting underneath all three passes: **`submitted_by` is an identity,
not a display name.** Two facts made the "protect team names" argument untenable — the Client SDK
never sends this field at all (`_submission()` omits it), so free-text submitters are a use case
nobody has; and the only real values in existence are two clean addresses on dev.

So whitespace stops being evidence of intent and becomes formatting noise. The rule is now: **remove
all whitespace, then require a non-empty local part and a dotted domain.**

| Input | Published |
|---|---|
| `trask@openmined.org`, `"trask@openmined.org "`, `" trask@openmined.org"` | `trask` |
| `"me @ openmined.org"`, `"trask @ openmined.org"` | `me`, `trask` |
| `"filip.boltuzic @ openmined . org"` | `filip.boltuzic` |
| `"Team A @ OpenMined"`, `"me @ github"`, `user@github` | unchanged — an undotted domain is a word, not a host |
| `@openmined.org`, `" @openmined.org"`, `"  @openmined.org  "` | unchanged, never blank |
| `tester`, `""`, `null` | unchanged |

The **dotted domain**, not the whitespace, is what now keeps free text safe. That is a narrower and
more honest test, and it is the reason the rule got simpler rather than more baroque.

Accepted cost: free text whose right-hand side happens to contain a dot is truncated —
`"Contact: trask @ openmined.org please"` publishes `Contact:trask`. It loses formatting; it does not
leak an address.

**This is still a read-time guess**, which is why it took four passes. `OME-840` closes it properly by
validating the address on the write path, after which this function reduces to "everything before the
last `@`".

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
