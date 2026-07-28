---
id: OME-561
linear_url: https://linear.app/openmined/issue/OME-561/agent-session-coordination-events-aiurl4session
status: backlog
type: decision
priority: P3
labels: [url4-cloud, design-session, agentic]
created: 2026-07-22
closed:
---

# OME-561 — Agent session / coordination events ai.url4.session.*

Kevin's `mode=agent` (persistent multi-turn) + `coord=session/debate`
(`coord.rounds/max_turns/convergence/turn_timeout`) surface as
`session.{started,turn,turn.progress,concluded,agent.failed}` — multi-agent conversations
observable turn-by-turn. Ours has none (debate/convergence is entirely inside the engine).

**Proposal to prepare:** `ai.url4.session.*` CloudEvents for multi-agent coordination
observability. Largest execution-semantics item.

**Open questions:** scope — observe-only vs steerable; how convergence/limit/timeout are
signalled; relation to OTel spans.

design-session — prepare; ratify with Kevin.

Parent: alignment epic (`…-spec-c-alignment`).
