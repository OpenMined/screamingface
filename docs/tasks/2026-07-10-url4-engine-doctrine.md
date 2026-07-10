---
id: OME-377
linear_url: https://linear.app/openmined/issue/OME-377/docsurl4-url4-engine-execution-and-telemetry-doctrine-skill-ensemble
status: in_progress
type: task
priority: P3
labels: [repo, url4 Engine, autonomous, agentic, needs-owner]
created: 2026-07-10
closed:
---

Design-stage doctrine for the url4-engine AI-ensemble **execution & telemetry protocol**,
captured as a reusable skill + two diagrams. Not ratified (no spec; engine legacy-tag-only,
reviving as `pkg/url4-python-sdk`). Deliverables: `.claude/skills/url4-engine/SKILL.md`
(invariant groups N/T/O/F + Red-flags, embeds both diagrams); paired SVG+PNG
`docs/diagrams/ensemble-node-{architecture,sequence}.*`; `.claude/README.md` skills-index row.
Scope = skill + diagrams only (spec/plan/code are separate future items). STOP `needs-owner`:
**F4** — does a one-shot HTTP-GET leaf return telemetry in the response body or only via the
Enclave store + `Link` header? (diagrams assume store-side only) + owner to bless the
design-stage framing. Ledger: `docs/work/2026-07-10-OME-377-url4-engine-doctrine.md`.
