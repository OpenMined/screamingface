# Complexity Baseline — apps/server (SF-218)

Captured on 2026-05-26 from commit `0cca2ae`.

These are the high-water marks the day-1 thresholds were set to accommodate. Each tightening PR (one rule, one ratchet at a time) should reference this file and the file:line below it's reducing.

Baseline produced via:

```bash
uv run ruff check src \
  --select C901,PLR0911,PLR0912,PLR0915,PLR1702 \
  --no-fix --output-format json --preview \
  --config 'lint.mccabe.max-complexity = 1' \
  --config 'lint.pylint.max-statements = 5' \
  --config 'lint.pylint.max-branches = 3' \
  --config 'lint.pylint.max-returns = 2'
```

## C901 — McCabe cyclomatic complexity

- **Day-1 threshold:** `max-complexity = 47`
- **Top offenders:**

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

## PLR0915 — Too many statements

- **Day-1 threshold:** `max-statements = 194`
- **Top offenders:**

| Statements | File:line |
|-----------:|-----------|
| 194 | `src/screamingface/plugins/ollama_frontend/proxy.py:105` |
| 164 | `src/screamingface/plugins/ollama_frontend/proxy.py:130` |
| 130 | `src/screamingface/plugins/codex_frontend/proxy.py:186` |
| 110 | `src/screamingface/plugins/llm_base/routes_shared.py:98` |
| 107 | `src/screamingface/plugins/gemini_frontend/proxy.py:116` |
| 101 | `src/screamingface/plugins/codex_frontend/proxy.py:211` |
| 99  | `src/screamingface/plugins/claude_frontend/proxy.py:156` |
| 97  | `src/screamingface/plugins/claude_frontend/tests/test_e2e_claude_frontend.py:128` |
| 89  | `src/screamingface/plugins/aigw_base/auth_proxy_router.py:56` |
| 77  | `src/screamingface/plugins/gemini_frontend/proxy.py:146` |

## PLR0912 — Too many branches

- **Day-1 threshold:** `max-branches = 30`
- **Top offenders:**

| Branches | File:line |
|---------:|-----------|
| 30 | `src/screamingface/plugins/ollama_frontend/proxy.py:130` |
| 28 | `src/screamingface/plugins/claude_frontend/tests/test_e2e_claude_frontend.py:128` |
| 27 | `src/screamingface/cli/run.py:12` |
| 20 | `src/screamingface/plugins/codex_frontend/proxy.py:211` |
| 19 | `src/screamingface/plugins/gemini_frontend/proxy.py:146` |
| 18 | `src/screamingface/plugins/claude_frontend/_sse.py:17` |
| 18 | `src/screamingface/plugins/claude_backend_api/adapter.py:302` |
| 15 | `src/screamingface/plugins/python_runner/plugin.py:95` |
| 13 | `src/screamingface/plugins/codex_backend_api/adapter.py:53` |
| 13 | `src/screamingface/plugins/aigw_runner/plugin.py:141` |

## PLR0911 — Too many return statements

- **Day-1 threshold:** `max-returns = 11`
- **Top offenders:**

| Returns | File:line |
|--------:|-----------|
| 11 | `src/screamingface/plugins/llm_base/routes.py:124` |
| 11 | `src/screamingface/plugins/aigw_base/backend.py:110` |
| 11 | `src/screamingface/plugins/aigw_base/backend.py:71` |
| 10 | `src/screamingface/plugins/gemini_backend_api/backend.py:152` |
|  7 | `src/screamingface/plugins/url4_executor/url4_resolve.py:33` |
|  7 | `src/screamingface/plugins/url4_executor/routes.py:35` |
|  7 | `src/screamingface/plugins/llm_base/routes.py:344` |
|  6 | `src/screamingface/plugins/url4_executor/tests/test_e2e_url4.py:75` |
|  6 | `src/screamingface/plugins/llm_base/routes.py:263` |
|  6 | `src/screamingface/plugins/gemini_backend_api/backend.py:207` |

## PLR1702 — Too many nested blocks (no tunable)

This rule has no configurable threshold; ruff also lists it under preview-only in 0.15.x, so it surfaces violations only when `--preview` is on. It is included in `select` so any NEW violations are blocked once preview is enabled or the rule promotes to stable. Existing known-debt at baseline:

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
