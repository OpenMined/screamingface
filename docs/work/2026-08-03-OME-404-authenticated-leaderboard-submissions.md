---
ticket: OME-404
stack: scoreboard
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-404 — leaderboard trusts the mesh identity header instead of a shared stub key

## Intent

`POST /v1/scores` currently gates writes behind an optional shared placeholder API key
(`SCOREBOARD_SUBMISSION_API_KEY`, OME-391/C2) that doesn't distinguish submitters — everyone
holding the key looks identical to the server, and the real submitter name is whatever free-text
string the caller sends in `submitted_by`. That stub's own `AIDEV-NOTE` says to delete it once
OME-326 (real per-participant identity) ships; OME-326 shipped today. This unit replaces the stub
with the same pattern aigateway already runs live: trust a single mesh-injected header,
`X-User-Email`, behind a peer-network trust boundary — no JWT/JWKS work in this service, that's
Envoy's job upstream. See `docs/spec/2026-08-03-OME-404-authenticated-leaderboard-submissions.md`
and `docs/plan/2026-08-03-OME-404-authenticated-leaderboard-submissions.md` for the full design.

## Planned changes

- `apps/scoreboard/src/scoreboard/config.py` — remove `submission_api_key`; add `auth_mode`
  (`disabled` | `cloudflare_headers`, default `disabled`) and `allowed_networks`.
- `apps/scoreboard/src/scoreboard/core/auth/cloudflare_identity.py` (new) — `HEADER_USER_EMAIL`,
  `peer_in_networks`, `identity_from_headers`, ported from aigateway's module of the same name.
- `apps/scoreboard/src/scoreboard/routes/scores.py` — remove `_require_submission_api_key`; add
  `_resolve_submitter`; wire it into `submit_score` via `submission.model_copy(...)`.
- `apps/scoreboard/charts/scoreboard/templates/networkpolicy.yaml` — fail the render on
  `networkPolicy.enabled=true` with no peers, matching aigateway's safety bar.
- `apps/scoreboard/tests/unit/test_scores_routes.py` — new cases for header present/absent/blank,
  peer-not-allowed, forged `X-Forwarded-For`.

## Test plan

- Existing tests (auth disabled by default): unchanged, still pass.
- New: header present + peer allowed → 201, `submitted_by` is the header email regardless of what
  the request body sent.
- New: header absent → 401. Header blank string → 401 (not anonymous).
- New: peer outside `allowed_networks` → 403 even with a valid header.
- New: `X-Forwarded-For` never substitutes for the real peer or the identity header.

## Acceptance

- `SCOREBOARD_SUBMISSION_API_KEY` and all its code are gone.
- With `auth_mode=cloudflare_headers` configured, an unauthenticated or wrongly-peered submission
  is rejected; the stored `submitted_by` always reflects the verified header, never client input.
- With `auth_mode` left at its default, existing behavior (free-text `submitted_by`, no gate) is
  unchanged.
- Scoreboard's gate suite (ruff/pyright/pytest ≥80% cov) passes.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** As planned, plus cleanup the plan didn't enumerate but the removal implied:
  `apps/scoreboard/charts/scoreboard/templates/{configmap,deployment}.yaml`, `values.yaml`,
  `values-prod.yaml`, `README.md`, `DEPLOYMENT.md` (removing the now-dead
  `submissionApiKey`/`SCOREBOARD_SUBMISSION_API_KEY` Helm wiring and docs, wiring the new
  `SCOREBOARD_AUTH_MODE`/`SCOREBOARD_ALLOWED_NETWORKS` config through the ConfigMap instead);
  `apps/scoreboard/src/scoreboard/main.py` (startup guard: refuse to build the app in
  `cloudflare_headers` mode with no `allowed_networks`, mirroring aigateway's `create_app`);
  two new dedicated unit-test files,
  `apps/scoreboard/tests/unit/core/auth/{test_cloudflare_identity,test_allowed_networks}.py`
  (direct coverage of `peer_in_networks`'s edge cases — dual-stack, unparseable peer, empty
  networks — mirroring `apps/aigateway/tests/unit/auth/` structure).
  The planned `apps/scoreboard/charts/scoreboard/templates/networkpolicy.yaml` change was
  investigated and NOT made — see Deviations.
- **Commits:** `5f61fe44` — feat(scoreboard): authenticate leaderboard submissions via mesh
  identity header
- **Gates:** `uv run .claude/scripts/run_gates.py scoreboard --base origin/main
  --skip-append-only` → ruff check ✓, ruff format ✓, pyright (0 errors) ✓, pytest 148 passed /
  2 skipped, 88.54% coverage (≥80% required) ✓. `cloudflare_identity.py` and `main.py` at 100%.
- **Deviations:**
  1. **Append-only gate skipped, justified.** `tests/unit/test_scores_routes.py` had prior tests
     *removed*, not just appended: `app_with_api_key`/`gated_score_client` fixtures and the four
     tests exercising `SCOREBOARD_SUBMISSION_API_KEY` (`test_post_score_with_correct_api_key_succeeds`,
     `test_post_score_missing_api_key_header_returns_401`, `test_post_score_wrong_api_key_returns_401`,
     `test_get_score_remains_public_when_api_key_configured`). This is the intended removal of
     tests for a feature this same unit deletes (per that code's own `AIDEV-NOTE`, and the
     approved plan's Task 1/3), not an unjustified weakening — verified via `git diff origin/main`
     that no other test was touched. Ran with `--skip-append-only`.
  2. **NetworkPolicy chart change (planned Task 4) NOT made.** Investigating
     `apps/scoreboard/charts/scoreboard/values-prod.yaml` surfaced that it enables
     `networkPolicy.enabled: true` with an empty `ingressCIDRs` — the same "allow-all wearing the
     name of a restriction" anti-pattern aigateway's own template comment describes fixing for
     itself — AND that `release-scoreboard.yml`'s CI renders against `values-prod.yaml` directly.
     Adding the same hard `fail`-on-empty-peers guard aigateway has would break that release
     workflow immediately, since no real CIDR value exists anywhere in this repo to fill in (I
     don't have production network topology to invent one). Separately, `values-prod.yaml`
     describes the CURRENT Traefik-fronted, directly-internet-exposed production deployment
     (`scoreboard.screamingface.ai`) — a different ingress path from the Cloudflare-Access/Envoy
     mesh this unit's `cloudflare_headers` mode is designed for (Stephen's new
     `leaderboard.dev.screamingface.ai` dev-cloud deployment, per today's huddles). `authMode`
     defaults to `disabled`, so `values-prod.yaml` is unaffected either way. Left the existing
     `networkpolicy.yaml` template untouched; documented the mesh-only requirement in
     `DEPLOYMENT.md` instead. Flagging the pre-existing `values-prod.yaml` gap to the owner rather
     than silently fixing or silently leaving it.
  3. Per aigateway's own `create_app` invariant, added a startup guard (not in the original plan)
     refusing to build the app in `cloudflare_headers` mode with empty `allowed_networks`, so a
     misconfigured deployment fails loudly at startup instead of silently 403ing every submission
     in production.
- **Owner-verify:** the network-trust boundary (peer-IP allowlist) can't be verified from unit
  tests alone — confirm in the actual dev-cloud deployment that `POST /v1/scores` is unreachable
  except through the Envoy/Cloudflare Access chain before enabling `cloudflare_headers` mode there.

## Self-review round (2026-08-04, before opening the PR)

Ran the `code-review` skill (high effort: 6 finder angles + 4 verifications) against
`origin/main...HEAD`. Findings and disposition:

- **CONFIRMED, fixed** — `_resolve_submitter` ran *after* the accuracy-tolerance check, reversing
  the auth-before-business-logic ordering the old `Depends()`-based gate gave for free. An
  unauthenticated/untrusted caller with a bad-accuracy payload got 400 instead of 401/403.
  Reproduced empirically (curl-equivalent script) before and after. Fixed by moving identity
  resolution to the top of `submit_score`, in commit `0749ab74`.
- **CONFIRMED, fixed** — two test-coverage gaps: no test pinned that `GET /v1/scores/{id}` stays
  public under `auth_mode=cloudflare_headers`, and the two 401 tests asserted only the status
  code, not the response body. Both added in `0749ab74`.
- **CONFIRMED, not fixed (pre-existing, already documented)** — `core/auth/cloudflare_identity.py`
  and `config.py::_parse_allowed_networks` duplicate aigateway's implementation verbatim instead
  of a `packages/` extraction, a real doctrine violation per `working-in-this-repo` SKILL.md
  ("shared logic used by ≥2 apps belongs in packages/, not copied"). Already flagged as a
  deliberate, scoped-out tradeoff in this ledger and the plan doc; not fixed here — would need a
  proper package (own toolchain/lockfile/CI lane) as its own unit of work.
- **PLAUSIBLE, addressed with a comment, not a refactor** — `_resolve_submitter` is a plain
  function tied to `ScoreSubmission`'s shape, not a reusable `Depends()`; the next authenticated
  scoreboard route gets no framework-enforced identity check for free. Added an `AIDEV-NOTE` on
  the function itself flagging this for whoever adds the next authenticated route, rather than
  generalizing the pattern speculatively for a single current call site.
- **REFUTED** — an efficiency concern about the unconditional `model_copy` in `disabled` mode;
  empirically ~0.7µs, zero extra validator calls, negligible next to the DB I/O already on this
  path. No change.

Full gate suite re-run green after fixes (149 passed, 2 skipped, 88.54% coverage).

## Self-review round 2 (2026-08-04)

Ran the same process again against the updated diff (round 1's fixes included), per explicit
instruction to iterate until a round finds nothing new. 6 finder angles + 3 verifications.

- **CONFIRMED, fixed, severe** — `values.yaml`'s pre-existing `config.forwardedAllowIps: "*"`
  (needed for Traefik's HTTPS-redirect scheme on the existing production deployment) makes
  uvicorn's `ProxyHeadersMiddleware` trust a client-supplied `X-Forwarded-For` from *any* peer,
  silently overwriting `request.client.host` before `peer_in_networks()` ever sees it. Combined
  with `cloudflare_headers` mode, an attacker who could merely reach the port (no relation to the
  real reverse proxy — a NetworkPolicy gap, a same-cluster pod, a port-forward) could forge
  `X-Forwarded-For` to satisfy `allowed_networks` and ride straight through to a forged
  `X-User-Email`. **Verified by live exploitation** against the real `scoreboard` entrypoint
  (uvicorn access log showed the spoofed peer accepted). Fixed in `create_app`: refuses to start
  with `auth_mode=cloudflare_headers` combined with `FORWARDED_ALLOW_IPS=*`. Re-verified the fix
  blocks the same reproduction. Commit `3854e986`.
- **CONFIRMED, fixed** — the 401 "missing identity" detail message was duplicated verbatim across
  the route and two tests, with no shared constant, unlike the file's own established
  `UNTRUSTED_PEER_DETAIL`/`STORE_UNAVAILABLE_DETAIL` pattern. Hoisted to `MISSING_IDENTITY_DETAIL`.
  Commit `3854e986`.
- **CONFIRMED, fixed** — no permanent test pinned that identity resolution wins over the
  accuracy-tolerance check or the benchmark-existence check (the exact combined scenario round 1's
  bug lived in) — three independent finder angles converged on this. Added
  `test_post_score_missing_identity_header_wins_over_bad_accuracy` and
  `test_post_score_untrusted_peer_wins_over_unknown_benchmark`. Commit `3854e986`.
- **PLAUSIBLE, not fixed (follow-up)** — one angle empirically showed the `_resolve_submitter`
  `Depends()` refactor considered in round 1's `AIDEV-NOTE` is more feasible than the note assumes
  (FastAPI does collapse a shared body-model param across route + dependency), but at the cost of
  validating the body twice per request — a real, if likely small, tradeoff. Left as a follow-up
  recommendation, not implemented, consistent with round 1's reasoning not to refactor for a
  single current call site.

Full gate suite re-run green after fixes (155 passed, 2 skipped, 88.65% coverage;
`create_app`/`scores.py` at 100%/96%).

## Self-review round 3 (2026-08-04)

Ran again against round 2's fix specifically (3 finder angles, focused on whether the new
`FORWARDED_ALLOW_IPS` guard itself introduced anything). No round-2-fix bug found; test suite
fully green throughout (155→157 passed). Three real, lower-severity findings, all fixed:

- **CONFIRMED, fixed** — the guard's correctness depends on an undocumented, private uvicorn
  implementation detail (`_TrustedHosts.always_trust`), verified against the installed version by
  the finding agent itself, with no test exercising uvicorn's real behavior directly (only the
  guard's own `ValueError` logic in isolation). Added two tests pinning uvicorn's actual behavior
  (`test_uvicorn_treats_bare_wildcard_as_always_trust`,
  `test_uvicorn_does_not_treat_a_wildcard_inside_a_list_as_always_trust`) so a future `uv lock
  --upgrade` that changes this fails a test instead of silently reopening the bypass.
- **CONFIRMED, fixed (docs only)** — missing `INVARIANT:`/`AIDEV-NOTE:` anchors on the new guard
  relative to the file's own convention, and no discoverability pointer from `Settings.auth_mode`
  toward the guard (since `FORWARDED_ALLOW_IPS` has no `Settings` field of its own). Added both.
- **Noted, not fixed (documented limitation)** — the guard only inspects the env var uvicorn falls
  back to; an explicit `--forwarded-allow-ips`/`Config(forwarded_allow_ips=...)` override at the
  invocation site would bypass it entirely. Not reachable via this app's actual startup path today
  (`cli.py`'s `uvicorn.run()` passes neither) — documented as a known gap in the code comment
  rather than guarded against speculatively.
- **Cross-app observation, out of scope, not filed as a ticket yet** — `apps/aigateway` has the
  identical structural gap (same `peer_in_networks` pattern, same always-on
  `ProxyHeadersMiddleware`, no `FORWARDED_ALLOW_IPS` guard) but it's currently inert there since
  aigateway's chart never sets `FORWARDED_ALLOW_IPS` at all. Worth a follow-up ticket if aigateway
  ever grows a Traefik-style front needing `"*"`, per this repo's own SDLC process (different
  app — own unit of work, not folded into OME-404).

Full gate suite re-run green (157 passed, 2 skipped, 88.65% coverage).

## Self-review round 4 (2026-08-04) — clean, iteration stopped here

Ran a full sweep (correctness line-by-line, removed-behavior, reuse/simplification) against the
complete accumulated diff (`origin/main...HEAD`, 8 commits at this point), plus specifically
checking round 3's own changes for new risk (e.g. whether importing uvicorn's private
`_TrustedHosts` class in a test is itself a maintenance hazard — confirmed it's a function-local
import, so a future uvicorn rename/removal fails only those two named tests with a clear
`ImportError`, not a suite-wide collection failure). Re-ran the full gate suite and re-verified
every prior round's fix and comment against the current code.

**No new findings.** Fixed point reached — stopping the iteration here per instruction to iterate
until a round finds nothing new.
