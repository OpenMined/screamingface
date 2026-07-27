---
id: OME-534
linear_url: https://linear.app/openmined/issue/OME-534/url4-abnf-conformance-name-only-sources-contribute-weight-00
status: Done
type: Feature
priority: P2
labels: [url4-engine, autonomous, agentic]
created: 2026-07-21
closed: 2026-07-21
---

# url4: ABNF conformance — name-only sources contribute (patch 1/2)

Owner adopted the external formal ABNF as normative. Name-only sources
(`a: v` / `a=v`) now contribute to the packed context as `name: value`
lines; scalar `weight 0.0` marks a source INSTRUMENTAL (resolved,
`$name`-referenceable, excluded) — replacing reference-only Bindings;
name-only calls join fan-outs labeled; the fan-out gate needs ≥1
contributing call. Under OME-500.

See `docs/work/2026-07-21-OME-534-abnf-contribution-semantics.md`.
