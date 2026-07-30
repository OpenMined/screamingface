---
ticket: OME-684
stack: aigateway
status: done
started: 2026-07-30
finished: 2026-07-30
---

# OME-684 — refuse header identity from outside the declared networks

PR #444 review. Continues the branch; does not change any decision the earlier ledgers record.

## Intent

`cloudflare_headers` mode trusts `X-User-Email` because the mesh guarantees a client cannot set it.
Today two things enforce that guarantee, and **both are deployment configuration**: no Ingress, and
the aigateway NetworkPolicy. The topology diagram already flags the second as an *unverified
precondition* — a NetworkPolicy only restricts traffic if the cluster's CNI enforces it, and where
it does not, the object is decoration and the mode is an open impersonation endpoint.

This adds the same boundary **in the application**, where no CNI can decline to enforce it: in
`cloudflare_headers` mode the caller's peer address must fall inside a declared set of networks, or
the request is refused before the header is read. Defence in depth behind the NetworkPolicy, not a
replacement for it.

## Decisions (owner, this session)

1. **In the auth path, not middleware.** The check goes in `_account_from_cloudflare_headers` —
   exactly where the header is trusted. Rejected an app-wide middleware: kubelet liveness/readiness
   probes originate from the **node** IP, not the Pod CIDR, so a blanket check would fail every
   probe and CrashLoop the Pod unless `/health` were exempted — a carve-out the auth-path placement
   does not need.
2. **Unset is a startup error in this mode.** Not a permissive default. This matches how the branch
   already treats unsafe auth configuration: the chart fails the render on an empty NetworkPolicy
   peer set and on `cloudflare_headers` + Ingress. An operator cannot obtain the trust without
   stating who they trust. `jwt` and `disabled` ignore the setting entirely.
3. **The chart ships the private ranges,** overridable and commented "narrow this to your Pod CIDR".
   An empty chart default would break `helm install` at the defaults — the exact defect `dead9dc4`
   fixed for the url4-cloud chart one commit ago.
4. **`cloudflare_headers` only.** `jwt` is self-authenticating and stays reachable from anywhere.

Correcting the review comment's example while implementing it: `192.168.0.0/8` has host bits set and
is not a network (the intended range is `/16`), and `172.0.0.0/8` is not RFC1918 (`172.16.0.0/12`
is). Neither example covers `10.0.0.0/8`, where Kubernetes Pod IPs usually live — taken literally,
that configuration would refuse every real caller.

## Planned changes

- `apps/aigateway/src/aigateway/config.py`
  - `allowed_networks: tuple[IPv4Network | IPv6Network, ...]`, alias `AIGW_ALLOWED_NETWORKS`,
    comma-separated. `field_validator(mode="before")` parses with `ip_network(..., strict=True)`.
  - A `model_validator(mode="after")` declared **below** `_reconcile_auth_mode` — the mode may be
    *derived* from the legacy `AIGATEWAY_AUTH_ENABLED`, and Pydantic runs after-validators in
    definition order, so reading `auth_mode` before it is reconciled would check the wrong value.
- `apps/aigateway/src/aigateway/core/auth/cloudflare_identity.py`
  - `peer_in_networks(host: str | None, networks) -> bool`. Pure; normalizes IPv4-mapped IPv6
    (`::ffff:10.1.2.3`) so a dual-stack cluster does not fail closed by accident.
- `apps/aigateway/src/aigateway/core/auth/middleware.py`
  - `_account_from_cloudflare_headers` calls it FIRST, before the header is read. **403**, not 401:
    the caller is not unidentified, they are not entitled to be believed.
- `apps/aigateway/charts/aigateway/values.yaml` — `config.allowedNetworks` (RFC1918 + CGNAT +
  loopback), commented.
- `apps/aigateway/charts/aigateway/templates/configmap.yaml` — emit `AIGW_ALLOWED_NETWORKS`.
- `apps/aigateway/charts/aigateway/templates/_helpers.tpl` — `aigateway.validateAuth` gains a third
  refusal, so the misconfiguration surfaces at `helm template` rather than as a CrashLoop.
- `apps/aigateway/charts/aigateway/values.schema.json` — the new key, if the schema constrains
  `config`.
- `docs/diagrams/gateway-identity.md` + `gateway-identity-topology.mmd` /
  `gateway-identity-auth-modes.mmd` — §2 says two settings enforce the boundary; it is now three,
  and this is the only one that holds where the CNI does not enforce NetworkPolicy. Re-render.

## Test plan

RED first, in `tests/unit/auth/test_cloudflare_identity.py` (parsing/helper) and
`tests/unit/auth/test_middleware.py` (request path).

- Parsing: comma-separated list; surrounding whitespace; a single entry; IPv6; empty string → `()`.
- Parsing refuses host bits set (`192.168.0.0/8`) — the review comment's own example.
- Startup: `cloudflare_headers` + no networks → `ValueError`; `jwt` + none → constructs;
  `disabled` + none → constructs; `AIGATEWAY_AUTH_ENABLED=false` alone + none → constructs (the
  derived-mode ordering).
- Peer matching: in range → account resolved; out of range → 403; `request.client is None` → 403;
  IPv4-mapped IPv6 peer matches an IPv4 network.
- **The invariant protected:** peer out of range but `X-Forwarded-For` in range → still 403.
  Trusting a forgeable header to decide whether to trust a forgeable header is circular, and this
  test is what stops someone "fixing" the proxy case later.

## Acceptance

- In `cloudflare_headers` mode a request from outside the declared networks gets 403 and never
  reaches `identity_from_headers`.
- A `cloudflare_headers` deployment that declares no networks fails at boot, and fails earlier at
  `helm template`.
- `jwt` and `disabled` behaviour is byte-for-byte unchanged.
- `run_gates.py aigateway` green; `helm lint` clean; `values-prod.yaml` renders the new key.

## Outcome

- **Actual files:** as planned, MINUS `charts/aigateway/values.schema.json` (this chart has none —
  the schema belongs to the url4-cloud chart), PLUS `src/aigateway/main.py` and
  `tests/conftest.py`. Both additions are recorded under Deviations.
- **Commits:** see `Refs: OME-684` on this branch.
- **Gates:** `run_gates.py aigateway --skip-append-only` → ALL GATES GREEN. `helm lint` clean; all
  four chart behaviours rendered and checked by hand (default, `values-prod.yaml`, both refusals,
  and `jwt` with no networks). Both diagrams re-rendered with `mmdc` and inspected as images.

## Deviations

Three, all owner-approved mid-flight.

1. **The mandatory-networks check moved from `Settings` to `create_app`.** Placing it on `Settings`
   broke a prior test — `test_an_explicit_mode_wins_over_the_legacy_default` constructs
   `Settings(auth_mode="cloudflare_headers")` with no networks to assert something about *mode
   reconciliation*, and had nothing to do with networks. `create_app` already branches on
   `auth_mode` to install the loopback middleware, so it is the established site for mode-dependent
   assembly, and `main.py` binds `app = create_app()` at import — so a misconfigured deployment
   still fails at startup. The prior test survives verbatim. Building `Settings` stays a pure parse.

2. **`tests/conftest.py` modified — a prior-test path.** The shared `client` fixture built
   `TestClient(create_app())`, whose peer defaults to `("testclient", 50000)`. That is not an
   address, so the guard fails closed on it and eight prior `header_client` tests would have
   flipped 200 → 403. The fixture now passes `client=("10.1.2.3", 50000)` and sets
   `AIGW_ALLOWED_NETWORKS`. **No test body or assertion changed** — only shared setup, and the
   whole suite now takes the production-shaped path. This trips the append-only gate, which reports
   paths rather than diffing content, so the gate run used `--skip-append-only`. Recorded here
   rather than passed silently.

3. **`AIGW_ALLOWED_NETWORKS` needs `NoDecode`.** pydantic-settings JSON-decodes complex field types
   read from the environment, so a `tuple` field would reject `10.0.0.0/8` as malformed JSON before
   any validator ran. `Annotated[..., NoDecode]` (pydantic-settings 2.14) turns that off. Tests
   build settings through `model_validate` rather than the constructor, because the field's
   declared type is the parsed tuple while the input under test is a string.

## Still open

- **Unchanged and still unverified:** whether the cluster's CNI enforces the NetworkPolicy. This
  unit reduces the consequence of it not doing so from silent cluster-wide impersonation to a 403,
  but it does not answer the question. The curl-from-another-namespace test in
  `docs/diagrams/gateway-identity.md` §2 is still owed.
- The shipped `allowedNetworks` default is the private ranges, which is wider than the two
  workloads that should reach the gateway. Narrowing it to the real Pod CIDR is a deployment-time
  action, flagged in the values comment and the topology note.
- Unchanged from the earlier ledgers: nothing provisions credentials for a header-derived
  principal (`404 profile_not_found`).
