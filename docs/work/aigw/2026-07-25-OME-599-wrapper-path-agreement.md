---
ticket: OME-599
stack: aigateway
status: done
started: 2026-07-25
finished: 2026-07-25
---

# OME-599 — Enforce wrapper-path agreement between provider discovery and rules

## Intent

Each plugin declares which native fields ride the `provider_params.*` wrapper TWICE, in two
independent hand-synced literals with no import between them:

- `plugins/anthropic_provider/discovery.py:42` — `_WRAPPED_NATIVE_PARAMS = frozenset({"top_k"})`
- `plugins/openrouter_provider/discovery.py:53` — same literal
- `plugins/gemini_provider/discovery.py:105` — `_NATIVE_TO_REQUEST_PATH` (native camelCase → path)
- and implicitly, each `provider_native_rule(request_path="provider_params.X", …)` in the plugin's
  `parameters.py`

Both files carry an implementation note conceding "keep in sync". Consistent today; drift is contract-output
only (dispatch unaffected).

## Design (scope corrected by an empirical probe — see below)

**The finding's premise "no test enforces agreement" is only partly true.** Probed by building the
real anthropic contract document with a drifted observation (rule stays at `provider_params.top_k`,
observation regresses to bare `top_k`) and re-applying the existing conformance assertions:

| auth mode | drifted document | existing conformance |
|---|---|---|
| `api_key` (rule ENABLED) | `provider_params.top_k` enabled/`support=unknown`/`source=none` **and** `top_k` disabled/supported — listed twice | **FAILS** (`support=unknown`, `source=none`) |
| `oauth` (rule DISABLED) | only bare `top_k`, disabled/supported — no duplicate | **PASSES** — drift invisible |

So `test_every_enabled_param_is_fully_evidenced` already catches drift transitively, but ONLY where
the rule is enabled. The genuine residual gaps:

1. Any auth mode where the rule is disabled — the contract is silently wrong for that mode.
2. A native rule enabled under NO auth mode — never checked.
3. Diagnosis quality: when the existing assertion fires it blames missing EVIDENCE, pointing the next
   engineer at the observation source rather than the actual cause (path disagreement).

**Why not "derive one from the other" (the finding's first option):** not uniformly possible. Gemini's
`_NATIVE_TO_REQUEST_PATH` also carries the native camelCase → caller-path correspondence
(`topP`→`top_p`, `maxOutputTokens`→`max_tokens`), information `parameters.py` does not hold. Only
anthropic/openrouter could derive their literal, leaving gemini — the most complex mapping — unguarded,
plus it would impose a `discovery.py → parameters.py` import direction for a partial win. Enforcing
agreement directly covers all three plugins and every future one.

**Chosen design.** A pure, provider-agnostic predicate in the core wrapper-path algebra
(`core/parameter_projection.py`, which already owns `WRAPPER_KEY`):

```
wrapper_path_conflicts(request_paths) -> tuple[str, ...]
```

returns the native names addressed at BOTH their bare path and their `provider_params.*` path, sorted.
Then a registry-wide conformance assertion over the union of each provider's rule paths and
observation paths, under the summary view AND every real auth mode (so gap 1 and 2 are closed), whose
failure message names the conflicting field (gap 3).

INVARIANT: within one provider view, a native name is addressed at exactly one path — never both bare
and wrapped. Note this is a *different* invariant from OME-597's one-rule-per-target: that one is
about two rules racing to one wire field; this one is about the rule set and the evidence set
disagreeing on where a field lives.

## Planned changes

Source (1):
- `src/aigateway/core/parameter_projection.py` — add `wrapper_path_conflicts`.

Tests (2 files, appends):
- `tests/unit/core/test_parameter_projection_hardening.py` — RED unit tests for the predicate.
- `tests/unit/core/test_provider_contract_conformance.py` — registry-wide agreement guard.

No schema, model, ORM or migration change.

## Test plan (RED first)

Predicate (fails before the function exists):
- bare + wrapped for one name → returns that name.
- coherent paths (wrapped only, or bare only) → returns empty.
- multiple conflicts → returned sorted, deterministic.
- a wrapped path whose bare twin is absent → empty (the normal, correct case).
- nested/dotted native under the wrapper (`provider_params.a.b`) does not false-positive on `a`.

Conformance (green today, regression guard):
- every registered provider × (summary view, each real auth mode): union of rule paths and observation
  paths has no conflict; assertion message names provider, mode, and conflicting field.

## Acceptance

- The predicate reports conflicts and is empty for coherent input.
- No registered provider has a native addressed at both bare and wrapped path in any view.
- Full aigateway gate green.

## Outcome

**Status: DONE.** Wrapper-path agreement is now enforced for every registered provider in every
auth-mode view.

### Actual changes (match plan)

Source (1) — `src/aigateway/core/parameter_projection.py` (190 → 214 lines):
- Added the public `wrapper_path_conflicts(request_paths) -> tuple[str, ...]`, placed beside
  `WRAPPER_KEY` / `_WRAPPER_PREFIX` (whose prefix constant it reuses — DRY). Three lines of logic:
  set the paths, strip the wrapper prefix to recover native names, return `sorted(wrapped & paths)`.
  Docstring records the INVARIANT and the WHY for using the whole remainder as the native name.

Tests (2 files, appends):
- `tests/unit/core/test_parameter_projection_hardening.py` — 8 predicate tests: the conflict case,
  wrapped-only, bare-only, empty input, multi-conflict determinism/sorting, the nested-native
  non-false-positive (`provider_params.a.b` vs bare `a`), the bare wrapper key itself, and
  iterable/duplicate tolerance. Import line extended (no assertion removed).
- `tests/unit/core/test_provider_contract_conformance.py` — registry-wide guard over
  `(None, *available_auth_modes())` per model, asserting the union of rule paths and observation
  paths has no conflict, failing with `(canonical, mode)`.

### Quality gate

`uv run .claude/scripts/run_gates.py aigateway --skip-append-only`.

- **Attempt 1 — FAILED (my defect):** `ruff format --check` wanted one blank line before the new
  top-level `def` (PEP 8 two-blank-line rule); my insertion left one. Fixed by running
  `ruff format` on the file — the code was changed, never the gate.
- **Attempt 2 — GREEN:** ruff check ✓ · ruff format --check ✓ · pyright ✓ · check_no_enterprise ✓ ·
  pytest --cov ≥80% ✓.

Targeted suites: predicate + conformance = 31 passed.

### Verification beyond the gate

The finding's premise was **empirically re-scoped before any code was written.** Probed the real
anthropic contract with a drifted observation:

| auth mode | drifted document | existing conformance |
|---|---|---|
| `api_key` (rule enabled) | listed TWICE — `provider_params.top_k` enabled/`support=unknown`/`source=none` plus bare `top_k` disabled/supported | **FAILS** (already caught) |
| `oauth` (rule disabled) | only bare `top_k`, disabled/supported | **PASSES** — drift invisible |

So "no test enforces agreement" was only partly true; the real gap was drift in modes where the rule
is not enabled. After the change, a second probe fed the new guard the real rule paths plus the
drifted observation set:

```
mode=None     baseline=()  drifted=('top_k',)
mode=api_key  baseline=()  drifted=('top_k',)
mode=oauth    baseline=()  drifted=('top_k',)
```

The guard fires in ALL views including `oauth` — the precise mode the previous assertion missed —
proving the new guard is discriminating rather than green-by-construction.

### Deviations

1. **The finding's first fix option was rejected with cause** (derive one literal from the other):
   gemini's `_NATIVE_TO_REQUEST_PATH` also encodes the native camelCase → caller-path correspondence
   (`topP`→`top_p`), which `parameters.py` does not hold, so only anthropic/openrouter could derive
   theirs — leaving the most complex mapping unguarded and imposing a `discovery → parameters` import
   for a partial win. The conformance route covers all three plugins and every future one.
2. **The finding's severity framing was narrowed by evidence**, as documented above; the ticket states
   the corrected scope rather than the original "no test enforces agreement".
3. **`--skip-append-only` used honestly:** the only deleted test line is an `import` statement that was
   extended to add the new symbol — no assertion deleted or weakened.
4. **The new helper is PUBLIC with a test-only caller today.** Judged correct rather than speculative:
   it is wrapper-path algebra whose natural home is beside `WRAPPER_KEY`, the conformance suite already
   consumes core primitives (`GATEWAY_OWNED_FIELDS`, `normalize_rules`), and keeping it in core made a
   genuine RED unit test possible.

### Commit

`d3bcb6e6` — `feat(aigateway): enforce wrapper-path agreement between discovery and rules`
(`Refs: OME-599, OME-479`). 3 files, +123/-1.
