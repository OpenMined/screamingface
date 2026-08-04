---
id: OME-730
linear_url: https://linear.app/openmined/issue/OME-730/confirm-dev-cloud-deploy-path-consumes-the-acr-image-for-scoreboard
status: backlog
type: task
priority: P2
labels: [scoreboard, agentic, task]
created: 2026-08-03
closed:
---

`dev-build-scoreboard.yml` already builds and pushes the scoreboard image to both GHCR and the
platform's ACR (`acropenmined.azurecr.io/screamingface-scoreboard`) on every merge to `main`.
`apps/scoreboard/charts/scoreboard/values.yaml`'s `image.repository` still defaults to GHCR, and
no `values-dev.yaml` exists anywhere in the repo (checked aigateway/aigateway-ui too — neither has
one). Need to confirm with Stephen whether the ACR override happens on the platform side (his
~30-minute instrumentation, once back from holiday) or whether scoreboard needs a values overlay.
Found while working OME-404.
