---
ticket: OME-649
stack: aigateway
status: done
started: 2026-07-28
finished: 2026-07-28
---

# OME-649 — Publish auth applicability and distinguish wrong-auth from unimplemented projection

## Intent

Two coupled defects in detail composition, both about what happens to a rule that does not cover
the read's auth mode.

**The rule is dropped.** `compose_contract_entries` builds `enabled_rules` by filtering on
`auth_mode in rule.applicable_auth_modes`, so a rule the gateway HAS but which does not cover this
mode disappears from the rule side entirely. If the path is also observed it falls through to the
observation-only branch and is published as `projection_not_implemented` with
`applicable_auth_modes=()`; if it is not observed it vanishes.

**The published reason is therefore false and unactionable.** "The gateway has no projection for
this path" and "the gateway has a reviewed projection this credential cannot use" have opposite
remedies — wait for gateway work vs. connect the other credential — and the contract currently
gives the first answer to the second question.

**Applicability is never serialized.** `ParameterContractEntry` carries `applicable_auth_modes`,
but `to_detail_dict()` omits it, so even a correct value could not reach a client.

## Verified before starting

- **Dispatch is structurally insulated.** Auth-mode filtering for dispatch happens on its own path
  (`core/parameter_projection.py:178`), not through `compose_contract_entries`. Every entry this
  change adds or re-labels is DISABLED, so nothing new becomes forwardable.
- **The `/v1/models` summary is unaffected**: it derives from `inline_supported_parameters` over
  the rule set and the intersection of available auth modes — a different function.
- **Exactly one shipping rule is auth-restricted**: Anthropic `provider_params.top_k`
  (`_API_KEY_ONLY`). It already carries a static observation, so **zero new rows** appear in any
  shipping contract; only that row's reason, schema and the new key change.
- **Blast radius measured, not estimated**: the production change was written first and the full
  suite run against it. Exactly **three** prior tests fail (see Owner approval).

## Design decisions

**Publish under `gateway`, not at the row top level.** `applicable_auth_modes` is gateway policy,
belonging with `status`, `projection`/`reason` and `cache_behavior`. The top-level alternative was
cheaper — the two exact-equality locks are on the `gateway` sub-dict and would not have noticed a
new top-level key — but a lock noticing a new published key is the lock working, not a cost.

**A third reason rather than reuse.** `projection_not_available_for_auth_mode` keeps the same
subject as `projection_not_implemented` (the projection) with a different predicate, so a client
switching on the `projection_` prefix still separates the two.

**The rule's reviewed schema wins on a disabled-by-auth row.** The row now asserts that a reviewed
projection exists; publishing `null` for what it validates would contradict that in the same
object. No identity gap either way — `_rules_revision` and `_evidence_revision` already hash both
schemas.

**Rules are no longer filtered out, only re-labelled.** This also closes a publish/hash asymmetry:
`_rules_revision` folds EVERY rule's `applicable_auth_modes` into `contract_id` regardless of the
read's mode, so the digest already moved on a field the document never showed.

## Owner approval — prior-test changes

The append-only rule was set aside for this unit, for three changes, each one line:

1. `tests/unit/anthropic/test_anthropic_parameter_overlay.py::test_native_top_k_is_visible_but_disabled_under_oauth`
   — a genuine INVERSION: the assertion `reason == "projection_not_implemented"` encoded the defect
   as the contract.
2. `tests/unit/core/test_chat_parameter_contract.py::test_contract_entry_serializes_to_locked_detail_shape`
   — the exact-equality lock on the `gateway` block gains the new key, staying exact.
3. `tests/unit/core/test_model_parameter_contract.py::test_parameters_are_keyed_by_path_and_use_the_detail_shape`
   — same class as (2).

Also approved: the reason string, the `gateway` placement, and the disabled-by-auth schema change
(`null` → the rule's reviewed schema for Anthropic `provider_params.top_k` under OAuth), which no
prior test asserted.

## Planned changes

- `src/aigateway/core/chat_parameters.py` — `_DISABLED_AUTH_MODE_REASON`; `compose_contract_entries`
  keys off ALL rules and derives `gateway_status` from coverage; `to_detail_dict` serializes
  `gateway.applicable_auth_modes`.
- `tests/unit/core/test_auth_applicability_contract.py` — NEW.
- The three approved prior-test lines above.

## Test plan

RED first:

1. A rule not covering the read's mode SURVIVES composition as a disabled entry rather than being
   dropped — including when nothing observed it.
2. Its reason is `projection_not_available_for_auth_mode`, and an observed-but-unruled path in the
   same document still reads `projection_not_implemented` — the two are distinguishable side by side.
3. Both entries publish their real applicability: the rule's tuple, and `[]` for no rule at all.
4. An enabled entry publishes its applicability too.
5. The disabled-by-auth row publishes the rule's reviewed schema.
6. The serialized `gateway` block shape, exact-equality, for a disabled-by-auth row.
7. Through the real route, both credentials: Anthropic `provider_params.top_k` reads enabled with
   `["api_key"]` on an api-key profile and disabled-for-auth with `["api_key"]` on an OAuth profile.
8. Evidence-only preserved: the newly visible rule does NOT become dispatchable under the mode that
   does not cover it, and does not enter the `/v1/models` summary.

## Acceptance

- No rule is dropped from the detailed contract for not covering the read's auth mode.
- Wrong-auth and unimplemented are separately readable, with applicability published for both.
- Full aigateway gate green; no prior test weakened beyond the three approved lines.

## Outcome

- **Actual files:**
  - `src/aigateway/core/chat_parameters.py` — `_DISABLED_AUTH_MODE_REASON`;
    `compose_contract_entries` keys off ALL rules and separates the rule that EXISTS
    (`rule`) from the rule that AUTHORIZES this read (`covering`), so status, projection,
    cache behaviour and reason each derive from one expression; `to_detail_dict` publishes
    `gateway.applicable_auth_modes`.
  - `tests/unit/core/test_auth_applicability_contract.py` — NEW, 16 tests: rule survival
    (with and without an observation), reason separation, published applicability (including
    that it describes the rule and not the reading mode), schema precedence, an
    exact-equality lock on the disabled-for-auth `gateway` block, two evidence-only guards,
    and three tests through the real `/v1/model-parameters` route on both credentials.
  - Three prior test files modified under explicit owner approval (see above).
- **Commits:** `f77ec7d1` — `fix(aigateway): publish auth applicability in the detailed
  contract` (`Refs: OME-649`).
- **Gates:** `run_gates.py aigateway --skip-append-only` → ALL GATES GREEN (ruff check, ruff
  format --check, pyright, `check_no_enterprise.py`, pytest with `--cov-fail-under=80`). Full
  suite **2056 passed / 40 skipped** (from 2040 — net +16). Enabled-OpenRouter conformance →
  11 passed. The append-only check was then run without the skip and flags exactly the three
  approved files, nothing else.
- **Deviations:**
  - **Production code was written BEFORE the tests, deliberately and then discarded.** The
    owner's standing gate requires asking before changing a prior test, and asking well
    requires the exact list. The change was implemented, the full suite run to measure the
    blast radius (exactly three failures), then reverted to `HEAD`; the test module was
    written and confirmed RED against unmodified production code (13 failing on their own
    assertions, 3 passing because they are before-and-after invariant guards); only then was
    the change re-applied. The RED run is the one that counts, and it was genuine.
  - **The measured blast radius was far smaller than the reason-string survey suggested.**
    14 `projection_not_implemented` assertions exist across 9 test files; only one of them
    sits on an auth-filtered rule. Counting occurrences would have over-stated the ask by an
    order of magnitude — running the suite settled it.
  - **A publish/hash asymmetry closed as a side effect.** `_rules_revision` folds EVERY
    rule's `applicable_auth_modes` into `contract_id` regardless of the read's auth mode, so
    the identity already moved on a field the document never showed. Not named by the review.
  - **One undemanded published-value change, approved before shipping.** On a disabled-by-auth
    row the rule's reviewed schema now wins, so Anthropic `provider_params.top_k` under OAuth
    publishes `{"type":"integer","minimum":1}` where it published `null`. No prior test
    asserted it; the alternative was a row claiming a reviewed projection exists while
    withholding what it validates.
  - **Zero new rows in any shipping contract.** Exactly one production rule is auth-restricted
    and it already carries a static observation, so the "surviving rule with no observation"
    branch is exercised only by tests today — which is why it has one.
  - **`contract_id` does not move for this change.** The digest versions the composer's
    INPUTS, and none changed; a gateway build that alters serialization therefore serves a
    different document under an unchanged id. That is the same property OME-647 shipped with
    when `provider.deprecated` was added, and closing it would mean bumping the locked v1
    `SCHEMA_VERSION`, which is out of scope. Recorded, not silently accepted.
  - **`chat_parameters.py` is now 643 lines** against the ≤450 guideline (OME-602 already
    exists for this module, filed at 498). Left for the FR5 split pass, which is required to
    be a separate, behaviour-preserving commit.
  - **The two public surfaces still name this condition differently.** Dispatch rejects a
    known-but-wrong-mode path with `wrong_auth_mode`; the contract now says
    `projection_not_available_for_auth_mode`. The divergence predates this unit — dispatch
    already says `unknown` where the contract says `projection_not_implemented` — and the
    contract-side string was chosen for consistency within its own published vocabulary.
    Aligning the two would change the dispatch 400 body, which is outside this scope.
    Carried to the readiness review rather than acted on.
  - **No schema/model change**, so stack rule S1 does not apply.
