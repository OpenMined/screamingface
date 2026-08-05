---
ticket: OME-712
stack: aigateway
status: in_progress
started: 2026-08-04
finished:
---

# OME-712 — certify AI Gateway benchmark support

## Intent

Audit the Gateway-specific benchmark prerequisites as one narrow landing: exact model
registration, provider-neutral hosted retrieval, provider discovery, database bootstrap, and a
local launcher that inherits canonical settings.

## Planned files

- Existing production/test changes under `apps/aigateway` only when supported by the spec.
- `docs/spec/2026-08-04-OME-712-aigateway-benchmark-support.md` — owned contract.
- `docs/plan/2026-08-04-OME-712-aigateway-benchmark-support.md` — certification sequence.
- `docs/work/2026-08-04-OME-712-aigateway-benchmark-support.md` — this evidence ledger.
- `docs/work/2026-08-04-OME-712-gateway-launcher-defaults.md` — existing focused launcher
  evidence retained as a child record.

No database model/schema change is introduced by this audit; the migration command applies the
existing Tortoise migration history.

## Test plan

- Full canonical AI Gateway gate for the unchanged rebased branch.
- Focused OpenRouter projection/settings tests.
- CLI, health/discovery, and launcher contract tests.
- Cross-check every registered model id against the upper Engine definitions.

## Acceptance

- Gateway behavior and the focused spec agree.
- No benchmark execution or grading logic enters the Gateway.
- No launcher or downstream app duplicates canonical model settings.
- Any required inherited-test edit has explicit Confidence-Gate approval; no test is deleted,
  skipped, or weakened.
- Complete gates and review evidence are recorded below.

## Outcome

### Implemented surface

- Canonical OpenRouter seeds now include the exact DRACO and current IFEval lineup. All ten ids
  were re-verified against OpenRouter's public `/api/v1/models` catalog on 2026-08-05, including
  `anthropic/claude-fable-5` and `moonshotai/kimi-k3`.
- `web_search` and `web_search_excluded_domains` are bounded standard parameters. The adapter
  owns OpenRouter's private plugin envelope, unions caller/operator exclusions, and emits the
  documented `exclude_domains` spelling.
- Exclusions without `web_search: true` now fail closed. The audit first added a failing
  behavior-level test, then added the parameter-combination validation.
- Web-search projection moved from the 482-line OpenRouter plugin into the focused 54-line
  `web_search.py` module; the plugin is now 410 lines and every changed Python module is below
  the repository's 450-line ceiling.
- Authenticated and explicitly auth-disabled `/v1/providers` discovery is derived from loaded
  provider plugins. Its tests live in the new `test_providers_route.py` module; inherited
  `test_health.py` is restored.
- `aigateway migrate` reuses the production Tortoise command. The Helm migration Job and local
  launcher invoke that public entry point; the launcher enables OpenRouter without shadowing its
  canonical model defaults.
- OpenRouter's server-tool API is not exposed as a fallback. The comments now record the dated
  compatibility probe and require fresh conformance evidence before adding that second surface.

### Verification evidence

- Focused Gateway behavior: **90 passed** across OpenRouter projection/settings/dispatch,
  launcher, CLI, and provider discovery.
- Ruff: full `apps/aigateway` check passed; all **392** Python files are formatted.
- Targeted Pyright over every changed production module: **0 errors**.
- Enterprise import guard: passed.
- Diagnostic full suite in the pre-existing LiteLLM 1.87 environment: **2669 passed, 40
  skipped, 4 failed, 92.41% coverage** after applying the repository-documented macOS
  `ulimit -n 4096`. Two failures are inherited Anthropic tests whose LiteLLM-private call
  signature targets the branch's 1.95 lock; two are inherited Codex OAuth setup failures. No
  changed-surface test failed. This borrowed environment is diagnostic, not an authoritative
  branch gate.
- Canonical fresh-environment gate: blocked before lint on macOS because LiteLLM 1.95 has no
  compatible wheel here and a source dependency requires Rust 1.94.1 while the host has 1.92.0.
- Current `main` at `0571f440` has a green Linux AI Gateway workflow on Python 3.12 and 3.13
  ([run 30926214566](https://github.com/OpenMined/screamingface/actions/runs/30926214566)).
  This unpublished branch still needs its own authoritative Linux run after owner-approved
  publication.

### Confidence-Gate decision

The inherited OpenRouter settings test pins the exact seed list independently from production.
Adding real benchmark routes necessarily updates that expected array. The dispatch test consumes
the configured defaults so every seed is exercised without maintaining a second copy. This is a
narrow Confidence-Gate exception: the exact pin remains strict, and no assertion is removed or
weakened. The owner approved this exception on 2026-08-04.

- **Actual files:** Gateway code/tests/docs listed above plus the linked spec and plan.
- **Commits:** five reviewer-oriented groups: model seeds, web search, provider discovery,
  migration/local tooling, and certification docs.
- **Gates:** focused and static checks green; authoritative branch Linux gate pending.
- **Deviations:** OME-712 remains cross-cutting; Linear and GitHub were not mutated.
