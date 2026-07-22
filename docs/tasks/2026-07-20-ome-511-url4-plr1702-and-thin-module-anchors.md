---
id: OME-511
linear_url: https://linear.app/openmined/issue/OME-511/url4-activate-the-inert-plr1702-gate-anchor-the-two-thin-modules
status: Done
type: Improvement
priority: P2
labels: [url4-python-sdk, url4-engine, autonomous, agentic]
created: 2026-07-20
closed: 2026-07-20
---

# url4: activate the inert PLR1702 gate + anchor the two thin modules

Fix the no-op `PLR1702` ruff gate in url4 (surgical `preview` + `explicit-preview-rules`)
and add semantic anchors to `dag/compiler.py` and `peer/server.py`. url4 only;
apps/* share the same inert select and are left for a follow-up.

See `docs/work/2026-07-20-OME-511-url4-plr1702-and-thin-module-anchors.md`.
