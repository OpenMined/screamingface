---
id: OME-474
linear_url: https://linear.app/openmined/issue/OME-474/url4-pypi-name-url4-is-already-taken-release-url4yml-publish-step
status: backlog
type: task
priority: P1
labels: [pkg/url4-python-sdk, design-session, human]
created: 2026-07-17
closed:
---

`release-url4.yml` (#401, OME-465) tells an owner to "reserve the `url4` project on PyPI" and
publishes to `https://pypi.org/p/url4` — but that name is already taken by Andrew Trask's
separate `iamtrask/url4` (v0.1, uploaded 2026-02-22, homepage url4.ai, requires-python >=3.10).
This repo's `packages/url4` is v0.1.0 / >=3.12 and unpublished. The lane will verify + build
green and fail at publish on the first `url4-v*` tag; `pip install url4` today installs Trask's
package, not ours.

Owner fork: Trask adds a Trusted Publisher on the existing project · transfer/co-own to
OpenMined · or publish under a different name (changing `pyproject.toml` name + the workflow's
env URL + header).

Found while doing OME-365 (docs refresh), which consequently states nothing about installing
the SDK. Filed without a workstream `Epic` label — that group is gone from Linear.
