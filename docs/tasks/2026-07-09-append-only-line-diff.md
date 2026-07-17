---
id: OME-369
linear_url: https://linear.app/openmined/issue/OME-369/run-gatespy-append-only-check-flags-pure-test-additions-as-violations
status: in_review
type: task
priority: P2
labels: [repo, autonomous, agentic, "Repo & Dev Process"]
created: 2026-07-09
closed:
---

`append_only_check()` in `.claude/scripts/run_gates.py` flags any git-modified test
file regardless of content, so pure additions to an existing test file false-positive
as a rule-5 violation. Found while working OME-322.

Fix: diff added/removed lines within each changed test file rather than file-level git
status — only fail if a `-` line falls inside a previously-existing test function body.

No dedicated stack/tests exist for `.claude/scripts/`; verified with a manual
synthetic-scenario check per owner decision, no new permanent test infra added.

**Round 2 (2026-07-17):** `HupBaHa`'s PR review requested changes — the fix still
let prior tests be modified undetected in nested stack roots (`apps/scoreboard`
etc.), plus asked for a permanent test matrix. Confirmed and fixed three bugs
(nested-root `git show` path resolution, decorator lines outside the recorded test
range, dash-prefixed removed-line content false-matching the header skip); added
`.claude/scripts/tests/test_run_gates.py` (8 permanent tests, stdlib `unittest`)
replacing the manual-only verification. See the ledger's Round 2 section for full
detail. Status stays `in_review` pending re-review.

**Round 3 (2026-07-17):** two more concerns from the same review, both confirmed:
pure insertions inside an existing test (zero removed lines) could neuter an
assertion undetected, and fixtures/helpers (e.g. `conftest.py`, real in both
`apps/scoreboard` and `apps/aigateway`) weren't protected at all since only
`test_*`-named functions were tracked. Fixed by protecting every function's range
(not just tests) and adding insertion-position detection with an exclusive upper
bound (so appending a new function directly after an existing one stays legitimate).
12/12 tests pass. See the ledger's Round 3 section.
