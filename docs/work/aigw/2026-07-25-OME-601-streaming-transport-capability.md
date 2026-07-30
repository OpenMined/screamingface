---
ticket: OME-601
stack: aigateway
status: done
started: 2026-07-25
finished: 2026-07-25
---

# OME-601 — Publish the streaming transport capability in the parameter contract

## Intent

The gateway enforces a per-provider streaming policy that no client can discover from the
contract. Make the enforced behaviour discoverable.

## Evidence

- `routes/chat.py:150-158` — `if body.get("stream") and not plugin.supports_chat_streaming():`
  raises HTTP 400 `{"code": "streaming_not_supported", ...}`. A live, enforced gate.
- `plugin_base.py:195-197` — `supports_chat_streaming()` defaults to `True`. Overridden to
  `False` in `antigravity_provider`, `codex_provider`, `gemini_provider`, `openrouter_provider`.
  So the split is real: **anthropic / huggingface / ollama stream; the other four do not.**
- `plugin_base.py:275-284` — `chat_transport_capabilities` returns `()`, and a repo-wide search
  finds **no plugin overriding it**. The `transport` section of every contract document is `{}`,
  for every provider, in every auth mode.
- `stream` ∈ `GATEWAY_OWNED_FIELDS`, so it is structurally barred from ever being a parameter
  rule (already asserted by `test_no_rule_enables_a_gateway_owned_or_transport_field`). The
  transport section is its ONLY possible home — there is no other surface a client could consult.
- That same conformance test's transport half is vacuous today: `transport_names & rule_paths ==
  set()` holds trivially over an empty tuple.

## Design

**Why this satisfies the "prove it reaches the wire" discipline.** This unit ENABLES nothing. The
capability is derived 1:1 from a flag that already gates real dispatch, so the proof is the live
request path rather than an inspection of a provider transform. Reporting `disabled` is strictly
conservative; reporting `enabled` mirrors a request that succeeds today.

**Two axes, kept honest.** `supports_chat_streaming`'s own docstring is "whether
`/v1/chat/completions` may create a streaming response" — that is gateway POLICY, so it maps to
`gateway_status`. `provider_support` stays `"unknown"`: the base class holds no evidence about the
upstream, and inventing `"supported"` would fabricate evidence. A plugin that has real evidence
overrides the hook.

**Placement.** The reason code and the capability's shape are published contract vocabulary, so
they belong in `core/chat_parameters.py` beside `_DISABLED_UNPROJECTED_REASON` and the
`TransportCapability` type — not in the port. `plugin_base` only wires:

```
chat_parameters.stream_transport_capability(gateway_enabled=...) -> TransportCapability
plugin_base.chat_transport_capabilities()  ->  (that,)
```

Import direction is safe: `chat_parameters` imports only `re`, stdlib typing, pydantic and
`.profile_models` — nothing that reaches `plugin_base`, so the new runtime import creates no cycle.
(The existing `plugin_base` import of these types is `TYPE_CHECKING`-only, which is why this needs
checking at all.)

Deriving the default in the BASE rather than per plugin means a new provider reports its streaming
posture correctly with no extra code, and the seven existing plugins need no edit — the DRY choice,
and it removes the possibility of a plugin publishing a status that contradicts its own flag.

`chat_transport_capabilities`'s docstring currently says "Default: none until a transport control
is separately reviewed." This unit IS that review; the docstring is updated rather than left
contradicting the code.

## Planned changes

Source (2):
- `src/aigateway/core/chat_parameters.py` — transport reason constant + the
  `stream_transport_capability` factory.
- `src/aigateway/core/plugin_base.py` — default `chat_transport_capabilities` derives from
  `supports_chat_streaming()`; docstring updated.

Tests (2, appends):
- `tests/unit/core/test_chat_parameter_contract.py` — the factory's two states.
- `tests/unit/core/test_provider_contract_conformance.py` — registry-wide agreement between the
  published status and the dispatch gate.

No schema, model, ORM or migration change.

## Test plan (RED first)

Factory:
- `gateway_enabled=True` → name `stream`, `gateway_status="enabled"`, `provider_support="unknown"`,
  and NO `reason` key in the serialized form.
- `gateway_enabled=False` → `gateway_status="disabled"` with the stable reason code present.

Conformance (registry-wide, the anti-drift guard):
- every registered provider × (summary view, each real auth mode) publishes exactly one `stream`
  transport capability, and `(gateway_status == "enabled") == plugin.supports_chat_streaming()`.
  This binds the document to the enforced gate so the two cannot drift.
- the transport section of a composed document is non-empty for a real provider (the previously
  vacuous assertion now has content to check).

Prior tests: none modified. No existing test pins an empty transport section — verified by
grepping every `["transport"]` assertion in the suite; all four are in the composer test and use
explicit fixtures.

## Acceptance

- Every provider's contract reports `stream` with a status matching its dispatch behaviour.
- A provider whose flag and published status disagree fails conformance.
- Full aigateway gate green.

## Outcome

**Status: DONE.** Every provider now publishes its streaming posture, bound in CI to the gate that
dispatch actually enforces.

### Actual changes (match plan)

Source (2):
- `core/chat_parameters.py` (463 → 498) — `_DISABLED_TRANSPORT_REASON`, public
  `STREAM_TRANSPORT_NAME`, and the `stream_transport_capability(*, gateway_enabled)` factory with
  `INVARIANT:` (policy vs evidence are different claims) and an implementation note (never publish a control
  the dispatch path does not yet honour, or the contract starts lying).
- `core/plugin_base.py` (413 → 430) — default `chat_transport_capabilities` returns the derived
  capability; docstring rewritten (it previously read "Default: none until a transport control is
  separately reviewed", which this unit contradicts); runtime import of the factory with a comment
  explaining why it is not `TYPE_CHECKING`-only.

Tests (2, pure appends):
- `test_chat_parameter_contract.py` — 3 factory tests (enabled/disabled/name).
- `test_provider_contract_conformance.py` — the registry-wide dispatch-agreement guard and a
  populated-section check on the composed document.

### Quality gate

`uv run .claude/scripts/run_gates.py aigateway --skip-append-only` from the repo root —
**GREEN on attempt 1**: ruff check ✓ · ruff format --check ✓ · pyright ✓ · check_no_enterprise ✓ ·
pytest --cov ≥80% ✓.

Full suite run separately: **1699 passed, 40 skipped**. No prior test broke, confirming the
pre-work check that nothing pinned an empty transport section.

### Verification beyond the gate

RED was concrete: the conformance failure was literally `AssertionError: ('anthropic/claude-opus-4-8',
'api_key') assert {}` — the empty transport section on a real provider, which is the finding itself.

After the change, every registered provider was inspected against the gate it enforces:

| provider | dispatch gate | published transport | contract_id moves |
|---|---|---|---|
| anthropic | streams | `stream` enabled, no reason | ✅ |
| antigravity | `stream=true` → 400 | `stream` disabled + reason | ✅ |
| codex | `stream=true` → 400 | `stream` disabled + reason | ✅ |
| gemini-cli | `stream=true` → 400 | `stream` disabled + reason | ✅ |
| huggingface | streams | `stream` enabled, no reason | ✅ |
| ollama / openrouter | — | no models registered locally, not observable | — |

Published status matches the enforced gate in every observable case. The `contract_id` column is
the OME-600 work paying off immediately: populating the section moves the identity, which is the
correct signal that the contract genuinely changed.

ollama and openrouter can register no models when provider discovery returns no rows,
so they could not be observed directly — but the capability is derived in the BASE class, so they
are covered by construction rather than by per-plugin code, and the conformance guard will cover
them wherever their models do register.

### Deviations

1. **`chat_parameters.py` is 498 lines against the ≤450 guideline** (was 463; this unit added 35).
   The factory's placement is correct — it is published contract vocabulary, sibling to
   `_DISABLED_UNPROJECTED_REASON` and the `TransportCapability` type. The alternatives are worse:
   the app-layer composer would invert the layering (the port cannot import upward), and the
   dispatch-side projection module is the wrong domain. The real fix is splitting the module, but
   every plugin imports it, so that is a repo-wide change that does not belong inside a feature
   unit. **Filed as OME-602** rather than accepted silently a third time — the overage is now
   growing, not holding, which is the point to stop re-accepting it.
2. **Docstring corrected, not just extended.** `chat_transport_capabilities` said "Default: none
   until a transport control is separately reviewed." Leaving that in place would have left the
   code contradicting its own contract text.
3. **`STREAM_TRANSPORT_NAME` is public while the reason code is private**, matching the existing
   split: `_DISABLED_UNPROJECTED_REASON` is private too. The name is public because it is the
   request field callers send and other modules legitimately reason about it.
4. **`--skip-append-only` used honestly:** zero deleted test lines; the import line was extended,
   not replaced. All 3 source-side deletions are in `plugin_base`.

### Commit

`bae47ff2` — `feat(aigateway): publish the streaming transport capability in the contract`
(`Refs: OME-601, OME-479`). 4 files, +116/-3.
