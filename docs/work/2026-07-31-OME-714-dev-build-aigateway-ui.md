---
ticket: OME-714
stack: repo
status: done
started: 2026-07-31
finished: 2026-07-31
---

# OME-714 — dev-build-aigateway-ui.yml: get the console into the dev cluster's registry

## Intent

`OME-710` produced the console's Dockerfile and chart; `OME-711` publishes them on a release tag.
Neither puts an image where the **dev cluster** can reach it.

#452 (`18cf7379`, landed on main 2026-07-30) wired the three existing dev lanes to push into ACR
alongside GHCR, because the dev cluster pulls from there. That makes `aigateway-ui` the **only
containerised app in the repo with no dev-build lane**:

| app | Dockerfile | dev-build lane |
|---|---|---|
| aigateway | yes | yes |
| scoreboard | yes | yes |
| url4-cloud | yes | yes |
| **aigateway-ui** | **yes** | **NO** |

The gap is not cosmetic. The console and the gateway deploy as a **pair** — the console is a BFF
whose only purpose is calling `/v1/admin`. On a merge to main the gateway gets a fresh `main-<sha>`
image in ACR and the console gets nothing, so the dev cluster can only run a console from a tagged
release against a gateway from `main`. They drift by construction, and the admin API is precisely
where that bites: `OME-706` added it recently enough that **no release tag contains it at all**.

## Planned changes

- `.github/workflows/dev-build-aigateway-ui.yml` — new, mirroring `dev-build-aigateway.yml`
- `.claude/skills/working-in-this-repo/SKILL.md` — the routing table's CI column

## Two things to decide rather than copy

1. **Cache scope.** Must be `dev-aigateway-ui`, not `dev-aigateway`. Sharing a GHA cache scope
   between a uv/Python image and a node/Next.js image is not a correctness bug but it is pure
   waste — the layer sets are disjoint, so neither ever hits.
2. **Path filter breadth.** `apps/aigateway-ui/**` includes `charts/`, so a chart-only edit
   rebuilds an image that cannot have changed. Decide deliberately rather than inherit it.

## Test plan

A push-triggered workflow cannot be run locally. What CAN be checked:

- the workflow parses, and its job/permission shape matches the three siblings exactly
- the image it pushes IS the one the chart names — the same invariant `verify_chart_wiring.py`
  already enforces for the release lane, extended to this one
- the cache scope is unique across all dev lanes
- the path filter triggers on a console source change and (per the decision above) is understood
  for chart-only changes

## Acceptance

- lane parses, mirrors the siblings, own cache scope
- image/registry pair matches the chart's `image.repository`
- routing docs list it

## Outcome

- **Shape matches the three siblings exactly** — same `permissions` set
  (`contents:read`, `packages:write`, `id-token:write`), same single `image` job, same 7 steps.
  Compared programmatically rather than by eye.
- **`verify_chart_wiring.py` 23 → 26.** Three new checks, all mutation-tested:

  | mutation | caught by |
  |---|---|
  | rename the dev image | "the dev lane pushes the SAME image repository…" |
  | collide the cache scope with aigateway's | "every dev-build lane has its OWN cache scope (4 lanes, **3** distinct)" |
  | add a floating `:latest` tag | "publishes only immutable main-`<sha>` tags" |

  The cache-scope check spans **all four** lanes, so it also protects the ones that already existed.

- `charts.yml`'s path filter gained `dev-build-*.yml` (a glob, because the cache-scope check is
  repo-wide) so editing any dev lane re-runs the comparison.

## Decisions

**Path filter is the sibling's bare `apps/aigateway-ui/**`,** which includes `charts/`. A chart-only
edit therefore rebuilds an image whose content cannot have changed. Accepted rather than excluded:
the tag is keyed on the commit so nothing is overwritten and nothing breaks, whereas a filter that
differs from the other three lanes is the kind of inconsistency someone later "corrects" back
without knowing why it differed.

**The release lane still pushes GHCR only.** #452 touched only the dev lanes, so aigateway's
released images are GHCR-only too. Making the console's release lane push to ACR would be the one
app out of four doing something different — that is a platform decision about all released images,
not a gap to patch here.

## Deviations from the plan

1. **Three checks added to the verifier**, where the plan named one. The cache-scope check in
   particular is repo-wide rather than console-specific: it was cheap to generalise, and the failure
   it prevents (copying a sibling lane and inheriting its scope) is exactly how this lane was
   written.

## Still open

- **The lane has never run.** It triggers on a merge to `main` and this work is on a branch, so the
  GHCR push, the ACR push and the OIDC federation to `sp-screamingface-ci` are unexercised until
  #451 merges. That is the first real test.
- **The OIDC federation is scoped to this repo's `main` branch** (per #452's comment). Nothing here
  changes that, but it does mean the first run is also the first proof that the console's lane is
  covered by the same federation — it should be, since the subject is the branch, not the workflow.
