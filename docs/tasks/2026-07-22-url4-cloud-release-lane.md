---
id: OME-567
linear_url: https://linear.app/openmined/issue/OME-567/register-url4-cloud-release-please-lane-image-release-helm-oci-publish
status: done
type: task
priority: P2
labels: [url4-cloud, autonomous, agentic]
created: 2026-07-22
closed: 2026-07-22
---

# OME-567 — Register url4-cloud release-please lane (image; Helm publish deferred)

Register `apps/url4-cloud` in release-please (config + manifest, python, tag `url4-cloud-v*`,
mirroring aigateway) + `release-url4-cloud.yml` (GHCR image build/push + chart lint + draft
release). Helm OCI chart publish deferred until the placeholder NATS dependency is pinned. Lands in
the existing PR #419. Sub-issue of the url4-cloud app epic (`OME-513`). Ledger:
`docs/work/2026-07-22-OME-567-url4-cloud-release-lane.md`.
