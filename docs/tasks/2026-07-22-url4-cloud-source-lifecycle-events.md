---
id: OME-558
linear_url: https://linear.app/openmined/issue/OME-558/source-lifecycle-events
status: backlog
type: decision
priority: P3
labels: [url4-cloud, design-session, agentic]
created: 2026-07-22
closed:
---

# OME-558 — Source lifecycle events ai.url4.source.{resolving,retrying,resolved,failed,timeout}

Kevin surfaces a per-source state machine (pending→resolving→retrying→resolved|failed) as
first-class events. Ours has no source concept on the wire — a run is a black box emitting
telemetry + one result (per-node work appears only as OTel spans).

**Proposal to prepare:** `ai.url4.source.*` CloudEvents carrying source id / url4 sub-expression
+ state + timing, correlated by W3C `traceparent` to the OTel span for the same node.

**Open questions:** relationship to spans (avoid double-modelling the same node); cardinality /
sampling for wide fan-outs.

design-session — prepare; ratify with Kevin.

Parent: alignment epic (`…-spec-c-alignment`).
