---
ticket: OME-849
stack: repo
status: done
started: 2026-08-17
finished: 2026-08-17
---

# OME-849 — Report real run cost from provider-authored OpenRouter evidence

## Intent

A run's report shows `—` where a cost belongs, because `apps/url4-cloud` hardcodes
`pricing_version="unpriced"` and `total_usd=0`. Every other link is built: aigateway now publishes
per-attempt usage accounting under `_aigw` (`OME-303`), `packages/url4` already carries five token
classes and five USD components, and the SDK already reads all of it. This epic joins the chain for
the OpenRouter case, taking the provider-authored amount as the source at 1 credit = 1 USD.

This ledger covers the SPEC unit only. Implementation runs under `OME-850` (packages/url4) and
`OME-851` (apps/url4-cloud), each with its own ledger.

## Planned changes

- `docs/spec/2026-08-17-OME-849-run-cost-openrouter.md` — the normative spec.
- `docs/tasks/2026-08-17-OME-849-run-cost-openrouter.md` and the two sub-issue mirrors.

No source change in this unit.

## Test plan

Not applicable — spec unit, no code. The spec itself carries the required test list that
`OME-850`/`OME-851` must implement RED-first, including the two P0 cases (never price a cache
reference; never collapse "genuinely free" with "unknown").

## Acceptance

- Spec states the normative pricing rule as a total decision table with no unreachable row.
- Spec pins the degradation rule (`unpriced`, never `$0`) and the rollup poisoning rule.
- Spec names every file to change in both components, and the invariants not to regress.
- Locked decisions from the 2026-08-17 owner session are recorded verbatim.
- Open questions are listed as open, not silently defaulted.

## Outcome

Status: done (spec unit). Both child units also landed on this branch.

- **Actual files:** as planned — `docs/spec/2026-08-17-OME-849-run-cost-openrouter.md` plus the three
  `docs/tasks/` mirrors and this ledger.

- **Commits:**
  - `095f4588` docs(OME-849): spec run cost from provider-authored OpenRouter evidence
  - `105ef9c1` feat(url4): allow a total-only cost and widen the usage seam (`OME-850`)
  - `405a6869` feat(url4-cloud): price runs from provider-authored cost evidence (`OME-851`)

- **Gates:** not applicable to this unit (no code). Both child stacks green — see their ledgers.

- **LIVE END-TO-END VERIFICATION (2026-08-17).** Ran a real local stack — aigateway on 9105 with
  `AIGW_AUTH_MODE=disabled` + `AIGW_OPENROUTER_ENABLED=true`, url4-cloud `serve --local` on 9108, an
  owner-supplied OpenRouter API key — and compared the published cost against OpenRouter's own
  billing meter (`GET /api/v1/credits`, `data.total_usage`).

  | run | meter delta (ground truth) | published `subtree.total_usd` | |
  |---|---|---|---|
  | direct gateway call | `0.000044` | `0.000044` | exact |
  | url4 run — "capital of France" | `0.007905000` | `0.007905` | exact |
  | url4 run — "largest planet" | `0.009372000` | `0.009372` | exact |

  What this proved that no unit test could: the exact-decimal chain survives a real provider —
  OpenRouter's raw body carries `cost: 4.4e-05` (a float once JSON-parsed) and `"0.000044"` reached
  the wire unrounded across four processes; the 1 credit = 1 USD assumption holds for this account;
  and `provider` / `response_model` arrive authoritatively (`openrouter`,
  `anthropic/claude-haiku-4.5`) rather than derived from the requested id.

  **Method note worth keeping:** OpenRouter's usage endpoint lags roughly 10–40s. A first comparison
  appeared to be off by `0.000058`, which turned out to be a probe call of my own inside the
  measurement window — not a defect. Every figure above comes from a settle loop (poll until two
  consecutive reads agree) around exactly one run.

  **Not exercised live, and stated as such:** every live run was single-call / single-span, so the
  multi-span rollup and the poisoning rule were NOT proven against a real provider — only by unit
  tests, each verified to fail with its guard removed. An attempt at a nested two-model expression
  ran and matched, but the gateway log shows it made one call: the inner expressions resolved as data,
  not model calls, so the expression form was wrong for a fan-out. Also untested live: the
  cache-hit-priced-at-zero branch (every run reported `cache: bypass`) and the unpriced branch (no
  Anthropic credential on the box).

  Secret hygiene: the key lived only in a `600` scratchpad file and process env, was never written to
  a tracked path (verified by grepping the full key across the repo — no hits), and the key file, env
  file and the sqlite DB holding the encrypted credential were deleted afterwards. The key was
  disclosed in a chat transcript and must be rotated regardless.

  **Local bring-up findings (not fixed here):** aigateway has migrations under
  `src/aigateway/migrations/` but nothing applies them at startup and there is no CLI to do it, so a
  fresh DB starts with `no such table: credential_blobs`. Tests use `Tortoise.generate_schemas()`; I
  did the same for a throwaway DB. Separately, a url4 expression with an empty `('')` source produces
  an empty message that OpenRouter rejects with HTTP 400 surfacing as `bad_request` — the source needs
  real text.

- **Deviations:**
  1. §3.4 of the spec was **corrected after implementation**: it required an unknown token class to
     force `unpriced`, which is wrong under a provider-authored pricing method and was deliberately
     not implemented. §4 case 13 was corrected to match. Recorded inline in the spec rather than
     silently, so the spec and the code agree.
  2. One prior test was changed under owner authorisation — see the `OME-851` ledger for the full
     Confidence-Gate record.

- **S1 (migrations):** not applicable — no schema change in any unit of this epic.

- **Open at hand-off:** the `packages/screamingface` warning noise (a third sub-issue, not yet filed),
  and the two questions in spec §7.
