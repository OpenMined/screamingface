---
ticket: OME-708
stack: aigateway-ui
status: done
started: 2026-07-30
finished: 2026-07-30
---

# OME-708 — apps/aigateway-ui: the admin console over the BFF

## Intent

Make `OME-706`'s `/v1/admin` surface usable by a human. An allowlisted operator lists tenants,
provisions one ahead of their first request, and attaches a static provider API key — closing the
`404 profile_not_found` gap `OME-684` left open.

`OME-707` shipped the registered, CI-gated shell. This is the console itself.

## Design system

**OpenMined DS, not `screamingface-design`** — owner decision during `OME-707`. This is internal
operator tooling, so it wears the parent brand. Tokens are vendored at `src/brand/tokens/`; the
Linear issue's original "Design law" section is superseded and is corrected as part of this unit.

## Architecture — BFF, non-negotiable

The browser never reaches the admin API.

- Every call is server-side: a Server Component read or a Server Action write.
- `src/lib/aigateway/client.ts` carries `import "server-only"`, so a client-component import
  fails the BUILD rather than shipping the admin API's address to a browser.
- `X-User-Email` is read from the incoming request via `next/headers` and forwarded. Never
  constructed, never accepted as input.
- The UI holds **no** copy of the allowlist. A 403 from the API becomes the not-an-admin page.

`peer_in_networks` checks the TCP peer, so in-cluster the UI pod must sit inside
`AIGW_ALLOWED_NETWORKS` — the chart default already admits it.

## Planned changes

- `src/lib/aigateway/schema.d.ts` — generated from aigateway's live OpenAPI (`openapi-typescript`)
- `src/lib/aigateway/client.ts` — server-only typed client + error taxonomy
- `src/lib/auth.ts` — `requireAdmin()`
- `src/components/` — OMDS React primitives (Button, Input, Select, Table, Field, Notice)
- `src/app/page.tsx` — accounts table, search, create form
- `src/app/accounts/[id]/page.tsx` — detail, active toggle, profiles table
- `src/app/accounts/[id]/credentials/new/page.tsx` — API-key form
- `src/app/actions.ts` — server actions + `revalidatePath`
- tests alongside each

## Test plan (RED first)

- client: forwards the header; maps 401/403/503/`profile_index_conflict` to typed errors
- `requireAdmin`: 403 → not-an-admin page, never a local allowlist decision
- accounts page: renders rows, empty state, search
- create form: validation error surfaces, success revalidates
- api-key form: field is `type="password"`; the key never appears in rendered output
- detail page: deactivate toggle, profile list, delete

## Acceptance

- `run_gates.py aigateway-ui` green (5 gates incl. the OMDS token gate)
- Against a live aigateway: create a tenant and attach a key **through the browser**, then confirm
  that tenant's `GET /v1/auth/profiles` returns it
- Light and dark both verified

## Outcome

- **Gates:** `run_gates.py aigateway-ui` — npm ci · lint · lint:css · typecheck · test:ci →
  ALL GATES GREEN. **166 tests**, coverage above the 80% floor.

- **Verified in a browser against a live gateway**, not only in tests: accounts list renders real
  tenants, detail page shows the empty-credentials state, the attach form submits through the
  server action to `/v1/admin/.../api-key`, and the provider's genuine rejection surfaces on the
  right field. Confirmed in the live DOM that `api_key` is `type="password"`, `autocomplete="off"`,
  carries **no** `value` attribute, and that the submitted key is absent from `document.body`
  after the round trip.

- **Method:** a 6-agent workflow (1 primitives + 3 pages in parallel + 2 adversarial reviews).
  The BFF foundation (generated types, client, auth gate) was built inline first, because it is
  the contract everything else depends on.

## Three real defects, and how each was caught

1. **Path traversal in the BFF client — found by the adversarial review agent.**
   `accountId` and `provider` were interpolated raw into the upstream path while `name` went
   through `encodeURIComponent`; the inconsistency inside one template literal read as deliberate.
   `getAccount("../../v1/models")` normalizes to `/v1/v1/models` BEFORE the request is sent, so a
   crafted route param made the console issue an arbitrary gateway call under the admin's
   forwarded identity. Both inputs are attacker-reachable (route param, hidden form field).
   Fixed with a single `segment()` helper on every interpolation; regression test pins it.

2. **The stylelint token gate had a hole — found by the token review agent, with a proof.**
   `declaration-strict-value` is scoped to color-ish properties and `color-no-hex` only sees hex,
   so a functional literal on a SHORTHAND (`outline: 2px solid rgb(...)`) passed every rule — which
   is exactly how every focus ring in this app is written. No live violation, but the gate CLAUDE.md
   calls a merge blocker would not have stopped the next one. Closed with `function-disallowed-list`
   and verified it now rejects the proven bypass.

3. **`anthropic` was missing from the provider dropdown — found by USING the console.**
   `listProviders()` derived providers by splitting model ids on `/`, which silently dropped every
   provider whose models are advertised bare. That is `anthropic`, the one this repo defaults to.
   The list still showed four other providers, so it looked plausible and no test caught it. Now
   reads `owned_by`, which the gateway sets explicitly. Regression test added.

  Defect 3 is the one worth remembering: it was invisible to the type system, invisible to the
  tests, and invisible to two reviewers. Only opening the dropdown found it.

## Deviations

- **A dev-only identity fallback was added** (`AIGATEWAY_DEV_USER_EMAIL`). There is no Envoy in
  front of `npm run dev`, so without it every request 401s and the console cannot be exercised at
  all. Hard-gated on `NODE_ENV !== "production"`, checked at call time so a production build cannot
  be tricked by setting the variable at runtime. aigateway independently refuses header identity
  from outside `AIGW_ALLOWED_NETWORKS`, so two failures would have to line up for it to matter.
- **Coverage excludes** `schema.d.ts` (generated declarations, no runtime code) and `src/brand/**`
  (vendored upstream).
- **The Linear issue's "Design law" section was corrected** in place — it still named
  `screamingface-design`, superseded by OMDS during OME-707.

## Not done

- **The full happy path with a REAL provider key.** Every link is proven except the last: the form
  reaches the provider's genuine validation and surfaces its refusal. `AIGW_E2E_REAL_KEY=<key> bash
  <scratch>/e2e-verify.sh` completes attach → tenant sees profile → the request that 404'd now
  reaches the provider.
- **Dockerfile and Helm chart.** OME-707 deliberately deferred them; they still need writing before
  this deploys.
- **Dark mode was not visually checked for this console.** The tokens switch (verified in OME-707),
  but no screenshot was taken of these pages in dark.
