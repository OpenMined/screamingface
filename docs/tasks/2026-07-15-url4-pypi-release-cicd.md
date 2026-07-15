---
id: OME-465
linear_url: https://linear.app/openmined/issue/OME-465/url4-sdk-pypi-release-cicd-trusted-publishing-release-please
status: in_progress
type: task
priority: P2
labels: [pkg/url4-python-sdk, autonomous, agentic]
created: 2026-07-15
closed:
---

PyPI release CI/CD for `packages/url4`: `release-url4.yml` (Trusted Publishing / OIDC),
PyPI metadata (README, LICENSE, `py.typed`, classifiers/urls), a packaging-validation gate
in `url4-tests.yml`, and a Dependabot `uv` entry. Delivered as a PR; PyPI trusted-publisher
+ `pypi` GitHub Environment remain owner actions.
