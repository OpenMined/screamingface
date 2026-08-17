---
ticket: OME-849
stack: repo
status: in_progress
started: 2026-08-17
finished:
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

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** <vs planned>
- **Commits:** <sha — message>
- **Gates:** <run_gates.py result line / counts>
- **Deviations:** <anything that differed from the plan, or "none">
