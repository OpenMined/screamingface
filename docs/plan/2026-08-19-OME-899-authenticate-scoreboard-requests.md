# OME-899 — Implementation plan

1. Add sync and async regression tests at the public Leaderboards interface proving protected
   score reads and submissions use Scoreboard-origin authentication rather than Engine
   credentials.
2. Move the Cloudflare Access adapter to a service-neutral package, bind one adapter to each
   origin, and share credentials only after both origins prove the same Access audience.
3. Declare replay safety explicitly at each Leaderboards operation; permit score submission replay
   only alongside its stable `Idempotency-Key`.
4. Run focused Client/Leaderboard tests, static checks, and the full ScreamingFace gate.
5. Exclude notebook execution changes, record the outcome, and update the OME-899 pull request.
