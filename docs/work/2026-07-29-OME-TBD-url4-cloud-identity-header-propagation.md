---
ticket: OME-TBD
stack: url4-cloud
status: in_progress
started: 2026-07-29
finished:
---

# OME-TBD — Propagate the PULSE gateway-identity headers to aigateway

## Intent

Envoy verifies who is calling and re-injects the result as four plain headers
(https://pulse.dev.openmined.org/docs/products/gateway-identity-flow/). url4-cloud must carry
that identity to aigateway so the gateway can attribute a chat request to a principal without
parsing a token itself.

The App and the Runner are different Pods, so this is NOT header pass-through. The App captures
the headers, serializes them into the Job spec as plain env, and the Runner re-renders them onto
its outgoing aigateway request. `packages/url4` is deliberately untouched: the engine reaches
aigateway through the connector, and the connector already carries per-run values (`token`,
`profile`) this way.

Headers carried: `X-User-Email`, `X-User-Id`, `X-Service-Id`, `X-Tenant`.

## Planned changes

- `src/url4_cloud/job_env.py` — the four env names, the header↔env table, `identity_from_headers`
  / `identity_to_env` / `identity_from_env`; add the names to `WRITTEN_BY_APP` (NOT `SECRET` —
  identity is not a credential).
- `src/url4_cloud/ports.py` (new) — `IdentityAwareJobRunner(JobRunner)`, widening `schedule` with
  `identity`. The port itself lives in `packages/url4` and is out of scope, so the widening is
  declared locally.
- `src/url4_cloud/rest/routes.py` — read identity off the inbound request, pass through `_schedule`.
- `src/url4_cloud/adapters/inprocess.py` — `schedule`/`_env` carry identity.
- `src/url4_cloud/adapters/k8s.py` — `schedule`/`_schedule_blocking`/`_manifest`/`_env` carry it
  as plain env values.
- `src/url4_cloud/runner/main.py` — read identity from env, pass to `build_aigateway_world`.
- `src/url4_cloud/runner/connector.py` — `build_aigateway_world(identity_headers=…)`,
  `_ModelEndpoint`, `_headers()` merge.
- Test fakes: `tests/unit/_fakes.py`, `tests/integration/test_e2e_compose_flow.py`.

## Test plan

- Identity headers on `GET /` reach the scheduled Job's env (all four, and any subset).
- Absent headers write no env keys — no empty-string identity.
- `_headers()` renders the identity onto the aigateway POST alongside `Authorization`/`X-Profile`.
- Identity survives the env round-trip in both adapters (the two renderings agree).
- Identity is NOT in `job_env.SECRET`; it IS in `WRITTEN_BY_APP` (existing
  `test_job_env_contract.py` enforces both adapters write it).
- A caller-supplied identity header cannot override the gateway-owned `Authorization` header.

## Acceptance

- A run started through Envoy sends `X-User-Email`/`X-User-Id`/`X-Service-Id`/`X-Tenant` on its
  `POST /v1/chat/completions` to aigateway.
- `packages/url4` has no diff.
- `check_layering.py` clean; `run_gates.py` clean.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus `tests/unit/test_identity_header_propagation.py` (13 tests) and
  a one-line `ruff format` fix to `rest/catalog.py` — pre-existing formatting drift on this branch
  that `ruff format --check` fails on; unrelated to this change but the gate cannot pass without it.
- **Commits:** not committed yet.
- **Gates:** `run_gates.py url4-cloud --skip-append-only` → ALL GATES GREEN (ruff, ruff format,
  pyright 0 errors, check_layering, pytest 488 passed / 5 skipped, coverage ≥80).
- **Deviations:**
  - `packages/url4` untouched, per owner instruction mid-task. The `JobRunner` port lives there, so
    the `identity` parameter is declared in a local `IdentityAwareJobRunner` subclass instead.
  - Absent identity normalizes to `None`, not `{}` — one representation for "nothing to forward",
    matching `credential`/`profile`. Two existing tests asserted this and were left untouched.
  - No Linear issue filed (owner deferred it); ticket id still `OME-TBD`.

## Not done — needed before this is usable end to end

- aigateway does not yet READ these headers. It still authenticates via its own JWT
  (`core/auth/middleware.py` reads `Authorization`), so identity currently arrives and is ignored.
  That is the aigateway half of the cross-cutting change.
- The chart/Envoy side is unverified: nothing here proves aigateway is unreachable except from
  url4-cloud and Runner Pods, and header trust is only sound if it is.
