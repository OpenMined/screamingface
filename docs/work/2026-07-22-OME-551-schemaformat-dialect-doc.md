---
ticket: OME-551
stack: url4-cloud
status: done
started: 2026-07-22
finished: 2026-07-22
---

# OME-551 — Document the AsyncAPI payload schema dialect (schemaFormat decision)

## Intent

The ticket's original approach — declare `schemaFormat: application/schema+json;version=draft-2020-12`
on the AsyncAPI messages — was proven **infeasible**: AsyncAPI 3.0 removed `schemaFormat` from the
Message Object (it moves into `payload` as a Multi-Format Schema Object), and the AsyncAPI parser
ships no `draft-2020-12` schema parser, so declaring it produces `Unknown schema format` **errors**
(verified with `@asyncapi/cli` — both message-level and payload-level forms). Our payloads use only
draft-07-compatible keywords (`const`, `anyOf`+`type:null`, `enum`, `$ref`), so the parser's default
AsyncAPI Schema dialect already interprets them correctly — the misinterpretation the ticket targeted
does not materialize. **Owner decision: Option 1** — keep the default dialect and *document* the
choice, rather than ship a declaration that regresses validation.

## Planned changes

- `apps/url4-cloud/docs/protocol.md` §8 — a note that WS message payloads are authored as JSON
  Schema via Pydantic (draft-07-compatible keyword subset) and served under AsyncAPI's default
  Schema dialect, deliberately with **no** `schemaFormat` (the parser has no draft-2020-12 parser).
- `apps/url4-cloud/docs/protocol.md` §10 — a decision-log row recording it.

No code / schema change — `schemas/asyncapi.py` stays as-is (default dialect); the AsyncAPI doc is
unchanged and keeps validating.

## Test plan

- Docs-only decision record; no new test. Invariant preserved and re-verified: the generated
  AsyncAPI 3.0 doc still validates with `@asyncapi/cli` (0 errors) — unchanged from before.

## Acceptance

- The §8 note + §10 decision row exist; `run_gates.py url4-cloud` green; AsyncAPI 3.0 still validates.

## Outcome

- **Actual files:** `apps/url4-cloud/docs/protocol.md` (§8 "Payload schema dialect" note + §10
  decision-log row D13). No code/schema change — `schemas/asyncapi.py` untouched.
- **Commits:** see the OME-551 commit on `OME-513-url4-cloud`.
- **Gates:** `run_gates.py url4-cloud` GREEN (append-only · ruff · format · pyright · pytest 119
  passed · cov ≥ 80). The AsyncAPI doc is byte-identical to the last externally-validated build
  (`@asyncapi/cli` 0 errors) — unchanged, so no re-validation needed.
- **Deviations:** the ticket's original approach (declare draft-2020-12 `schemaFormat`) was dropped
  as infeasible + unnecessary (owner Option 1). This commit resolves the design fork raised
  mid-batch, not the originally-scoped code change.
