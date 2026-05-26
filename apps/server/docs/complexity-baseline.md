# Complexity Baseline — apps/server (SF-218)

Captured on 2026-05-26 from commit `0cca2ae`. Re-baselined on 2026-05-26 to include
`tests/` after CI was observed running `ruff check` from the app root (full repo scope),
not `src/` only. The fix-PR widened the `tests/`-side blind spot — see split tables below.

These are the high-water marks the day-1 thresholds were set to accommodate. Each
tightening PR (one rule, one ratchet at a time) should reference this file and the
file:line below it's reducing.

Baseline produced via (now run from the app root, not `src/`):

```bash
uv run ruff check . \
  --select C901,PLR0911,PLR0912,PLR0915,PLR1702 \
  --no-fix --output-format json \
  --config 'lint.mccabe.max-complexity = 1' \
  --config 'lint.pylint.max-statements = 5' \
  --config 'lint.pylint.max-branches = 3' \
  --config 'lint.pylint.max-returns = 2'
```

## C901 — McCabe cyclomatic complexity

- **Day-1 threshold:** `max-complexity = 47`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

| Complexity | File:line |
|-----------:|-----------|
| 47 | `src/screamingface/plugins/ollama_frontend/proxy.py:105` |
| 37 | `src/screamingface/plugins/ollama_frontend/proxy.py:130` |
| 37 | `src/screamingface/plugins/codex_frontend/proxy.py:186` |
| 30 | `src/screamingface/plugins/llm_base/routes_shared.py:98` |
| 30 | `src/screamingface/plugins/gemini_frontend/proxy.py:116` |
| 30 | `src/screamingface/plugins/aigw_base/auth_proxy_router.py:56` |
| 27 | `src/screamingface/plugins/codex_frontend/proxy.py:211` |
| 26 | `src/screamingface/core/admin_router.py:138` |
| 25 | `src/screamingface/plugins/claude_frontend/proxy.py:156` |
| 25 | `src/screamingface/cli/run.py:12` |

### Top offenders — test code (`tests/`)

| Complexity | File:line |
|-----------:|-----------|
| 21 | `src/screamingface/plugins/claude_frontend/tests/test_e2e_claude_frontend.py:128` |
| 16 | `tests/e2e/test_url4_matrix.py:336` |
| 16 | `tests/e2e/test_url4_matrix.py:184` |
| 14 | `tests/e2e/test_aigw_claude_e2e.py:90` |
| 11 | `src/screamingface/plugins/claude_intercept/tests/test_e2e_intercept.py:59` |
| 10 | `tests/e2e/infrastructure/claude_code_client.py:101` |
|  9 | `tests/e2e/conftest.py:89` |
|  8 | `src/screamingface/plugins/url4_executor/tests/test_e2e_url4.py:107` |
|  7 | `tests/e2e/infrastructure/otlp_collector.py:72` |
|  7 | `tests/e2e/infrastructure/otlp_collector.py:41` |

## PLR0915 — Too many statements

- **Day-1 threshold:** `max-statements = 194`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

| Statements | File:line |
|-----------:|-----------|
| 194 | `src/screamingface/plugins/ollama_frontend/proxy.py:105` |
| 164 | `src/screamingface/plugins/ollama_frontend/proxy.py:130` |
| 130 | `src/screamingface/plugins/codex_frontend/proxy.py:186` |
| 110 | `src/screamingface/plugins/llm_base/routes_shared.py:98` |
| 107 | `src/screamingface/plugins/gemini_frontend/proxy.py:116` |
| 101 | `src/screamingface/plugins/codex_frontend/proxy.py:211` |
|  99 | `src/screamingface/plugins/claude_frontend/proxy.py:156` |
|  89 | `src/screamingface/plugins/aigw_base/auth_proxy_router.py:56` |
|  77 | `src/screamingface/plugins/gemini_frontend/proxy.py:146` |
|  77 | `src/screamingface/cli/run.py:12` |

### Top offenders — test code (`tests/`)

| Statements | File:line |
|-----------:|-----------|
| 97 | `src/screamingface/plugins/claude_frontend/tests/test_e2e_claude_frontend.py:128` |
| 55 | `src/screamingface/plugins/url4_executor/tests/test_e2e_url4.py:107` |
| 49 | `src/screamingface/plugins/claude_intercept/tests/test_e2e_intercept.py:59` |
| 46 | `tests/e2e/test_aigw_claude_e2e.py:90` |
| 45 | `tests/e2e/test_url4_matrix.py:336` |
| 40 | `tests/e2e/test_url4_matrix.py:184` |
| 37 | `tests/e2e/test_aigw_codex_auth_e2e.py:47` |
| 37 | `tests/e2e/test_aigw_auth_e2e.py:57` |
| 35 | `tests/e2e/test_aigw_claude_e2e.py:217` |
| 33 | `src/screamingface/plugins/aigw_runner/tests/test_runner.py:102` |

## PLR0912 — Too many branches

- **Day-1 threshold:** `max-branches = 30`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

| Branches | File:line |
|---------:|-----------|
| 30 | `src/screamingface/plugins/ollama_frontend/proxy.py:130` |
| 27 | `src/screamingface/cli/run.py:12` |
| 20 | `src/screamingface/plugins/codex_frontend/proxy.py:211` |
| 19 | `src/screamingface/plugins/gemini_frontend/proxy.py:146` |
| 18 | `src/screamingface/plugins/claude_frontend/_sse.py:17` |
| 18 | `src/screamingface/plugins/claude_backend_api/adapter.py:302` |
| 15 | `src/screamingface/plugins/python_runner/plugin.py:95` |
| 13 | `src/screamingface/plugins/codex_backend_api/adapter.py:53` |
| 13 | `src/screamingface/plugins/aigw_runner/plugin.py:141` |
| 12 | `src/screamingface/plugins/url4_executor/collection_parser.py:31` |

### Top offenders — test code (`tests/`)

| Branches | File:line |
|---------:|-----------|
| 28 | `src/screamingface/plugins/claude_frontend/tests/test_e2e_claude_frontend.py:128` |
| 15 | `tests/e2e/test_url4_matrix.py:336` |
| 15 | `tests/e2e/test_url4_matrix.py:184` |
| 15 | `tests/e2e/test_aigw_claude_e2e.py:90` |
| 12 | `src/screamingface/plugins/claude_intercept/tests/test_e2e_intercept.py:59` |
| 10 | `tests/e2e/infrastructure/claude_code_client.py:101` |
| 10 | `tests/e2e/conftest.py:89` |
|  9 | `src/screamingface/plugins/url4_executor/tests/test_e2e_url4.py:107` |
|  6 | `tests/e2e/test_aigw_codex_auth_e2e.py:47` |
|  6 | `tests/e2e/test_aigw_auth_e2e.py:57` |

## PLR0911 — Too many return statements

- **Day-1 threshold:** `max-returns = 12` (raised from 11 to accommodate a tests/-side offender)
- **High-water came from:** `tests/` (`tests/e2e/test_url4_matrix.py:184` at 12 returns)

### Top offenders — production code (`src/`)

| Returns | File:line |
|--------:|-----------|
| 11 | `src/screamingface/plugins/llm_base/routes.py:124` |
| 11 | `src/screamingface/plugins/aigw_base/backend.py:110` |
| 11 | `src/screamingface/plugins/aigw_base/backend.py:71` |
| 10 | `src/screamingface/plugins/gemini_backend_api/backend.py:152` |
|  7 | `src/screamingface/plugins/url4_executor/url4_resolve.py:33` |
|  7 | `src/screamingface/plugins/url4_executor/routes.py:35` |
|  7 | `src/screamingface/plugins/llm_base/routes.py:344` |
|  6 | `src/screamingface/plugins/llm_base/routes.py:263` |
|  6 | `src/screamingface/plugins/gemini_backend_api/backend.py:207` |
|  6 | `src/screamingface/plugins/codex_backend_api/backend.py:189` |

### Top offenders — test code (`tests/`)

| Returns | File:line |
|--------:|-----------|
| 12 | `tests/e2e/test_url4_matrix.py:184` |
|  7 | `tests/e2e/infrastructure/otlp_collector.py:41` |
|  6 | `src/screamingface/plugins/url4_executor/tests/test_e2e_url4.py:75` |
|  5 | `tests/e2e/infrastructure/otlp_collector.py:59` |
|  4 | `tests/e2e/infrastructure/claude_oauth.py:20` |
|  3 | `tests/e2e/test_url4_matrix.py:513` |
|  3 | `tests/e2e/test_url4_matrix.py:440` |
|  3 | `tests/e2e/infrastructure/claude_code_client.py:54` |
|  3 | `tests/e2e/conftest.py:63` |
|  3 | `src/screamingface/plugins/claude_frontend/tests/test_e2e_claude_frontend.py:128` |

## PLR1702 — Too many nested blocks (no tunable)

This rule has no configurable threshold; ruff also lists it under preview-only in 0.15.x, so it surfaces violations only when `--preview` is on. It is included in `select` so any NEW violations are blocked once preview is enabled or the rule promotes to stable. Existing known-debt at baseline (no new `tests/`-side violations surfaced by the rebaseline):

| Nesting depth | File:line |
|--------------:|-----------|
| 7 | `src/screamingface/plugins/ollama_frontend/proxy.py:325` |
| 6 | `src/screamingface/plugins/tracing/plugin.py:63` |
| 6 | `src/screamingface/plugins/ollama_frontend/proxy.py:164` |
| 6 | `src/screamingface/plugins/codex_frontend/proxy.py:347` |
| 6 | `src/screamingface/plugins/claude_frontend/_observability.py:64` |

## Tightening roadmap (one PR per ratchet)

1. C901 max-complexity: target 10 (industry default).
2. PLR0915 max-statements: target 50.
3. PLR0912 max-branches: target 12.
4. PLR0911 max-returns: target 6.
5. Promote PLR0913 (too-many-arguments) to enforced once Pydantic/FastAPI dependency-injection patterns have been audited for per-file ignores.
