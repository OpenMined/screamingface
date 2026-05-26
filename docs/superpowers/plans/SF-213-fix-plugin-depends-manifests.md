# SF-213: Fix `Plugin.depends` manifests per SF-208 audit (quick wins)

**Asana:** [SF-213](https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215115079155250)
**Branched from:** `SF-208-plugin-dependency-audit` (PR #202 — must merge first or pair-merge).

**Goal:** Apply the audit's REMOVAL findings only. Adding new declared deps tightens runtime activation requirements and breaks ~25 tests with narrow `plugins=[...]` fixtures; those additions are deferred to a follow-up ticket that scopes the necessary test-fixture updates alongside.

**Approach:** Edit each plugin's `plugin.py` `depends: list[str] = [...]` to drop entries no plugin imports. After all edits, re-run `tools/plugin_dependency_audit.py` and verify the residual matches expectations.

## Apply: removals

| Plugin (`<dir>/plugin.py`) | Remove from `depends` |
|---|---|
| `claude_env_intercept` | `claude-frontend` |
| `claude_frontend` | `url4-specs` |
| `codex_frontend` | `url4-specs` |
| `gemini_frontend` | `url4-specs` |
| `ollama_frontend` | `url4-specs` |

## Steps

- [ ] **Step 1: Apply every row of the removals table.** For each plugin: read the current `depends: list[str] = [...]` line in `apps/server/src/screamingface/plugins/<dir>/plugin.py` and splice out the listed removal. Preserve ordering of remaining items. For `claude_env_intercept`, the dropped entry leaves an empty list — keep the `depends: list[str] = []` form (typed annotation, consistent with other plugins).

- [ ] **Step 2: Run the audit and assert the expected residual.**

  ```bash
  cd /Users/sergey/work/openmind/screamingface
  uv run --directory apps/server python -m tools.plugin_dependency_audit \
    --plugins-root src/screamingface/plugins \
    --report ../../docs/superpowers/plans/plugin-dependency-audit.md
  ```

  Inspect the report:
  - **Cycles section:** 2 cycles remain (the two real prod cycles — see Out of scope).
  - **Per-plugin prod-missing:** 12 plugins still flagged (all moved to the follow-up ticket — see Out of scope).
  - **Per-plugin extraneous:** drops from 7 to 2. Only `aigw-codex-backend` and `aigw-gemini-backend` should still show extraneous (`['backend-api-base']`), which is the known asymmetric-inheritance false positive.

  Verify these counts match. Commit the refreshed report.

- [ ] **Step 3: Run the server test suite (fast subset).**

  ```bash
  cd /Users/sergey/work/openmind/screamingface/apps/server
  uv run pytest -m "not e2e and not e2e_live" -q
  ```

  Expected: green. If a plugin-metadata test pins exact `depends` content for any of the 5 edited plugins, update only that test to match the new declared list.

- [ ] **Step 4: Lint gates.**

  ```bash
  cd /Users/sergey/work/openmind/screamingface/apps/server
  uv run ruff format src/screamingface/plugins
  uv run ruff check src/screamingface/plugins
  ```

- [ ] **Step 5: Commit and push.**

  ```bash
  git add apps/server/src/screamingface/plugins/*/plugin.py \
          apps/server/src/screamingface/plugins/*/tests/test_plugin.py \
          docs/superpowers/plans/plugin-dependency-audit.md \
          docs/superpowers/plans/SF-213-fix-plugin-depends-manifests.md
  git commit -m "SF-213: remove extraneous Plugin.depends entries (per SF-208 audit)"
  git push -u origin SF-213-fix-plugin-depends-manifests
  ```

- [ ] **Step 6: Open PR.** Base: `main`. Note in body that this depends on PR #202 (SF-208) for the audit script. **Stop — do not merge.**

## Out of scope

Deferred to follow-up ticket(s) that scope test-fixture updates and architectural work:

- **All 12 prod-missing additions from the audit.** Adding new declared deps tightens runtime activation: any test that instantiates the plugin via a narrow `plugins=[X]` fixture starts failing because the registry refuses to activate `X` without its newly-declared transitive deps. The audit's additions table (previously in this plan) belongs in the follow-up ticket verbatim, paired with the corresponding test-fixture widening. Plugins affected: `aigw_base`, `aigw_runner`, `backend_api_base`, `claude_backend_api`, `claude_frontend`, `codex_backend_api`, `frontend_base`, `gemini_backend_api`, `llm_base`, `ollama_backend_api`, `python_runner`, `url4_executor`.
- **The two real prod cycles** (`aigw-base ↔ url4-executor` via `backend-api-base`, and `aigw-base ↔ llm-base`). Architectural call — likely move shared types out of `aigw-base`, or invert a dep.
- **Asymmetric inheritance handling in the audit script** (`backend-api-base` extraneous false-positives on `aigw-codex-backend` / `aigw-gemini-backend`). The audit follows inheritance for `depends` but not for the corresponding imports, producing this asymmetric false positive. Track the audit-script fix as a separate refinement.
- **Test-only undeclared imports** (6 plugins). `Plugin.depends` is a runtime contract; test imports don't belong there.
