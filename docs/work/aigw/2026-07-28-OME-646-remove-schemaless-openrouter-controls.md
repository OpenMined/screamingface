---
ticket: OME-646
stack: aigateway
status: done
started: 2026-07-28
finished: 2026-07-28
---

# OME-646 — Remove the schema-less OpenRouter routing controls and make enabled-OpenRouter conformance non-vacuous

## Intent

OpenRouter enables four controls — `provider`, `plugins`, `route`, `models` — as `direct_rule`
entries carrying no `ParameterSchema`. `core/parameter_projection.py::_accept` validates only when
`rule.parameter_schema is not None`, so each of these accepts arbitrary nested JSON and forwards it
verbatim. That breaks the locked rule that an enabled ordinary parameter must carry a gateway-owned
validation schema, and `models` / `route="fallback"` / `plugins` additionally reach into routing,
fallback and hosted-tool surfaces this task explicitly excludes.

The defect is invisible to the default gate: `OpenRouterPluginSettings.enabled` defaults to false and
`test_provider_contract_conformance.py` iterates models belonging to *enabled* providers, so it
examined zero OpenRouter rows and still reported success. Reproduced 2026-07-28:

```
AIGW_OPENROUTER_ENABLED=true uv run pytest \
  tests/unit/core/test_provider_contract_conformance.py -q
FAILED test_every_enabled_param_is_fully_evidenced
  AssertionError: ('openrouter/anthropic/claude-fable-5', 'api_key', 'models')
  assert None is not None
1 failed, 9 passed
```

Removing the four rules restores the invariant. Making the conformance suite exercise OpenRouter
non-vacuously stops the same class of defect from hiding behind a disabled provider again — the
second half matters more than the first, because it is what makes the gate capable of failing.

## Planned changes

- `src/aigateway/plugins/openrouter_provider/parameters.py` — delete the four schema-less
  `direct_rule` entries and the comment that rationalized them.
- `tests/unit/core/test_provider_contract_conformance.py` — make the provider sweep non-vacuous so
  a disabled-by-default provider is still conformance-checked.
- `tests/unit/openrouter/test_openrouter_security.py` — the existing test asserts the four fields
  reach `litellm.acompletion` kwargs. That behavior is being removed, so this is a prior test whose
  premise this change invalidates. **Flagged to the owner rather than edited silently.**
- Possibly `src/aigateway/plugins/openrouter_provider/settings.py` if the sweep needs an enable hook.

## Test plan

RED first:

1. A conformance test that examines OpenRouter rows without requiring the env var — proving the
   sweep is non-vacuous. Must fail before the rule removal.
2. `provider`, `plugins`, `route`, `models` are each rejected as unknown parameters, before any
   credential is read (the standard fail-closed path).
3. Boundary: removal must not disturb the OpenRouter rules that legitimately remain
   (`top_k`, penalties, logprobs, tools, …) — assert the surviving enabled set explicitly.
4. Invariant protected: no enabled parameter, on any provider, under any available auth mode, lacks
   a validation schema.

## Acceptance

- Enabled-OpenRouter conformance passes, and the suite would fail if a schema-less enabled rule were
  reintroduced.
- The four fields are refused before credential access.
- The surviving OpenRouter rule set is unchanged.
- Full aigateway gate green; no prior test weakened.

## Outcome

- **Commit:** `2a9a531f` —
  `fix(aigateway): stop enabling OpenRouter parameters that cannot be validated`;
  `Refs: OME-646`.

- **Actual files:**
  - `src/aigateway/plugins/openrouter_provider/parameters.py` — four schema-less
    `direct_rule` entries removed; module INVARIANT now states that every rule carries a
    validation schema; the rationale comment is replaced by an implementation note recording why
    the fields are excluded and what re-enabling would require.
  - `tests/unit/core/test_provider_contract_conformance.py` — `_load_registry` builds the
    sweep with every operator gate forced ON, so the whole file's invariants now apply to
    gated providers; new `test_an_operator_gate_cannot_hide_a_provider_from_conformance`.
  - `tests/unit/openrouter/test_openrouter_security.py` — `test_ordinary_openrouter_fields_
    pass_through` narrowed to the schema-backed sampling fields (its surviving assertions
    are unchanged); four parametrized refusal tests plus a dispatch-ordering tripwire added.
  - `tests/unit/openrouter/test_openrouter_parameter_projection.py` — the summary assertion
    drops the four fields and gains a disjointness assertion.
  - `tests/unit/openrouter/test_openrouter_parameter_overlay.py` — the OpenRouter instance
    of "ruled but unobserved" is replaced by an absence assertion; the general property is
    retained in core.
  - `tests/unit/core/test_chat_parameter_contract.py` — strengthened with the
    `provider_source == "none"` half so nothing was lost in that move.
  - `settings.py` was NOT needed: the plugin is registered even when disabled, so only the
    sweep's model source had to change.

- **Gates:** `run_gates.py aigateway --skip-append-only` — ALL GREEN (ruff check, ruff
  format, pyright, no-enterprise, pytest with coverage ≥80). Full suite 1996 passed /
  40 skipped, up from 1990/40 (net +6 tests).

- **Deviations:**
  1. **Prior tests changed — owner-approved for this unit only.** The append-only gate
     blocked the run. The five changes were put to the owner with a per-file account of
     what each gained and lost; approval was given for OME-646 alone, with the instruction
     to ask again if FR2–FR4 needs the same. Two files were strengthened only, two became
     stronger claims, and one (`test_openrouter_security`) is a genuine inversion, because
     the governing task inverts the requirement it encoded.
   2. **A second vacuity hole was found and later closed.** At this unit's snapshot, forcing
      operator gates on revealed that Ollama contributed zero models to the conformance sweep
      because its catalogue was runtime-dependent. Commit `0e16d652` later added a
      provider-owned deterministic conformance representative without changing runtime model
      registration, and registry-wide plus Ollama no-auth tests now cover its rules. This paragraph
      supersedes the earlier open-residual wording while preserving when the gap was discovered.
  3. **A tempting wrong fix was rejected.** Adding the four fields to
     `strip_dispatch_controls` would also have turned the suite green, and would breach the
     requirement that unknown parameters fail closed and are never silently dropped.
     Stripping drops silently; classification returns a 400 naming the field. Accordingly
     `test_strip_preserves_ordinary_and_provider_fields` is untouched and still correct.
