# OME-899 — Implementation plan

1. Add sync and async regression tests at the public Leaderboards interface proving protected
   score reads and submissions use Scoreboard-origin authentication rather than Engine
   credentials.
2. Bind a Scoreboard-origin Cloudflare Access adapter to each Scoreboard HTTP client at the
   existing Client transport seam.
3. Mark Scoreboard requests replay-safe only for read methods or requests carrying an
   `Idempotency-Key`, and include the new adapter in logout and close lifecycles.
4. Run focused Client/Leaderboard tests, static checks, and the full ScreamingFace gate.
5. Exclude notebook execution changes, record the outcome, and open the OME-899 pull request.
