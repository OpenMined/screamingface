---
id: OME-892
linear_url: https://linear.app/openmined/issue/OME-892/deliver-large-evaluation-results-in-full-instead-of-cutting-them-off
status: in_progress
type: bug-fix
priority: High
labels: [screamingface-engine, py-screamingface, agentic, autonomous]
created: 2026-08-19
closed:
---

# Deliver large Evaluation results in full instead of cutting them off at 1 MiB

Sub-issue of OME-888 (mirrors GitHub #642). The Engine truncates Candidate Results over
1 MiB mid-JSON and still reports the run `succeeded`; the SDK then fails to decode the only
copy of the result, destroying paid Evaluation work.

Fix (spill-to-disk + claim ticket): results ≤ 1 MiB stay inline in the terminal event;
larger results are written to a content-addressed file on the Engine and the event carries
`artifact: {id, size_bytes, sha256}` which the SDK redeems via `GET /artifacts/{id}` with
size + sha256 verification; results over an env-configurable hard cap (default 1 GiB)
terminate `failed` with `result_too_large`. Truncation path deleted. SDK additionally
recognizes the legacy `…[truncated]` marker from older Engines and raises an actionable
error.

Ledger: `docs/work/2026-08-19-OME-892-deliver-large-results.md`
