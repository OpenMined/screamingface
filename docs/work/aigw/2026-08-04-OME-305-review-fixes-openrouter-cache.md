---
ticket: OME-305
stack: aigateway
status: done
started: 2026-08-04
finished: 2026-08-04
---

> The OpenRouter review fixes were committed as `9e40657b`. This ledger also records the
> final-review remediation authorized by the owner and included in this continuation commit.

# OME-305 — global review fixes: OpenRouter cache participation and the `top_k` leaf

Continues `docs/work/aigw/2026-08-03-OME-305-global-request-cache-fingerprint.md`, which was
closed while the branch was still unmerged. A global review of that branch's commit
(`f7bc1674`) found two confirmed Medium defects in code that has not shipped, so fixing them
is part of delivering OME-305 rather than new work.

Review under repair: `.agent-team-AIGW/caching-model-and-fingerprinting/global-review-2026-08-04.md`
Branch: `OME-305-global-request-cache-fingerprint` @ `9e40657b`

## Intent

Two provider-local defects let OpenRouter's declared cache contract diverge from its behaviour.
MEDIUM-1: an operator can disable the OpenRouter provider and the gateway keeps replaying that
provider's previously filled global cache rows indefinitely — the projection cannot see
`settings.enabled` because it delegates to a pure module function that receives the body alone.
Independently reproduced: an enabled and a disabled instance of the plugin produce a
**byte-identical** `key_hash`, so the disabled instance reads exactly the row space the enabled
one wrote. MEDIUM-2: `provider_params.top_k` is published as `cache_behavior="keyed"` but every
such request bypasses with `unprojected_parameter`, because the projection never emits the
`extra_body` root its own rule targets. Fail-safe, but the published contract is not honoured
and benchmark traffic using the one supported output-affecting parameter never reuses a response.

## Planned changes

- `src/aigateway/plugins/openrouter_provider/plugin.py` — `global_cache_projection` returns
  `CacheBypass(PROJECTION_BYPASS_REASON)` when `settings.enabled` is false, with a provider-local
  anchor: the operator gate decides PARTICIPATION, never KEY MATERIAL.
- `src/aigateway/plugins/openrouter_provider/parameters.py` — publish `EXTRA_BODY_OBJECT` /
  `TOP_K_LEAF` and derive `provider_target` from them, so the rule's target root and the
  projection's root cannot drift (drift would silently bypass every `top_k` request).
- `src/aigateway/plugins/openrouter_provider/global_cache.py` — emit
  `prepared["extra_body"]["top_k"]` when, and only when, the wrapper carries `top_k`.
- `tests/unit/openrouter/test_openrouter_global_cache_projection.py` — projection-level cases.
- `tests/unit/openrouter/test_openrouter_routing_policy_routes.py` — route-level cases.

No migration, no schema change, no adapter-revision bump: disabled instances stop participating
while enabled ones keep identical key material, and `extra_body` is emitted only for requests
that have never produced a v2 row.

## Test plan

MEDIUM-1 (RED first):
- A disabled plugin's `global_cache_projection` returns `CacheBypass`, reason `provider_projection`.
- Route regression: cache enabled, provider enabled, fill a row; then disable the provider and
  repeat the identical request — the row is not served as a hit and the disabled-provider path
  determines the response.
- Invariant protected: a provider kill switch gates the cache path, not only the dispatch path.

MEDIUM-2 (RED first):
- The exact projected leaf: `prepared["extra_body"] == {"top_k": 3}`.
- A bare request still projects no `extra_body` at all (boundary — the root must not appear
  unconditionally, or a future leaf omission would silently un-key `top_k`).
- Repeat-hit: two identical `top_k` requests → miss then hit, one dispatch, one row.
- Different-value-miss: `top_k=3` and `top_k=7` never share an entry.
- Dispatch/projection agreement: the projected leaf equals what the real dispatch path places at
  `extra_body.top_k`.
- Invariant protected: a value declared `keyed` participates in the key by the same spelling the
  provider will actually send.

## Acceptance

- `provider_params.top_k` no longer bypasses with `unprojected_parameter`; identical requests hit
  and different values miss.
- A disabled OpenRouter never serves a global cache hit.
- Every prior test remains unmodified and green; the aigateway gate card is green.

## Test supersession record (required for `--skip-append-only`)

`run_gates.py` runs `append_only_check` before every gate and aborts on any `M`/`D`/`R` under the
stack's test globs (`.claude/scripts/run_gates.py:68-101`). The check is **file-level**: git reports
appending to an existing test file as `M`, so it cannot distinguish "added a test" from "changed a
test". All three files below are flagged; only ONE carries a real prior-line change. Per the convention
established in the 2026-08-03 ledger, the sanctioned `--skip-append-only` flag is used only with this
record present, one row per modified file, naming exactly what changed.

**Case-level proof that nothing was lost, obtained independently of the diff:** HEAD's versions of the
two flagged OpenRouter files were collected side by side with the current versions and their case IDs
compared — **73 baseline cases → 83 current, with zero baseline case IDs absent from the current
set**. Whole suite: 2988 → **3002** passed, 45 skipped, so +14 cases and none lost.

| File | Prior lines changed | Class | Invariant that survives |
|---|---|---|---|
| `tests/unit/openrouter/test_openrouter_routing_policy_routes.py` | **none** — appended only. Flagged solely because appending makes git report `M`. | pure append | all 22 prior cases unchanged and green |
| `tests/unit/test_global_cache_plan.py` | **none** — appended only. | pure append | all 37 prior cases unchanged and green |
| `tests/unit/openrouter/test_openrouter_global_cache_projection.py` | **1 line**, and it is an EXPANSION: `from aigateway.core.parameter_projection import WRAPPER_KEY` now also imports `classify_and_project_chat_parameters`. No name removed. | pure append + import expansion | all 51 prior cases keep their assertions **verbatim** |

So `git diff HEAD -- tests/` removes exactly **one** line in total across all three files, and that line
gains a name rather than losing one. Zero `def test_`, zero parametrize rows, zero assertions, zero
arrangement helpers changed. Nothing is superseded and no invariant is retired, so no supersession row
is owed — this is the file-level check's known blind spot (an append reads as `M`), not the
"STOP and ask" case it warns about.

**An earlier draft of this change DID require modifying a prior test, and that is why it was
abandoned.** The first implementation put the `enabled` gate inside
`OpenRouterProviderPlugin.global_cache_projection`. Because `enabled` ships FALSE, that broke 30 prior
projection cases on arrangement, and it also failed
`tests/unit/test_global_cache_projection_purity.py::test_no_projection_reads_operator_configuration` —
a deliberate REVIEW TRIPWIRE whose own AIDEV-NOTE says to bring the case to review rather than edit
the sweep. Two governing authorities settled it without a judgment call: the owner's ruling that
settings may gate PARTICIPATION but never shape KEY MATERIAL, and the port contract that
`global_cache_projection` is pure and receives the request body ALONE. Both hold only if the gate
lives outside the projection. Moving it to the plan layer satisfied the ruling more precisely, left
the tripwire untouched and green, and removed the need for the arrangement change entirely.

## Outcome (fill at the end — required before COMMIT)

- **Actual files (5 production, 3 test) — one more production file and one more test file than planned:**
  - `src/aigateway/core/plugin_base/_provider.py` — NEW port method `participates_in_global_cache()`,
    default `True`, documenting the PARTICIPATION vs KEY-MATERIAL split. **Not planned** (see D1).
  - `src/aigateway/core/request_cache/global_plan.py` — consults it; a hook that raises fails closed
    to a bypass. **Not planned** (see D1).
  - `src/aigateway/plugins/openrouter_provider/plugin.py` — implements the port as
    `self.settings.enabled`; the projection stays pure, with a note recording why the gate is not
    inside it.
  - `src/aigateway/plugins/openrouter_provider/parameters.py` — publishes `EXTRA_BODY_OBJECT` /
    `TOP_K_LEAF`; the rule now derives both its wrapper path and its `provider_target` from them.
  - `src/aigateway/plugins/openrouter_provider/global_cache.py` — emits
    `prepared["extra_body"]["top_k"]` when, and only when, the wrapper carries the leaf.
  - `tests/unit/openrouter/test_openrouter_global_cache_projection.py` — projection-level cases (as
    planned).
  - `tests/unit/openrouter/test_openrouter_routing_policy_routes.py` — route-level cases (as planned).
  - `tests/unit/test_global_cache_plan.py` — plan-level cases. **Not planned**; owed by D1, because the
    gate now lives in `build_global_cache_plan` and its fail-closed path is only reachable there.
- **Commits:** `9e40657b` — `fix(aigateway): enforce OpenRouter cache contract` (`Refs: OME-305`).
- **Gates:** `uv run .claude/scripts/run_gates.py aigateway --skip-append-only` → **ALL GATES GREEN**
  (ruff check · ruff format --check · pyright · check_no_enterprise · pytest with coverage). Full
  suite **3002 passed, 45 skipped** against a **2988 passed, 45 skipped** baseline: +14 cases, none
  lost. Coverage **92.24%** against the 80% floor. `--skip-append-only` is justified by the
  supersession record above — the check is file-level and cannot see that every change is an append.
- **Deviations — two, both material:**
  - **D1 — the MEDIUM-1 gate moved layer, and this was forced, not chosen.** Planned: return
    `CacheBypass` from `OpenRouterProviderPlugin.global_cache_projection`. Actual: a new provider port
    method `participates_in_global_cache()`, consulted by `build_global_cache_plan`. The projection's
    port contract is that it is pure and receives the request body ALONE, and
    `tests/unit/test_global_cache_projection_purity.py::test_no_projection_reads_operator_configuration`
    enforces that with a poison-settings twin. The owner's ruling (settings may gate PARTICIPATION,
    never KEY MATERIAL) and that contract are simultaneously satisfiable only if the gate sits outside
    the projection. The cost is a new core port the plan did not budget for; the benefit is that the
    ruling is now structural rather than merely commented, and the projection's purity sweep stayed
    untouched and green. "Provider-local" still holds in the sense that matters: the decision is the
    provider's, taken in provider code, from provider settings.
  - **D2 — the bypass reason is `provider_projection`, not `disabled`.** Found by reading the real
    response header rather than trusting the plan-level constant.
    `chat_cache_stage._closed_gate_reason` re-maps a plan-level `disabled` to `cache_unavailable`
    whenever the cache's own switch is on, so the first attempt published "your cache store is
    unavailable" for a healthy store and a switched-off provider. A dedicated `provider_disabled`
    would be more precise than either value, but the reason vocabulary is a caller-visible contract
    that URL4 reads and `test_global_cache_reason_vocabulary._WIRE_CONTRACT` spells out as literals,
    so adding a value is an owner decision. Flagged for the owner, deliberately not taken; the
    argument is recorded as an AIDEV-NOTE at the decision site.
- **Verification worth recording — both fixes were proven by neutralizing them, not only by watching
  new tests pass.** With the participation check removed from `build_global_cache_plan`, the route
  regression fails with `x-aigw-cache: hit` and a real key (`22bc51f35b2c`), returning a 200 body from
  a provider that is switched off. That also upgraded MEDIUM-1 from defence-in-depth to
  route-reachable: this stage runs ahead of model resolution and credential reads, so the D2-era
  404/400 refusals never see the request. With the `extra_body` emission removed, the `top_k` cases
  fail on `unprojected_parameter` as the review described.
- **Findings surfaced during the prior unit:**
  - The `provider_disabled` reason above — a cross-service vocabulary addition.
  - The initially stale `top_k` projection-test comment was corrected before this continuation:
    `top_k` is still not a routing control, but its `extra_body` projection contributes to the key.
  - `run_gates.py`'s `append_only_check` is file-level, so a pure append reads as `M`. Every cycle
    that adds a case to an existing test file must pass `--skip-append-only`, which also disables the
    check for genuine rewrites in the same run.
- **Issue scope:** the owner kept these fixes under OME-305; no separate Linear issue was required.

## Final-review continuation

Review under repair: `.agent-team-AIGW/caching-model-and-fingerprinting/final-review-2026-08-04.md`.

### Owner ruling 59

Anthropic `provider_params.top_k` remains available for `api_key` only. Because the global key is
built before auth resolution and cannot depend on caller identity, this mode-restricted parameter
declares `cache_behavior="bypass"`. It must not be widened to OAuth without provider evidence. This
clarifies rulings 7 and 52 rather than changing the identity-free cache architecture.

### Remediation scope

- Canonicalization includes UTF-8 hashing in its fail-to-bypass boundary.
- A hit already decoded and validated survives any ordinary hit-metadata update failure.
- Every reachable Anthropic/OpenRouter keyed path has an explicit value-sensitive proof, with a
  registry guard preventing future non-bypass mode-restricted declarations.
- Cache-on invalid-parameter validation remains HTTP 400 and cannot replay a hit.
- Caller-controlled model newlines are escaped at every cache-stage log site.
- Confirmed stale comments are corrected without changing their deferred behavior.

### TDD evidence

- RED: a lone surrogate escaped from the real route as `UnicodeEncodeError`; a post-validation
  `RuntimeError` from hit metadata discarded the response; Anthropic `top_k` violated the new
  all-modes conformance guard and still published `keyed`; cache read logging retained a literal
  newline in the formatted record.
- Coverage-only additions for the already-correct A3 and B2 behavior were green on first write, as
  expected: they close missing tripwires rather than change runtime behavior.
- Focused GREEN after the minimal implementation: `175 passed` across the store, registry,
  Anthropic/OpenRouter key, and global-cache route suites.

### Final-review test-preservation record

The gate runner reports every edited existing test file as non-append-only. No prior behavioral
assertion was removed, weakened, skipped or renamed in this continuation.

| File | Existing content changed | Preservation evidence |
|---|---|---|
| `tests/unit/test_global_cache_store.py` | stale expired-row docstring corrected; one new metadata case appended | all prior store cases remain and pass |
| `tests/unit/test_global_cache_registry_conformance.py` | measured population `75→72` and rationale updated under ruling 59; one guard appended | the threshold follows the approved contract change rather than masking an unexplained drop |
| `tests/unit/anthropic/test_anthropic_global_cache_projection.py` | imports/helper plus new keyed-coverage and `top_k` cases | no prior test body changed |
| `tests/unit/openrouter/test_openrouter_global_cache_projection.py` | new keyed-coverage table and exact-set guard | no prior test body changed |
| `tests/unit/test_chat_global_cache_route.py` | imports plus three new route regressions | no prior test body changed |
| `tests/unit/test_global_cache_plan.py` | stale future-tense fixture docstring corrected | fixture behavior and assertions unchanged |
| `tests/integration/test_global_cache_store_postgres.py` | inaccurate docstring `steps 3–5` corrected to `steps 3–4` | test behavior and assertions unchanged |

The broadened related slice after these edits is `336 passed`. Running the required gate with
`--skip-append-only` is therefore explicit and bounded to this recorded diff; it is not evidence that
the preservation check itself passed.

### Current outcome

- **Actual files:**
  - Production: `global_keys.py`, `store.py`, `standard_parameters.py`, Anthropic
    `parameters.py`/`plugin.py`, and route `chat.py`/`chat_cache_stage.py`.
  - Tests: global store/registry/plan/route suites, Anthropic/OpenRouter global-cache suites, and
    the PostgreSQL migration-test docstring.
  - Governing artifacts: implementation plan status through ruling 59, the original OME-305 ledger
    with ruling 59, and this continuation ledger.
- **Commits:** this continuation commit; no push performed.
- **Gates:** focused related slice `336 passed`; the strengthened B2 replay regression passed after
  independent review; `uv run .claude/scripts/run_gates.py aigateway --skip-append-only` ended
  `ALL GATES GREEN`; PostgreSQL marker `12 passed, 3056 deselected`. One unrelated login timing test
  flaked once during the first complete gate (`14.4%` timing difference against a `10%` threshold),
  passed alone, and the complete gate then passed unchanged.
- **Independent review:** stage 1 found that the first B2 test used an empty cache and could not catch
  replay-before-validation. It was strengthened to fill a bare row first. Stage 2 then found no
  material runtime, persistence, contract or test findings; its falsification slice was `34 passed`
  with high confidence.
- **Deviations:** optional B4 participation sweep was not taken; Linear reconciliation remains a
  separate owner/external-state closure action. Five of six escaped model-log sites are source-pinned
  rather than each receiving a separate behavioral test; all six use the same `%r` mechanism.
