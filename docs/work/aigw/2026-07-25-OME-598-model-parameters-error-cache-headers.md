---
ticket: OME-598
stack: aigateway
status: done
started: 2026-07-25
finished: 2026-07-25
---

# OME-598 — Apply private cache headers to model-parameters error responses

## Intent

`GET /v1/model-parameters` (routes/model_parameters.py) serves a per-account/per-profile contract and
declares it non-shareable with `Cache-Control: private, no-store` + `Vary: Authorization, X-Profile`.
Those two headers are assigned at `:106-107` — AFTER `build_model_parameter_document` succeeds — so
they only ever reach the wire on the normal return. Every error exit leaves without the policy the
route's own module docstring promises.

The bodies that escape uncovered are the profile-dependent ones, i.e. exactly the responses that carry
caller-identifying data: `404 profile_not_found`, `409 profile_pending_auth`, and `401 auth_required`
(the last carries a profile-specific `reauth_url`), plus `404 model_not_found` and the
unknown/malformed-provider `400`s.

## Design (confirmed against the installed libraries)

**Root cause — two distinct header channels.** Verified by reading the installed FastAPI:

- Normal return: `fastapi/routing.py::get_request_handler` does
  `response.headers.raw.extend(solved_result.response.headers.raw)` — the injected `Response` is
  merged into the reply only AFTER the handler returns normally.
- Raise: `fastapi/exception_handlers.py::http_exception_handler` builds a fresh
  `JSONResponse(..., headers=getattr(exc, "headers", None))` — it reads the EXCEPTION's headers and
  never consults the injected `Response`.

So a policy set on the injected `Response` is structurally invisible to every raise. This is a general
FastAPI trap, not a local slip: any route setting a security header that way loses it on all errors.

**Chosen fix — a route-level boundary (the finding's own second option).** Hoist the policy to a
module constant, assign it to the injected response BEFORE any profile-dependent branch, and wrap the
handler body in `except HTTPException` that stamps the same policy onto the exception and re-raises.

Two consequences verified by reading the raise sites:

1. `_credential_target_for_chat` (routes/chat_credentials.py:134-185) and its helper
   `_active_oauth_connection_for_profile` (:89-131) raise plain `HTTPException` with detail dicts and
   NO `headers=`. Catching at the route covers helper-raised errors without editing the shared helper
   — which the chat route also uses, so editing it would widen blast radius for no gain.
2. Merge direction is `{**(exc.headers or {}), **_PRIVATE_CACHE_HEADERS}` — policy LAST. Any header a
   raiser sets (a future `WWW-Authenticate`, `Retry-After`) is preserved, while the route's cache
   policy wins on the two keys it owns. Fail-closed: an error can never emit a weaker cache directive
   than the success response.

**Deliberately out of scope (documented, not silently skipped):**

- The `401` produced by the `CurrentAccount` dependency fires during dependency resolution, BEFORE the
  handler body, so no in-handler boundary can catch it. It is also generic (no profile data) and
  shared by every authenticated route — changing it is a cross-cutting auth concern, not this unit.
- `CredentialBlobMutationConflict` → `503` is served by the app-level handler registered in
  `main.py:226`, bypassing `except HTTPException`. Also generic, no profile data.

Both are non-profile-dependent, so the finding's acceptance ("every profile-dependent status") is
fully met without them.

**Rejected alternatives:** an app-level `HTTPException` handler (would have to sniff the path, or
impose one route's policy on every route — wrong layer); middleware (broadest blast radius for a
single-route concern); adding `headers=` at each raise site (touches the shared chat helper, and a
future raise would silently forget it — the boundary is the invariant-preserving form). A reusable
decorator is YAGNI at one call site: `/v1/models` is profile-independent and carries no such policy.

## Planned changes

Source (1):
- `src/aigateway/routes/model_parameters.py` — add `_PRIVATE_CACHE_HEADERS` module constant; assign it
  to `response.headers` before the provider/profile branches; wrap the body in
  `except HTTPException` that merges the policy onto `exc.headers` and re-raises. Record the
  two-channel INVARIANT in a comment so a future maintainer does not "simplify" the boundary away.

Tests (1 file, appends):
- `tests/unit/test_model_parameters_route.py` — error-path header coverage (see test plan).

No schema, model, ORM or migration change.

## Test plan (RED first)

Appended to the existing route suite; no prior test touched.

- `404 model_not_found` (bad model id, valid provider) carries both headers.
- `400 unknown provider` carries both headers.
- Profile-dependent `404 profile_not_found` carries both headers.
- Profile-dependent `409 profile_pending_auth` carries both headers, asserted for a distinct
  `X-Profile` value (the finding explicitly asks for two profile values).
- Profile-dependent `401 auth_required` carries both headers AND still carries its `reauth_url`
  detail — proving the boundary adds headers without disturbing the body.

All FAIL before the change (headers absent on every raise); the existing success-path test
`test_returns_locked_headers_and_v1_envelope` must stay green unmodified.

## Acceptance

- Every profile-dependent status (401/404/409) from this route carries `Cache-Control: private,
  no-store` and `Vary: Authorization, X-Profile`.
- `model_not_found` 404 and unknown/malformed-provider 400 carry them too.
- Success response unchanged; full aigateway gate green.

## Outcome

**Status: DONE.** Every response the route produces — success or error — now carries the private
cache policy.

### Actual changes (match plan)

Source (1) — `src/aigateway/routes/model_parameters.py` (109 → 138 lines):
- Added `_PRIVATE_CACHE_HEADERS` module constant with the two-channel INVARIANT comment explaining
  why the policy must be applied twice.
- Extracted `_contract_document(request, *, account_id, model)` — the provider/model/profile
  resolution and document composition, unchanged in behavior.
- The route handler is now purely the HTTP policy boundary: assigns the policy to the injected
  response, delegates, and on `except HTTPException` merges the policy onto `exc.headers` and
  re-raises. Merge is `{**(exc.headers or {}), **_PRIVATE_CACHE_HEADERS}` — policy last.

Tests (1 file, +139 lines, pure append) — `tests/unit/test_model_parameters_route.py`:
- 6 error-path tests: unknown provider 400, unprefixed model 400, `model_not_found` 404,
  `profile_not_found` 404, `profile_pending_auth` 409 (distinct `X-Profile: staging`),
  `auth_required` 401 (asserts the `reauth_url` detail survives alongside the new headers).
- 1 invariant test pinning the merge direction with a synthetic raiser that sets both
  `Retry-After` and a weaker `Cache-Control: public, max-age=600`.
- Added `_seed_profile_record` / `_get_as_profile` / `_assert_private_cache_policy` helpers.

### Quality gate

Full aigateway gate GREEN on the FIRST attempt:
`uv run .claude/scripts/run_gates.py aigateway --skip-append-only` — ruff check ✓ ·
ruff format --check ✓ · pyright ✓ · check_no_enterprise ✓ · pytest --cov ≥80% ✓.
Full unit suite before the gate: 1673 passed. Route suite: 15 passed.

### Verification beyond the gate

- **Library behavior confirmed by inspecting the installed FastAPI**, not assumed:
  `routing.py::get_request_handler` does `response.headers.raw.extend(solved_result.response.headers.raw)`
  (normal return only); `exception_handlers.py::http_exception_handler` builds
  `JSONResponse(..., headers=getattr(exc, "headers", None))`. Two separate channels — the root cause.
- **RED was verified to fail for the right reason:** all 6 new tests failed with
  `cache-control: None` and error headers limited to content-length/content-type.
- **Mutation-tested the new invariant.** Reversing the merge to
  `{**_PRIVATE_CACHE_HEADERS, **(exc.headers or {})}` made `public, max-age=600` reach the wire and
  failed EXACTLY ONE test (the invariant test); the other 14 stayed green. The assertion is therefore
  discriminating and precisely targeted, not vacuous. Reversed edit restored and re-verified green.

### Deviations

1. **Refactor beyond the minimal fix (deliberate).** The minimal GREEN was an inline `try` wrapping
   ~45 lines. Extracting `_contract_document` instead keeps the handler at ~15 lines of pure HTTP
   policy, makes the boundary structurally obvious, and made the merge-semantics test possible via
   monkeypatch. Behavior identical; 1673 tests confirm.
2. **Minor test-helper duplication accepted.** `_seed_profile_record` duplicates ~6 lines of the
   existing `_seed_profile` rather than generalizing it, so no prior test helper is edited
   (append-only discipline valued over removing 6 duplicated lines).
3. **`--skip-append-only` used honestly:** `git diff HEAD -- apps/aigateway/tests | grep '^-'` is
   EMPTY — this unit deleted no prior test line at all.
4. **Two error exits deliberately left uncovered, as designed and documented above:** the
   dependency-level `401` (fires before the handler body, generic, cross-cutting auth concern) and
   `CredentialBlobMutationConflict` → `503` (app-level handler, bypasses `except HTTPException`).
   Neither is profile-dependent, so the acceptance criterion is fully met.

### Observation for a future unit (not fixed here — out of scope)

`routes/chat_dispatch.py:201-206` sets `X-AIGW-Cache*` on the injected response and so loses them on
raises via the same two-channel mechanic. Those are diagnostic/observability headers, not a privacy
policy, so the consequence is cosmetic rather than a leak — noted, not fixed, to keep this unit scoped.

### Commit

`104b8b74` — `fix(aigateway): apply private cache headers to model-parameters error responses`
(`Refs: OME-598, OME-479`). 2 files changed, 181 insertions(+), 12 deletions(-).
