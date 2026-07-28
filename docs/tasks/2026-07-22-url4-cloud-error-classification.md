---
id: OME-563
linear_url: https://linear.app/openmined/issue/OME-563/align-error-classification-errorinfo-transientpermanent-http-map
status: backlog
type: decision
priority: P3
labels: [url4-cloud, design-session, agentic]
created: 2026-07-22
closed:
---

# OME-563 — Align error classification: ErrorInfo ↔ transient/permanent + HTTP map + opaque + Retry-After

Ours: `ErrorInfo{code, permanent}` + the `ai.url4.error` nack. Kevin: richer classification —
transient vs permanent, an HTTP-status→code map, `opaque` passthrough for unclassifiable upstream
errors, and a `Retry-After` override.

**Proposal to prepare:** extend `ErrorInfo` / the error frame with a classification enum +
`retry_after` + `opaque`; establish a shared error-code registry with Kevin.

**Open questions:** code-registry ownership (Kevin's grammar spec vs url4-cloud); mapping
precedence.

design-session — prepare; ratify with Kevin.

Parent: alignment epic (`…-spec-c-alignment`).
