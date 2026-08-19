---
ticket: OME-899
stack: screamingface
status: in_progress
started: 2026-08-19
finished:
---

# OME-899 — Authenticate protected Scoreboard requests

## Intent

Make every protected Scoreboard action work through the normal Python SDK interface by placing
Cloudflare Access authentication at the Client's Scoreboard transport seam, without making public
reads interactive or risking duplicate score submissions.

## Planned changes

- `packages/screamingface/src/screamingface/client.py` — Scoreboard-origin authentication, replay
  declaration, and lifecycle ownership.
- `packages/screamingface/src/screamingface/_access/` — service-neutral Access adapter and
  audience-scoped in-memory credential sharing.
- `packages/screamingface/src/screamingface/_scoreboard/leaderboards.py` — explicit domain-owned
  replay declarations.
- `packages/screamingface/tests/test_authentication.py` — same- and distinct-audience regression
  coverage.
- `packages/screamingface/tests/test_leaderboards.py` — sync and async protected-action regression
  coverage.
- `docs/{tasks,spec,plan,work}/2026-08-19-OME-899-*` — required SDLC artifacts.

## Test plan

- A protected score GET receives Scoreboard credentials and is declared replay-safe.
- An idempotency-keyed score POST receives Scoreboard credentials and is declared replay-safe.
- Engine credentials are not substituted for Scoreboard-origin credentials.
- A Scoreboard origin proving the Engine audience reuses the existing credential without a second
  browser login; a distinct audience starts a separate login.
- Sync and async public interfaces return decoded `LeaderboardScore` values.
- Focused tests, Ruff, Pyright, and the full ScreamingFace gate pass.

## Acceptance

- `sf.leaderboards.submit(result.candidates[0])` needs no private header manipulation.
- Calling it after one Engine login does not request a second browser login when the two origins
  advertise the same Access audience.
- Protected score reads authenticate through the same internal seam.
- Public reads remain non-interactive when no Access challenge is returned.
- Score submission replay remains idempotency-gated.
- No notebook execution changes are included.

## Outcome

- **Actual files:** service-neutral Access authentication with an audience-keyed credential store;
  sync/async Client Scoreboard wiring and lifecycle ownership; explicit Leaderboards replay
  declarations; same- and distinct-audience regressions; required OME-899 SDLC artifacts.
- **Commits:** `4d27a2a6` — initial protected Scoreboard authentication; the current change refines
  shared-audience credential reuse and lifecycle cleanup.
- **Gates:** authentication suite — 73 passed; focused authentication/Leaderboard suites — 118
  passed; the complete ScreamingFace gate is green, including Ruff, formatting, Pyright, coverage,
  notebook validation, package build, and distribution checks.
- **Deviations:** Cloudflare dev configuration changed from separate Engine/Scoreboard audiences
  to one multi-domain audience during diagnosis. The implementation remains origin-scoped so
  custom deployments with separate Access applications are also supported. No notebook changes
  are included.
