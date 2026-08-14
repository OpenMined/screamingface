# OME-825 — Benchmark refusal integrity (spec)

Status: approved for implementation (Khoa, 2026-08-14, "fix all these").
Parent policy: `docs/spec/2026-08-13-OME-807-benchmark-failure-handling.md` — unchanged.
This spec closes two seams where OME-807's "refusal is data, carried end-to-end"
doctrine leaks, plus three structural cleanups from the PR #584 review.

## 1. Null-text provider refusal (resolves the open safety-filter question)

A provider content-filter turn normally carries **no refusal text**
(`runner/model_response.py`'s own invariant comment). Today the Candidate adapter
encodes that event as `output="" refusal=None` — indistinguishable from a legitimate
empty answer, so it is judged, scored ~0, and published as `status=scored`: exactly
the "plausible zero" the OME-807 contract forbids.

Normative rule: **a provider refusal without refusal text is still a refusal.** The
Candidate adapter substitutes the named placeholder text
`"No refusal text (provider refused the request)."` as the refusal. Rationale and
precedent: HealthBench's official harness grades the literal marker
`"No response (bad request)."` when the provider errors — a synthesized marker string
graded as the answer is the originals-faithful mechanism. The OME-807 rules then apply
unchanged: the refusal text flows through the normal checker, the Case publishes
`status=refused` with its grade, and coverage stays factual. This is not refusal
inference from answer text (forbidden by OME-807): the provider *signaled* refusal;
only its text is missing.

## 2. LANL selection carries the refusal marking

LANL member records gain a `refusal` field (from the check record, which already
carries it), and selection re-encodes the chosen member with **its own refusal**
instead of hardcoded `None`. A refused member's answer text IS its refusal text, so a
chosen refused member encodes as `output="", refusal=<text>` — the downstream re-check
grades the same text, and Aggregation's refused branch fires. LANL_FLOW gains the
clause "…verbatim, carrying the member's refusal marking"; `LANL_PROTOCOL_REVISION`
bumps to v2. Only the LANL variant revision changes; canonical IFEval, DRACO, and
HealthBench protocol expressions stay byte-identical.

## 3. Cleanups (no wire change)

- One shared outcome-triple validator (`contract.validate_candidate_outcome`) replaces
  the byte-identical copies in `draco/records.py` and `healthbench/records.py`.
- One shared coverage formula (`contract.candidate_coverage`) used by both the
  producer (`finalize_candidate_result`) and the contract validator.
- The dead `provider_refusal` Failure-code clause in `_require_failed_case` and
  ifeval's dead `provider_`/`aigateway_` stage heuristic are removed: no producer can
  emit that code (url4 collect strips error codes to kind+message), and the clauses
  imply a refusal-as-Failure model OME-807 deleted.

## Don't regress

- Refusals are graded through the normal checker (never auto-zeroed) — OME-807 §grading.
- Duplicate-rubric abort, positional row binding, and coverage semantics unchanged.
