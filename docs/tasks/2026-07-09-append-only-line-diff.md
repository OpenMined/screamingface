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

**Round 4 (2026-07-17):** fixed the reviewer's last P2 (module-level test data,
e.g. `_BASE_KW`, wasn't protected). 16/16 tests pass. Two further findings from
deeper probing deliberately NOT fixed here, tracked as separate follow-up
tickets instead: decorator-stacking (concern A) and name-shadowing/monkeypatching
(a structural line-diffing limitation). A third, non-code finding (no CI/hook
independently enforces this check at all) filed as its own distinct ticket. See
the ledger's Round 4 section for full detail and ticket links.

**Round 5 (2026-07-17):** a structured multi-angle code-review pass on the
pushed PR found round 4's own fix was too broad (a denylist, not an allowlist)
— editing a module docstring, an `if __name__ == "__main__":` block, or an
import nested in a version-guard all got falsely flagged, reopening OME-369's
original false-positive problem. Also found a separate anchor-computation bug:
replacing the blank line between two functions falsely flagged the second one.
Fixed both at the root (switched to an `_MODULE_LEVEL_DATA` allowlist; anchor
tracking now keyed off the diff hunk's declared old-line count) plus an
anchor-syntax convention fix. 20/20 tests pass. See the ledger's Round 5
section.

**Round 6 (2026-07-17):** second structured review pass — 5 of 8 angles clean.
Fixed one more real gap (`ast.AugAssign` module-level accumulators were
unprotected) and one docs-process gap (Round 1's ledger placeholder never
filled). A walrus-statement edge case documented as a known limitation rather
than fixed (too exotic to warrant a special case). 21/21 tests pass. See the
ledger's Round 6 section.
