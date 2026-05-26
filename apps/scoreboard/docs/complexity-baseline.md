# Complexity Baseline — apps/scoreboard (SF-218)

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

- **Day-1 threshold:** `max-complexity = 8`
- **Top offenders:**

| Complexity | File:line |
|-----------:|-----------|
| 8 | `src/scoreboard/scores/store.py:135` |
| 6 | `src/scoreboard/routes/scores.py:70` |
| 3 | `src/scoreboard/routes/scores.py:119` |
| 3 | `src/scoreboard/main.py:24` |
| 2 | `src/scoreboard/scores/store.py:202` |
| 2 | `src/scoreboard/scores/store.py:189` |
| 2 | `src/scoreboard/scores/schemas.py:101` |
| 2 | `src/scoreboard/scores/schemas.py:95` |
| 2 | `src/scoreboard/scores/schemas.py:88` |
| 2 | `src/scoreboard/scores/schemas.py:81` |

## PLR0915 — Too many statements

- **Day-1 threshold:** `max-statements = 18`
- **Top offenders:**

| Statements | File:line |
|-----------:|-----------|
| 18 | `src/scoreboard/scores/store.py:135` |
| 15 | `src/scoreboard/routes/scores.py:70` |
| 10 | `src/scoreboard/main.py:24` |
|  7 | `src/scoreboard/routes/scores.py:119` |
|  6 | `src/scoreboard/main.py:16` |

## PLR0912 — Too many branches

- **Day-1 threshold:** `max-branches = 7`
- **Top offenders:**

| Branches | File:line |
|---------:|-----------|
| 7 | `src/scoreboard/scores/store.py:135` |
| 5 | `src/scoreboard/routes/scores.py:70` |

## PLR0911 — Too many return statements

- **Day-1 threshold:** `max-returns = 3`
- **Top offenders:**

| Returns | File:line |
|--------:|-----------|
| 3 | `src/scoreboard/scores/store.py:135` |

## PLR1702 — Too many nested blocks (no tunable)

No violations at baseline. Rule is preview-only in ruff 0.15.x; included in `select` so any future violations are surfaced once the rule promotes to stable or preview is enabled.

## Tightening roadmap (one PR per ratchet)

1. C901 max-complexity: target 10 (industry default).
2. PLR0915 max-statements: target 50.
3. PLR0912 max-branches: target 12.
4. PLR0911 max-returns: target 6.
5. Promote PLR0913 (too-many-arguments) to enforced once Pydantic/FastAPI dependency-injection patterns have been audited for per-file ignores.
