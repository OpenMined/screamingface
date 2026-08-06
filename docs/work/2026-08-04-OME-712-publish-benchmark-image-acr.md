---
ticket: OME-712
stack: url4-cloud
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-712 — Publish the dev Benchmark image to ACR

## Intent

Keep the dev control-plane and Runner Benchmark images available in the same registries. The Helm
chart derives `<control-plane-repository>-benchmark`; when the dev deployment uses
`acropenmined.azurecr.io`, the dev workflow must therefore publish the paired Benchmark image there
under the same immutable `main-<shortsha>` tag.

## Planned changes

- `.github/workflows/dev-build-url4-cloud.yml`
- `apps/url4-cloud/tests/unit/test_dev_benchmark_image_registry_parity.py`
- `docs/spec/2026-08-04-OME-712-benchmark-runtime-certification.md`
- `docs/plan/2026-08-04-OME-712-benchmark-runtime-certification.md`
- `docs/work/2026-08-04-OME-712-benchmark-runtime-certification.md`
- `docs/work/2026-08-04-OME-712-publish-benchmark-image-acr.md`

## Test plan

- RED through the committed workflow contract: the dev Benchmark job must authenticate to every
  registry used by its base-image job and publish both GHCR and ACR Benchmark tags with the same
  immutable suffix.
- Keep the release workflow unchanged: it publishes its base image only to GHCR, so it has no ACR
  parity gap.
- Run the focused workflow-contract test, then the complete url4-cloud canonical gate.

## Acceptance

- The dev Benchmark job uses the existing Azure OIDC variables and logs in to
  `acropenmined.azurecr.io` through `az acr login --name acropenmined`.
- One Benchmark build publishes both
  `ghcr.io/openmined/screamingface-url4-cloud-benchmark:main-<sha>` and
  `acropenmined.azurecr.io/screamingface-url4-cloud-benchmark:main-<sha>`.
- GHCR behavior, exact base-image pairing, cache scope, and single-architecture dev behavior remain
  unchanged.
- No registry login, image build/push, GitHub mutation, or Linear mutation is performed locally.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** all six planned files; no unplanned production surface.
- **Commits:** none planned; owner review first
- **Gates:** focused workflow-contract test 1 passed; workflow parsed successfully as YAML;
  canonical url4-cloud gate all green; cumulative full run 774 passed, 10 skipped, 94.07% coverage,
  129 warnings.
- **Deviations:**
  - Linear status was not mutated because the owner explicitly constrained this pass to local
    changes.
  - The cumulative gate still uses `--skip-append-only` because the prior zero-Case iteration has
    two approved test reversals; this ACR iteration itself modifies no prior test.
  - No real registry login or image push ran locally. The unit verifies the committed workflow
    contract; GitHub execution remains the deployment proof.

## Wisdom and confidence review

- Separate GitHub jobs do not share Docker credentials, so repeating the existing Azure OIDC login
  in the Benchmark job is necessary rather than duplicated application logic.
- One BuildKit invocation publishes both tags; the change does not double preparation, network cost,
  or image content.
- It uses the existing non-secret Azure identifiers and federated identity. No credential is added,
  stored, printed, or passed into the image build.
- GHCR, the exact base tag, cache scopes, architecture, and release workflow remain unchanged. The
  release workflow is consistently GHCR-only and therefore has no ACR parity gap.
- The test observes the versioned workflow output contract without mocking internal Python code or
  contacting a registry.
