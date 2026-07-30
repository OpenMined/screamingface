---
ticket: OME-597
stack: aigateway
status: done
started: 2026-07-25
finished: 2026-07-25
---

# OME-597 — Reject duplicate provider targets at rule-set construction

## Intent

`normalize_rules` (core/chat_parameters.py) enforces one rule per `request_path` but NOT one rule per
provider wire target. Two rules with distinct request paths that resolve to the same `provider_target`
pass construction and normalization silently; the collision surfaces only later, inside `_project`, as
a caller-facing `duplicate_channel` 400 — and only if a caller supplies both channels in one request.
A provider-config mistake thus becomes a latent, caller-triggered runtime failure instead of a
deterministic build-time error. This unit adds the missing one-rule-per-target invariant to
`normalize_rules`, plus a conformance assertion over every registered provider.

## Design (confirmed)

`ParameterProjectionRule.target` (existing property) = `provider_target or request_path`. It unifies
both rule kinds:

- `direct` rules have `provider_target=None` → `target == request_path`, so they live in the
  request-path space that the existing check already makes unique.
- `provider_native` rules require a `provider_target` (model validator) → `target == provider_target`.

So target-uniqueness is a strictly stronger invariant than the existing path-uniqueness. A collision
can only be: (a) two native rules with different `provider_params.*` paths mapping to one target, or
(b) a direct rule whose `request_path` equals a native rule's `provider_target`.

Change `normalize_rules` to also reject a repeated `rule.target`, raising the SAME
`DuplicateParameterRuleError` (both violations are "rule set internally inconsistent at construction";
no caller branches on the type, so a new subclass would be YAGNI). The message names both colliding
request paths. Reuse the `rule.target` property (DRY — no recomputation of `provider_target or path`).

**Additive-safety (verified read-only):** the only `provider_target`s across all plugins today are
`top_k` (anthropic, gemini — different rule sets) and `extra_body.top_k` (openrouter); each provider
has exactly one rule per target, and no direct rule uses request_path `top_k`/`extra_body.top_k`. So
NO current provider rule set violates the new invariant — enforcement is purely additive. No prior
test asserts a duplicate-target rule set constructs successfully.

## Approved prior-test change — one test

Planning assumed this was purely additive; it was not. Enforcing target-uniqueness in
`normalize_rules` made one prior test's SETUP a build-time error:
`tests/unit/core/test_parameter_projection_hardening.py::test_duplicate_channel_to_the_same_target_rejects`
built a synthetic two-rule set (a bare `top_k` direct rule + a `provider_params.top_k` native rule,
both targeting `extra_body.top_k`) purely to exercise the RUNTIME `duplicate_channel` guard. That
rule set is now rejected at construction, so `_classify` raised `DuplicateParameterRuleError` during
normalization before reaching the guard.

Verified the runtime `duplicate_channel` guard remains reachable and necessary via the legitimate
same-rule-two-encodings path: ONE `provider_params.top_k` rule + a caller body carrying BOTH the flat
dot-key top-level form and the nested wrapper form still collides on one target (confirmed by reading
`_project`/`_resolve` in `core/parameter_projection.py`).

The owner approved re-pointing the prior test to the
one-rule/two-encodings scenario (preserving the `duplicate_channel` runtime assertion) AND retaining a
separate construction-time test proving `normalize_rules` rejects two distinct rules that share a
target. Both protections are required and complementary: load-time rejects a conflicting rule config;
runtime rejects two encodings of one legitimate rule. The other two test files are pure appends (no
deletions). The request-path branch, its `DuplicateParameterRuleError`, and its message are unchanged.

## Planned changes

Source (1):
- `src/aigateway/core/chat_parameters.py` — extend `normalize_rules` with a per-`target` uniqueness
  check (raises `DuplicateParameterRuleError`); document both invariants in the docstring.

Tests (2 files, appends):
- `tests/unit/core/test_chat_parameter_contract.py` — two RED tests: (1) two distinct native paths →
  same `provider_target` raises; (2) a direct rule whose path equals a native rule's target raises.
- `tests/unit/core/test_provider_contract_conformance.py` — conformance guard: every registered
  provider's rule set has unique targets (regression guard; green today, fails on a future collision).

## Test plan (RED first)

- `test_duplicate_provider_target_across_paths_rejected` — build two `provider_native` rules
  `provider_params.a`→`top_k` and `provider_params.b`→`top_k`; `normalize_rules([...])` raises
  `DuplicateParameterRuleError`. FAILS before the change (only request_path is checked).
- `test_direct_path_colliding_with_native_target_rejected` — a `direct` rule `top_k` + a
  `provider_native` rule `provider_params.top_k`→`top_k` → raises. FAILS before the change.
- `test_registered_providers_have_unique_rule_targets` — for each registered provider, `normalize_rules`
  does not raise and target count == rule count. Green today; guards against future misconfig.

## Acceptance

- A rule set with two request paths mapping to one provider target raises at construction, not at
  request time.
- Every registered provider's rule set passes target-uniqueness.
- Existing one-rule-per-request-path behavior/error unchanged; full gate suite green.

## Outcome

**Status: DONE.** The one-rule-per-target invariant is enforced at rule-set construction.

### Actual changes (match plan)

Source (1):
- `src/aigateway/core/chat_parameters.py` — `normalize_rules` now tracks `seen_paths` (set) and
  `seen_targets` (dict target→first request_path) in its single ordered pass. A repeated
  `rule.target` raises `DuplicateParameterRuleError` naming BOTH colliding request paths. Reuses the
  existing `rule.target` property (`provider_target or request_path`) — no recomputation. Two INVARIANT
  docstring blocks record one-rule-per-path AND one-rule-per-target.

Tests (3 files):
- `tests/unit/core/test_chat_parameter_contract.py` (+2 appended) — construction-time RED:
  two native paths → one target raises; a direct path clashing with a native target raises.
- `tests/unit/core/test_provider_contract_conformance.py` (+1 appended) — conformance guard:
  every registered provider's rule set (each auth-mode view) has unique targets. Green today;
  a future colliding rule turns it red in CI.
- `tests/unit/core/test_parameter_projection_hardening.py` (re-pointed, OWNER-APPROVED) —
  `test_duplicate_channel_to_the_same_target_rejects` now exercises the still-reachable runtime case:
  ONE legitimate `provider_params.top_k` rule reached via TWO caller encodings (flat dot-key +
  nested wrapper) → `duplicate_channel` 400. Preserves the runtime assertion the old two-rule setup
  tested (that setup is now a construction error, covered above).

### Quality gate

Full aigateway gate GREEN via `uv run .claude/scripts/run_gates.py aigateway --skip-append-only`:
ruff check ✓ · ruff format --check ✓ · pyright ✓ · check_no_enterprise ✓ ·
pytest --cov ≥80% ✓ (≈1668 passed, 40 skipped; coverage ~91%). OME-597 core suite alone:
68 passed in ~2s.

### Deviations

1. **Prior-test modification — owner-approved.** Enforcing
   target-uniqueness turned the old two-distinct-rules setup of
   `test_duplicate_channel_to_the_same_target_rejects` into a construction error. Owner approved
   re-pointing it to the one-rule/two-encodings scenario AND retaining a separate construction-time
   test. Both protections kept: load-time (reject conflicting config) + runtime (reject two encodings
   of one legitimate rule). Fully documented in the "Prior-test change" section above.
2. **`--skip-append-only` used honestly.** The only deleted test lines are the owner-approved
   re-point; verified `git diff HEAD -- apps/aigateway/tests` shows no other removed assertions.
3. **`chat_parameters.py` is 463 lines — 13 over the ≤450 REFACTOR guideline.** The change added
   the INVARIANT docstring + the target check. Accepted, not force-split: the file is one cohesive
   parameter-contract module (`ParameterSchema` + `ParameterProjectionRule` + `normalize_rules` +
   `inline_supported_parameters`), and `run_gates.py` does not gate line count. Splitting purely to
   shave 13 lines would fragment a coherent unit and widen the import blast radius (YAGNI + blast
   radius). Implementation note: if this file grows materially, extract `ParameterSchema`
   validation into its own module rather than splitting `normalize_rules` from its rule type.
4. **First full-gate run showed one UNRELATED failure — environmental, not this diff.**
   `tests/unit/auth/test_login.py::test_unknown_user_timing_close_to_wrong_password` (a login
   timing-side-channel test asserting missing-user vs wrong-password medians within 10%) failed under
   saturated gate load (pyright + full suite + coverage contending for CPU skews the median). Proven
   non-causal: this diff touches ZERO auth files, and the test passes 3/3 in isolation (~13s each).
   Re-ran the gate unchanged (never modified that test — append-only + not this unit's test); the
   re-run was fully green. Implementation note: that timing test is gate-load-fragile independent of this work
   — a candidate for CPU-time measurement or a load-aware tolerance in a separate unit.

### Commit

`928fa51d` — `feat(aigateway): reject duplicate provider targets at rule-set construction`
(`Refs: OME-597, OME-479`). 4 files changed, 76 insertions(+), 10 deletions(-).
