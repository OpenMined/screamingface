---
id: OME-557
linear_url: https://linear.app/openmined/issue/OME-557/align-partial-results-result-version-is-final-sources-usedormissing
status: backlog
type: decision
priority: P2
labels: [url4-cloud, design-session, agentic]
created: 2026-07-22
closed:
---

# OME-557 — Align partial results: result_version / is_final / sources_used|missing / intent_mode

Kevin emits interim `trigger.result` with `result_version` (monotonic), `is_final`,
`sources_used`/`sources_missing`, and `intent_mode` (llm vs rds stability). Ours emits a single
`ResultEvent` then `Terminated` — no partial-result concept.

**Proposal to prepare:** extend `ResultData` with `result_version:int` (monotonic),
`is_final:bool`, `sources_used`/`sources_missing`, `intent_mode`; allow multiple `ai.url4.result`
frames before the terminal frame. Align field names with URL4-Spec-C.

**Open questions:** field-name alignment with Kevin; interaction with resume
(`sequence`/`attach{from_sequence}`) so a re-attached client reconstructs the latest
`result_version`.

design-session — agent prepares the crosswalk section; owner + Kevin ratify.
**Acceptance** = ratified section in the alignment spec + a proposed CloudEvents frame shape.

Parent: alignment epic (`…-spec-c-alignment`).
