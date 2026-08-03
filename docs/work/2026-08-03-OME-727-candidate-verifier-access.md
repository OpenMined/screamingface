---
ticket: OME-727
stack: url4-cloud
status: done
started: 2026-08-03
finished: 2026-08-03
---

# OME-727 — Give candidate blobs verifier access: case slot + ifeval action routes

## Intent

Enable candidate-side verifier loops (the Skurikhin et al. ensemble,
https://openreview.net/forum?id=XSIYfTm2h7) without touching the exam: the engine
binds `$case` into the Candidate blob's scope, and ifeval advertises three
deterministic actions (check-feedback, select, finalize) via an additive manifest
`actions` map. Owner call: build now, flag the candidate-contract change for Keelan
review rather than pre-agreeing it.

## Planned changes

- `runner/connector.py` — `_CandidateEndpoint` binds `$case` when the invocation
  carries the second slot; old single-slot invocations byte-identical
- `benchmarks/definition.py` — `candidate(input, case=None)` builder emits the
  two-slot form when case is given
- `benchmarks/ifeval/definition.py` — both methods' builds pass `case=$item.id`;
  `ACTIONS` map exported; `Benchmark` resource gains additive `actions` (shared
  dataclass: optional field, absent for draco)
- `benchmarks/ifeval/runtime.py` — `/check` `feedback` intent (record JSON in →
  violations text or `PASSED`; INVARIANT: no instruction ids in the output);
  `select` route (letter + member answers in → verbatim chosen answer, deterministic
  fallback to first member on unparseable letter); `finalize` route (selection +
  verdict pairs in → earliest PASSED else last)
- Tests: probes-first for the slot wire format; unit tests per action; candidate
  two-slot binding test; manifest actions field; draco byte-identity guard

## Test plan

- RED: two-slot /candidate invocation binds $input AND $case in the blob (a blob
  referencing $case resolves it; a blob ignoring it unchanged); feedback intent
  never leaks instruction ids; select returns the letter's answer verbatim and
  falls back deterministically; finalize picks earliest PASSED else last; ifeval
  manifests advertise actions; draco manifest has no actions field

## Acceptance

- `run_gates.py url4-cloud` green; both ifeval methods' e2e gates still pass;
  a hand-built blob using $case + the actions executes against the local world

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned. Wire findings from probes: slot-packed contexts
  arrive newline-form via DAG lowering and comma-form on direct invocation — the
  endpoint parses both (case-first protocol); param-channel refs are mangled by the
  engine (avoided, probe-documented).
- **Commits:** `86538e90` feat: add IFEval corrective method and candidate verifier actions (pushed to upstream/OME-605-screamingface-client-v1).
- **Gates:** engine suite 712 green, run_gates ALL GREEN. In-process ensemble
  execution proof: 12 model calls exactly (3 members x 3 attempts + 3 judge),
  fail -> feedback -> pass -> verbatim select -> clean exam record, score 1.0.
- **Deviations:** none.
