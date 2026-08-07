**Goal:** Replace the temporary shared-API-key stub on `POST /v1/scores` with the mesh-verified
`X-User-Email` identity header, exactly the pattern aigateway already runs in production.

**Architecture:** No new abstraction layer. A small `core/auth/cloudflare_identity.py` module
(header constant + peer-network check + header parse, all pure functions, no DB/Account model —
scoreboard has no accounts table and doesn't need one) plus one resolver function called directly
inside `submit_score`, which either trusts the client-supplied `submitted_by` (dev/test default,
`auth_mode=disabled`) or requires and reads the verified header (`auth_mode=cloudflare_headers`).

**Tech Stack:** Python/FastAPI/Pydantic-settings, matching `apps/scoreboard`'s existing stack — no
new dependencies.

**Source:** `apps/aigateway/src/aigateway/core/auth/cloudflare_identity.py` +
`apps/aigateway/src/aigateway/core/auth/middleware.py::_account_from_cloudflare_headers` +
`apps/aigateway/src/aigateway/config.py`'s `auth_mode`/`allowed_networks` fields — read in full
before writing any of this.

## What's being removed

`apps/scoreboard/src/scoreboard/routes/scores.py::_require_submission_api_key` and its
`Depends()` wiring, plus `Settings.submission_api_key` in `apps/scoreboard/src/scoreboard/config.py`
— both carry an `AIDEV-NOTE` that explicitly says to delete them once OME-326 ships real identity.
OME-326 shipped today (2026-08-03).

## Task 1: Settings — `apps/scoreboard/src/scoreboard/config.py`

- Remove `submission_api_key` and its AIDEV-NOTE.
- Add, mirroring aigateway's fields (simplified — scoreboard needs only two modes, no legacy
  `auth_enabled` reconciliation, no `jwt`/bearer mode, no `admin_emails` equivalent):
  ```python
  AuthMode = Literal["disabled", "cloudflare_headers"]

  auth_mode: AuthMode = "disabled"
  allowed_networks: Annotated[tuple[IPv4Network | IPv6Network, ...], NoDecode] = Field(default=())
  ```
  (`env_prefix="SCOREBOARD_"` already applies automatically — no explicit `validation_alias`
  needed, matching how `submission_api_key` worked before.)
- Add the same `_parse_allowed_networks` `field_validator(mode="before")` as aigateway's
  (comma-separated CIDR strings, `strict=True` on `ip_network`).

## Task 2: New module — `apps/scoreboard/src/scoreboard/core/auth/cloudflare_identity.py`

Port verbatim (these are pure, Account-free, so they move over unchanged):
- `HEADER_USER_EMAIL = "X-User-Email"`
- `peer_in_networks(host: str | None, networks: Sequence[IPv4Network | IPv6Network]) -> bool`

Port simplified (no `CloudflareIdentity` dataclass, no `Account` lookup — scoreboard stores the
submitter as a plain string, not an account row):
- `identity_from_headers(headers) -> str | None` — `email = (headers.get(HEADER_USER_EMAIL) or "").strip(); return email or None`.

## Task 3: Wire into `apps/scoreboard/src/scoreboard/routes/scores.py`

- Delete `_require_submission_api_key` and its `dependencies=[Depends(...)]` on `submit_score`.
- Add a plain async helper (not a `Depends` — it needs the already-parsed `submission` body for
  the disabled-mode fallback, which is simplest called directly rather than fought through FastAPI's
  dependency graph):
  ```python
  async def _resolve_submitter(request: Request, submission: ScoreSubmission) -> str | None:
      settings = cast(Settings, request.app.state.settings)
      if settings.auth_mode == "disabled":
          return submission.submitted_by
      if not peer_in_networks(
          request.client.host if request.client is not None else None,
          settings.allowed_networks,
      ):
          raise HTTPException(status.HTTP_403_FORBIDDEN, detail="...")
      email = identity_from_headers(request.headers)
      if email is None:
          raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=f"Missing {HEADER_USER_EMAIL} — ...")
      return email
  ```
- In `submit_score`, right after validating the benchmark exists: resolve the submitter, then
  `submission = submission.model_copy(update={"submitted_by": submitted_by})` before calling
  `store.submit(...)`. This keeps `scores/store.py` completely untouched — the override happens
  before the submission ever reaches the store.
- Update the module docstring (currently describes the API-key stub) and add 401/403 to
  `SUBMIT_SCORE_RESPONSES`.

## Task 4: Chart — `apps/scoreboard/charts/scoreboard/templates/networkpolicy.yaml`

Current template allows an empty `from:` (renders an ingress rule with no `from:` when
`ingressCIDRs` is empty) — aigateway's own comment calls exactly this shape "an allow-all wearing
the name of a restriction" and fails the render instead. Bring scoreboard's template to the same
safety bar: fail the render if `networkPolicy.enabled=true` with no peers declared, rather than
silently producing an unrestricted rule. Mirror aigateway's `{{- if not $peers -}}{{- fail ... -}}`
guard; scoreboard doesn't need the namespace/pod-selector richness (no in-cluster peer pods to
address today — only `ingressCIDRs`), so the peer-building logic can stay simpler.

## Task 5: Tests — `apps/scoreboard/tests/unit/test_scores_routes.py`

Existing tests all rely on the current default (auth disabled) and pass `submitted_by` as free
text or omit it — these keep passing unchanged since `auth_mode` still defaults to `"disabled"`.
Add new cases (mirroring `apps/aigateway/tests/unit/auth/test_cloudflare_identity.py` and
`test_allowed_networks.py`'s style, using `headers={...}` on `score_client.post(...)` exactly like
the existing Idempotency-Key tests), against an `app_with_benchmark` variant built with
`auth_mode="cloudflare_headers"` and a permissive `allowed_networks`:
- Header present, peer allowed → 201, stored `submitted_by` equals the header email, not any
  `submitted_by` the body tried to send.
- Header absent → 401.
- Header blank (`""`) → 401 (not treated as anonymous).
- Peer outside `allowed_networks` → 403, even with a valid header.
- A forged `X-Forwarded-For` does not substitute for the real peer or the identity header.

## Task 6: Docs closeout

- Fill `docs/work/2026-08-03-OME-404-authenticated-leaderboard-submissions.md`'s Outcome section.
- Update `docs/tasks/2026-08-03-OME-404-authenticated-leaderboard-submissions.md` status to done.
- Close OME-404 in Linear with the card's `close_template` (commits, gates, ledger path,
  deviations, owner-verify note — flag the network-trust boundary as something the platform team
  should visually confirm once deployed, since it can't be verified from unit tests alone).

# Stack conventions (apps/scoreboard, python/uv/FastAPI)

- Gates: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`,
  `uv run pytest --cov=scoreboard --cov-fail-under=80 -q`, all from `apps/scoreboard/`.
- Complexity thresholds (mccabe ≤8, max-statements 26, max-branches 7, max-returns 3 — see
  `apps/scoreboard/docs/complexity-baseline.md`): `_resolve_submitter` has 3 branches / 3 returns,
  within budget without a threshold-bump follow-up.
- Tortoise-dev companion skill is mandatory for this unit (Score model touched via
  `model_copy`, not schema/migration changes — no new migration needed here).

## Self-review

- Does this touch `scores/store.py`? No — the identity override happens on the Pydantic model
  before it reaches the store, so `_submission_to_kwargs` and the store's tests are untouched.
- Does this duplicate security-critical code across two apps? Yes — `peer_in_networks` and the
  header constant are copied, not shared, from aigateway. Per this repo's own "shared logic used
  by ≥2 apps belongs in packages/" rule, a `packages/` extraction is the more correct long-term
  home once a third consumer exists; flagging this explicitly rather than silently deciding either
  way, since creating a new package (own toolchain/lockfile/CI lane) is a bigger structural
  commitment than what was scoped here.
- Backward compatibility: existing callers relying on `submitted_by` free text keep working
  unchanged as long as `SCOREBOARD_AUTH_MODE` stays unset (`disabled`) — only deployments that
  explicitly opt in to `cloudflare_headers` mode see the new enforcement.
