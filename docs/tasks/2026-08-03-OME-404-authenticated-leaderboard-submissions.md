---
id: OME-404
linear_url: https://linear.app/openmined/issue/OME-404/leaderboard-stub-to-accept-authenticated-submissions
status: done
type: task
priority: P1
labels: [scoreboard, agentic, autonomous]
created: 2026-08-03
closed: 2026-08-03
---

`POST /v1/scores` accepted submissions behind an optional shared placeholder API key
(`SCOREBOARD_SUBMISSION_API_KEY`, OME-391/C2) that didn't distinguish submitters, and stored
whatever free-text `submitted_by` the caller sent. Blocked on OME-326 (real per-participant
identity), which shipped 2026-08-03.

Replaced the stub with the mesh-verified `X-User-Email` identity header, mirroring the pattern
already live in `apps/aigateway` (`core/auth/cloudflare_identity.py` +
`core/auth/middleware.py::_account_from_cloudflare_headers`) — no JWT/JWKS verification in
scoreboard itself, that stays Envoy's job. Defaults to `disabled` (unchanged free-text behavior)
until `SCOREBOARD_AUTH_MODE=cloudflare_headers` is explicitly set. See
`docs/spec/2026-08-03-OME-404-authenticated-leaderboard-submissions.md`,
`docs/plan/2026-08-03-OME-404-authenticated-leaderboard-submissions.md`, and
`docs/work/2026-08-03-OME-404-authenticated-leaderboard-submissions.md` (Outcome section, incl.
one deliberately-not-made chart change — a pre-existing `values-prod.yaml` NetworkPolicy gap that
would break `release-scoreboard.yml` CI without real production CIDR values).

Commit: `5f61fe44`.
