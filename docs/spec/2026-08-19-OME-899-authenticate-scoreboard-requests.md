# OME-899 — Authenticate protected Scoreboard requests

## Decision

The reusable `Client` owns one Cloudflare Access authentication adapter per configured service
origin. The Engine HTTP client remains bound to the Engine adapter and the Scoreboard HTTP client
is bound to a Scoreboard adapter. Leaderboard methods stay transport-agnostic and the public
`sf.leaderboards` interface does not grow authentication or header parameters.

Authentication remains reactive. Public Scoreboard responses pass through without starting a
browser flow; an Access challenge on a protected Scoreboard route authenticates against that
origin and replays only when the caller marked the request safe. Reads are safe to replay, while
score submission is safe only because it already carries a stable `Idempotency-Key` derived from
the evaluation run id.

This origin-scoped design works when Engine and Scoreboard share one Access audience and when a
deployment assigns them different audiences. It does not copy an opaque Engine token across
origins or encode the current dev Cloudflare topology into the public Client interface.

## Invariants

- `leaderboards.list()` and `leaderboards.get(...)` remain anonymous when the deployment exposes
  them publicly.
- `leaderboards.get_score(...)` may authenticate and replay its safe GET after an Access
  challenge.
- `leaderboards.submit(...)` may authenticate and replay only with an `Idempotency-Key`.
- Sync and async Clients have the same authentication, replay, logout, and close behaviour.
- `Client.authenticated` and the connection panel continue to describe Engine caller
  authentication; Scoreboard authentication is demand-driven and internal.
- Closing or logging out a Client accounts for every authentication adapter it owns.

## Explicit limitations

- Cloudflare Access application and policy configuration remains deployment-owned.
- This change does not publish a new SDK release or alter Scoreboard authorization policy.
- A deployment may still challenge routes that are public elsewhere; the Client responds to the
  challenge instead of hard-coding which routes require authentication.
