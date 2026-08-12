# OME-797 — Implementation plan

Spec: `docs/spec/2026-08-12-OME-797-unify-web-search.md` · Ledger:
`docs/work/2026-08-12-OME-797-unify-web-search.md`

One SDLC unit, one stack (`url4-cloud`), one commit. RED before GREEN at every step.

## Step 1 — RED: the routing contract

Add `tests/unit/test_web_search_routing.py`:

- `provider_of` — prefixed, nested, unprefixed.
- selection — openrouter ⇒ native; codex, gemini-cli, antigravity, huggingface, ollama and
  unprefixed anthropic ⇒ Tavily; `web_search = false` ⇒ neither.
- INVARIANT — mutual exclusion, and disjunction equals `web_search`.
- config — an omitted `web_search` is `true`; an explicit `false` parses; a non-boolean
  raises. No test pins the retired names: they are deleted, not migrated.

The tests must fail because the names do not exist yet.

## Step 2 — GREEN: `world_config.py`

- `WEB_SEARCH_NATIVE_PROVIDERS: frozenset[str] = frozenset({"openrouter"})`.
- `provider_of(model_id: str) -> str` using `partition("/")`.
- `ModelSpec.web_search: bool = True`, plus `uses_native_web_search` and `uses_web_tools`
  properties. Remove `web_tools` and `native_web_search` fields.
- `_MODEL_KEYS = frozenset({"id", "web_search"})`. Nothing else — the retired keys get no
  branch, no constant, and no message of their own.

Carry the WHY anchors from the spec (§2.1 substring trap, §2.3 one-provider set) into the
code as `WHY:` / `INVARIANT:` comments.

## Step 3 — GREEN: the three call sites

- `request_parameters.wants_web_search` — `declared = spec.web_search`.
- `connector._retrieval_request` — guard reads `spec.web_search`; native branch reads
  `spec.uses_native_web_search`.
- `web_tools.build_runtime` — return `None` when the route is native.

## Step 4 — `url4.toml`

Remove every `web_tools` / `native_web_search` line. Rewrite the header block: document
`web_search` (default true), the derived mechanism, and the fact that
`WEB_SEARCH_NATIVE_PROVIDERS` in `world_config.py` is the one place that grows when an
aigateway plugin gains a native envelope. Keep the route-path invariant and the RESERVED
tables untouched.

## Step 5 — the 13 prior test files

Rewrite only the assertions that name the retired flags; preserve every behavioural
guarantee. Each changed test is listed in the PR body under the Confidence Gate. Also update
the stale comment in `benchmarks/draco/aggregate.py`.

## Step 6 — gates and close

`uv run .claude/scripts/run_gates.py url4-cloud` green, then fill the ledger Outcome, commit
with `Refs: OME-797`, open the PR, and close the issue with the card's template.

## Risks

- **Behaviour drift in the 13 rewritten tests.** Mitigation: change assertions about the
  flag names only; the spec §4 list is the checklist that each guarantee still has a test.
- **A missed reference to a retired field.** Mitigation: pyright plus a repo-wide grep for
  both names before the gates run.
