---
id: OME-562
linear_url: https://linear.app/openmined/issue/OME-562/foreach-collection-iteration-events-aiurl4foreach-sourcesexpanded
status: backlog
type: decision
priority: P3
labels: [url4-cloud, design-session, agentic]
created: 2026-07-22
closed:
---

# OME-562 — foreach / collection-iteration events ai.url4.foreach.* + sources.expanded

Kevin's `*source(body)!intent` maps an intent over each element of a collection with bounded
concurrency: `foreach.{started,item.result,item.error,progress}` + `expand`/`sources.expanded`.
Ours has no per-element batch observability.

**Proposal to prepare:** `ai.url4.foreach.*` CloudEvents for per-element batch progress/results.

**Open questions:** concurrency reporting; correlation of expanded items to child sources
(source-lifecycle events).

design-session — prepare; ratify with Kevin.

Parent: alignment epic (`…-spec-c-alignment`).
