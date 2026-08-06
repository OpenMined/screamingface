---
ticket: OME-305
stack: aigateway
status: completed
started: 2026-08-03
finished: 2026-08-03
---

# OME-305 — Global caching model and full-call fingerprinting

Plan of record: `.agent-team-AIGW/caching-model-and-fingerprinting/implementation_plan.md`
Requirements: `.agent-team-AIGW/caching-model-and-fingerprinting/initial_task_description.md`
Baseline: branch `OME-305-global-request-cache-fingerprint` off `main` @ `6aa45b5b62e2`
Absorbs: OME-702 (Canceled). Excludes: OME-303 accounting, URL4 propagation, Engine rollups.

## Intent

Turn the prompt-only, account/profile-scoped, opt-in AIGateway response cache into **one global
exact-request cache** shared by every hosted user, keyed by the complete effective output-affecting
model call plus a pure provider projection. First successful fill wins globally; a hit performs no
provider credential access and no provider dispatch. The cache must never become an AIGateway
availability dependency.

**Current owner contract.** Profile-default values are merged body-wins before lookup and participate
in the key; profile/account identity and credential state do not. Anthropic remains keyed with
credential-agnostic first-fill replay. For MVP validation, response JSON is stored plaintext in the
existing `response_ciphertext` column. Response encryption, key management, rotation and migration of
plaintext rows are deferred until the feature proves useful. Historical encryption/canary rulings
below remain an audit trail but are superseded for the v2 response-cache lane by owner ruling 58.

## Baseline facts (verified at `6aa45b5b62e2`)

| Fact | Site |
|---|---|
| v1 key is prompt-only (`model`/`messages`/`system`); anything else → bypass | `core/request_cache/keys.py:19-24,112-117` |
| Key is account/profile scoped | `core/request_cache/keys.py:124-135` |
| Cache is opt-in per call (`use-cache` must be `true`) | `routes/chat_dispatch.py:191-192` |
| Operator gate defaults **off** | `config.py:127-129` |
| Cache plan runs **after** profile/auth/defaults/classification/prepare | `routes/chat.py:153-270` |
| `get()` dereferences `expires_at` (NULL-hostile) | `core/request_cache/store.py:68` |
| `get()` deletes corrupt rows unconditionally | `core/request_cache/store.py:80-85` |
| `get()` hit metadata is read-modify-write, not atomic | `core/request_cache/store.py:87-89` |
| `set()` overwrites the winner after `IntegrityError` | `core/request_cache/store.py:120-126` |
| `expires_at` is NOT NULL | `core/request_cache/models/request_cache_entry.py:27` |
| Latest migration is `0008` | `src/aigateway/migrations/0008_widen_account_username.py` |
| Auth-mode-independent rule set already available via `auth_type=None` | `core/plugin_base/_contract.py:63-79` |
| `cache_behavior` is one unconditional value per request path | `core/parameter_projection.py:189-192` |

## Lane ownership — file-disjoint, no two agents write one file

**Lane A — `impl-fingerprint`** (U1, U2, U3, then U5 after Lane B publishes the port):
- `src/aigateway/core/request_cache/global_keys.py` (new), and any new sibling modules it needs
- `src/aigateway/core/plugin_base/_contract.py`, `_ports.py`, `_provider.py`
- `src/aigateway/core/parameter_projection.py` (additive only)
- `src/aigateway/core/chat_parameters/*` (registry conformance guard, additive)
- `src/aigateway/plugins/**` (per-provider `global_cache_projection`)
- `src/aigateway/core/request_cache/global_plan.py`, `src/aigateway/routes/chat_cache_stage.py` (new,
  decision 11)
- `src/aigateway/routes/chat.py`, `src/aigateway/routes/chat_dispatch.py` (U5)
- `tests/unit/core/test_provider_contract_conformance.py` (**Lane A only**, decision 10)
- `tests/unit/test_chat_request_cache.py`, `tests/unit/test_chat_cache_contract_composition.py`,
  `tests/unit/openrouter/test_openrouter_routing_policy*.py`, `tests/unit/test_caller_cache_policy.py`,
  `tests/unit/openrouter/test_openrouter_top_p_promotion.py` (rewrites under decision 8)
- tests under `tests/unit/` and `tests/unit/openrouter/` named `*global_cache*`
- **not** `src/aigateway/core/request_cache/keys.py` — read-only for both lanes (decision 9)

**Lane B — `impl-persistence`** (U4, U6):
- `src/aigateway/core/request_cache/store.py`
- `src/aigateway/core/request_cache/models/request_cache_entry.py`
- `src/aigateway/core/request_cache/__init__.py` and `models/__init__.py`
- `src/aigateway/core/request_cache/canary.py` / availability module (new)
- `src/aigateway/migrations/0009_global_request_cache.py` (new)
- `src/aigateway/config.py`, `src/aigateway/main.py` (lifespan preflight)
- `apps/aigateway/charts/**`, `apps/aigateway/DEPLOYMENT.md`, deployment docs
- tests under `tests/unit/` and `tests/integration/` named `*global_cache_store*`,
  `*cache_canary*`, `*migration_0009*`

Neither lane edits the other's files. Cross-lane needs go through the frozen contracts below or
through the lead.

## Frozen cross-lane contracts (decided before implementation; changes go through the lead)

**AMENDED 2026-08-03** after phase-1 review. `get_global` originally returned `dict | None`, which
cannot distinguish "no row" (→ `miss`, dispatch **and** store) from "read failed" (→ `bypass` /
`cache_unavailable`, **no** store). Acceptance 16 is unimplementable against the old shape, and the
predictable failure was reporting `miss` and then writing to a database that had just failed to read.
Fixed before any code exists.

```python
# Lane B implements; Lane A codes against these names only.

KEY_VERSION_V2 = "aigw-global-chat-cache-v2"   # Lane A owns this constant in global_keys.py
GLOBAL_SENTINEL = "global"                     # account_id and profile_name for every v2 row

class CacheUnavailable(RuntimeError):
    """The cache could not be consulted. NOT a miss. Exported from core.request_cache."""

@dataclass(frozen=True)
class GlobalRequestCacheWrite:
    key_hash: str
    key_version: str          # always KEY_VERSION_V2
    prompt_hash: str
    provider: str
    model: str
    response: dict[str, Any]
    response_size_bytes: int
    # NOTE: no expires_at field — v2 always persists NULL. No account/profile input.

class GlobalRequestCacheStore(Protocol):
    async def get_global(self, key_hash: str) -> dict[str, Any] | None: ...   # raises CacheUnavailable
    async def set_if_absent(
        self, entry: GlobalRequestCacheWrite
    ) -> Literal["stored", "race_lost", "not_stored"]: ...   # never raises
    def cache_available(self) -> bool: ...
```

**Transport resolved 2026-08-03.** The lead's amendment and Lane B's implementation independently fixed
the same defect with different transports — a result value (`GlobalCacheLookup(outcome=…)`) versus a
raised `CacheUnavailable`. **Exceptions win.** Three reasons: `CacheUnavailable(RuntimeError)` is caught
by the broad degraded-mode handler U6 requires anyway, so a forgotten branch degrades instead of
returning HTTP 500; exceptions are already this codebase's idiom for the same class of failure
(`SecretDecryptionError`); and Lane B's version is implemented with 19 passing tests. The safety the
result form had for free is restored as an explicit requirement: **a test must prove a raising store
yields 200 + `X-AIGW-Cache: bypass`, never a 500.**

`get_global` raises `CacheUnavailable` on a database read failure or malformed stored JSON; it returns
`None` for a genuine miss. `set_if_absent` never raises — `"not_stored"` already covers infrastructure
failure.

Binding rules on that protocol:

- `get_global` filters on `key_hash` **and** `key_version=KEY_VERSION_V2`. Without the version
  predicate acceptance 17 ("v1 rows unreachable by v2 lookup") holds only probabilistically; with it
  the guarantee is structural and free against the existing unique index.
- Any database or decoding failure inside `get_global` **raises
  `CacheUnavailable`** — it never returns `None`, which is reserved for a genuine miss. A closed
  availability gate raises too (ruling 27). The route catches it, emits `bypass` +
  `cache_unavailable`, and performs **no write**.
- `set_if_absent` is create-only: it never issues an `UPDATE` against an existing row, and it must
  **not** call `delete_expired()`. Baseline `set()` purges on every write (`store.py:118,127`);
  inheriting that would make each v2 write delete expired v1 rows, which §4.2 ("no automatic
  inactive-version cleanup") and acceptance 17 forbid.
- v1 `get()` and `set()` are retained **unchanged**. The corrupt-row policy change (canary-gated
  instead of unconditional delete) lands on `get_global` only — `test_request_cache_store.py::
  test_corrupt_ciphertext_returns_none_and_deletes` legitimately keeps pinning v1's behaviour.

```python
# Lane A owns this port on the provider contract; default returns CacheBypass.
def global_cache_projection(self, body: dict[str, Any]) -> dict[str, Any] | CacheBypass: ...
```

The v2 `CacheBypass` type lives in `core/plugin_base/_ports.py`, **not** in `global_keys.py`:
otherwise all seven plugins import the cache subsystem's internal module layout just to satisfy a
provider port. Free to place correctly now, a seven-file change later.

## Decisions taken by the lead (assumptions stated, not silently made)

1. **Pre-cache classification uses `chat_parameter_rules(model=..., auth_type=None)`** — the
   provider-owned, auth-mode-independent rule set that already exists. `cache_behavior` is one
   unconditional value per request path, so this is well-defined without profile/auth state. Any
   caller path with no `keyed`/`transport_only` rule in that set → bypass.
2. **Accepted consequence (approved 2026-08-03):** a hit is served without the auth-specific
   parameter validation that a miss would run, so a request whose parameter is not enabled for the
   caller's auth mode can receive a 200 hit where a miss would 400. Provider auth mode is dispatch
   machinery, not cache-hit authorization. Documented, not defended against.
3. **Operator gate stays an explicit env gate, default `False` in code.** Per-call default-on
   (absent `cache` control → global read+write) is the code change; the operator capability is
   turned on deliberately via hosted config (`AIGW_REQUEST_CACHE_ENABLED=true` in chart values) and
   documented. Flipping the Python default would silently re-point every existing test that omits
   the flag — a test-preservation hazard for zero product gain.
4. **Canary lives in `credential_blobs` via `ORMStore`** (reserved service/account, create-only,
   fixed expected plaintext). That path is already AES-256-GCM through `SecretStoreMixin`, so the
   canary needs no new schema and proves exactly the property required: this worker's key can
   decrypt what the first worker wrote.
5. **`X-AIGW-Cache-Key` is retained** (12-char hash prefix, no identity). The plan's header list
   adds three headers without forbidding the existing one; dropping it would break current callers.
6. **No commits by any agent.** Commits/pushes await explicit owner approval (CLAUDE.md Git
   boundary overrides the SDLC skill's COMMIT step).

### Owner decisions (2026-08-03, answered directly by the owner)

7. **Keyed breadth = full.** Every reviewed output-affecting parameter across all six providers gets
   an explicit disposition, and the sampling/output-shaping ones become `keyed` — not just the five
   OpenRouter OME-704 controls. Requirements §2 names `temperature`, `top_p`, `max_tokens`,
   `reasoning_effort` and `response_format` as the exact parameters whose bypass drives the hit rate
   to ~0; the narrow reading leaves the ticket's stated purpose undelivered. `tools`/`tool_choice`
   stay `bypass` per plan §1.3. Every keyed rule must be covered by the registry-driven
   key-difference sweep (plan §10 stop condition), so future providers inherit the guarantee.
8. **Prior tests may be rewritten in place, invariants preserved.** Renaming is required where the
   test name states the reversed behaviour; deleting, skipping or weakening an assertion is not
   authorised. Every rewrite needs a row in the supersession record below, and phase-2 review
   verifies each one against the pre-change assertion.

### Lead decisions taken after phase-1 review (2026-08-03)

9. **v1 is retained byte-identical as storage compatibility.** `core/request_cache/keys.py` is not
   edited by either lane; the v2 control grammar and key builder live in `global_keys.py`, and
   `routes/chat.py` simply stops *calling* `parse_cache_controls`. Consequence: all 15 cases in
   `tests/unit/test_request_cache_keys.py` stay **green** and become the v1/v2-separation evidence
   for acceptance 17 — they are **not** in the supersession set. This is the correction to the
   fidelity review's inventory, which assumed v1 was modified in place.
10. **The conformance guard is repointed, never relaxed.**
    `tests/unit/core/test_provider_contract_conformance.py:356-381` enforces a real OME-479 property
    — a rule must not publish a promise the pipeline cannot deliver. The v1 predicate
    (`request_path in PROMPT_KEY_FIELDS`) is what makes `keyed` unreachable for every provider. Fix:
    export `GLOBAL_KEYABLE_REQUEST_PATHS` derived from the v2 key builder itself and repoint the
    assertion at it. The property survives; only its source of truth moves. **That file is assigned
    to Lane A** — it was previously in neither lane's list and is the likeliest two-agent conflict.
11. **The pre-cache stage is a pure core planner, not inline route code.** New
    `core/request_cache/global_plan.py::build_global_cache_plan(*, body, plugin, controls,
    cache_enabled)` — synchronous, pure, no `Request`/`app.state` — plus a thin
    `routes/chat_cache_stage.py` for the async store + header half. The argument is the test pyramid,
    not file length: a v2 hit is *defined* as needing no credential, yet every existing route-level
    cache test arranges an OAuth connection plus a credential blob just to reach the cache decision.
    Inline, acceptance 1–8 (the identity-invariance and projection-purity core of the ticket) could
    only be tested through `TestClient` with scaffolding the feature does not need.
12. **Reconstruction failure is a projection-time bypass.** Moving the lookup ahead of
    `prepare_chat_body` would otherwise let a request that today 503s on an OpenRouter
    routing-reconstruction mismatch be served a 200 hit — beyond what decision 2 approved, since a
    reconstruction mismatch is provider integrity, not auth-mode machinery. `build_provider_policy`
    (`plugins/openrouter_provider/routing_policy.py:227-259`) is pure, total, allocates a fresh dict
    per call and raises on any unrecognised key or shape, so the OpenRouter projection **calls it**
    and returns `CacheBypass` when it raises. A body whose policy cannot be reconstructed therefore
    performs no read and no write and reaches its existing 503 unchanged. This also gets the plan's
    price-equivalence and `zdr` pins for free instead of re-deriving them.
13. **`plugin.strip_provider_dispatch_controls` moves ahead of the pre-cache stage** (from
    `chat.py:166`). Omitting this move makes OpenRouter callers bypass on unknown fields, exactly
    reproducing the ~0% hit rate OME-305 exists to fix — U3 cannot pass without it.
14. **Port purity is enforced structurally, not by prose.** Assert
    `list(inspect.signature(type(plugin).global_cache_projection).parameters) == ["self", "body"]`
    and `not iscoroutinefunction(...)` for every registered plugin, plus an I/O-poison sweep (socket,
    `get_active_secret_store`, and Tortoise all raising) and a repeat-call determinism check. A port
    that cannot name identity cannot receive it — ~5 lines converts five of the seven prose
    invariants into structural facts.
15. **Decision 1 gets a conformance test.** Nothing currently asserts that a request path's
    `cache_behavior`, target and schema are identical between the `auth_type=None` view and each
    per-mode view, or that per-mode paths are a subset of the `None` view. If that premise breaks,
    the key describes a disposition the dispatch does not share — an invisible wrong hit. One sweep
    makes decision 1 true rather than merely reasonable.

### Rulings after the four phase-1 reviews (2026-08-03)

16. **Owner decision — Anthropic stays keyed in v2.** (Supersedes a first ruling of unconditional
    bypass; reversed by the owner the same day, and the reversal is the sharper reading.)
    `chat_handler.py:18-22` branches on `api_key.startswith("sk-ant-oat")`, and the OAuth path prepends
    a billing-attribution system block and hoists every `role=system` message into the top-level
    `system` array (`:39-67`). **Credential-dependent Anthropic prompt preparation is accepted
    first-fill behaviour under the global cache contract** — the same class of accepted consequence as
    decision 2, and consistent with §2.3.

    SF-244 audit finding F02 is **not** weakened, because F02 governs what the gateway *sends*: a raw
    API-key **miss** must never carry the Claude-Code billing block, and a **hit performs no outbound
    Anthropic request at all**, so F02 is simply not engaged on the hit path.

    Required, and both are mandatory rather than nice-to-have:
    - **Regression-test the F02 dispatch invariant directly** — an API-key miss dispatches without the
      billing block.
    - **Regression-test both cross-mode fill directions**: OAuth fills → API-key caller hits, and
      API-key fills → OAuth caller hits. Both must be tests, not prose.
    - **Document the accepted behaviour** in `DEPLOYMENT.md` alongside the other accepted trade-offs:
      the first caller's credential type determines the prompt text under which the globally replayed
      response was generated.
17. **v2 never deletes a row on decrypt failure.** Reverses the plan's "revalidate the canary, then
    delete only that row". The canary proves the *canary writer's* key, not *this row's* key —
    `request_cache_entries` has no `ciphertext_version`/key-id column, and a wrong key raises
    `InvalidTag` → `SecretDecryptionError`, indistinguishable from corruption. The trigger is the
    gateway's own advice: `credential_blob/store.py:188-200` instructs the operator to delete an
    undecryptable blob, so key rotation → correct degrade → operator complies → next worker mints a
    fresh canary, validates it, and then erases the entire old-key global cache one request at a time.
    Refuse to serve, emit a bounded metric, leave the row. An undecryptable row is already inert.
18. **The v2 read fails closed.** `LocalSecretStore.decrypt` returns non-matching input **unchanged**
    as legacy plaintext (`secrets/local.py:58-72`), so `json.loads` succeeds and an injected plaintext
    row is served to every user of that key. The credential path guards this with
    `_validate_ciphertext_version`; the cache path has neither the check nor a column to key it on.
    Require the `v1:` prefix before decrypt; a non-match is `CacheUnavailable`, never a value.
19. **`get_global` filters on `key_version` in addition to the `"global"` sentinels.** Sentinels alone
    leave v1-unreachability resting on SHA-256 disjointness. `expires_at IS NULL` must **not** be used
    as the v2 discriminator — it breaks when the deferred TTL lands.
20. **Two canary false-pass routes are closed.** A NULL-`ciphertext_version` row exploits
    `_validate_ciphertext_version`'s early return (`credential_blob/store.py:175-186`) plus the
    legacy-plaintext passthrough to validate under **any** key — and `credential_blob/model.py:24-28`
    already documents this hazard for exactly this kind of component ("*Future rotation tooling must
    treat NULL as pre-encryption/unknown*"); the canary **is** that tooling. Second: memoising the
    preflight turns "revalidate before delete" into a no-op. Require non-NULL
    `ciphertext_version == store.version` **and** the `v1:` prefix, and make revalidation a real
    read+decrypt.
21. **Master-key-in-database means degraded mode, not a startup refusal.** With `AIGATEWAY_SECRET_KEY`
    unset, `master_key.py:29-64` auto-generates the AES-256 key and persists it base64-unencrypted in
    the database it protects; the canary cannot detect this because every worker converges on the same
    row and validates. Since v2 stores the global corpus of every user's responses indefinitely, that
    combination must not cache: `request_cache_enabled` **and** `secret_provider == "local"` **and** no
    env-supplied key → `cache_available()` False, logged once. A refusal would violate the ticket's own
    invariant that cache problems never fail startup.
22. **`prompt_hash` for v2 rows is the v2 `key_hash`.** It has zero read path in v2 (one write at
    `chat_dispatch.py:259`; ~7.4 MB index, no readers), and an unsalted SHA-256 of the prompt
    projection is a confirmation oracle over the public benchmark prompt set for anyone with database
    read access but no key. The full-call digest removes the prompt-only oracle at zero cost.
23. **`test_runtime_catalog_conformance.py` is Lane A's too.** A *second* guard enforces the identical
    `PROMPT_KEY_FIELDS` property at `:8,50`, and it covers runtime-only catalogs — which is where
    OpenRouter lives, so U3 could not go green without it. Found independently by Lane A and by the
    fidelity review; missing from decision 10.
24. **Purity enforcement: the *synchronous* signature is the load-bearing barrier.** Signature checks
    are weak because `self` reaches `settings` and the credential factories; every credential read in
    this codebase is async, so keeping `global_cache_projection` synchronous is what actually prevents
    credential access. The `not iscoroutinefunction` assertion is primary; the parameter-list
    assertion is secondary. Refines decision 14.
25. **§5.4 must not swallow `build_secret_store` failure.** That would leave `_active = None` and 500
    every credentialed request while `/healthz` stays green — strictly worse than the crash it
    replaces.
26. **`0009` is a one-way door once v2 traffic exists** (the down path `SET NOT NULL` fails as soon as
    one v2 NULL row exists). State it in the migration docstring and `DEPLOYMENT.md`.

### Rulings after the phase-2 architecture pass (2026-08-03)

27. **"Could not consult the cache" has exactly one representation.** A closed availability gate must
    `raise CacheUnavailable` like a read failure does, not `return None` — `None` is the module's own
    documented *miss* signal, so a degraded worker would report `miss` + `not_stored` where plan §6
    requires `bypass`, and would attempt a write. `cache_available()` stays as the route's cheap
    pre-check.
28. **Publish `STRUCTURALLY_EXCLUDED_FIELDS` once in `global_eligibility.py`.** The registry guard
    currently re-derives the same four-set union that `_classify` consults, so a *fifth* exclusion set
    would be honoured by `_classify` and missed by the guard — the same silent narrowing the
    hand-maintained-list risk described, via a duplicated expression instead of a duplicated list.
    `_classify` does one membership test; the guard imports only that name.
29. **The purity sweep needs three additions**: interleaved determinism (A, B, A again) plus
    fresh-instance equality, because back-to-back calls in one process cannot catch a cached client or
    an import-time memo; a poisoned **clock**, `random` and `open` — the clock is highest yield, since a
    timestamp inside `prepared` fails silently as a 0% hit rate rather than as a wrong answer; and an
    explicit acknowledgement that the signature check does not close the `self` door (decision 24 is
    what does).
30. **One published enumeration for `X-AIGW-Cache-Reason`.** `global_controls.py:43-45` adds three
    bypass reasons outside the vocabulary `cache_ports.py:40-43` calls closed. The header's value set
    must be nameable from one place.
31. **`plugin_base/__init__.py` re-exports `CacheBypass` and `GlobalCacheProjection`.** Otherwise U3's
    plugins reach past the port package into private modules, against `_ports.py:8-9`.
32. **One comment-only edit to `keys.py` is permitted.** Its public `PROMPT_KEY_FIELDS` docstring
    (`:20-24`) claims the set is "locked by the registry conformance sweep rather than left to
    per-provider review" — false once the sweep is generalized. A module retained as storage
    compatibility must not carry a false public contract comment. No behavioural change; no test
    touched.

Two v1-keys consumers confirmed safe and left alone:
`tests/unit/openrouter/test_openrouter_dispatch_projection.py:26` and
`tests/unit/huggingface/test_huggingface_dispatch_projection.py:25` import v1 `CacheBypass`,
`CacheKeyResult` and `build_cache_key`, which all survive under decision 9.

Confirmed correct and not to be re-raised: narrowing v1 `get`'s `except Exception` is safe
(`SecretDecryptionError` subclasses `SecretStoreError`, `secrets/mixin.py:10`), and `set_if_absent`'s
SAVEPOINT claim holds on the pinned `tortoise-orm==1.1.7` — both backends return
`NestedTransactionContext` (`asyncpg/client.py:181`, `sqlite/client.py:228`).

### Rulings after the phase-3 premise check (2026-08-03)

33. **A rule that is not applicable in *every* auth mode the provider offers → bypass.** `_accept`
    (`global_eligibility.py:162-177`) checks existence, `cache_behavior` and schema but never
    `applicable_auth_modes`, and Anthropic ships an api-key-only rule (`provider_params.top_k`,
    `parameters.py:14-19`). Keyed, that lets an OAuth caller be refused on a miss and then served a 200
    hit from an entry an api-key caller filled, for a parameter the OAuth caller may not send. This is
    **not** covered by decision 2, which accepts skipping auth-specific *validation* ("your value is
    invalid"); this is *availability* ("this parameter is not offered in your auth mode"), a different
    kind. The containment is auth-mode-independent and therefore computable in the pure stage: bypass
    when the rule is not applicable across all of the provider's modes. **Correction:** this stays
    *latent*, not active — Anthropic's `parameters.py` declares no `cache_behavior` at all, so every
    rule takes the `"bypass"` default (`standard_parameters.py:81,104`) and a request carrying
    `provider_params.top_k` bypasses outright. Anthropic is the concrete future trigger, not a present
    one. The guard goes in now regardless: it is cheaper than the trap it prevents.
34. **Port invariant: a provider whose dispatch-time preparation is gated on the credential or the
    resolved auth mode must return `CacheBypass` unconditionally — unless the owner has explicitly
    accepted the cross-fill behaviour for that provider.** Anthropic is that accepted exception
    (decision 16). No sweep can detect a provider that ignores this: the transform is perfectly
    deterministic for a fixed dispatch body (which contains `api_key`), so the determinism test and the
    signature guard both pass. The rule must therefore be written on the port, not inferred.
35. **Correct two misleading comments.** `anthropic_provider/parameters.py:10-12` says forwarding is
    "auth-agnostic" — true of parameter forwarding, false if read as "the prepared body is
    auth-agnostic", which is exactly what an implementer skims for here. And record the *strong* form of
    decision 16's mechanism: the deciding input `api_key` is in `EXCLUDED_TRANSPORT_FIELDS`
    (`global_eligibility.py:65-67`) by design, so byte-identical caller bodies across credential types
    produce the identical key with different prompts. That framing is harder to erode later than "two
    auth modes differ".

36. **A keyed Anthropic must fold the billing-transform constants into `provider_adapter_revision`,
    unconditionally.** The transform's output depends on three module constants, none caller-visible:
    `_CLAUDE_CODE_VERSION = "2.1.142"`, `_FINGERPRINT_SALT`, `_FINGERPRINT_INDICES = (4, 7, 20)`
    (`chat_handler.py:12-14`, combined at `:86-101`). Bump the Claude Code version and OAuth traffic
    dispatches a different system block for a byte-identical caller body, while entries filled under
    the old constants keep being served. The projection cannot see this coming — `api_key` is stripped
    before the pre-cache stage, so it can neither know whether the block will be applied nor put the
    block itself in the key. The only mechanism that reaches it is `provider_adapter_revision`, which
    *is* inside the hashed material (`global_keys.py:204`), and it must be folded in **unconditionally**
    rather than gated on an auth mode the projection cannot observe. The projection stays perfectly
    deterministic either way, so **the conformance sweep cannot detect the omission** — which is why
    this is a stated obligation rather than an enforced one.

    The port docstring must say so. `_provider.py:174-205` currently says the revision is bumped
    "whenever that preparation changes without the caller's request changing", which reads as *the
    preparation the projection describes*. Anthropic is the first case where it must also cover
    dispatch-time preparation the projection **cannot** describe, and every future provider with a
    credential-gated transform inherits that obligation. Scoping note: **no plugin declares a
    `provider_adapter_revision` today** — the `projection_revision=` values in `plugins/*/parameters.py`
    are the per-rule mechanism, a different thing — so Anthropic sets the convention.

Detail that constrains decision 16's required tests: the billing header is **derived from the caller's
own first user text** via a SHA-256 fingerprint over characters at indices 4, 7 and 20
(`anthropic_provider/chat_handler.py:86-101`), and the transform lives at dispatch time rather than in
`prepare_chat_body` precisely because prepare runs before auth resolution (`plugin.py:155-158`, citing
SF-244 F02). So the prepended block varies per request; the cross-mode fill tests must not assume a
constant block.

### Rulings after the lead's own suite run (2026-08-03 18:10)

**The lead ran the suite. `uv run pytest tests/unit -m "not live" -q`, started 18:06:42, ended
18:10:34, exit=1: 18 failed, 2912 passed.** By file: `test_chat_request_cache.py` 9,
`test_openrouter_routing_policy_routes.py` 6, `test_chat_split_characterization.py` 1,
`test_chat_cache_contract_composition.py` 1, `test_openrouter_routing_policy_route_rejections.py` 1.
This is the first run in this unit taken by the lead rather than relayed. It supersedes 23/2879
(17:01:58Z) and 22/2880 (later) — failures falling and passes rising as the lanes landed. Both lanes
had reported their units green; the reports were true of their focused sets and false of the suite.

**37. Every failing prior test is triaged into exactly one of two classes, which get OPPOSITE
treatment.** *Class S — supersession:* the owner-approved requirement inverts the assertion (e.g. the
6 parametrized `test_a_routing_control_request_bypasses_the_cache_and_stores_nothing` cases, now
`assert 'miss' == 'bypass'`, since v2 keys routing controls). Rewrite in place, rename where the name
states the reversed behaviour, add `SUPERSEDED (OME-305, was …)` quoting the old assertion, **and add
a row**. *Class B — breakage:* the intent is still valid and the symbol moved (e.g. the decision-12
tripwire dying in `__enter__` on `aigateway.routes.chat.caller_cache_bypass_paths`, never reaching
`assert resp.status_code == 503`). Repair the reference, **do not touch the assertion, and add NO
row** — a row there would launder a broken test into an approved rewrite, the exact failure this
record exists to catch. The discriminating question: *would this assertion still be correct if the
symbol were reachable?* Decision 12 is therefore **unverified, not disproven**.

**38. `X-AIGW-Cache-Key`'s header comment is corrected, and the header is kept.** The 12-char prefix
is 48 bits, which identifies a request in any realistic corpus, so prefix comparison confirms request
equality exactly as well as full-digest comparison — truncation removes no confirmation capability and
the comment at `chat_cache_stage.py:62-66` must stop claiming it does. What truncation does buy:
bounded log volume, and not handing out a directly replayable lookup value. Request-equality
confirmation is inherent to `X-AIGW-Cache: hit|miss` and is an accepted trade-off of the approved
design. Also recorded: the header is emitted on **miss**, so it hands a caller the key of an entry now
stored, and its emission condition widened from `status in {"hit","miss"}` to whenever
`outcome.key is not None`.

**39. No metrics stack is added under this ticket.** There is no metrics infrastructure in aigateway
at all, so a permanently closed gate produces one boot warning and per-request bypass headers that
nothing aggregates — which composes badly with the refusal posture: prod's cache can be off by
construction *and* nothing in the app would reveal it. Building a metrics stack is not OME-305.
In-scope remedy: expose the degraded reason on an existing admin/health surface. Carried to the owner
as follow-up, not implemented here.

**40. The availability source must expose WHICH condition closed the gate.** `cache_available()` is one
bool, false both for the operator kill switch (`canary.py:220-221`) and for a failed canary
(`:224-226`), and `chat_cache_stage.py:138` collapses it into `cache_enabled`, which
`global_plan.py:86-87` maps to `BYPASS_DISABLED = "cache_disabled"`. So a key-mismatched replica
publishes "the operator turned it off" — a different remediation, and `DEPLOYMENT.md:173-183` walks an
operator through exactly this case. It also makes `cache_ports.py:35-39` false in the shipped path,
since it defines `cache_unavailable` as covering a closed gate and a closed gate never produces it.
Map operator→`cache_disabled`, degraded/canary→`cache_unavailable`. The object already knows the
difference; no new vocabulary member is needed. The `:138`/`:151` race is benign — `get_global` raises
per ruling 27, so a gate closing mid-flight bypasses without writing.

**41. Decision 31's premise is WITHDRAWN; decision 32 stands.** `aigateway.core.cache_ports` is a
public leaf module, not underscore-private, so no plugin importing from it violates `_ports.py:8-9`
and there is no privacy breach — 31 is retained as optional ergonomics only (`ProviderPluginBase`
declares a method whose return type its own package does not export, forcing two import sites for one
port). 32 remains required: `keys.py:20-23` still claims `PROMPT_KEY_FIELDS` is "locked by the registry
conformance sweep", now false in the dangerous direction because both guards were repointed off it.
Comment-only edit; the 32 green cases stay untouched.

**42. The generalized exclusion guard must adopt the first-segment form.** Measured:
`STRUCTURALLY_EXCLUDED_FIELDS` holds 10 entries, all bare field names with no dotted members. So the
full-path form is **vacuously true for every dotted rule** (`"provider_params.sort"` is never a member
of a set of bare names) while first-segment is equivalent for top-level paths and strictly stronger
for dotted ones — the only form that catches `messages.0.content`. This reverses an earlier reviewer
finding that the repointed guards were weakened: rows 1-2 are not weakened, and the near-vacuous
assertion is the **new** `test_no_non_bypass_rule_names_a_field_the_key_builder_structurally_excludes`.

**43. Pre-existing flake, not ours.** `tests/unit/auth/test_login.py::test_unknown_user_timing_close_to_wrong_password`
asserts a median-ratio tolerance over 20 HTTP logins and is load-sensitive by construction. It failed
in a reviewer's isolated run and **passed in the lead's heavier run**. No OME-305 path touches auth.
It sits on the G7 auth-surface gate, so it may surface there; treat as flake, not a regression.

**44. The coverage exposure is MEASURED and does not materialize.** The plan-fidelity review raised a
real risk: the failing cases were the coverage for `chat_dispatch.py`'s cache half, so red-or-repaired
cases lose their credit while the retired v1 lines stay in the denominator against
`--cov-fail-under=80` on both interpreters. Measured rather than argued —
`uv run pytest tests/unit -m "not live" -q --cov=aigateway`, 18:12:30→18:15:37: **TOTAL 92%**
(9141 statements, 753 missed), i.e. 12 points of headroom even with cases still red. Retired as a
blocker. Two per-file notes worth keeping: `migrations/0009_global_request_cache.py` is at **0%**
(46 statements) because migrations execute only under the PostgreSQL-marked subset, which this run
excludes — the general rule is that logic proven only under PostgreSQL earns zero coverage credit and
needs SQLite-executable unit tests *in addition* to the PG evidence; and `routes/chat_cache_stage.py`
is the lowest non-migration file at **80%** (17 missed), which is precisely the degraded/bypass region
where the missing route-level `CacheUnavailable` test belongs — the coverage gap and the untested
requirement are the same gap seen two ways.

**Repair is converging, measured twice by the lead.** 18:06:42→18:10:34: 18 failed / 2912 passed.
18:12:30→18:15:37: **9 failed / 2935 passed**. Halved in six minutes with passes rising, consistent
with Lane A working the class-S/class-B triage rather than with a systemic defect.

**45. THE CACHE IS NEAR-INERT FOR ITS TARGET WORKLOAD — the owner's keyed-breadth decision B is
unimplemented.** Verified by the lead at the source, three facts that compose:
`standard_parameters.py:81,:104` make `cache_behavior: CacheBehavior = "bypass"` the **default** for
`direct_rule` and its sibling; `grep -rn 'cache_behavior="keyed"' src/aigateway/plugins/` returns
exactly **one** live rule, in `openrouter_provider/routing_policy.py`; and
`global_eligibility.py:202-203` returns `CacheBypass(BYPASS_DECLARED)` for a `bypass` rule, which
`_classify:329-330` propagates as the **whole request's** disposition. Therefore any request carrying
`temperature`, `max_tokens`, `top_p`, `stop`, `response_format` or `seed` is never cached —
`max_tokens` confirmed `bypass` at `openrouter_provider/parameters.py:74` and
`anthropic_provider/parameters.py:101`, neither passing `cache_behavior`. The cache fires only for
requests containing nothing but prompt material plus OpenRouter's routing controls, while a benchmark
suite sets temperature and max_tokens as a matter of course. The owner ruled breadth **B (full)** —
"every reviewed output-affecting parameter across all six providers gets a disposition;
sampling/output-shaping ones become `keyed`; **not just OpenRouter's five**" — so what shipped is the
overruled narrow option. Implementing it is authorized work, not a new decision. **This is the second
inert-feature finding in this unit** (the first: a fail-closed guard on a precondition no deployment
provisions). Identical shape both times — every test green, every gate green, the feature does
nothing. A `bypass` default makes an unreviewed parameter fail *safe* and therefore *silent*, which is
the right safety posture and precisely why nothing complained.

**46. "Partial responses" (plan §1/§5.2/U5, never defined) means a response that is NOT FINISHED.**
Refuse to store when `choices` is missing or empty, when the first choice carries no `message`, or
when the first choice's `finish_reason` is null/absent. Store otherwise, **including
`finish_reason: "length"`**. The load-bearing reason is not the plan's wording: under decision B
`max_tokens` becomes **keyed**, so a `length` response is a complete, successful, deterministic answer
*for that exact key* — the caller's own budget is part of what identifies the request. Refusing it
would make the benchmark's dominant traffic permanently uncacheable, i.e. the feature defeating
itself. **This ruling is sound ONLY because `max_tokens` is keyed**; if it were unkeyed, serving a
truncated answer to a request with a larger budget would be a wrong hit and the `finish_reason == stop`
reading would be correct instead. That dependency must be stated in a comment so a future editor who
un-keys `max_tokens` is told they have created a wrong-hit class. `finish_reason: "tool_calls"` needs
no handling here — tool-bearing requests are excluded upstream. Verified as a boundary pair.

**47. Three never-store guards were lost in the v1→v2 rewrite and are restored.** All three were
enforced in v1's `chat_dispatch._store_cached_response`, and their only tests died with the v1 code
path, so the entire v2 suite was green without them — the fourth instance of "green because
uncovered" in this unit. Each is materially worse under v2 than v1, because a v2 row has
`expires_at = NULL` and is shared by every account, so v1's TTL used to bound the damage.
(a) **Oversized responses were being stored** — restored against the existing
`request_cache_max_response_bytes` (default 1 MB) as a `not_stored` **write outcome, not a bypass**,
because size is unknowable until the provider has answered. Tested as a boundary **pair**: a
rejection-only test is satisfied by a cap that refuses *everything*, which would disable the cache
while looking correct. (b) **Non-dict responses were being stored** — v1 had `isinstance(result, dict)`;
the route passes `model_dump()` when available and the raw object otherwise, so dict-ness is a plugin
convention, not a type guarantee. `result` widened to `Any`, because declaring `dict` stated a promise
the caller cannot make and hid the need for the check. (c) **Nothing tested that a provider ERROR
stores nothing** — the single most consequential never-store rule, since one transient failure under a
never-expiring globally-shared key would be served to every caller of that request forever. It held by
construction; "by construction" is exactly the claim that needs a test, because the construction can
change.

**Required before this unit can be called done** (all assigned, none optional): the two Anthropic
cross-mode fill tests; a route-level cross-account hit test (the story in both new module docstrings
is proven by nothing — no test posts as two identities); a route-level test that a raising
`get_global` yields 200 + `X-AIGW-Cache: bypass` rather than 500 (nothing outside the store/canary
units references `CacheUnavailable`); a test naming `BYPASS_UNPROJECTED_NATIVE` (currently zero grep
hits); the three decision-29 purity additions, the clock one most of all, since `:192-199` calls twice
back-to-back on one instance and a clock read at second granularity passes trivially; and an
executable assertion that the capability decision does not depend on `auth_mode`, replacing the
within-cycle test deleted when that branch was removed.

## Test supersession record (owner-approved 2026-08-03 under decision 8)

`run_gates.py` runs `append_only_check` before every gate and aborts on any `M`/`D`/`R` under the
stack's test globs, printing *"Changing a prior test is a Confidence-Gate decision — STOP and ask"*
(`.claude/scripts/run_gates.py:68-101`). That process was followed and answered, so the sanctioned
`--skip-append-only` flag (line 109) is used for this unit's gate runs. The bypass is auditable only
because of this record: **one row per modified test**, filled by the owning lane as it lands, each
naming the invariant that survives.

**The earlier estimate of "≈38 cases across 7 files" is WITHDRAWN as unsound (lead, 2026-08-03).**
It mixed `def test_` counts with pytest-collected counts, which diverge sharply under
`@pytest.mark.parametrize` — `test_openrouter_routing_policy.py` has 25 `def`s and **157** collected
cases; `test_openrouter_routing_policy_routes.py` has 8 `def`s and **22**. A denominator built that
way is worse than no denominator, because the whole point of the number is that a *missing* row must
not be able to hide inside the expected total. Measured collected counts, `pytest --collect-only -q`
at 2026-08-03 18:0x: routing_policy 157, route_rejections 35, top_p_promotion 30, request_cache_keys
32, routing_policy_routes 22, provider_contract_conformance 18, chat_request_cache 12,
chat_split_characterization 9, chat_cache_contract_composition 7, runtime_catalog_conformance 1.

**The denominator is therefore derived from observed failures plus inverted-but-passing cases, not
estimated up front.** Lead's own run (`uv run pytest tests/unit -m "not live" -q`, started 18:06:42
at worktree state after the 18:03 Anthropic landing) is the authority for the failure half; the
second half is the prior cases whose assertion the requirement inverts but which still pass, which
only a per-file read can enumerate. Until both halves are enumerated this record is INCOMPLETE and
`--skip-append-only` is NOT justified.

**Every failure must be triaged into exactly one of two classes before anything is rewritten**
(decision 37 below). Only class S earns a supersession row; class B must never get one.

**Correction to scope:** only **four** files are modified against the baseline, and there are **zero**
deletions and **zero** renames under the test globs — verified
`git diff --name-status 6aa45b5b62e2 -- apps/aigateway/tests` from the repo root. The four are
`test_provider_contract_conformance.py`, `test_runtime_catalog_conformance.py`,
`test_openrouter_routing_policy.py`, `test_openrouter_routing_policy_routes.py`. Every other failing
file is a prior file that is **unmodified**, so its failures are regressions or stale references, not
authorized rewrites.

| Test (file::name) | Pre-change assertion | Plan clause reversing it | Replacement invariant | Lane |
|---|---|---|---|---|
| `test_openrouter_routing_policy_routes.py::test_a_routing_control_request_bypasses_the_cache_and_stores_nothing` (6 params) | routing controls bypass the cache and store nothing (`X-AIGW-Cache == "bypass"`, `_stored_entries == 0`) | v2 keys routing controls (owner decision B; plan §4.6) | the same controls produce a `miss` that stores, and differing controls never cross-hit — relocated positive proof at `test_openrouter_global_cache_projection.py:351` | A |
| same file, the paired route-level case ~30 lines above | route asserts `X-AIGW-Cache == "bypass"` for a control-bearing request | same clause | route asserts `miss` + a stored entry | A |
| `..._route_rejections.py::test_a_reconstruction_mismatch_precedes_cache_credentials_dispatch_and_logs` | a reconstruction 503 provably meant cache planning never ran (v1 ordered prepare→plan) | v2 inverts the order: the cache stage runs BEFORE preparation | **split in two.** `..._refuses_without_credentials_dispatch_or_a_cache_fill` keeps every prior assertion verbatim (sanitized 503 detail, no credential read, no dispatch, marker absent from response and logs) with the two dead tripwires replaced by a store that raises on `set_if_absent`. Plus a NEW test for the property that replaces the retired ordering: `..._a_body_whose_routing_policy_cannot_be_rebuilt_is_never_served_from_cache` | A |
| `test_chat_cache_contract_composition.py` (1 of 7) | `X-AIGW-Cache-Reason == "stored"` | v2 splits the signal into `Reason == ""` plus a new `X-AIGW-Cache-Write` | both halves asserted, so the split itself is pinned. The other 6 retained deliberately: the module's rationale was backwards and was rewritten — v1's mechanism (a preparation hook running before cache planning) is now impossible, but the risk MOVED rather than vanished, since the key is built from `global_cache_projection`'s output and a projection dropping an output-affecting value reintroduces the same bug class one layer up | A |
| `test_chat_split_characterization.py::test_chat_success_dumps_model_and_sets_bypass_headers` | reason string `"disabled"` | reason vocabulary renamed to `"cache_disabled"` | same assertion against the new literal — kept as a **literal, not the `BYPASS_DISABLED` constant**, because for a caller-visible value importing the constant would let a rename pass silently; membership proven separately in `test_global_cache_reason_vocabulary.py` | A |
| `test_provider_contract_conformance.py`, `test_runtime_catalog_conformance.py` | guards required non-`bypass` rules to name a path inside `PROMPT_KEY_FIELDS` | decision 23/28 repoint to `STRUCTURALLY_EXCLUDED_FIELDS` | guards import the single four-set union at `global_eligibility.py:101` that `_classify:315` branches on, so guard and runtime cannot diverge; must adopt the **first-segment** form per decision 42 | A |

**NOT supersessions — class B repairs, no row owed** (decision 37): the decision-12 tripwire and any
other case failing on a moved symbol. Recorded here so their absence from this table is deliberate
rather than an omission.

**Still owed:** the passing-but-inverted set. A prior test whose assertion the requirement inverts but
which still passes never appears in a run, and is the one case where a row is owed and nothing forces
anyone to notice. Assigned to the plan-fidelity review; the lead's failure list plus that set is the
complete denominator.

Not in this set (verified): all **32** cases in `tests/unit/test_request_cache_keys.py` (decision 9),
all 11 in `tests/unit/core/test_caller_cache_policy.py` (path corrected — this record previously
named `tests/unit/`, which does not resolve; the file is under `tests/unit/core/` and existed at the
baseline, so it is a prior test) (verified to build synthetic rules via local
`_direct`/`_native` helpers with an explicit `cache_behavior=` argument at `:38-55`, never reading the
real registry, so decision 7 cannot reach them),
`test_request_cache_store.py::test_duplicate_write_updates_existing_row` and
`::test_corrupt_ciphertext_returns_none_and_deletes` (v1 `set()`/`get()` retained unchanged), and
`test_chat_request_cache.py::test_opt_in_hit_skips_provider_dispatch`'s
`len(X-AIGW-Cache-Key) == 12` assertion (decision 5 retains that header).

Two tests were written as tripwires for precisely this change —
`test_every_control_is_attributed_as_a_caller_visible_bypass_path` ("If a later cache change
(OME-702) makes the prepared body keyable… this test fails") and
`test_every_routing_control_bypasses_the_prompt_cache` ("until the cache key can carry that policy
(OME-702)"). OME-305 absorbed OME-702. They fired as designed; this record is the answer they asked
for, not a workaround.

## Planned changes

- `core/request_cache/global_keys.py` — closed `GlobalChatCacheKeyV2` DTO, deterministic
  canonicalization, SHA-256, revision constants, `CacheBypass` reasons, v2 control grammar.
- `core/plugin_base/*` — pure `global_cache_projection` port + fail-safe default.
- `core/parameter_projection.py` + `core/chat_parameters/*` — auth-mode-independent keyed/bypass/
  transport-only classification and an extended registry conformance sweep.
- `plugins/openrouter_provider/*` — projection reconstructing the five OME-704 controls plus
  mandatory `require_parameters=true`; the other cache-enabled providers get deterministic
  projections or an explicit bypass.
- `core/request_cache/store.py` + `models/request_cache_entry.py` + `migrations/0009_*.py` —
  nullable `expires_at`, plaintext compact JSON in the legacy `response_ciphertext` column,
  `get_global` (NULL = unexpired, v1 unreachable), create-only `set_if_absent`, atomic hit metadata.
- `main.py`, `config.py`, charts, `DEPLOYMENT.md` — explicit plaintext MVP posture and cache failure
  isolation; response encryption and migration deferred.
- `routes/chat.py` + `routes/chat_dispatch.py` — two-stage flow: merge only profile defaults before
  pre-cache lookup, while auth mode and provider credentials remain miss-only; miss keeps the existing
  validation and dispatch path;
  closed provenance headers.

## Test plan (RED first, per unit)

Acceptance tests 1–19 of the plan §8 are the contract. Each must map to a named test:
identity-invariance of the key · no credential access on a hit · projection purity (no I/O, no
identity) · exact prompt/message/parameter sensitivity · nothing sensitive persisted · OpenRouter
hit + per-control miss · metadata bypass · bypass does not weaken HTTP 400 · plaintext JSON round-trip ·
cache database failure isolation · NULL expiry readable · concurrent-fill winner preserved · atomic
single increment · explicit and legacy-control bypass performs no read/write · preflight failure
never fails startup/liveness/readiness · runtime read/metadata/write failure behavior · v1 rows
unchanged and unreachable · streaming and tools bypass · no variant lane and no OME-303 fields.

PostgreSQL-specific evidence is required (SQLite success is not evidence) for create-only
conflicts, the nullable-expiry migration from a populated `0008` database, and atomic hit
increments: `AIGW_TEST_PG=1 uv run pytest -m needs_postgres`.

## Acceptance

Plan §8 acceptance tests 1–19 pass and no plan §10 stop condition is triggered. Gate union — the
plan's §9 list is **incomplete**; these are the gates that actually apply to the paths this unit
touches:

- `uv run .claude/scripts/run_gates.py aigateway --skip-append-only` (decision 8 + supersession
  record above; without the flag the runner aborts before the first gate)
- `uv run ruff check .` **and `uv run ruff format --check .`** — plan §9 omits the format check
- `uv run pyright`
- `uv run python scripts/check_no_enterprise.py`
- `uv run pytest --cov=aigateway --cov-fail-under=80 -m "not live and not needs_postgres"` on
  **Python 3.12 and 3.13** (CI runs a matrix)
- the auth-surface coverage gate — listed in neither the plan nor the card, and it fires because U5
  restructures `routes/chat.py` next to auth:
  `uv run pytest tests/unit/auth tests/unit/test_auth_routes.py --cov=aigateway.core.auth
  --cov=aigateway.routes.auth --cov=aigateway.routes.auth_session --cov=aigateway.routes.accounts
  --cov-fail-under=80`
- `AIGW_TEST_PG=1 uv run pytest -m needs_postgres` — required evidence, SQLite success is not
  evidence for create-only conflicts, the nullable-expiry migration from a populated `0008`, or
  atomic hit increments
- `charts.yml` equivalents, because Lane B touches `apps/aigateway/charts/**`: `helm lint` ×3,
  `.github/scripts/verify_chart_wiring.py`, and `helm template` against prod values

**Lane B coverage hazard:** CI's coverage run *excludes* `needs_postgres`, so create-only, atomic-
increment and migration code proven only under PostgreSQL earns **zero** coverage credit. Lane B must
add SQLite-executable unit tests for the same logic or `--cov-fail-under=80` fails for a reason
unrelated to the feature.

`-m "not live"` is not load-bearing — live and PostgreSQL tests both self-skip on their env vars.

## Open items for the owner (not blocking implementation)

- **Done-when 11 is only half-satisfiable inside OME-305.** URL4 sends no cache control at all
  (`grep -rn 'use-cache|use_cache|"cache"' apps/url4-cloud/src packages/url4/src` → nothing), so
  default-on works for URL4 with no URL4 change. But explicit `use-cache=false` — the approved escape
  hatch for independent samples (plan §11, requirements §3.5) — is **unreachable from URL4** at the
  end of this unit. Recommend an `app/url4-cloud` sibling issue per CLAUDE.md rule 7 and amending
  Done-when 11; do not tick it on AIGateway evidence alone.
- **`apps/aigateway` has no automated layering gate.** `check_layering.py` is url4-cloud only
  (line 44), so "core never imports plugins" is convention here, not enforcement. Extending that
  script is ~30 lines and out of strict OME-305 scope — owner's call.
- **BLOCKING QUESTION — three caller-visible header values changed with no decision on record, and
  URL4 is a consumer.** `X-AIGW-Cache-Reason` values: `disabled`→`cache_disabled`; `not_requested`
  **removed** (the cache is default-on in v2, so the condition no longer exists);
  `unsupported_fields`→`bypassing_parameter`. Separately, `X-AIGW-Cache-Reason` no longer carries
  `stored` — that moved to a new `X-AIGW-Cache-Write` header (`chat_cache_stage.py:262`), miss only.
  `test_global_cache_reason_vocabulary.py` pins the *new* vocabulary tightly (exact bidirectional
  equality, dead-member and duplicate-condition detection); **nothing pins or accepts the
  transition.** This is a cross-app contract change, so per CLAUDE.md rule 7 it is an owner decision
  and above the lead's authority to absorb into a supersession row: either accept the break and file
  an `app/url4-cloud` sibling issue, or keep the v1 spellings as aliases. Raised by the plan-fidelity
  review; the lead is escalating rather than ruling.
- **Metrics (decision 39).** Expose the degraded cache reason on an existing admin/health surface so
  "is the cache serving" is answerable without reading pod logs. Not implemented under OME-305; the
  composition argument is that prod's cache can be off by construction *and* nothing in the app would
  reveal it.

## Lead's registry-sweep probe (2026-08-03 18:56) — decisions 48–50

Read-only probes against the **real** registry built by `tests/unit/_global_cache_registry_sweep.py`.
No source edited. These are measurements, not inspections: I ran the loops the tests run and counted
what reaches the assertion.

**48 — the new non-bypass sweeps are 92% vacuous, and one line reverts them to fully vacuous.**
Measured: **186 rule instances swept, 15 reach the assertion (8%)**. All 15 are openrouter's five
routing controls × three models. Per provider non-bypass count: anthropic 0/34, antigravity 0/6,
codex 0/5, gemini-cli 0/24, huggingface 0/60, openrouter 15/57 — so for **5 of 6 loaded providers the
loop body never executes** in `test_no_non_bypass_rule_names_a_field_the_key_builder_structurally_excludes`,
`test_every_non_bypass_rule_uses_an_addressing_form_the_key_builder_can_see`, and
`test_a_provider_that_declares_a_keyed_rule_backs_it_with_a_real_projection`. Deleting
`cache_behavior="keyed"` at `openrouter_provider/routing_policy.py:199` leaves all three passing
having examined nothing. `test_the_registry_sweep_is_not_vacuous` does **not** cover this: it asserts
`MODELS` is non-empty, which is a claim about models, not about rules reaching an assertion. This is
the near-inert `bypass` default reproduced one layer up, in the tests meant to catch it. **Ruling:**
non-vacuity counter required, asserting the examined count is non-zero and naming the current 15, so a
drop reads as a regression. Routed to Lane A.

**49 — `MODELS` silently drops a whole plugin, and the fix also repairs 48's blind spot.**
`REGISTRY.all()` yields **7** providers; `MODELS` reaches **6**. **`ollama` is registered but
unswept**, because `register_models()` returns `[]` with no daemon on :11434 — true in CI as well as
locally. So `test_the_projection_port_cannot_receive_identity_in_any_plugin`,
`test_no_projection_is_asynchronous` and `test_no_projection_opens_a_network_connection` never touch
ollama's plugin; an identity-taking or impure projection added there would pass. Those three already
ignore the model (`for plugin, _model in MODELS`), so iterating `REGISTRY.all()` for plugin-level
invariants is a strict improvement — it closes the gap *and* stops them running redundantly once per
model. Plus an assertion that `registered - swept` is empty or exactly a recorded commented set, so an
environment-dependent inventory cannot quietly shrink coverage again. Routed to Lane A. Note the
general shape: the sweep's docstring promise that "a provider added later is swept automatically" is
true, but a provider whose *inventory* is environment-dependent is swept **conditionally**, and
"registry-wide" then over-reads.

**50 — OWNER ESCALATION: 5 of 7 providers cannot cache anything at all.** Only **anthropic** and
**openrouter** define `global_cache_projection`; antigravity, codex, gemini-cli, huggingface and
ollama inherit the base default at `core/plugin_base/_provider.py:174`, so by
`test_a_bare_request_is_cacheable_exactly_when_the_provider_has_a_projection` **no request to those
five is cacheable, parameters irrelevant**. The base default bypassing is correct and
`test_the_default_projection_bypasses` should keep pinning it — this is a *coverage* question, not a
defect. The plan's only statement is line 388, "implement and test one deterministic no-I/O projection
per **cache-enabled** provider"; `cache-enabled` appears **exactly once in the whole plan and is
defined nowhere**, and no such config term exists in the code. So provider coverage was never scoped.
This is the **third** inertness layer found in this ticket and the widest one. Composed with decision
1's gap, the honest statement of shipped behaviour is: the cache serves **anthropic requests sending
none of the thirteen output-affecting parameters, and openrouter requests sending only its five
routing controls and none of the other thirteen** — nothing else. That sentence, not a percentage,
is what the owner needs to accept or reject.

## Owner rulings 51–53 (2026-08-03 19:16) — scope closed on the three open escalations

**51 — Provider scope: ship two.** `global_cache_projection` lands for **anthropic and openrouter
only**. Antigravity, codex, gemini-cli, huggingface and ollama keep inheriting the bypassing base
default; a follow-up epic adds one projection per provider. Resolves decision 50 and the undefined
"cache-enabled provider" in plan line 388 — the term is now *defined by this ruling* as those two.
`test_the_default_projection_bypasses` must stay: it is the fail-safe that makes shipping two
providers safe, since a provider becomes cacheable only by deliberately implementing the hook.

**52 — Keying breadth: explicitness everywhere, promotion for the two live providers.** This narrows
the earlier "all six providers, not just OpenRouter's five" ruling, on the ground escalated at 19:00:
promoting a parameter for a provider with no projection is **unobservable**, because
`build_global_cache_key` bypasses when either projection fails and the provider's bypass
short-circuits the request regardless of its rule dispositions. Both halves in scope: (i)
`cache_behavior` becomes a **required** argument at `core/standard_parameters.py:81` and `:104`, so
silence is impossible and all 49 sites state a disposition — no behaviour change, and it is the half
that prevents recurrence; (ii) real `keyed`/`transport_only` judgments for anthropic (0 of 34
non-bypass today) and openrouter (15 of 57) only. `transport_only` must meet plan §2.4's "proven not
to affect provider output" bar, not a guess. Tractable because the injected-default hazard was cleared
earlier: no `setdefault` anywhere adds a sampling parameter, so a promoted rule hashes the caller's own
value and cannot collide two callers who both omitted it.

**53 — Header: revert two of three renames.** Owner chose "rename only what must change".
`cache_disabled` → **back to `disabled`**; `bypassing_parameter` → **back to `unsupported_fields`**;
`not_requested` **stays removed**, the sole accepted break, because the cache is default-on in v2 and
that condition no longer exists — a removal, not a rename. `X-AIGW-Cache-Write` carrying `stored` is
additive and unaffected. No aliases, no deprecation window, **no url4-cloud sibling issue needed**,
which closes that blocking question. `test_global_cache_reason_vocabulary.py` keeps its exact
bidirectional equality and dead-member detection, repointed at the v1 names.
**Consequence for E4:** since `disabled` keeps its v1 spelling *and meaning*, the canary-degraded
condition must be expressed as a **new** value, never by repurposing `disabled` — adding a value is
far safer for URL4 than changing one, and it is the only way to satisfy E4 without reopening the break
the owner just declined.

## Supersession denominator — counted at BASELINE (review-fidelity + lead, 19:15)

**REINSTATED AS A BASELINE TABLE, after a real measurement settled it — see the resolution below.**
review-fidelity challenged the ten-file table at 18:57Z as mixing vintages (nine current, one
baseline), on the evidence that three files now measure 26 / 36 / 23 against my 12 / 35 / 22. The lead
confirmed all three current values at 19:15. **The rule the challenge argued for is right and adopted;
its diagnosis of the table was falsified by measurement.**

**RULE ADOPTED: the denominator is counted at baseline `6aa45b5b62e2`.** A row is owed for each
*prior* case that changed; added cases owe none, so a current count overstates it by exactly what the
lane added — +14 on that one file. Current counts answer "is the suite green"; baseline counts answer
"is every changed case accounted for".

**Instrument correction (lead):** `grep -c '^def test_'` equalled collected only on the one file with
no parametrize. At baseline `..._route_rejections.py` had 7 defs / 2 parametrize lines and
`..._routing_policy_routes.py` 8 / 3, so a def-count denominator understates them. A correct baseline
count also needs baseline **src**, since parametrize may range over a source constant this ticket
changes — collecting baseline tests against current `src/` would reprice the very rows being counted.
A detached worktree at `6aa45b5b62e2` therefore exists at `<scratchpad>/baseline-wt` and the full
baseline collect is the fixed reference. Measuring the immutable half is the right use of an in-flight
window: it cannot go stale.

### RESOLUTION — measured baseline counts (lead, 19:19). This is the authoritative denominator.

`pytest tests/unit --collect-only -q` in the baseline worktree, **baseline src and baseline tests**,
exit 0, **2644 collected**. Current column from the same command on the working tree at 19:19,
**2990 collected**.

| file | BASELINE | CURRENT | Δ |
|---|---|---|---|
| `openrouter/test_openrouter_routing_policy.py` | 157 | 157 | +0 |
| `openrouter/test_openrouter_routing_policy_route_rejections.py` | 35 | 36 | +1 |
| `openrouter/test_openrouter_routing_policy_routes.py` | 22 | 23 | +1 |
| `openrouter/test_openrouter_top_p_promotion.py` | 30 | 30 | +0 |
| `test_request_cache_keys.py` | 32 | 32 | +0 |
| `test_chat_request_cache.py` | **12** | 26 | **+14** |
| `test_chat_split_characterization.py` | 9 | 9 | +0 |
| `test_chat_cache_contract_composition.py` | 7 | 7 | +0 |
| `test_request_cache_store.py` | 10 | 10 | +0 |
| `core/test_provider_contract_conformance.py` | 18 | 18 | +0 |
| `core/test_runtime_catalog_conformance.py` | 1 | 1 | +0 |
| `core/test_caller_cache_policy.py` | 11 | 11 | +0 |

**All ten values in the original table are exactly the baseline counts, including the 12.** So it was
never nine-current-plus-one-baseline; it is a *uniformly baseline* table, which under the adopted rule
makes it the **correct** denominator rather than a withdrawn one. The three challenged deltas are real
measurements of **in-flight growth** — cases the lane ADDED — which by the same rule owe no rows and
must be excluded from the denominator.

**Not overclaimed:** the *provenance* of the original ten cannot be settled from the values, because
nine files have baseline == current so both hypotheses fit them, and the one discriminating file yields
12 either way if the reading predated its rewrite. Disclosed, not resolved. What IS established with
the right instrument is that the ten values equal the baseline collected counts, which is the only
property the denominator needs. The lesson stands: **publishing a count table without stating its
vintage is what made the challenge correct to raise**, independent of how the values turned out.

Two facts the measurement produces:
- **Only 3 of 12 audit files changed collected count: +14, +1, +1 — sixteen added cases inside the
  audit set.** For the other nine, baseline and current are interchangeable and no vintage hazard
  exists there at all.
- **The suite grew 2644 → 2990, about +346 cases** (the earlier 2944 figure was under `-m "not live"`,
  which deselects roughly 46). A *current*-vintage denominator would therefore have overstated the rows
  owed by roughly 350 — the concrete cost of the error the rule prevents.
- `test_request_cache_store.py` is **10** at baseline, so the two mutually-excluded cases there are 2
  of 10, not 2 of an unknown total.

**Cleanup owed at finish:** `git worktree remove <scratchpad>/baseline-wt` — it is registered in
`.git/worktrees` and must not outlive the ticket.

**Derivation as it stands: Set A = 27 (a FLOOR, dated to the five-file set at 17:17Z) + Set B = 14.**
Set A is assertion-reversed, file-modified, diff-findable. **Set B is assertion intact with the
*mechanism substituted*, file untouched — invisible to both diff and run**, and it is the half no
count of mine could have surfaced: B1 `test_chat_cache_contract_composition.py::test_a_preparation_hook_that_strips_an_accepted_field_cannot_make_it_cacheable`
(1); B2 `test_openrouter_top_p_promotion.py` (2, asserting against the now-uncalled
`caller_cache_bypass_paths`); B3 `tests/unit/core/test_caller_cache_policy.py` (11, counted at the
corrected path). The modified set has grown **5 → 8**, including `test_chat_split_characterization.py`
which nobody predicted, so Set A will grow; closing it is authorized the moment Lane A is hands-off.
Ruling 53 adds a **supersession of a supersession** — cases asserting the v2 header spellings are now
themselves superseded — which the table must express without double-counting the original row.

**Two-instrument convergence on one file, and the reason both fixes must land together.** The lead
found the *population* of `test_no_non_bypass_rule_names_a_field_the_key_builder_structurally_excludes`
near-vacuous (15 of 186, one provider, zero after deleting one line). review-fidelity §10.4 found the
*assertion* near-vacuous independently: `rule.request_path not in STRUCTURALLY_EXCLUDED_FIELDS`
**cannot fail for a dotted path**, since all ten excluded entries are bare field names. **Neither
implies the other**, and repairing either alone leaves a guard checking almost nothing — broaden to 186
instances of an assertion that cannot fail on dotted paths and little is gained. First-segment
comparison and non-vacuity counter ship in one change. Also adopted, better than the lead's L2
proposal: `test_the_registry_sweep_is_not_vacuous` pins a **minimum provider count**, because a
non-empty assertion cannot see ollama's absence.

**Generalization worth keeping past this ticket: evidence that exists only under a condition CI does
not provide earns nothing.** The registry sweep silently narrowing to environment-reachable providers
is the same shape as migration `0009` at 0% because migrations execute only under the
PostgreSQL-marked subset. Both look like coverage and are not.

## Rulings 54–56 (2026-08-03 19:23) — supersession accounting and the ruling-53 revert surface

**54 — SUPERSESSION IS NET OF BASELINE.** Proposed by review-fidelity, adopted verbatim: *a row is
owed iff the case's **final** assertion differs from its **baseline** assertion; the path between them
is churn, not supersession.* The table is keyed by **baseline case identity** (baseline file + baseline
test name), each row holding `baseline → current`; re-supersession **updates the row in place** and
never appends. Three consequences: (1) a **round-trip retires the row** and the denominator *decreases*;
(2) a **mixed delta keeps its row but the row's text must be rewritten**, because it now survives for a
different reason than the one written in it — a misrepresentation a correct total cannot detect, and the
precise failure this audit exists to catch; (3) **a file absent at baseline can never owe a row**, so
rewriting a new file twice is not supersession under any reading.

Consequence 3 is measured, not reasoned, from the baseline collect. Of the ruling-53 surface,
`test_global_cache_key.py`, `test_global_cache_write_eligibility.py` and
`test_global_cache_reason_vocabulary.py` are **ABSENT at baseline**. Pre-existing files touched by
ruling 53 are exactly **two**: `test_chat_split_characterization.py` (baseline 9) and
`test_chat_request_cache.py` (baseline 12). So "supersession of a supersession" reduces to **one row
retiring and one file needing no functional edit** — smaller than anyone assumed.

**Set A = 27 accepted at baseline vintage**, and specifically because the src-vintage hazard was
*excluded by inspection* rather than waved past: `_TARGETS` is a 5-entry dict literal, `_PATHS` derives
from it, `_CONTROLS` is a 5-entry tuple literal plus `("zdr", False)`, none reading `src/`, and both
conformance cases are undecorated at baseline. That check is what makes 27 a measurement. **Set A is a
FLOOR and will grow** — the modified set is 5 → 8. Closure authorized on Lane A's hands-off signal.

**55 — RULING 53's REVERT SURFACE (verified at the files, 19:21), and it invalidated landed work.**
`test_chat_split_characterization.py:256` had already been repaired **forward** to `"cache_disabled"`
with a `SUPERSEDED (OME-305)` block at `:221-225` arguing the rename's merits — "a bare `disabled` reads
as 'something was disabled' next to siblings like `opted_out` and `cache_unavailable`" — which is
exactly the rationale the owner declined. Baseline `:243` asserted `"disabled"`. **Correct end state:
baseline line restored verbatim, block DELETED, row retired** — not a second SUPERSEDED comment
explaining the revert. Caught by review-fidelity. Two functional `src/` sites drive everything:
`global_plan.py:44` `BYPASS_DISABLED` → `"disabled"`, and `global_eligibility.py:48` `BYPASS_DECLARED`
→ `"unsupported_fields"`, with `cache_ports.py:66,:74` vocabulary members moving in step. Comments now
asserting the declined rationale need correcting at `anthropic_provider/parameters.py:90` and
`chat_cache_stage.py:144,:160`. Breaking literal assertions: `test_global_cache_write_eligibility.py:231,:259`
plus **two test names that state the value** (`..._still_reports_cache_disabled`,
`..._not_cache_disabled`) and docstrings `:193,:242`; `test_global_cache_key.py:472`.
`test_chat_request_cache.py` needs **zero functional edits** — it asserts through imported constants at
`:171` and `:230`, so the value changes in `src/` and the assertions follow; only the `:158` docstring
names a literal.

**56 — CONSTANT-BINDING, WITH EXACTLY ONE LITERAL ANCHOR.** The two files above are the same ruling
producing a hand revert in one and nothing in the other, purely because one asserted a literal and one
an imported constant. So: **bind assertions to the constants in every file already being touched** (do
not open others), which makes the next vocabulary movement cost zero test edits. **But not universally**
— `assert resp.headers[...] == BYPASS_DISABLED` cannot detect a wrong *value* in the constant; it
verifies plumbing and is tautological about the spelling. The header is a caller-visible contract URL4
reads as exact bytes, so **exactly one place keeps asserting the literals**:
`test_global_cache_reason_vocabulary.py`, bidirectional equality repointed at `disabled` /
`unsupported_fields`. Convert everything and a rename passes the entire suite silently — the **fourth**
appearance in this ticket of a guard that checks nothing, after the `bypass` default, the 15-of-186
population, and the dotted-path assertion. Constants for the many, one literal anchor for the contract.

## Owner ruling 57 — key the EFFECTIVE request (P18 resolved; supersedes the write-gate)

**Escalated as P18** (review-security), **ruled by the owner** as a fifth option none of the four
offered: *"Resolve only the caller's profile defaults before cache lookup, without resolving auth
mode, provider credentials, API keys, or OAuth tokens. Apply those defaults to a copy of the request
using the existing body-wins merge rules, then build the global key from that effective request.
`system_prompt` becomes part of `messages`; `temperature`, `max_tokens`, and `reasoning_effort` enter
their normal keyed paths; transport-only defaults such as `timeout_seconds` remain excluded.
Profile/account identity and the fact that a value came from a profile never enter the key. Reuse the
same merged request/default snapshot on a miss so key construction and dispatch cannot diverge. If a
default cannot be represented safely by the key contract, bypass."* Contract wording moves from
**"same explicit request"** to **"same effective request"**; credentials remain miss-only.

**The defect.** `chat.py:218` merged profile defaults *after* the key was built at `:182`, and defaults
fill only omitted paths — so `keyed` disciplined the **caller-supplied value only**. Two callers both
POST bare `{model, messages}`; A's profile prepends "you are a pirate" and fills the row; B's profile
prepends "you are a formal legal assistant", gets an identical key and a **hit**, and receives A's
answer with B's own system prompt silently discarded. A *wrong answer*, categorically worse than the
accepted credential/billing first-fill semantics.

**Why review-security's write-gate was superseded rather than adopted — a transferable point.**
Gating the store at `chat.py:426-427` on `default_paths` being disjoint from key-participating paths
keeps polluted rows out of the corpus, but cannot close the **read** direction: a caller with *no*
defaults fills a clean bare row; a caller *with* a `system_prompt` default sends the same bare body,
hits that innocent row, and returns before `:218` ever applies their prompt. **A write-side filter is
a corpus-hygiene control, not a correctness control**, whenever a cache can be wrong in both
directions.

**Ruling 57 needs NO key-contract change. It is pure sequencing.** Four legs verified at the tree:

| leg | evidence |
|---|---|
| the merge is legal pre-cache | `_apply_defaults` (`chat_credentials.py:289`) is pure + sync — `(body, defaults, plugin)`, no request, no DB, no credential access |
| `system_prompt` needs no new keying | it prepends into `messages`, a `PROMPT_FIELD` already hashed as the prompt — the fix falls out |
| the three sampling defaults need no new keying | `temperature`/`max_tokens`/`reasoning_effort` already carry per-provider dispositions; promoted for anthropic+openrouter under ruling 52, `bypass` elsewhere — and the five projection-less providers are already uncacheable, so **no new bypass surface** |
| `timeout_seconds` is already excluded, not bypassed | `EXCLUDED_TRANSPORT_FIELDS = {"timeout","extra_headers","api_key"}` (`global_eligibility.py:71`) feeds `STRUCTURALLY_EXCLUDED_FIELDS`, consumed with `continue` at `:318`. **No `transport_only` disposition needed** — Lane A's "zero `transport_only`" invariant survives |

**THE TRAP — do not move `_credential_target_for_chat`.** It raises in three places: 404
`profile_not_found` (`:185`), 409 `profile_pending_auth` (`:196`), 401 `auth_required` on
`ProfileState.ERROR` (`:205`) — and yields non-empty defaults on exactly one line, the final
`return profile, None, profile.defaults`. Moving it ahead of Stage 1 would let those three
**preempt a cache hit**, destroying the invariant `chat.py:175-178` states as the design's headline
property: *"a hit returns without resolving any of them… including a caller whose provider is not
even connected."* A caller whose profile is absent, PENDING or ERRORED gets a hit today and would get
409/401/404 instead. **No current test covers this**, so it is a regression the suite would have
certified as green. Required instead: a new **non-raising** `_profile_defaults_for_key` doing
`idx.get(...)` → `profile.defaults` or empty, with no state checks, no OAuth lookup, and the reason in
its docstring naming `:185`/`:196`/`:205` so a later "consolidation" cannot silently reintroduce it.

**Fail-safe DIRECTION matters.** If the profile-index read raises, the implementation must **bypass**,
never proceed with empty defaults — an empty-defaults key omits defaults the miss path still applies,
manufacturing the exact wrong-hit class the ruling exists to remove. Reuse `cache_unavailable`
(adding a vocabulary value is safe, redefining one is not); a new value moves `_WIRE_CONTRACT` and its
byte-for-byte test in the same change.

**Comments falsified by 57 — five sites, rewrite rather than let rot.** `chat.py:175-178` (the central
invariant), `chat.py:227-230` ("Stage 1 now reads the caller's own body before ANY of these passes
run"), `chat_cache_stage.py:3-7` and `:187-189` (the second states the pre-57 body as an input
*precondition*, so it reads as the contract), and `_provider.py:192-196` at the port ("no account,
profile, user, auth mode or credential can reach a globally shared key" — insert "profile
**identity**" plus the positive half). OME-638 is **preserved**: classification stays at `chat.py:232`,
downstream of the merge, and both control-plane strips (`:144`, `:170`) still precede it.

### Corrections to this section, and the rules adopted from review (all tree-verified)

**MY CLAIM ABOVE WAS WRONG — a hit ALREADY master-key-decrypts, and always did.**
`core/request_cache/store.py:317` is `plaintext = await secrets.decrypt(row.response_ciphertext)`:
**the cached response body is itself encrypted at rest** in `request_cache_entries`, and the store
refuses to serve an entry that is not a recognised secret envelope. So `AIGATEWAY_SECRET_KEY` has been
on every hit's critical path since v2 was designed, and ruling 57 adds a **second** decryption in the
same failure domain, under the same key, behind the same gate — plus a **third** read on an unmigrated
account, because `ProfileIndexStore.read` falls back to `_read_legacy_account_index`
(`profile_index.py:44`,`:48`). **The availability posture does not change at all.** Correct wording for
`:175-178`, adopted verbatim from review-security because it will not need patching again: *a hit
resolves no provider credential, no auth mode and no profile identity; it does decrypt
master-key-encrypted gateway state.* Never write "now performs a decryption" — an operator debugging a
key rotation would read that as a regression introduced by this ticket, and there is none.

**THE GOVERNING ARTICULATION (review-arch, adopted over my provenance form).** `:175-178` was a
*provenance* rule — "no profile has been resolved at this point" — and provenance rules constrain where
the route is in its own execution, which any refactor may renegotiate; 57 is simply the first
renegotiation. The property the feature actually needs is a *value* rule: **the key is built from the
effective request; identity may be consulted to compute the effective request and may never enter the
key.** Two supports: identity was never deferred at all (`CurrentAccount = Annotated[BaseAccount,
Depends(current_account)]`, `auth/middleware.py:115` — authenticated before line one), so the old
comment overstated what was ever true; and v1 differs in **kind**, not degree — a v1 key *contained*
`profile_name`, identity in the digest, where 57 puts profile *values* in the digest and keeps the name
out. **The slope-closing test, mechanical rather than a judgement call: a value may enter the key only
if it is present in the merged body that dispatch itself will send.** Profile defaults qualify; auth
mode never will, because it is never in the body — and keying it would partition by credential kind
while not keying it while it shapes the outbound body is ruling 34's hazard exactly.

**PLACEMENT — the read goes INSIDE the `chat_cache_stage` no-raise boundary, not in `chat.py`.**
`ProfileIndexStore.read` raises (`ORMStore.read` on decrypt failure; `model_validate_json` on malformed
JSON), and `look_up_global_cache` is called **bare** at `chat.py:182` while the guarantee lives inside
the module: `chat_cache_stage.py:195-200` is `try: … except Exception: return
GlobalCacheOutcome(status="bypass", reason=CACHE_UNAVAILABLE_REASON)` under the `:13-18` absolute. In
`chat.py` a decrypt blip would be an **unhandled 500 on a previously-succeeding request**, inverting
§11. review-arch sharpened why this is not hypothetical: the read's failure condition is *the same
condition that closes the cache gate*, so in exactly the degraded state the cache exists to survive,
the route would fail before reaching the stage that knows how to degrade.

**FAIL-TO-BYPASS, NEVER FAIL-TO-EMPTY — derived independently three times** (me, review-security
pre-registering it as an attack, review-arch from availability). Empty defaults are not "no defaults";
they are **a different effective request**, so a caller carrying a `system_prompt` would key as though
they had none and hit an entry filled by a caller who genuinely had none. Second, easier-to-miss place
for the same rule: the non-raising read must return `profile.defaults` **independent of profile state**
— a PENDING or ERRORED profile still has the defaults that shape its effective request, and state is a
fact about credentials, not about the request. Anyone mirroring `_credential_target_for_chat`'s branch
structure fails-to-empty by construction. (Empty *is* correct at `:183` and `:193`: no profile exists.)

**THE MERGE IS CONDITIONAL, NOT DELETED — my own correction.** I first told Lane A to delete `:218`.
That is unsafe once the read can fail: on a bypass caused by a failed index read, Stage 2 must **still**
apply the caller's defaults before dispatch, or a decrypt blip silently drops a configured
`system_prompt` from a request that is still served — a 200 computed without the caller's own
configuration, recorded nowhere, and worse than the 500 we avoided. Two properties that look like one
requirement: **SINGLE SNAPSHOT** (key and dispatch cannot diverge) and **DEFAULTS ALWAYS APPLY** (a
cache failure must not change the dispatched request). Both must hold, so `_credential_target_for_chat`
keeps its signature — review-arch was right that `model_parameters.py:125` binds `_defaults` and
discards it and that tests reference the function zero times, but its "zero consumers → split it"
conclusion predates this correction; the fallback is a real consumer.

**THE DISCRIMINATOR IS A PRESENCE SENTINEL, not empty `default_paths`** (review-security). Empty
`default_paths` conflates "the profile genuinely has no defaults" with "Stage 1 bypassed before reading
them"; it is safe only because the fallback is a no-op in the benign state — *safety by coincidence*.
Carry the snapshot as `None` versus a possibly-empty object, so the states differ at the type level and
correctness stops resting on idempotency. Independently, pin **apply-twice == apply-once** on
`_apply_defaults` across all six fields: the conditional merge silently depends on an idempotency
asserted nowhere (it holds only via `not _has_system_message(body)` and `gateway_field not in body`,
`chat_credentials.py:311-330`) and dies the moment a default gains *append* semantics. The fallback
guard must be "Stage 1 already merged" — a control-flow fact — never "merging twice is safe".

**THE WORST AVAILABLE OUTCOME, AND A TRIAGE CLASS WE DID NOT HAVE.**
`_should_apply_profile_default` (`chat_credentials.py:95-97`) is a duck-typed hook returning **`True`
when absent** — it **fails open**. Anthropic's hook (`anthropic_provider/plugin.py:124`) returns `field
!= "reasoning_effort"` because applying it "enables Anthropic thinking on every request and burns the
Claude Code rate-limit pool unexpectedly". Pre-57, dropping that filter cost one caller their own
dispatches. **Post-57 the value enters the key and the stored row**, so every Anthropic entry filled by
such a profile becomes a thinking-enabled response served to callers who never asked — the rate-limit
burn becomes a property of the shared corpus. Hence: Lane A **must call** `_apply_defaults(body,
defaults, plugin)` and must not reimplement the merge inline to move it, since the lost line is a
plugin-dispatch indirection buried in a loop. First-ranked test: an Anthropic profile *with* the default
and one *without* must produce an **identical** snapshot and key, with no `reasoning_effort` dispatched.
**New triage class:** *a change that alters the BLAST RADIUS of an existing defect without changing it*.
Invisible to class-S and class-B analysis, because nothing about the existing code changes.

**Verified safe, recorded so they are not relitigated:** the pre-validation merge (an invalid stored
default is hashed then 400s — no row stored since the 400 precedes dispatch, no wrong hit since a
different value means a different key: wasteful, not unsafe); the OpenRouter `reasoning_effort` case
(pre-existing misconfiguration, newly visible); and `model` staying unreachable, since parsing precedes
the plugin lookup at `:168` which precedes Stage 1 at `:182`.

**Open follow-up, with its constraint attached so it is not rediscovered:** the profile-index read is
uncached, so a *miss* reads the index twice (pre-Stage-1, then `_credential_target_for_chat`) and the
legacy fallback can double each. Latency is not the case — one local AES-GCM decrypt is microseconds
against a hit that saves seconds — **duplication** is. Not in OME-305. When specified, it must be
**request-scoped only, never process-scoped and never TTL'd**: a process-scoped profile cache creates a
staleness class where a deleted, revoked or ERROR-marked profile keeps being applied, and profile state
drives credential selection and the OME-307 ownership CAS. Request scope has no invalidation semantics
to get wrong.

**Audit-method refinement (review-arch, folded into decision 37):** before classifying a failure as
class S, check whether the implementation value is itself still under negotiation — **a vocabulary
rename in flight makes a surviving spec look like a stale test**. Its own F3 advice was superseded this
way: it told me to rename a test's expectation to `cache_disabled` when what actually changed was the
implementation reverting to `disabled` under ruling 53. Right outcome, opposite mechanism, no row owed.
This is the first guard-that-checks-nothing on this ticket to come from the **audit** rather than the code.

## Owner ruling 58 — plaintext response storage for MVP

The owner confirmed that OME-305 must first prove the global cache behavior with the simplest
storage path: compact response JSON is stored plaintext in the existing
`RequestCacheEntry.response_ciphertext` column. The column name remains unchanged during MVP
validation to avoid a second migration. Reads parse and validate the stored JSON object directly.

This ruling supersedes response-cache encryption, encryption-canary, shared-key and key-rotation
requirements in the earlier plan and historical rulings. It does not change credential storage:
provider API keys, OAuth tokens and other credential blobs remain encrypted by their existing path.

The accepted MVP consequence is explicit: anyone with database or backup read access can read every
cached response, and rows currently have indefinite retention. Response encryption, key management,
rotation and migration of plaintext cache rows are one deferred follow-up after the feature proves
useful.

The Anthropic cross-mode matrix now uses a genuine `auth_type="api_key"` connection and a genuine
OAuth connection for both fill/read directions. Each direction proves that the reader performs no
provider dispatch and no auth-specific body preparation. Linear OME-305 was intentionally not updated.

## Owner ruling 59 — mode-restricted parameters bypass the global cache

The owner confirmed that Anthropic `provider_params.top_k` remains available for `api_key` only.
OAuth forwarding is still unproven and must not be enabled without separate provider evidence.

The global cache key is built before auth-mode and credential resolution and must remain identical
across callers. A parameter whose `applicable_auth_modes` is narrower than the provider's complete
`available_auth_modes()` therefore cannot honestly declare `cache_behavior="keyed"`: the pre-auth
stage can neither know that this caller will use the supported mode nor partition the key by that
identity-derived fact. Such a rule must declare `bypass`; the runtime mode-restriction guard remains
defence in depth.

This ruling clarifies rulings 7 and 52. Their requirement to key reviewed output-affecting parameters
applies where the auth-independent key can represent the parameter safely. Anthropic's API-key-only
`top_k` is the explicit exception: its request remains dispatchable under API-key auth but bypasses
the global cache. Do not widen it to OAuth merely to make caching reachable.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** v2 plaintext persistence in `core/request_cache/store.py`; static configured
  availability in `store.py`/`main.py`; response-cache canary and its canary-only credential-store
  API removed; configuration, chart and deployment guidance simplified to the single enable switch;
  global store/route/auth-mode/PostgreSQL tests updated. Migration `0009` was unchanged.
- **Commits:** this OME-305 implementation commit; no push performed.
- **Gates:** final focused store slice `35 passed`; full suite `2988 passed, 45 skipped`, coverage
  `92.23%`; PostgreSQL subset `5 passed`; Ruff check and format, Pyright, no-Enterprise guard,
  Helm lint, prod render and chart wiring `26/26` all passed.
- **Deviations:** owner ruling 58 superseded the earlier response-encryption and canary design.
  Credential encryption remains unchanged; no response-storage schema migration was added.
