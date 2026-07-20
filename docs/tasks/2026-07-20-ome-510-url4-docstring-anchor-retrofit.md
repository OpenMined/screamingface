---
id: OME-510
linear_url: https://linear.app/openmined/issue/OME-510/url4-fix-stale-docstring-cross-refs-adopt-semantic-anchor-pattern
status: In Progress
type: Improvement
priority: P2
labels: [url4-python-sdk, url4-engine, autonomous, agentic]
created: 2026-07-20
closed:
---

# url4: fix stale docstring cross-refs + adopt semantic-anchor pattern across src

Follow-up to the `OME-499` reorg merge (`6912fa8`): repath ~94 stale
`url4.<flat>` docstring/RST cross-references to the new subpackage paths and
adopt the `sdlc-python` semantic-anchor comment vocabulary across `src/url4`.
Documentation-only; `tests/**` out of scope.

See `docs/work/2026-07-20-OME-510-url4-docstring-anchor-retrofit.md` for the ledger.
