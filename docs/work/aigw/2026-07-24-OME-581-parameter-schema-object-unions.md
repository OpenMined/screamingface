---
ticket: OME-581
stack: aigateway
status: done
started: 2026-07-24
finished: 2026-07-24
---

# OME-581 — Parameter schema: object type + top-level type unions + object-discriminator

## Intent

`ParameterSchema` (core `chat_parameters`) validates only scalars and typed arrays
(number/integer/string/boolean/array-of-scalar). To later advertise + enforce the standard
OpenAI-compatible structured fields, the schema model must be able to describe:

- `stop` — string | array[string]
- `tools` — array[object] (each object gated by a `type` discriminator)
- `tool_choice` — string | object (object gated by a `type` discriminator)
- `response_format` — object

The detailed `/v1/model-parameters` contract requires every enabled parameter to carry a
non-null schema, so these fields cannot be enabled until the schema can describe them. This
unit adds exactly that minimum to the **core** model — deliberately shallow: a top-level
object type, top-level type unions, `object` as an array item type, and an optional
object-discriminator (a named key inside an object / each array item must be in an allowed
enum). Nested function/JSON-schema bodies, tool names, and provider transforms stay with
LiteLLM. **No provider rule is enabled in this unit** — pure core capability + tests.

## Planned changes

- `apps/aigateway/src/aigateway/core/chat_parameters.py` — extend `ParameterSchema`:
  - `type` accepts a single type OR a tuple of types (top-level union); add `"object"`.
  - `item_type` gains `"object"`.
  - new optional `object_discriminator: str | None` + `object_discriminator_enum:
    tuple[str, ...] | None`: when the value (or each array item) is an object, its
    `object_discriminator` key value must be in the enum (fail closed otherwise).
  - `validate_value`: match value against ANY declared type; run the discriminator check on
    an object value and per-item for an array of objects; preserve ALL existing
    scalar/array/enum/bounds behavior byte-for-byte.
  - `to_json_schema`: render a union as a JSON-Schema type array; render `object`; render
    `items: {type: object}`. Discriminator stays a gateway-side validation constraint
    (allowed tool types are advertised separately in the contract's tools section — DRY).
  - construction guard: `object_discriminator` requires a non-empty enum and an object-capable
    type (fail closed at construction).

- `apps/aigateway/tests/unit/core/test_parameter_schema.py` — NEW focused test file.

## Test plan

- RED (object): accepts `{}`; rejects `5`, `"x"`, `[]`.
- RED (union string|array[string]): accepts `"x"` and `["a","b"]`; rejects `5` and `[1]`.
- RED (array[object] + discriminator): accepts `[{"type":"function"}]`; rejects `[1]`
  (item not object) and `[{"type":"web"}]` (type not enabled); allowed type passes.
- RED (string|object + discriminator): accepts `"auto"`; accepts `{"type":"function"}`;
  rejects `{"type":"web"}` and `5`; rejects `{}` (missing discriminator).
- RED (to_json_schema): union → `{"type":["string","array"],"items":{"type":"string"}}`;
  object → `{"type":"object"}`; array[object] → `{"type":"array","items":{"type":"object"}}`.
- RED (construction guard): discriminator without enum raises at construction.
- GREEN: minimal implementation.
- Regression: every existing scalar/array `ParameterSchema` test stays green (append-only).

## Acceptance

- `ParameterSchema` can describe `string | array[string]`, `array[object]`,
  `string | object`, and `object`.
- Object-discriminator enum rejects a disallowed discriminator value (object and per-item),
  accepts an allowed one.
- `to_json_schema()` renders a faithful fragment for each new shape.
- Existing scalar/array validation unchanged; full `aigateway` gate suite green.

## Outcome

- **Actual files (match planned):**
  - `apps/aigateway/src/aigateway/core/chat_parameters.py` — `ParameterSchema.type` now accepts
    a single type OR a tuple (top-level union) including `object`; `item_type` gains `object`;
    new `object_discriminator` + `object_discriminator_enum` with a fail-closed
    `_check_schema_consistency` construction guard (both set together, non-empty enum,
    object-capable type); `validate_value` matches ANY declared type then runs the
    discriminator on an object value and per array item; `to_json_schema` renders a union as a
    JSON-Schema type array and stays structural. REFACTOR: extracted a module-level
    `_TYPE_PREDICATES` table as the single source of per-type checks (top-level + items).
  - `apps/aigateway/tests/unit/core/test_parameter_schema.py` — NEW, 15 tests (object; unions;
    array[object] + per-item discriminator; string|object discriminator; to_json_schema for
    each shape; construction guards; scalar back-compat).
- **Commit:** `24456642`
  `feat(aigateway): describe object, union, and tool-discriminator param shapes` — a coherent
  follow-up on the base snapshot `b9c219ad` (2 files: source + new test).
- **Gates:** ALL GATES GREEN — `run_gates.py aigateway`: append-only (vs HEAD=base), ruff,
  ruff format, pyright, check_no_enterprise, `pytest --cov` (fail-under 80), full suite.
- **Deviations / notes:**
  - No provider parameter is enabled here — by design; this is the prerequisite core capability
    for the provider-enablement unit that follows.
  - No schema/model migration (stack rule S1 N/A — no ORM change).
  - `to_json_schema` for a single-type schema is byte-identical to before (renders
    `{"type": "<name>"}`), so every existing `contract_id` is unchanged — verified by the
    green OME-579 digest tests and the full conformance suite.
  - The discriminator is validation-only and NOT embedded in `to_json_schema`; the allowed
    tool types are advertised in the contract's tools section (single source of truth).
  - Implementation verification completed; Linear workflow state is maintained separately.
