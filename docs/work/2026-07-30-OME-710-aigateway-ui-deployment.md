---
ticket: OME-710
stack: aigateway-ui
status: done
started: 2026-07-30
finished: 2026-07-30
---

# OME-710 — container image + Helm chart for aigateway-ui, wired to aigateway in-cluster

## Intent

`OME-708`/`OME-709` built the admin console. It runs locally and deploys nowhere. This makes it
deployable and — the part with actual content — connects it to the gateway inside the cluster.

## The connection has two ends, and the far end already says "no"

The console is a BFF: the browser never reaches the admin API, the **UI Pod** does. In-cluster the
console is therefore just another aigateway client, and aigateway is deliberate about who its
clients are.

`charts/aigateway/values.yaml` defaults `networkPolicy.clientPodNames` to `[url4-cloud,
url4-runner]`, and `networkpolicy.yaml` **fails the render** rather than emit a rule with no
`from:`. In `cloudflare_headers` mode that policy is not hardening — it *is* the authentication
boundary, as its own docstring says. So a console deployed without being named there is not
misconfigured-but-working; it is **denied at the CNI**. The symptom is a connect timeout in the UI
Pod and *nothing at all* in the gateway's logs, because the packet never arrives.

Second end: `AIGATEWAY_ADMIN_EMAILS` has no chart path. The ConfigMap emits a **fixed** key set, so
`OME-706`'s admin API would answer `503 admin API disabled` forever regardless of values. `extraEnv`
could smuggle it, but the allowlist is the security boundary of the entire admin surface — it gets a
named key, not the escape hatch.

## Planned changes

**aigateway (the far end)**

- `charts/aigateway/values.yaml` — `config.adminEmails: []`; add `aigateway-ui` to
  `networkPolicy.clientPodNames`
- `charts/aigateway/templates/configmap.yaml` — emit `AIGATEWAY_ADMIN_EMAILS`
- `charts/aigateway/values-prod.yaml` — name `aigateway-ui` in the explicit prod peer list
- `charts/aigateway/README.md` — document both

**aigateway-ui (the near end)**

- `Dockerfile` + `.dockerignore` — multi-stage on node 22 slim, non-root, `EXPOSE 9107`
- `charts/aigateway-ui/` — Chart, values, `_helpers.tpl`, deployment, service, configmap,
  serviceaccount, networkpolicy, ingress, `tests/test-connection.yaml`, README

**CI**

- a `chart` job in `aigateway-ui-tests.yml`
- a `chart` job in `aigateway-tests.yml` — the aigateway chart is currently linted **only** in the
  release workflow, so a chart change in a PR has no gate at all today

## The invariant this must not break

The console trusts `X-User-Email`, exactly as the gateway does. So it inherits the gateway's rule:
it is safe **only** while unreachable except through the mesh that injects that header. A direct
route to port 9107 is a full admin impersonation with one `curl -H`. `ingress.enabled` therefore
defaults to `false` and, mirroring `aigateway.validateAuth`, the chart **refuses to render** the
unsafe combination rather than documenting it in a comment nobody reads.

One asymmetry to get right rather than copy: aigateway's egress is `- {}` (unrestricted — its job is
dialling provider APIs whose ranges are unknowable). The console dials aigateway and DNS. It gets no
such hole.

## Test plan

Chart behaviour is only observable in rendered output, so the tests are render-and-assert:

- the console Deployment resolves `AIGATEWAY_ADMIN_BASE_URL` to the gateway Service DNS
- the aigateway NetworkPolicy contains an `aigateway-ui` peer, paired with its namespace selector
  in ONE `from` element (splitting them would admit the whole namespace)
- `AIGATEWAY_ADMIN_EMAILS` reaches the gateway container, comma-joined
- an empty `config.adminEmails` still emits the key (declared-empty, not absent)
- `ingress.enabled=true` FAILS the render — asserted on the failure, not just on the happy path
- the console's egress names the gateway rather than `{}`

## Acceptance

- `helm lint` + `helm template` clean for both charts
- every assertion above holds against real rendered output
- `run_gates.py aigateway` and `aigateway-ui` still green

## Outcome

- **Gates:** `run_gates.py aigateway` green (1407 tests) · `run_gates.py aigateway-ui` green
  (181 tests) · `verify_chart_wiring.py` **21/21**.

- **The image was built and RUN, not just written.** `docker build` then a live container:
  - `/healthz` → `{"status":"ok"}`
  - `id` → `uid=1000(node)`, matching the chart's `runAsUser: 1000`
  - `/theme-init.js` → 200, 1133 bytes — proves `public/` was copied, so `OME-709`'s no-flash
    contract survives containerisation
  - a hashed `/_next/static/…css` → 200, 38248 bytes — proves `.next/static` was copied
  - Docker `HEALTHCHECK` → `healthy`; image 423 MB

- **The verifier was mutation-tested**, because a check that has never failed proves nothing.
  Three deliberate breakages, all caught, then reverted and re-verified green:
  1. dropping `aigateway-ui` from the gateway's `clientPodNames` → 2 checks fail
  2. pointing the console at the wrong Service name → 2 checks fail
  3. splitting the paired namespace/pod selectors into separate `from` elements → **4** checks fail

  (3) is the one worth naming: it renders a policy that still *mentions* `aigateway-ui` while
  actually admitting the whole namespace. Every grep-based assertion would pass it.

## Deviations from the plan

1. **The Dockerfile does NOT create its own user.** Planned as a copy of aigateway's
   `useradd --uid 1000`. That **failed the build** — `useradd: UID 1000 is not unique`, because the
   node images already ship a `node` user at 1000 while `python:3.12-slim` ships none. Uses the
   existing `node` user instead.

   Worth recording separately: the first build reported success because the command was piped to
   `tail`, and a pipeline's exit status is the *last* command's. The failure was invisible until
   the smoke test found no image. Subsequent builds use `set -o pipefail`.

2. **Chart CI is its own workflow (`charts.yml`), not jobs inside the two app lanes.** `paths:` is
   workflow-level, so a chart job inside `aigateway-tests.yml` would run the entire Python suite on
   every chart edit — and the important assertions are about the *pair* of charts, which neither
   app's lane owns.

3. **The verifier parses YAML rather than grepping**, unlike the `url4-cloud-tests.yml` precedent.
   Mutation (3) above is why: the property that matters is structural, and text matching cannot see
   it.

4. **A `charts.yml` `image` job builds the Dockerfile on every PR.** Not in the plan. Nothing else
   in CI compiles it — `aigateway-ui-tests.yml` runs `next build` on the host, which never
   exercises the multi-stage copy of the three artefacts the runtime stage depends on. Omitting any
   one produces an image that starts cleanly and serves a broken page.

5. **The console chart ships no Ingress template at all,** and `ingress.enabled` carries no
   `className`/`hosts`/`tls` sub-keys. Planned as `ingress.enabled: false` mirroring aigateway.
   But aigateway's Ingress is *reachable* under `authMode: jwt`, whereas there is no console
   configuration under which a second front door is safe. Keeping dead sub-keys would imply a
   feature that does not exist; the lone `enabled` key exists so the refusal is discoverable where
   an operator would look to turn it on.

6. **A stale line in `CONTRIBUTING.md` was corrected** — it claimed the image/chart would land with
   `OME-708`. They land here.

7. **`OME-709`'s `docs/tasks/` mirror was missing** and was created alongside `OME-710`'s. It was
   never filed when that work landed; reconstructed from the Linear issue and its ledger, and
   labelled as such rather than backdated silently.

## Still open

- **No publish lane.** `release-aigateway-ui.yml` does not exist, so an `aigateway-ui-v*` tag
  builds and pushes nothing. The Dockerfile and chart are ready for it. Scoped out on the issue.
- **Never applied to a real cluster.** Everything above is render-and-run verification: the charts
  render correctly and the image serves correctly. `helm install` against a live cluster, and the
  end-to-end path through a real mesh gateway, are unverified.
- **`app › aigateway-ui` label** still missing (owner action, shared with `OME-708`/`OME-709`).
