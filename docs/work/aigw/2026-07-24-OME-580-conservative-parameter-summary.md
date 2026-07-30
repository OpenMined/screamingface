---
ticket: OME-580
stack: aigateway
status: done
started: 2026-07-24
finished: 2026-07-24
---

# OME-580 — Conservative /v1/models parameter summary (no-auth-mode edge + inline-vs-detail semantics)

## Intent

The `/v1/models` `supported_parameters` summary is a conservative, profile-independent view:
a path is advertised only when it is enabled under EVERY auth mode the provider offers (the
cross-auth intersection), so the summary never overclaims an auth-specific field. Two gaps:

1. **No-auth-mode edge.** `inline_supported_parameters` admits a path when
   `available_auth_modes ⊆ rule.applicable_auth_modes`. With no auth modes the available set is
   empty and `∅ ⊆ anything` is vacuously true, so the summary would advertise EVERY ruled path —
   the opposite of conservative. Inert today (no-auth providers carry no rules) but a latent
   trap the moment a rule is added to one.
2. **Inline-vs-detail semantics.** The summary is the cross-auth intersection; the detailed
   `/v1/model-parameters` contract is per-auth-mode. So an api-key-only field (Anthropic's
   native `top_k`) is correctly enabled in the api-key detail yet absent from the summary. The
   composition code does not state this deliberate, safe asymmetry, inviting a future reader to
   "correct" the summary into an overclaiming exact-equality.

Make the no-auth summary empty (advertise nothing when nothing can be proven), and state the
conservative-subset relationship in code + lock it with tests.

## Planned changes

- `apps/aigateway/src/aigateway/core/chat_parameters.py` — `inline_supported_parameters`:
  return `()` when `available_auth_modes` is empty (no mode can prove a field); keep the
  intersection for the non-empty case. Tighten the docstring.
- `apps/aigateway/src/aigateway/core/model_capabilities.py` — state in the module docstring
  that the inline summary is the cross-auth intersection ⊆ any single mode's enabled detail
  (same rule SOURCE, not identical OUTPUT).
- Tests:
  - `apps/aigateway/tests/unit/core/…` — new: empty `available_auth_modes` → empty summary
    (and a non-empty intersection still works).
  - `apps/aigateway/tests/unit/anthropic/…` — new: `provider_params.top_k` is enabled in the
    api-key detail contract but ABSENT from the inline summary (the intersection asymmetry).
  - `apps/aigateway/tests/unit/core/test_provider_contract_conformance.py` — flip the
    no-auth-mode branch of `test_summary_is_the_independent_cross_auth_mode_intersection` from
    `expected = all_paths` to `expected = set()` (pre-approved change to a prior test).

## Test plan

- RED: `inline_supported_parameters((rule,), available_auth_modes=())` currently returns the
  rule path; assert it returns `()`.
- RED: the conformance no-auth branch currently expects `all_paths`; assert the summary is `∅`.
- GREEN-through: the api-key-only-field asymmetry test (already true under the intersection)
  stays green and pins this resolution against regression.

## Acceptance

- No-auth-mode summary is empty; non-empty-auth intersection unchanged.
- Composition code states the conservative-subset relationship.
- Tests lock the empty-auth ∅ and the api-key-only asymmetry.
- Full `aigateway` gate suite green.

## Outcome

- **Actual files (matches planned):**
  - `apps/aigateway/src/aigateway/core/chat_parameters.py` — `inline_supported_parameters`
    returns `()` when `available_auth_modes` is empty; docstring states the invariant.
  - `apps/aigateway/src/aigateway/core/model_capabilities.py` — module docstring now states
    the conservative-subset relationship (summary = cross-auth intersection ⊆ any single
    mode's enabled detail; the api-key-only asymmetry is intentional).
  - `apps/aigateway/tests/unit/core/test_chat_parameter_contract.py` — +1 test (empty
    `available_auth_modes` → empty summary).
  - `apps/aigateway/tests/unit/anthropic/test_anthropic_parameter_projection.py` — +1 test
    (api-key-only `provider_params.top_k` dropped from the cross-auth summary, kept in the
    single-mode view).
  - `apps/aigateway/tests/unit/core/test_provider_contract_conformance.py` — flipped the
    no-auth-mode branch of `test_summary_is_the_independent_cross_auth_mode_intersection`
    from `expected = all_paths` to `expected = set()` (pre-approved prior-test change).
- **Commits:** landed within the OME-479 base snapshot `b9c219ad`
  (`feat(aigateway): per-provider chat parameter contract (OME-479 base)`). Every affected file
  was introduced in that same base snapshot, so there is no earlier committed intermediate state;
  the refinement is inseparable from the base and was folded into it;
  fixes from here on land as their own follow-up commits.
- **Gates:** ALL GATES GREEN — `run_gates.py aigateway` (append-only check, ruff, format,
  pyright, no-enterprise, `pytest --cov` 91.01%). One flaky failure on the first run,
  `test_login.py::test_unknown_user_timing_close_to_wrong_password` — a load-sensitive auth
  timing-side-channel test with zero coupling to this change (passed 5/5 in isolation; green
  on gate re-run). Blast-radius suites (core+anthropic+gemini+openrouter): 672 passed.
- **Deviations:** no standalone commit (see above). No schema/model touched → no migration (S1
  N/A). Pre-existing auth-timing flake noted above is out of this unit's scope. The empty-auth
  branch is inert today (no registered no-auth provider carries rules); the fix closes the
  latent trap and the pre-approved conformance edit keeps intent aligned.
