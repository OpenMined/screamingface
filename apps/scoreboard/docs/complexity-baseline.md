# Complexity Baseline — apps/scoreboard (SF-218)

Captured on 2026-05-26 from commit `0cca2ae`. Re-baselined on 2026-05-26 to include
`tests/` after CI was observed running `ruff check` from the app root (full repo scope),
not `src/` only. The original PLR0915 threshold (18) was set against `src/` but
`tests/conftest.py:43` raises the high-water mark to 26 — the threshold has been
bumped accordingly.

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

- **Day-1 threshold:** `max-complexity = 8`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

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

### Top offenders — test code (`tests/`)

| Complexity | File:line |
|-----------:|-----------|
| 4 | `tests/conftest.py:43` |
| 3 | `tests/unit/scores/test_schemas.py:76` |
| 3 | `tests/unit/scores/test_schemas.py:64` |
| 3 | `tests/unit/scores/test_schemas.py:52` |
| 3 | `tests/unit/scores/test_schemas.py:40` |
| 3 | `tests/unit/scores/test_schemas.py:28` |
| 3 | `tests/unit/scores/test_models.py:46` |
| 2 | `tests/unit/test_scores_routes.py:193` |
| 2 | `tests/unit/test_leaderboard_routes.py:202` |
| 2 | `tests/unit/test_leaderboard_routes.py:138` |

## PLR0915 — Too many statements

- **Day-1 threshold:** `max-statements = 26` (raised from 18 to accommodate a tests/-side offender)
- **High-water came from:** `tests/` (`tests/conftest.py:43` at 26 statements)

### Top offenders — production code (`src/`)

| Statements | File:line |
|-----------:|-----------|
| 18 | `src/scoreboard/scores/store.py:135` |
| 15 | `src/scoreboard/routes/scores.py:70` |
| 10 | `src/scoreboard/main.py:24` |
|  7 | `src/scoreboard/routes/scores.py:119` |
|  6 | `src/scoreboard/main.py:16` |

### Top offenders — test code (`tests/`)

| Statements | File:line |
|-----------:|-----------|
| 26 | `tests/conftest.py:43` |
| 18 | `tests/unit/test_leaderboard_routes.py:91` |
| 15 | `tests/unit/test_leaderboard_routes.py:165` |
| 14 | `tests/unit/test_scores_routes.py:225` |
| 11 | `tests/unit/test_leaderboard_routes.py:116` |
| 11 | `tests/unit/scores/test_store.py:66` |
| 10 | `tests/unit/test_leaderboard_routes.py:138` |
| 10 | `tests/unit/test_leaderboard_routes.py:74` |
| 10 | `tests/unit/scores/test_store.py:128` |
|  9 | `tests/unit/test_leaderboard_routes.py:240` |

## PLR0912 — Too many branches

- **Day-1 threshold:** `max-branches = 7`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

| Branches | File:line |
|---------:|-----------|
| 7 | `src/scoreboard/scores/store.py:135` |
| 5 | `src/scoreboard/routes/scores.py:70` |

### Top offenders — test code (`tests/`)

No violations.

## PLR0911 — Too many return statements

- **Day-1 threshold:** `max-returns = 3`
- **High-water came from:** `src/`

### Top offenders — production code (`src/`)

| Returns | File:line |
|--------:|-----------|
| 3 | `src/scoreboard/scores/store.py:135` |

### Top offenders — test code (`tests/`)

No violations.

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
