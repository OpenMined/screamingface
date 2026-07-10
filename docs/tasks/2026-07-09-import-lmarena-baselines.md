---
id: OME-322
linear_url: https://linear.app/openmined/issue/OME-322/sf-28-leaderboard-import-single-model-baselines-from-lmarena
status: done
type: task
priority: P2
labels: [Leaderboard, app/scoreboard, autonomous, agentic]
created: 2026-07-09
closed: 2026-07-10
---

Seed each benchmark's "line to beat" from external single-model baselines.

**Scope**

* Import single-model scores (LMArena / Artificial Analysis) as baseline entries with
  source attribution, surfaced via the existing `GET /v1/leaderboard/{benchmark_id}`
  read path.
* Later: scheduled auto-sync (out of scope here).

**Done when** each board shows real imported single-model baselines as the target
line.

**Scoping decisions (agreed with owner 2026-07-09):**
- Build the import mechanism only — no real baseline numbers seeded this pass
  (`livetruth`/`livetruth-latest` are OpenMined-proprietary; only `hle` has real
  external single-model data to import, and that's left for a follow-up once sourced).
- Backend/API only — the portal "target line" rendering is an explicit follow-up, not
  covered by this ticket.

Plan: `/Users/filip/.claude/plans/resume-fluttering-moon.md` (approved in plain words).
