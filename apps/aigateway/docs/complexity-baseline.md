# Complexity Baseline — apps/aigateway (SF-218)

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

- **Day-1 threshold:** `max-complexity = 25`
- **Top offenders:**

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

## PLR0915 — Too many statements

- **Day-1 threshold:** `max-statements = 76`
- **Top offenders:**

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

## PLR0912 — Too many branches

- **Day-1 threshold:** `max-branches = 24`
- **Top offenders:**

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

## PLR0911 — Too many return statements

- **Day-1 threshold:** `max-returns = 8`
- **Top offenders:**

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

## PLR1702 — Too many nested blocks (no tunable)

No violations at baseline. Rule is preview-only in ruff 0.15.x; included in `select` so any future violations are surfaced once the rule promotes to stable or preview is enabled.

## Tightening roadmap (one PR per ratchet)

1. C901 max-complexity: target 10 (industry default).
2. PLR0915 max-statements: target 50.
3. PLR0912 max-branches: target 12.
4. PLR0911 max-returns: target 6.
5. Promote PLR0913 (too-many-arguments) to enforced once Pydantic/FastAPI dependency-injection patterns have been audited for per-file ignores.
