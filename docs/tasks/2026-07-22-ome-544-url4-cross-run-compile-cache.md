---
id: OME-544
linear_url: https://linear.app/openmined/issue/OME-544
status: Backlog
type: Feature
priority: P3
labels: [url4-engine, autonomous, agentic]
parent: OME-537
created: 2026-07-22
closed:
---

# url4: cache compiled graphs across runs

The spawn cache dies with its run, so a node serving the same expression compiles it every time (~67us). The compiler docstring already establishes a compiled Graph is pure template data. Spec must state the eviction bound — expression text is attacker-supplied on a public endpoint.

Spec → plan → owner approval before code. Under OME-537.
