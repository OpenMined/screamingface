---
ticket: OME-711
stack: repo
status: done
started: 2026-07-30
finished: 2026-07-30
---

# OME-711 — release-aigateway-ui.yml: publish the console image and chart on `aigateway-ui-v*`

## Intent

`OME-707` registered `aigateway-ui` with release-please, so merging its release PR bumps
`package.json` and tags `aigateway-ui-v*`. **Nothing listens to that tag.** `OME-710` produced the
Dockerfile and chart it would consume. This closes the loop.

Mirrors `release-aigateway.yml`: `verify` → (`image`, `chart`) → `release`.

## Four real differences from the lane being mirrored

1. **The chart REFUSES to render with default values.** The one a copy-paste gets wrong.
   `charts/aigateway-ui` fails deliberately when `networkPolicy.clientPodNames` is empty, because a
   NetworkPolicy ingress rule with no `from:` admits every source and this console trusts
   `X-User-Email`. The render step must pass the value. Without it the lane fails at the first real
   tag and looks like a broken workflow rather than a chart doing its job.
2. **Version from `package.json`, not `pyproject.toml`.** The awk-on-TOML becomes `jq -r .version`
   — a version field is structured data, not something to regex.
3. **No `sf-installer` publish.** `release-aigateway.yml` mirrors into the public
   `OpenMined/sf-installer`. The console is internal operator tooling behind Cloudflare Access, not
   part of a product install; publishing it there advertises an admin surface to the wrong audience.
4. **Tag prefixes must be confirmed disjoint,** not assumed. `aigateway-v*` should not match
   `aigateway-ui-v0.1.0`.

## Planned changes

- `.github/workflows/release-aigateway-ui.yml` — new
- `CONTRIBUTING.md` — the releases table still says the tag is "a version marker only"

## Test plan

A release workflow cannot be run locally, so the parts that CAN be executed are executed, and the
rest is reviewed against the mirrored lane:

- run the exact `helm package`/`helm template` commands the lane will run, locally, against the
  real chart — proving the required-values problem is actually solved
- run the version-extraction shell against the real `package.json`
- assert the version check FAILS on a mismatched tag (the check only has value if it can fail)
- confirm `aigateway-v*` does not glob-match `aigateway-ui-v0.1.0`, by testing the pattern rather
  than reasoning about it
- confirm the image name matches what `charts/aigateway-ui/values.yaml` already points at — a
  released chart naming a non-existent image is the failure this prevents

## Acceptance

- workflow parses; every locally-runnable step verified
- `CONTRIBUTING.md` no longer claims the tag publishes nothing

## Outcome

A release workflow cannot be run locally, so every step that CAN be executed was executed against
the real artefacts rather than reviewed by eye.

- **The version check, both ways.** `aigateway-ui-v0.1.0` against the real `package.json` → passes.
  `aigateway-ui-v9.9.9` → emits the `::error::` and exits non-zero. A check that cannot fail is not
  a check.
- **The chart steps, verbatim.** `helm lint`, then the exact `helm template … --set
  'networkPolicy.clientPodNames[0]=…'` the lane runs → 6 documents. Then `helm package --version
  0.1.0 --app-version 0.1.0`, which produced `aigateway-ui-0.1.0.tgz` — **the exact filename the
  push step assumes**. A mismatch there would fail only at the first real tag.
- **The loop is closed.** Rendering the *packaged* chart yields
  `image: "ghcr.io/openmined/screamingface-aigateway-ui:0.1.0"` — precisely what the lane pushes.
  The chart's values file names no version at all; `--app-version` from the tag flows through the
  image helper's fallback.
- **Tag filters are disjoint**, confirmed with two independent matchers (bash `[[ ]]` and Python
  `fnmatch`) rather than reasoned about. Each tag matches exactly one lane.
- **Job shape matches** the other three release lanes: `verify` → (`image`, `chart`) → `release`.
- `verify_chart_wiring.py` **23/23** (up from 21).

## Deviations from the plan

1. **Two checks were added to `verify_chart_wiring.py`,** which the plan did not mention. The
   important one compares the chart's image against `env.IMAGE` in the release lane. A chart naming
   an image nobody publishes is installable and permanently `ImagePullBackOff`, and neither file can
   notice on its own — renaming either side is a silent break, and this is the only place they meet.
   Mutation-tested: renaming the lane's image alone fails the check.

   `.github/workflows/charts.yml` gained `release-aigateway-ui.yml` in its path filter so editing
   the lane actually re-runs that comparison. A cross-file check that does not trigger on either
   file is decoration.

2. **`ACTOR` moved into an `env:` binding** for the `helm registry login` step. `release-aigateway.yml`
   interpolates `${{ github.actor }}` straight into the `run:` body. It is a GitHub username so the
   risk is theoretical, but the surrounding workflow is already written the safe way and one
   inconsistent line invites the pattern to be copied.

3. **`set -euo pipefail` on every multi-line `run:`.** The mirrored lane omits it. This work already
   produced one silent failure from an unchecked pipeline exit status (`OME-710`, the Docker build
   piped to `tail`), which is reason enough to be explicit.

## Still open

- **The lane has never actually run.** It publishes on a tag, and no tag has been pushed. Every
  locally-runnable step is verified and the job graph parses, but the GHCR pushes, the multi-arch
  build under QEMU, and the draft-release step are unexercised until the first real release.
- **The first release is an owner action** — merging the release-please PR for `aigateway-ui`.
