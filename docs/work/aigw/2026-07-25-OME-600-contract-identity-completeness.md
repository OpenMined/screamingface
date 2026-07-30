---
ticket: OME-600
stack: aigateway
status: done
started: 2026-07-25
finished: 2026-07-25
---

# OME-600 — Move contract identity when any published section changes

## Intent

`contract_id` and `context.revision` are opaque cache keys over the `/v1/model-parameters`
document. Their whole purpose is: **if the served document changed, the id changed.** A client
that caches on the id and never sees it move keeps serving a stale contract indefinitely.

Four published fields can change today while both digests stay byte-identical.

## Evidence — coverage map of the published document

`digest_inputs` (`model_parameter_contract.py:118-126`) is
`(canonical_id, auth_mode, scope, context_identity, evidence_revision, projection_revision,
SCHEMA_VERSION)`. Walking every top-level key the composer returns:

| published section | source | covered? |
|---|---|---|
| `schema_version` | `SCHEMA_VERSION` | ✅ hashed directly |
| `model.id` / `model.upstream_id` | `canonical_id` (upstream derived from it) | ✅ hashed |
| `model.gateway_provider` | independent argument | ❌ **never hashed** |
| `context.scope` / `context.auth_mode` | `scope`, `auth_mode` | ✅ hashed |
| `parameters` | rules + observations + auth_mode | ⚠️ partial — see below |
| `tools` | `tools` argument | ❌ **never hashed** |
| `transport` | `transport` argument | ❌ **never hashed** |
| `freshness` | caller | deliberately excluded (time-varying) |

`parameters`: `to_detail_dict` (`chat_parameters.py:324-343`) publishes only rule-sourced fields
(all in `_rules_revision`) and observation-sourced fields — of which `support`, `source` and
`stale` are in `_evidence_revision` but **`schema` is not**. That schema is genuinely published:
`compose_contract_entries:435` uses it as the fallback for an ENABLED entry whose rule carries no
schema, and `:452` publishes it directly for EVERY disabled entry.

`gateway_provider` is redundant at today's only call site — `model_parameters.py:73` derives
`provider = model.split("/", 1)[0]` and passes it at `:108`. But `build_model_parameter_document`
takes the two as independent arguments and enforces no relationship, so "unreachable" is a
property of the caller, not of the composer's contract.

## Design

**Hash the SERIALIZED section, not the input objects.** The tools/transport sections are built as
dicts for the response; digest that same dict. This makes coverage structural rather than
remembered: a field added to `ToolCapability.to_dict()` lands in the digest automatically, with no
second edit to keep in sync. (This is exactly the failure the finding describes — a second place
that must be remembered — so the fix must not introduce another one.)

```
_section_revision(section: Mapping[str, Any]) -> str   # sorted "key|canonical-json(value)"
```

Reuses `_sha` and the canonical-JSON convention already used by `_schema_key`.

**Failure asymmetry drives the inclusion rule.** Omitting a published field from the digest fails
DANGEROUSLY (a stale document served under a fixed cache key, forever). Including a field that did
not need it fails SAFELY (extra id churn). So the default is include; every exclusion must be a
stated decision.

`freshness` is the one exclusion: it is time-varying, so folding it in would move the id on
essentially every request and destroy its value as a cache key entirely. Today that exclusion is
implicit and therefore indistinguishable from the four bugs — it becomes an `INVARIANT:` anchor
plus a test that asserts the id does NOT move.

Not doing: a digest over the serialized `parameters` section. It is fully determined by the rules,
the observations and `auth_mode`, all of which are hashed (once the schema gap is closed), and
hashing derived data on top would be redundant. Note the input-level hashes are deliberately MORE
sensitive than the output: `_rules_revision` covers rules that are not applicable to the current
auth mode and so do not appear in `parameters` at all. That over-sensitivity errs toward churn —
the safe direction — so it is kept.

## Planned changes

Source (1) — `src/aigateway/core/model_parameter_contract.py`:
- add `_section_revision`;
- add `_schema_key(o.parameter_schema)` to `_evidence_revision`;
- build `tools`/`transport` sections once, digest them, serve the same objects;
- add `gateway_provider` + the two section revisions to `digest_inputs`;
- `INVARIANT:` anchor recording the freshness exclusion and the include-by-default rule.

Tests (1) — `tests/unit/core/test_model_parameter_contract.py` (append only):
- one mutation test per previously-uncovered field;
- the freshness non-mutation test;
- a tripwire over the document's top-level keys.

No schema, model, ORM or migration change.
No prior test is modified: the existing `test_both_digests_change_when_any_relevant_input_changes`
mutation list stays untouched and new cases go in new functions.

## Test plan (RED first)

Each asserts BOTH ids move (`contract_id` and `context.revision`), since both derive from the same
`digest_inputs`:

1. tool gateway_status flip `enabled` → `disabled`, same tool type.
2. adding a tool type.
3. transport gateway_status flip.
4. transport `reason` change alone (the field that only appears when non-None).
5. observation schema change alone — under BOTH publication routes: a disabled entry, and an
   enabled entry whose rule has no schema (the `:435` fallback).
6. `gateway_provider` change alone.
7. freshness change → ids UNCHANGED, and the document body DOES differ (proving the test would
   catch an accidental inclusion, not merely a no-op).
8. tripwire: the document's top-level key set equals the classified set.

Also asserted: the sections still serialize exactly as before (no behavior change to the response).

## Acceptance

- Every published section except `freshness` moves both digests when it changes.
- `freshness` moves neither.
- Adding a top-level section to the document fails the tripwire until classified.
- Full aigateway gate green.

## Outcome

**Status: DONE.** Every published section now moves both digests; `freshness` alone is excluded,
as a stated and tested decision.

### Actual changes (match plan)

Source (1) — `src/aigateway/core/model_parameter_contract.py` (147 → 190 lines):
- `_section_revision(Mapping) -> str` — sorted `key|canonical-json(value)` over an already
  serialized section, reusing `_sha` and the canonical-JSON convention of `_schema_key`.
- `_evidence_revision` now appends `_schema_key(o.parameter_schema)`, with an `INVARIANT:` naming
  both publication routes for that schema.
- `tools_section` / `transport_section` built once before the digest, then served verbatim — the
  hashed object and the served object are the same object.
- `digest_inputs` gained `gateway_provider` and the two section revisions.
- `INVARIANT:` block recording the freshness exclusion and the include-by-default rule.
- `Mapping` added to the `collections.abc` import.

Tests (1) — `tests/unit/core/test_model_parameter_contract.py` (245 → 440 lines), pure append:
helpers `_ids`, `_tool`, `_obs`, then 8 mutation tests (tool status flip, tool added, transport
status, transport reason value, transport reason APPEARING, disabled-entry observation schema,
enabled-entry fallback observation schema, `gateway_provider`), the freshness non-mutation test,
and the top-level-key tripwire.

### Quality gate

`uv run .claude/scripts/run_gates.py aigateway --skip-append-only`, run from the repo root.

- **Attempt 1 — FAILED (my defect):** `E501` — one test line at 102 chars. Split the call across
  lines; `ruff format` then reflowed the file. The code was changed, never the gate.
- **Attempt 2 — did not run.** The shell's working directory had persisted into `apps/aigateway`
  from an earlier command, so the runner path did not resolve (`Failed to spawn`, exit 2). An
  environment error, not a gate result; not counted as a retry.
- **Attempt 3 — GREEN:** ruff check ✓ · ruff format --check ✓ · pyright ✓ · check_no_enterprise ✓ ·
  pytest --cov ≥80% ✓.

Targeted: 19 in this file; 924 across every contract-consuming suite (core, route, and the
anthropic / gemini / openrouter / huggingface overlays) — no existing digest expectation broke,
confirming nothing pins a literal digest value anywhere in the repo.

### Verification beyond the gate

RED was per-gap and exact: **7 of the 8 mutation tests failed, each reporting identical digests for
differing bodies** — one failure per omission claimed in the ticket, no more and no fewer. The
freshness test and the tripwire passed from the start, correctly: both assert already-intended
behavior, and their value is to pin it against future drift.

The design claim — that digesting the *serialized* section makes coverage structural rather than
remembered — was mutation-tested by substituting the plausible wrong implementation (a hand-listed
`provider_support`/`gateway_status` hash) and re-running the transport cases:

| `_section_revision` | field APPEARS caught | field VALUE changes caught |
|---|---|---|
| serialized (shipped) | ✅ | ✅ |
| hand-listed (regression) | ❌ | ❌ |

So the two transport tests genuinely defend the design: a later "simplification" to a fixed field
list fails them rather than sliding through.

### Deviations

1. **Scope grew by one field during design.** The finding named tools, transport and the
   observation schema. Walking every top-level key of the served document to build the coverage
   table surfaced a fourth of the same class: `model.gateway_provider`, published but never hashed.
   It is unreachable at today's only call site (`model_parameters.py:73` derives it from the model
   id) — but that is a property of the caller, not of the composer's contract, so it is hashed
   rather than assumed. Recorded in the ticket.
2. **The freshness exclusion was promoted from implicit to explicit** — not requested, but without
   it the exclusion is textually indistinguishable from the four bugs, and the next reader has no
   way to tell "decided" from "forgotten".
3. **Rejected: a digest over the serialized `parameters` section.** It is fully determined by the
   rules, observations and `auth_mode`, all hashed. Worth noting the input-level hashes are
   deliberately MORE sensitive than the output — `_rules_revision` covers rules not applicable to
   the current auth mode, which never reach `parameters` — and that over-sensitivity errs toward
   churn, the safe direction, so it was kept rather than tightened.
4. **`--skip-append-only` used honestly:** `git diff HEAD -- tests | grep '^-'` returns nothing at
   all. Zero test lines deleted; all 4 source-side deletions are in the composer.

### Commit

`cff9932c` — `feat(aigateway): move contract identity when any published section changes`
(`Refs: OME-600, OME-479`). 2 files, +248/-4.
