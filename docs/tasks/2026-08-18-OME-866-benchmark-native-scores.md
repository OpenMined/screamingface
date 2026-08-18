---
id: OME-866
linear_url: https://linear.app/openmined/issue/OME-866/replace-binary-accuracy-submissions-with-benchmark-native-leaderboard
status: in_progress
type: feature
priority: 1
labels: [scoreboard, py-screamingface, agentic, autonomous]
created: 2026-08-17
closed:
---

# Replace binary accuracy submissions with benchmark-native Leaderboard Scores

Scoreboard accepts, stores and ranks the exact primary score produced by any Engine
Benchmark without recomputing it. The binary-accuracy contract (`correct/total`, 0..1)
only fits IFEval; DRACO's fractional and HealthBench's negative scores are rejected by
the Client submission adapter today.

Minimal scope for the tester deadline (owner-approved 2026-08-18): generic `score`
contract + `accuracy`→`score` rename end-to-end; typed `metrics` field and
score-presentation metadata deferred to a follow-up issue. Six design deltas vs the
ticket recorded as a Linear comment for Keelan's confirmation.

Work ledger: `docs/work/2026-08-18-OME-866-benchmark-native-scores.md`.
