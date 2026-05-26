# Complexity Baseline — apps/aigateway (SF-218)

Captured on 2026-05-26 from commit `0cca2ae`. Re-baselined on 2026-05-26 to include
`tests/` after CI was observed running `ruff check` from the app root (full repo scope),
not `src/` only. No threshold changes were required for this app — all `tests/`-side
violations fall under the existing high-water marks — but the offender tables below now
include both surfaces so future tightening PRs see the full picture.

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

- **Day-1 threshold:** `max-complexity = 25`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

| Complexity | File:line |
|-----------:|-----------|
| 25 | `src/aigateway/routes/chat.py:224` |
| 17 | `src/aigateway/main.py:100` |
| 14 | `src/aigateway/plugins/gemini_provider/message_adapter.py:15` |
| 12 | `src/aigateway/routes/auth.py:473` |
| 12 | `src/aigateway/plugins/gemini_provider/message_adapter.py:130` |
| 11 | `src/aigateway/routes/auth.py:593` |
| 10 | `src/aigateway/routes/auth.py:186` |
| 10 | `src/aigateway/plugins/codex_provider/auth.py:75` |
|  8 | `src/aigateway/plugins/codex_provider/chat_handler.py:148` |
|  8 | `src/aigateway/plugins/codex_provider/chat_handler.py:110` |

### Top offenders — test code (`tests/`)

| Complexity | File:line |
|-----------:|-----------|
| 8 | `tests/unit/test_registry.py:56` |
| 5 | `tests/unit/test_main.py:64` |
| 5 | `tests/live/test_ollama_live.py:75` |
| 4 | `tests/unit/test_credential_store.py:106` |
| 4 | `tests/unit/gemini/test_chat_handler.py:147` |
| 4 | `tests/unit/auth/test_passwords.py:54` |
| 4 | `tests/unit/auth/test_passwords.py:32` |
| 4 | `tests/live/test_ollama_live.py:107` |
| 4 | `tests/live/test_ollama_live.py:94` |
| 4 | `tests/live/test_gemini_live.py:73` |

## PLR0915 — Too many statements

- **Day-1 threshold:** `max-statements = 76`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

| Statements | File:line |
|-----------:|-----------|
| 76 | `src/aigateway/routes/chat.py:224` |
| 50 | `src/aigateway/main.py:100` |
| 48 | `src/aigateway/routes/auth.py:186` |
| 46 | `src/aigateway/routes/auth.py:473` |
| 34 | `src/aigateway/plugins/gemini_provider/message_adapter.py:15` |
| 31 | `src/aigateway/plugins/gemini_provider/message_adapter.py:130` |
| 30 | `src/aigateway/routes/auth.py:593` |
| 30 | `src/aigateway/plugins/codex_provider/auth.py:75` |
| 25 | `src/aigateway/routes/oauth_connections.py:56` |
| 22 | `src/aigateway/plugins/gemini_provider/chat_handler.py:196` |

### Top offenders — test code (`tests/`)

| Statements | File:line |
|-----------:|-----------|
| 25 | `tests/unit/gemini/test_chat_handler.py:97` |
| 23 | `tests/unit/test_auth_routes.py:139` |
| 23 | `tests/unit/gemini/test_gemini_routes.py:201` |
| 23 | `tests/unit/gemini/test_gemini_provider.py:15` |
| 22 | `tests/unit/test_auth_routes.py:482` |
| 22 | `tests/unit/anthropic/test_bootstrap.py:106` |
| 21 | `tests/unit/gemini/test_gemini_routes.py:351` |
| 21 | `tests/unit/gemini/test_gemini_routes.py:296` |
| 20 | `tests/unit/test_oauth_connections_routes.py:174` |
| 20 | `tests/unit/test_oauth_connections_routes.py:137` |

## PLR0912 — Too many branches

- **Day-1 threshold:** `max-branches = 24`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

| Branches | File:line |
|---------:|-----------|
| 24 | `src/aigateway/routes/chat.py:224` |
| 13 | `src/aigateway/plugins/gemini_provider/message_adapter.py:130` |
| 13 | `src/aigateway/plugins/gemini_provider/message_adapter.py:15` |
| 11 | `src/aigateway/routes/auth.py:473` |
| 10 | `src/aigateway/routes/auth.py:593` |
| 10 | `src/aigateway/routes/auth.py:186` |
|  9 | `src/aigateway/plugins/codex_provider/auth.py:75` |
|  9 | `src/aigateway/main.py:100` |
|  7 | `src/aigateway/plugins/codex_provider/chat_handler.py:188` |
|  7 | `src/aigateway/plugins/codex_provider/chat_handler.py:148` |

### Top offenders — test code (`tests/`)

| Branches | File:line |
|---------:|-----------|
| 4 | `tests/live/test_ollama_live.py:75` |

## PLR0911 — Too many return statements

- **Day-1 threshold:** `max-returns = 8`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

| Returns | File:line |
|--------:|-----------|
| 8 | `src/aigateway/core/auth/log_filter.py:37` |
| 6 | `src/aigateway/routes/auth.py:186` |
| 6 | `src/aigateway/routes/auth.py:137` |
| 6 | `src/aigateway/plugins/gemini_provider/auth.py:77` |
| 5 | `src/aigateway/plugins/ollama_provider/discovery.py:134` |
| 5 | `src/aigateway/plugins/ollama_provider/discovery.py:84` |
| 5 | `src/aigateway/plugins/gemini_provider/auth.py:127` |
| 5 | `src/aigateway/core/auth/local_only.py:12` |
| 4 | `src/aigateway/routes/auth.py:697` |
| 4 | `src/aigateway/plugins/gemini_provider/auth.py:53` |

### Top offenders — test code (`tests/`)

| Returns | File:line |
|--------:|-----------|
| 4 | `tests/live/test_ollama_live.py:94` |

## PLR1702 — Too many nested blocks (no tunable)

No violations at baseline (neither `src/` nor `tests/`). Rule is preview-only in ruff
0.15.x; included in `select` so any future violations are surfaced once the rule
promotes to stable or preview is enabled.

## Tightening roadmap (one PR per ratchet)

1. C901 max-complexity: target 10 (industry default).
2. PLR0915 max-statements: target 50.
3. PLR0912 max-branches: target 12.
4. PLR0911 max-returns: target 6.
5. Promote PLR0913 (too-many-arguments) to enforced once Pydantic/FastAPI dependency-injection patterns have been audited for per-file ignores.
