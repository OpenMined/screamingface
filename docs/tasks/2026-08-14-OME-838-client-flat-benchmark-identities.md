---
id: OME-838
linear_url: https://linear.app/openmined/issue/OME-838/align-client-examples-and-local-catalogue-with-flat-benchmark-identities
status: In Review
priority: P1
labels: [py-screamingface, agentic, autonomous, task]
created: 2026-08-14
parent: OME-836
---

# Align Client examples and local catalogue with flat benchmark identities

Remove Client `Benchmark.variant` decoding and all smoke/lite examples, use canonical DRACO with
explicit limits, and rename the HealthBench challenge throughout the Client and public docs. Keep
Leaderboard identities flat, reject partial-result publication, and synchronize the local
Scoreboard seed to the exact public catalogue without deleting stored results.
