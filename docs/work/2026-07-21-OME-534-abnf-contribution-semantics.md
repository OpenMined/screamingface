---
ticket: OME-534
stack: url4
status: done
started: 2026-07-21
finished: 2026-07-21
---

# OME-534 — ABNF conformance patch: name-only sources contribute; weight 0.0 instrumental; `name: value` packing

## Intent

CONFORMANCE PATCH (1 of 2) toward the external formal ABNF, adopted by owner
decision (2026-07-21) as the engine's normative grammar. The ABNF's
`annotated-source` (`[name-part ":"] … data-binding`) and `sugar-source`
(`name=value`, "equivalent to name-part : value") make every named source a
CONTRIBUTING source; the engine instead excludes name-only descriptors from
the packed context (reference-only Bindings) — verified by execution in both
the local merge and the fan-out reduce (where a named call even executes but
its response is dropped from the reducer input). Owner-decided semantics:

1. Name-only sources (`a: v` AND `a=v`) contribute.
2. Scalar `weight 0.0` = INSTRUMENTAL — resolved, `$name`-referenceable,
   excluded from the packed context (replaces the reference-only concept).
3. Named contributions pack as `name: value` lines; unnamed pack bare;
   expanded (`*src`) elements stay bare (the name binds the JSON array).
   Fan-out reduce keeps `name (weight=w):` headers; name-only calls now JOIN
   the fan-out (labeled `name:`) instead of demoting the group to local merge.

## Planned changes

- `src/url4/dag/compiler.py` — `_Slot.is_binding` → `instrumental`
  (set by `_slot_identity`: Source with scalar weight 0.0; Binding → False);
  `_fanout_call` unwraps `BindingNode` (and then `GuardNode`);
  `_fanout_graph` labels binding-wrapped calls with the binding name.
- `src/url4/dag/nodes.py` — `SlotSpec` bool means instrumental; `_gather` /
  `_gather_expanded` pack named slots as `name: value` and skip instrumental;
  `FanoutReduceNode.resolve` keeps instrumental (weight-0.0) entries
  referenceable but excludes them from the reducer input; docstrings.
- `tests/spec/test_abnf_contribution.py` — NEW spec test file (RED first).
- Prior tests pinning the OLD exclusion semantics: rewritten under the
  owner's explicit sign-off (this session); every change itemized below.

## Test plan

- name-colon and name-equals sources contribute, labeled (`named: DOC`).
- weighted named source packs labeled (`judged: V`).
- scalar weight 0.0: excluded from packing, still `$name`-substitutable.
- fan-out reduce: name-only call joins the fan-out labeled `name:`;
  weight-0.0 call excluded from reducer input but `$name` still resolves.
- deferred lazy-group binding (`g=(…)!j`) contributes labeled.
- INVARIANT protected: everything the author lists is data the processor
  sees, except what weight 0.0 explicitly marks instrumental.

## Acceptance

- New spec tests green; full suite green with prior-test rewrites itemized.
- `run_gates.py url4` all green.
- OME-534 closed with sha; ledger + docs/tasks mirror updated.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned (`dag/compiler.py`, `dag/nodes.py`,
  `tests/spec/test_abnf_contribution.py` NEW, +9 tests) PLUS
  `peer/client.py` — `_passthrough` migrated from the removed
  reference-only-Binding idiom to the instrumental descriptor
  (`(r:0:<remote>)!'$r'`), and one design refinement found during GREEN:
  the fan-out gate additionally requires ≥1 CONTRIBUTING call (an
  all-instrumental call group has an empty panel — its intent, with `$name`
  resolved, IS the result: the extraction idiom `(r:0:/call(…)!x)!'$r'`).
- **Commits:** `91a64a8` — feat(url4)!: ABNF contribution semantics.
- **Gates:** ALL GREEN — ruff check, format, pyright,
  pytest --cov=url4 --cov-fail-under=95 (1064 passed).
- **Prior-test rewrites (itemized; owner sign-off given this session):**
  - `spec/test_iteration_spec.py` — 4 vehicles → instrumental `:0:` idiom
    (purposes — $item placement, on_error — unchanged).
  - `spec/test_references.py` — 8 `(data=…)` → `(data:0:…)` (field paths).
  - `spec/test_substitution_coverage.py` — 6 vehicles → instrumental
    (`$$`-escape pins unchanged).
  - `spec/test_mandatory_intent.py` — 1 expectation now labeled-packed;
    processor-expression vehicle → instrumental.
  - `spec/test_processor_delegation.py` — Form-3 vehicle → instrumental.
  - `spec/test_grammar_conformance.py` — 2 transport-param vehicles →
    instrumental (stripping assertions unchanged).
  - `unit/test_ensemble.py` — 2 vehicles → instrumental.
  - `unit/test_characterization.py` — 2 characterizations updated to the
    new contract (labeled contribution).
  - `unit/test_execution.py` — 2 expectations updated (labeled packing).
  - `unit/test_client.py` — request-string spelling `(r=` → `(r:0.0:`.
  - `unit/test_dag.py` — SlotSpec pin `("a", True)` → `("a", False)`
    (bool now means instrumental); 3 expectations labeled-packed; 5
    vehicles → instrumental.
  - `unit/test_serve_app.py` / `unit/test_serve_params.py` /
    `unit/test_server.py` — 3 vehicles → instrumental; 1 request-string.
- **Deviations:** the fan-out-gate refinement above (not in the plan;
  surfaced by `(r=/solve($item.q)!go)!'$r'`-style rows spawning spurious
  reducer dispatches once bindings joined the gate). Serve-smoke CI shape
  `(/upper(x)!'go')!''` unaffected (unnamed single-call fan-out predates
  this unit).
