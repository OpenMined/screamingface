---
id: OME-554
linear_url: https://linear.app/openmined/issue/OME-554/url4-cloud-url4-spec-c-alignment-posture-event-crosswalk-transport
status: in_progress
type: epic
priority: P1
labels: [url4-cloud, design-session, agentic]
created: 2026-07-22
closed:
---

# OME-554 — url4-cloud ↔ URL4-Spec-C alignment: posture, event crosswalk, transport (epic)

Anchor epic for aligning url4-cloud's `url4_streaming_protocol` (CloudEvents 1.0 + OTel GenAI
telemetry over WebSocket) with Kevin's **URL4-Spec-C** (url4 execution semantics over SSE).
Context: the url4-cloud app epic is `OME-513`.

**Owner decision (2026-07-22): Posture C — Converge.** Propose our WS + CloudEvents stream as
the **streaming binding of URL4-Spec-C**; adopt Kevin's execution-semantics events under our
envelope; and contribute our telemetry / cost / cancellation / resume as the layer his spec is
thin on. **Sequenced through a design-session with Kevin** — no execution-semantics code ships
before the event crosswalk + transport decision are ratified. Kevin owns the grammar/execution
spec; agents PREPARE proposals, owner + Kevin decide.

**Alignment is bidirectional:**

| Axis | url4-cloud | URL4-Spec-C |
|---|---|---|
| Telemetry (OTel GenAI spans, logs, cost.usage self/subtree) | Ahead | Thin |
| Cancellation (`ai.url4.stop` + `DELETE`→204) | Ahead | Open gap (his §16) |
| Resume/attach (CloudEvents `sequence` + `attach{from_sequence}`) | Ahead | Weaker |
| Partial results (`result_version`/`is_final`/`sources_used`\|`missing`/`intent_mode`) | Behind | First-class |
| Execution semantics (source/quorum/trigger/degradation/session/foreach) | Behind | Deep |
| Streaming transport | WebSocket + CloudEvents | SSE (fork) |

**Transport fork:** propose WS+CloudEvents as the URL4-Spec-C streaming binding; optionally
define an SSE projection of the same event stream for his sync/async delivery modes.

**Roadmap (sub-issues, all dated 2026-07-22):**
- Concrete, autonomous (implement now): e2e docs (`…-e2e-execution-docs`), `URL4-Capability`
  header (`…-capability-token-header`).
- Execution-semantics forks (design-session — prepare crosswalk proposals, ratify with Kevin):
  partial results, source lifecycle, quorum×triggers, degradation cascade, agent sessions,
  foreach, error-classification.

**Acceptance:** a ratified alignment spec in `docs/spec/` — posture C confirmed with Kevin, an
event crosswalk table (our CloudEvents types ↔ his bespoke events), and the transport decision —
from which the execution-semantics children become implementable design/plan/code units.

Related: `OME-513` (url4-cloud app epic).
