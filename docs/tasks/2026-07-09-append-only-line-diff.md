---
id: OME-369
linear_url: https://linear.app/openmined/issue/OME-369/run-gatespy-append-only-check-flags-pure-test-additions-as-violations
status: in_progress
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
