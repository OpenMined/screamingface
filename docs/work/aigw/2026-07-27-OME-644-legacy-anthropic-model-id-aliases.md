---
ticket: OME-644
stack: aigateway
status: withdrawn
started: 2026-07-27
finished: 2026-07-27
---

# OME-644 — Accept the five legacy bare Anthropic model IDs on chat dispatch

> **WITHDRAWN 2026-07-27. The premise of this unit was false and the work was undone.**
> The implementation was correct, bounded and gate-green, but it solved a problem that did
> not exist. Nothing from it remains in the branch. This ledger is kept as the record of a
> wrong call and why it was wrong; the sections below the line are the original text, left
> unedited so the reasoning that produced the error stays legible.

## Withdrawal

**What was claimed.** That publishing canonical provider-prefixed IDs from `/v1/models` broke a
working chat path — a consumer holding one of the five bare Anthropic IDs would have its next
`/v1/chat/completions` request fail outright — and that a bounded compatibility shim was therefore
needed to restore previously working behavior.

**Why that is false.** Two checks against the repository challenged the premise on 2026-07-27:

1. **No chat path regressed.** At the OME-479 baseline `c55c56cf` (2026-07-23), `routes/chat.py`
   lines 78-81 already read
   `provider = model.split("/", 1)[0] if "/" in model else None` /
   `if not provider: raise HTTPException(status_code=400, detail="model must be provider-prefixed")`.
   And `tests/unit/test_chat_split_characterization.py::test_chat_400_when_model_not_provider_prefixed`
   already posted bare `claude-sonnet-4-5` and asserted exactly that 400. Canonical IDs changed
   which ID the **catalog publishes**; they never changed which IDs **chat accepts**. A bare ID has
   never been dispatchable on this gateway, so no working request stopped working.

2. **The named consumer was gone, and was compatible regardless.** `aigw_claude_backend` used
   `anthropic/`-prefixed IDs from introduction; `630bd736` moved its dropdown suggestions to derive
   from `/v1/models`, with `_model_ids_from_payload` prefixing bare catalog rows and preserving
   already-prefixed ones, and its tests covered canonical discovery and canonical dispatch. It was
   then deleted by `9a9cf82d` (SF-348 re-foundation), and
   `git merge-base --is-ancestor 9a9cf82d c55c56cf` exits 0 — the removal **predates** the OME-479
   baseline. The consumer was not in the tree when this work landed.

The governing OME-479 plan locks canonical provider-prefixed IDs as the client request identity and
states no legacy-alias requirement, so the shim traced to no approved requirement.

**What was done about it.** The withdrawn change and its revert netted to a byte-identical tree and
were removed from branch history. No alias implementation shipped. The final tree contains no
`legacy_model_alias`, `LEGACY_BARE_MODEL_IDS` or `canonical_for_legacy` residue in `src/` or
`tests/`, and the full gate is green.

**The associated release-gate finding is withdrawn too.** The same baseline evidence proves it is
not a release gate and never was.

**How this got missed — the transferable lesson.** The refuting evidence was inside this unit's own
diff. The change had to edit `test_chat_400_when_model_not_provider_prefixed`, a test that predated
it and pinned bare `claude-sonnet-4-5` to a 400. That was recorded here as Deviation 1 and treated
as a fixture collision to route around, when it was proof the behavior being "restored" had never
existed. **A prior test that must be weakened or re-fixtured to accommodate a restoration is
evidence there was nothing to restore.** Two further signals pointed the same way and were also
mis-weighted: the consumer could not be found in any checkout (it had been deleted, not relocated),
and no Linear issue tracked the supposed coordination (there was nothing to coordinate). The
process failure was accepting a regression claim without dating it against the baseline — the check
that would have settled it in one command is `git show <baseline>:<path>`.

---

## Intent

OME-479 made every `/v1/models` id canonical and provider-prefixed. Exactly five ids changed
shape, all Anthropic (`claude-opus-4-8`, `claude-opus-4-7`, `claude-sonnet-4-6`,
`claude-sonnet-4-5`, `claude-haiku-4-5`); the other fifteen registered ids were already
canonical. Because `routes/chat.py` derives the provider from the first path segment, a
consumer that persisted one of the old bare ids now fails its next chat request outright with
`400 model must be provider-prefixed` — a hard break, not a stale label. The affected consumer
(the aigw-claude-backend model dropdown, SF-284) lives outside this repository and cannot be
verified or fixed here.

Owner scope decision, 2026-07-27: resolve this inside OME-479 with a narrowly bounded
compatibility shim rather than blocking the release. `/v1/chat/completions` accepts those five
exact bare ids and normalizes each to its canonical form **before** provider and profile
resolution, so every downstream stage — credential target, parameter rules, cross-field
validation, cache key, dispatch — sees only the canonical id and behaves identically. SF-284
verification (OME-642) then gates REMOVAL of the shim, not the release.

The design constraint that shapes the code: the alias declaration must stay provider-owned. Core
gets a neutral hook and a registry lookup; no Anthropic conditional and no generic
unprefixed-model fallback may enter core.

## Planned changes

- `src/aigateway/core/plugin_base.py` — new `legacy_model_aliases()` hook returning `()` by
  default; a provider declares BARE ids only, and core prefixes them with that plugin's own
  `custom_llm_provider`, so a plugin can only alias into its own namespace.
- `src/aigateway/core/registry.py` — fold each plugin's declared aliases into a
  `bare id → canonical id` map at `register()` time, raising on a cross-provider collision;
  expose `canonical_for_legacy_model_id()`.
- `src/aigateway/plugins/anthropic_provider/settings.py` — `LEGACY_BARE_MODEL_IDS`, frozen at
  the OME-479 cutover, with the removal condition recorded next to it.
- `src/aigateway/plugins/anthropic_provider/plugin.py` — override `legacy_model_aliases()`.
- `src/aigateway/routes/chat.py` — consult the registry map when the submitted model has no
  `/`; rewrite `model` and `body["model"]` to the canonical id before provider resolution;
  otherwise keep the existing 400 verbatim.
- `tests/unit/anthropic/test_legacy_model_id_aliases.py` — new.
- `tests/unit/core/test_provider_contract_conformance.py` — registry-wide guards (append only).

## Test plan

- For each of the five models: the legacy bare id and the canonical id produce the SAME
  provider, the same resolved profile/credential target, and a byte-identical upstream request
  body — captured at the final transform, not asserted on the route's inputs.
- `body["model"]` reaching the provider is the canonical form; the bare id never survives past
  normalization.
- Normalization happens before credential access and before parameter classification (ordering
  tripwires, matching the OME-640 pattern).
- Unrelated bare ids still return `400 model must be provider-prefixed`: `gpt-4o`,
  `claude-opus-9` (plausible-but-unregistered), `""`, and a bare id belonging to another
  provider's namespace.
- A canonical id with an unknown provider still returns `400 unknown provider: …` — the shim
  must not convert that into a different error.
- `/v1/models` contains no bare id; `/v1/model-parameters?model=claude-sonnet-4-5` is rejected;
  the alias appears in no discovery output.
- Registry: two plugins declaring the same alias raise at registration; a plugin's alias is
  always prefixed with its OWN provider key even if it declares a foreign-looking name.
- Conformance: only the Anthropic plugin declares aliases, and every declared alias names a
  model that plugin actually registers.

## Acceptance

- All five legacy ids dispatch exactly as their canonical equivalents.
- Every other unprefixed id still fails closed with `400`.
- `/v1/models`, `/v1/model-parameters` and discovery remain canonical-only.
- Core contains no provider name and no generic unprefixed fallback.
- Full AIGateway quality gate green.

## Outcome

> Superseded by the Withdrawal section above. The commit named here (`120f7bf8`) and its revert
> (`96c51fcd`) are both dropped from branch history; the acceptance criteria below were met, but
> the unit itself should never have been built.

- **Actual files:** as planned, with one addition and one subtraction.
  - `src/aigateway/core/plugin_base.py` — `legacy_model_aliases()`, default `()`.
  - `src/aigateway/core/registry.py` — alias map built at `register()`, plus
    `canonical_for_legacy_model_id()`.
  - `src/aigateway/plugins/anthropic_provider/settings.py` — `LEGACY_BARE_MODEL_IDS`.
  - `src/aigateway/plugins/anthropic_provider/plugin.py` — the override.
  - `src/aigateway/routes/chat.py` — normalization ahead of provider resolution.
  - `tests/unit/core/test_legacy_model_alias_registry.py` — new, 14 tests.
  - `tests/unit/anthropic/test_legacy_model_id_aliases.py` — new, 28 tests.
  - ADDED: `tests/unit/test_chat_split_characterization.py` — see Deviations.
  - NOT NEEDED: `tests/unit/core/test_provider_contract_conformance.py`. The two
    registry-wide guards (only Anthropic declares; every alias names a registered
    model) live in the new core test file with the rest of the alias mechanics
    rather than being split across two files.

- **Commits:** `120f7bf8` — feat(aigateway): accept the five legacy bare Anthropic model ids.
  Reverted by `96c51fcd`; both subsequently dropped from history (see Withdrawal).

- **Gates:** `run_gates.py aigateway --skip-append-only` → ALL GATES GREEN.
  ruff check ✓ · ruff format ✓ · pyright ✓ · check_no_enterprise ✓ ·
  pytest **2032 passed, 40 skipped, coverage 92.12%**.
  Three rounds: (1) `ruff format` reformatted `registry.py` and the new core test;
  (2) two prior tests failed — see Deviations; (3) pyright rejected a `getattr`
  read of the hook as `object`, replaced with an `isinstance` guard (no `cast`,
  no `# type: ignore`).

- **Deviations:**

  1. **A prior test changed.** `tests/unit/test_chat_split_characterization.py::
     test_chat_400_when_model_not_provider_prefixed` posted `claude-sonnet-4-5` and
     asserted `400 model must be provider-prefixed`. That id is one of the five the
     owner's 2026-07-27 scope decision explicitly moved to "accepted and
     normalized", so the test asserted the superseded contract. The
     characterization it exists for — *an unprefixed id is rejected* — is unchanged
     and its assertion is untouched; only the fixture value moved to `some-model`,
     an id no provider declares. Not a weakening: the same rejection is now
     additionally asserted for five other bare ids in the new test file, including
     `gpt-5.5`, which this gateway serves only as `codex/gpt-5.5`. An implementation note at
     the test records why the value moved and where the accepted ids are covered.

     > **This deviation was the refutation, misread.** The test predated the change
     > and pinned the true contract. See Withdrawal.

  2. **A real defect found by a prior test.** `tests/unit/test_main.py::
     test_create_app_mounts_provider_auth_router` registers a duck-typed plugin
     double that does not derive from `ProviderPluginBase`. Calling the new hook
     unconditionally in `register()` crashed it with `AttributeError` — a genuine
     robustness regression, since registration had always accepted anything shaped
     like a plugin. Fixed in the source, not the test: `_resolve_legacy_aliases`
     returns `{}` for a non-derived plugin, which is also what the base class would
     answer. That keeps the shim removable without touching the plugin contract.

  3. **`plugin_base.py` is now ~595 lines**, over the 450-line guideline it already
     exceeded before this unit (~575). Splitting the provider contract is a
     separate, wider change; recorded rather than done here.

     > Now back to ~575 after the withdrawal.

  4. **A shared cache entry is intentional.** The cache key is computed from the
     normalized body, so a legacy request and its canonical twin hash identically
     and share one entry. That is correct — they are the same request — and it
     falls out of normalizing before cache planning rather than being special-cased.

## Acceptance — verified

> Verified as written at the time, against a requirement that did not exist.

- All five legacy ids dispatch with `model == "anthropic/<id>"`, and the complete
  dispatch body (including the injected credential for the resolved profile) is
  identical to the canonical form's. Both auth modes covered.
- `gpt-4o`, `claude-opus-9`, `claude-sonnet-4-5-20250929`, `gpt-5.5` and `""` all
  still return `400 model must be provider-prefixed`; `nosuch/…` still returns
  `400 unknown provider: nosuch`.
- The rejection still precedes credential access — asserted by spying on
  `_credential_target_for_chat`, which records exactly one call for the accepted
  request and none for the refused one.
- Normalization precedes classification — asserted through the model-specific
  cross-field thinking constraint, which refuses legacy `claude-sonnet-4-5` with
  `incompatible_parameters` and accepts the identical pair on legacy
  `claude-opus-4-8`. A bare id reaching that seam would have matched neither.
- `/v1/models` publishes no unprefixed id and none of the five; every legacy id is
  refused by `/v1/model-parameters`, whose document reports the canonical id as its
  public identity (`upstream_id` is bare by design and is Anthropic's own name,
  not a gateway-accepted id).
- Registration rejects a duplicate alias and a non-bare declaration, and leaves the
  registry unchanged when it does.
- `grep -rn "provider-prefixed" src/` confirms only two rejection sites exist:
  the shimmed one in `chat.py` and the canonical-only one in `model_parameters.py`.
