---
ticket: OME-400
stack: screamingface
status: blocked
started: 2026-07-20
finished:
---

# OME-400 — Phase 9B.5 live HF and Tavily acceptance

## Intent

Prove the implemented URL4 -> verified Hugging Face model through AI Gateway -> Tavily -> model
loop against real researcher-owned services, beginning with no-spend readiness and one bounded
member before attempting one DRACO Preview case. Configure the two already approved, officially
live DeepInfra pins through AI Gateway's existing deployment environment surface without changing
AI Gateway source or broadening ScreamingFace's verified-tool allowlist.

## Planned changes

- Add the exact DeepSeek V4 Pro/DeepInfra and GLM 5.2/DeepInfra IDs to the local Compose profile's
  AI Gateway model override while retaining every existing default HF route.
- Add an append-only regression test proving the deployment exposes the approved pins and does not
  silently replace the existing model set.
- Update current engine/task documentation with the local configuration and live acceptance state.
- Restart the stack, verify health/registry/connections, then stop before paid work unless all
  readiness checks pass and the researcher has connected Hugging Face and Tavily.
- Preserve AI Gateway payment-required failures as HTTP 402 at the public engine boundary.
- Report exhausted tool-loop limits with the configured round budget and safe per-tool counts.
- Distinguish attempted cases from scored cases in progress, omit empty grading progress, and end
  an incomplete evaluation as stopped rather than complete.

## Test plan

- RED: the Compose contract test requires both exact DeepInfra IDs plus all five prior HF defaults.
- GREEN: the deployment-only model override satisfies the contract and Docker Compose validates.
- Run the focused test, full ScreamingFace gate, container restart, public registry inspection,
  sanitized connection inspection, then separately authorized one-member live acceptance.
- RED/GREEN regression coverage for payment-required mapping, bounded tool-loop diagnostics, and
  incomplete evaluation progress; then the authoritative ScreamingFace gate.

## Acceptance

- Both exact approved routes appear in `/.well-known/screamingface` with `web_search` and
  `web_fetch`; existing HF routes remain available and tool-free.
- Hugging Face and Tavily are connected after the final restart before any model spend.
- One real verified-HF member completes at least one Tavily tool turn and returns final plaintext,
  or the exact external blocker is recorded without adding a fallback.
- No secret is printed, logged, committed, placed in URL4, or sent directly by the SDK to AI
  Gateway or Tavily.
- A failed live case produces an honest stopped receipt: attempted and scored counts remain
  distinct, no `0/0` grading stage is shown, and safe actionable failure context is retained.

## Outcome

- **Actual files:** added a complete local AI Gateway HF model override, its Compose contract test,
  HTTP/payment and tool-budget failure contracts, honest stopped evaluation progress, current
  engine/task documentation, and this live acceptance record. AI Gateway and URL4 source were
  unchanged.
- **Commits:** pending.
- **Gates:** Ruff, formatting, Pyright, 95.34% SDK coverage, all 205 engine tests, and 645 of 646
  combined tests pass. The only substantive-gate failure is the user's locally executed
  `examples/00_quickstart.ipynb`, whose saved output intentionally remains untouched; the
  output-free generated-notebook assertion fails. Focused new/related suites pass 14 SDK and 15
  engine tests. Docker Compose config is valid; the restarted registry exposed seven HF routes
  and both verified pins with exactly `web_search` and `web_fetch`.
- **Deviations:** the bounded DeepSeek canary succeeded with HTTP 200 final plaintext after three
  model turns. The approved one-case DRACO Preview then made multiple successful model turns but a
  later DeepSeek continuation received HTTP 402 Payment Required. The atomic case produced no
  partial Fusion, no grading tasks, and no score; all provider connections remained connected.
  After funding was restored, the second approved one-case Preview reached the GLM member's
  configured 12-round tool budget and correctly returned no partial Fusion or grading spend. That
  run also exposed the progress and error-contract issues covered by this follow-up. No automatic
  retry, model substitution, reduced policy, or second case was attempted.

## Cost boundary

The validated earlier reproduction cost `$3,487.394779` for 100 source questions across its full
seven-solo plus nine-Fusion evaluation matrix (`1,600` planned system evaluations), not for one
Fusion on one question. Dividing by 100 gives `$34.87` for running the entire matrix on an average
source question; dividing by all 1,600 system-question evaluations gives `$2.18` each before
accounting for cache and shared-panel attribution. DRACO Preview runs only one two-member Fusion,
one synthesis, and three judge requests, so `$30` is not a reasonable one-case expectation. An
exact Preview estimate remains unavailable until the engine/Gateway response contract includes
usage and cost telemetry; the current live acceptance must not invent a price from account balance
changes or incomplete requests.
