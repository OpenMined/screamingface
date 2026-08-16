---
id: OME-769
linear_url: https://linear.app/openmined/issue/OME-769/leaderboard-fill-submissions-board-ranked-rows-core-columns-sota-medal
status: done
type: task
priority: P1
labels: [scoreboard]
created: 2026-08-12
closed: 2026-08-13
---

Fill the per-benchmark board that `OME-768` shelled out: rows ranked by accuracy, an Author
column, accuracy rendered as a value plus a proportional bar, and a mark column that
`OME-770`'s frontier marks and `OME-771`'s medal will share.

**Descoped in review (PR #569):** the SOTA medal and the reproducible-SOTA summary stat. The
medal must name the best *reproduced* run, but `/v1/leaderboard` returns one row per spec chosen
by accuracy alone, so a spec's verified run is hidden whenever that spec also has a higher
unverified run. Moved to `OME-771`, which filters the pool in the query and therefore makes the
verified run a real, badgeable row.

**Not built — missing backend fields rather than choices:** a fusion name (no such field
exists — `spec_id` is a technical key), a Models column (`ran_with_providers` is providers, not
models), and the accuracy range whisker (no min/max or variance in the schema). Each is a gap
`OME-772` already catalogues.

Spec: `docs/spec/2026-08-12-OME-769-submissions-board.md`
Plan: `docs/plan/2026-08-12-OME-769-submissions-board.md`
Ledger: `docs/work/2026-08-12-OME-769-submissions-board.md`
