# OME-899 — Authenticate protected Scoreboard requests

## Decision

The reusable `Client` owns one Cloudflare Access authentication adapter per configured service
origin and one in-memory credential store keyed by Access audience. The Engine HTTP client remains
bound to the Engine adapter and the Scoreboard HTTP client is bound to a Scoreboard adapter.
Leaderboard methods stay transport-agnostic and the public `sf.leaderboards` interface does not
grow authentication or header parameters.

Authentication remains reactive. Public Scoreboard responses pass through without starting a
browser flow. An Access challenge first proves the Scoreboard origin's audience. If it matches an
unexpired credential already obtained through `Client.login()` or an Engine request, the
Scoreboard adapter reuses that credential without a second browser transfer. A distinct audience
starts its own origin-specific login. The adapter replays only when the Leaderboards call site
explicitly marked the operation safe; score submission is safe because it already carries a
stable `Idempotency-Key` derived from the evaluation run id.

This audience-scoped design works when Engine and Scoreboard share one Access application and when
a deployment assigns them different applications. It never sends a cached credential to a new
origin until that origin advertises the matching audience, and it does not encode the current dev
Cloudflare topology into the public Client interface.

## Invariants

- `leaderboards.list()` and `leaderboards.get(...)` remain anonymous when the deployment exposes
  them publicly.
- `leaderboards.get_score(...)` may authenticate and replay its safe GET after an Access
  challenge.
- `leaderboards.submit(...)` may authenticate and replay only with an `Idempotency-Key`.
- One successful browser login is sufficient for every configured origin that subsequently
  proves the same Access audience.
- Distinct Access audiences never share credentials and authenticate separately.
- Sync and async Clients have the same authentication, replay, logout, and close behaviour.
- `Client.authenticated` and the connection panel continue to describe Engine caller
  authentication; Scoreboard authentication is demand-driven and internal.
- Closing or logging out a Client accounts for every authentication adapter it owns.
- Replay safety is declared by the domain operation and defaults to denied; it is not inferred
  from an HTTP method.

## Explicit limitations

- Cloudflare Access application and policy configuration remains deployment-owned.
- This change does not publish a new SDK release or alter Scoreboard authorization policy.
- A deployment may still challenge routes that are public elsewhere; the Client responds to the
  challenge instead of hard-coding which routes require authentication.
