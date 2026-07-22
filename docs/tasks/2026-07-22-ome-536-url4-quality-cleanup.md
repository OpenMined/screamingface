---
id: OME-536
linear_url: https://linear.app/openmined/issue/OME-536/url4-package-wide-quality-cleanup-dedup-scanners-drop-derivable-state
status: Done
type: Chore
priority: P3
labels: [url4-engine, autonomous, agentic]
created: 2026-07-22
closed: 2026-07-22
---

# url4: package-wide quality cleanup

Behaviour-preserving cleanup from a four-angle review (reuse, simplification,
efficiency, altitude) of the whole `packages/url4` package. Drops derivable and
dead state, guards three measured hot paths (brace scan, `render(check=True)`,
eager httpx import), and folds the duplicated top-level scanners into
`core/_scan.py`. Adds `children()` to the `DagNode` protocol so the executor no
longer special-cases `GuardNode`.

Architectural findings (dual compile pipelines, wire codec in `core/`, the
`MapNode` structure→text round-trip) are recorded on the issue as out of scope.

See `docs/work/2026-07-22-OME-536-url4-quality-cleanup.md`.
