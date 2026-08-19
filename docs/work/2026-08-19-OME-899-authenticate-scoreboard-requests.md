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
- `packages/screamingface/tests/test_leaderboards.py` — sync and async protected-action regression
  coverage.
- `docs/{tasks,spec,plan,work}/2026-08-19-OME-899-*` — required SDLC artifacts.

## Test plan

- A protected score GET receives Scoreboard credentials and is declared replay-safe.
- An idempotency-keyed score POST receives Scoreboard credentials and is declared replay-safe.
- Engine credentials are not substituted for Scoreboard-origin credentials.
- Sync and async public interfaces return decoded `LeaderboardScore` values.
- Focused tests, Ruff, Pyright, and the full ScreamingFace gate pass.

## Acceptance

- `sf.leaderboards.submit(result.candidates[0])` needs no private header manipulation.
- Protected score reads authenticate through the same internal seam.
- Public reads remain non-interactive when no Access challenge is returned.
- Score submission replay remains idempotency-gated.
- No notebook execution changes are included.

## Outcome

- **Actual files:** sync/async Client Scoreboard-auth wiring and replay declaration;
  Leaderboard regression/lifecycle tests; required OME-899 task, spec, plan, and work artifacts.
- **Commits:** this implementation commit — authenticate protected Scoreboard requests.
- **Gates:** `python3 .claude/scripts/run_gates.py screamingface` — ALL GATES GREEN;
  focused Client/Leaderboard suites — 73 passed; live protected `get_score` through the patched
  public interface — expected `404 unknown_score`, no Access 302.
- **Deviations:** Cloudflare dev configuration changed from separate Engine/Scoreboard audiences
  to one multi-domain audience during diagnosis. The implementation remains origin-scoped so
  custom deployments with separate Access applications are also supported. No notebook changes
  are included.
