# SF-218: Python code complexity analysis on pre-commit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror SF-210 on the Python side: enable McCabe + Pylint-refactor complexity rules in ruff for each Python app (apps/server, apps/aigateway, apps/scoreboard), with thresholds set just above each app's current high-water mark so day 1 is green, and the rules ride through the existing ruff pre-commit hook.

**Architecture:** Extend `[tool.ruff.lint]` in each of the 3 pyproject.toml files to `select` the McCabe (`C901`) and Pylint refactor (`PLR09xx`, `PLR1702`) complexity rules. Per-rule thresholds go in `[tool.ruff.lint.mccabe]` and `[tool.ruff.lint.pylint]`. The existing `apps/server/.pre-commit-config.yaml` already runs `ruff check --fix` on Python files — adding rules is enough, no hook plumbing changes. Each app gets its own baseline doc so future tightening PRs reference a per-app "from → to" table.

**Tech Stack:** Python 3.12, ruff v0.9.x (pinned in `.pre-commit-config.yaml`), uv-managed envs, existing pre-commit infra.

**Asana:** [SF-218](https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215118841850238).

**Branch:** `SF-218-python-complexity-precommit` (already created from `origin/main`).

**Companion ticket:** SF-210 (merged in #208) — same shape on the JS/TS side. The `apps/desktop/docs/complexity-baseline.md` is the structural template to copy.

**Out of scope (separate tickets if pursued):** xenon for cognitive-complexity (richer metric, separate pre-commit invocation), radon reporting tooling, refactoring the existing high-CC functions (each tightening is its own PR), the `web-iterations/` Python (none) and `cloud/` (none) trees.

---

## File Structure

- Modify: `apps/server/pyproject.toml` — extend `[tool.ruff.lint] select` and add `[tool.ruff.lint.mccabe]` + `[tool.ruff.lint.pylint]` sections.
- Modify: `apps/aigateway/pyproject.toml` — same shape.
- Modify: `apps/scoreboard/pyproject.toml` — same shape.
- Create: `apps/server/docs/complexity-baseline.md` — per-app baseline.
- Create: `apps/aigateway/docs/complexity-baseline.md` — per-app baseline.
- Create: `apps/scoreboard/docs/complexity-baseline.md` — per-app baseline.
- Create: `docs/superpowers/plans/SF-218-python-complexity-precommit.md` — this plan (already created).

No edits to `.pre-commit-config.yaml`. No edits outside the 3 Python apps.

## Rule selection rationale

Ruff already runs on every Python commit via the existing hook, and it bundles all the relevant complexity rules — picking ruff means **zero new tooling, zero new orchestration**, and a single config file per app.

Initial enforced rules:
- **`C901`** (mccabe cyclomatic complexity per function) — the foundational complexity gate. Threshold: `[tool.ruff.lint.mccabe] max-complexity`.
- **`PLR0915`** (too-many-statements per function) — catches "the function that does everything". Threshold: `[tool.ruff.lint.pylint] max-statements`.
- **`PLR0912`** (too-many-branches) — flags deep `if`/`elif`/`except` chains. Threshold: `max-branches`.
- **`PLR0911`** (too-many-return-statements) — multiple-exit functions get hard to reason about. Threshold: `max-returns`.
- **`PLR1702`** (too-many-nested-blocks) — pure nesting depth. No tunable; if a function exceeds the built-in cap, refactor.

**Deliberately NOT enforcing yet** (collect as `warn`/observe only — would be a follow-up):
- `PLR0913` (too-many-arguments) — would fight FastAPI dependency-injection routes and Pydantic models; needs a high threshold or per-file ignores in those areas. Defer to a follow-up.
- `PLR0904` (too-many-public-methods) — class-level metric, not function-level; defer.

**About `--statistics`:** ruff supports `--statistics` to count violations per rule. We use it for the baseline pass.

---

## Task 1: Inspect current state and baseline apps/server

**Files:** none yet (read-only baselining).

- [ ] **Step 1: Sanity-check ruff version**

```bash
cd /Users/sergey/work/openmind/screamingface
grep '^uv = \|astral-sh/ruff-pre-commit' apps/server/.pre-commit-config.yaml
cd apps/server && uv run ruff --version
```

Expected: ruff version 0.9.x or later. The rules listed in this plan exist in 0.9+.

- [ ] **Step 2: Baseline apps/server — unrestricted violations**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
# Run each rule at its lowest meaningful threshold so we see every offender.
# C901 has max-complexity=1 to surface every function.
uv run ruff check src \
  --select C901,PLR0911,PLR0912,PLR0915,PLR1702 \
  --no-fix \
  --output-format json \
  --config 'lint.mccabe.max-complexity = 1' \
  --config 'lint.pylint.max-statements = 5' \
  --config 'lint.pylint.max-branches = 3' \
  --config 'lint.pylint.max-returns = 2' \
  > /tmp/sf218-server-baseline.json 2>&1 || true
```

Note: `--config 'key = value'` is ruff's CLI override syntax for ad-hoc settings. The `|| true` keeps the shell happy when violations exist.

- [ ] **Step 3: Extract worst-case values per rule for apps/server**

```bash
python3 <<'PY'
import json, re
from collections import defaultdict

data = json.load(open('/tmp/sf218-server-baseline.json'))

# Each violation message embeds the actual measured value. Parse it.
patterns = {
    'C901': re.compile(r'is too complex \((\d+)'),
    'PLR0915': re.compile(r'\((\d+) > \d+\)'),
    'PLR0912': re.compile(r'\((\d+) > \d+\)'),
    'PLR0911': re.compile(r'\((\d+) > \d+\)'),
    'PLR1702': re.compile(r'\((\d+) > \d+\)'),
}

by_rule = defaultdict(list)
for v in data:
    code = v.get('code')
    if code not in patterns: continue
    msg = v.get('message', '')
    mm = patterns[code].search(msg)
    if not mm: continue
    by_rule[code].append((int(mm.group(1)), v['filename'], v['location']['row']))

for code in ['C901', 'PLR0915', 'PLR0912', 'PLR0911', 'PLR1702']:
    rows = sorted(by_rule[code], reverse=True)
    print(f'=== {code} — {len(rows)} violations — max {rows[0][0] if rows else 0} ===')
    for v, f, l in rows[:10]:
        print(f'  {v:4d}  {f.split("apps/server/")[-1]}:{l}')
    print()
PY
```

Expected: per-rule max + top-10 offenders for apps/server. Record them for the baseline doc.

- [ ] **Step 4: Repeat baseline for apps/aigateway**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/aigateway
uv run ruff check src \
  --select C901,PLR0911,PLR0912,PLR0915,PLR1702 \
  --no-fix --output-format json \
  --config 'lint.mccabe.max-complexity = 1' \
  --config 'lint.pylint.max-statements = 5' \
  --config 'lint.pylint.max-branches = 3' \
  --config 'lint.pylint.max-returns = 2' \
  > /tmp/sf218-aigateway-baseline.json 2>&1 || true
```

Run the same Python extraction script against `/tmp/sf218-aigateway-baseline.json`. Record max + top-10.

- [ ] **Step 5: Repeat baseline for apps/scoreboard**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/scoreboard
uv run ruff check src \
  --select C901,PLR0911,PLR0912,PLR0915,PLR1702 \
  --no-fix --output-format json \
  --config 'lint.mccabe.max-complexity = 1' \
  --config 'lint.pylint.max-statements = 5' \
  --config 'lint.pylint.max-branches = 3' \
  --config 'lint.pylint.max-returns = 2' \
  > /tmp/sf218-scoreboard-baseline.json 2>&1 || true
```

Run the same extraction. Record per-app maxes.

- [ ] **Step 6: Decide per-rule day-1 thresholds**

For each app and each rule:
- **Threshold = the max value observed in that app, exactly.** No buffer. The file at the max IS at the limit.
- If a rule has zero violations across the app, use the industry/ruff default:
  - C901 max-complexity: 10
  - PLR0915 max-statements: 50
  - PLR0912 max-branches: 12
  - PLR0911 max-returns: 6

- [ ] **Step 7: Don't commit anything yet** — Task 2 enables rules + writes the docs in one cohesive commit per app.

---

## Task 2: Wire rules + baseline doc for apps/server

**Files:**
- Modify: `apps/server/pyproject.toml`
- Create: `apps/server/docs/complexity-baseline.md`

- [ ] **Step 1: Extend `[tool.ruff.lint]` in `apps/server/pyproject.toml`**

The current shape is:
```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
```

Replace with:
```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "C901", "PLR0911", "PLR0912", "PLR0915", "PLR1702"]

[tool.ruff.lint.mccabe]
# Day-1 threshold — see apps/server/docs/complexity-baseline.md
max-complexity = <SERVER_MAX_C901>

[tool.ruff.lint.pylint]
# Day-1 thresholds — see apps/server/docs/complexity-baseline.md
max-statements = <SERVER_MAX_PLR0915>
max-branches = <SERVER_MAX_PLR0912>
max-returns = <SERVER_MAX_PLR0911>
```

Replace each `<SERVER_MAX_*>` with the integer measured in Task 1 Step 3.

- [ ] **Step 2: Run ruff with the new config to confirm day-1 passes**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/server
uv run ruff check src --no-fix --statistics
```

Expected: exit code 0. Statistics may show counts of the new rules in case of unrelated existing violations — but for the complexity rules specifically, zero.

If a complexity rule still fires at the configured threshold, the threshold isn't right — re-check Task 1 Step 3's extraction or the rule code:msg parser. Don't fudge the threshold up — the goal is to know the real high-water mark.

- [ ] **Step 3: Create `apps/server/docs/complexity-baseline.md`**

Use this template, filling in real numbers from Task 1 Step 3:

```markdown
# Complexity Baseline — apps/server (SF-218)

Captured on 2026-05-26 from commit `<short-sha>` (run `git rev-parse --short HEAD`).

These are the high-water marks the day-1 thresholds were set to accommodate. Each tightening PR (one rule, one ratchet at a time) should reference this file and the file:line below it's reducing.

## C901 — McCabe cyclomatic complexity

- **Day-1 threshold:** `max-complexity = <SERVER_MAX_C901>`
- **Top offenders:**

| Complexity | File:line |
|-----------:|-----------|
| <N>        | `<path>:<line>` |
| ...        | up to 10 rows |

## PLR0915 — Too many statements

- **Day-1 threshold:** `max-statements = <SERVER_MAX_PLR0915>`
- **Top offenders:** (same table shape)

## PLR0912 — Too many branches

- **Day-1 threshold:** `max-branches = <SERVER_MAX_PLR0912>`
- **Top offenders:**

## PLR0911 — Too many return statements

- **Day-1 threshold:** `max-returns = <SERVER_MAX_PLR0911>`
- **Top offenders:**

## PLR1702 — Too many nested blocks (no tunable)

If any violations exist they cannot be muted without a per-line `# noqa: PLR1702`. List them here as known-debt:

- `<path>:<line>` — <N> nested blocks

## Tightening roadmap (one PR per ratchet)

1. C901 max-complexity: target 10 (industry default).
2. PLR0915 max-statements: target 50.
3. PLR0912 max-branches: target 12.
4. PLR0911 max-returns: target 6.
5. Promote PLR0913 (too-many-arguments) to enforced once Pydantic/FastAPI dependency-injection patterns have been audited for per-file ignores.
```

- [ ] **Step 4: Run pre-commit-style check**

```bash
cd /Users/sergey/work/openmind/screamingface
uv run --directory apps/server ruff check apps/server/src --no-fix
```

Exit 0 expected (same as Step 2; sanity-double-checking).

- [ ] **Step 5: Commit apps/server changes**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/server/pyproject.toml apps/server/docs/complexity-baseline.md
git commit -m "SF-218: enforce ruff complexity rules for apps/server (day-1 baseline)"
```

---

## Task 3: Wire rules + baseline doc for apps/aigateway

**Files:**
- Modify: `apps/aigateway/pyproject.toml`
- Create: `apps/aigateway/docs/complexity-baseline.md`

Repeat Task 2 verbatim, substituting `apps/aigateway` everywhere and using the numbers measured for aigateway in Task 1 Step 4.

- [ ] **Step 1: Extend `[tool.ruff.lint]`** with the same select list and 4 threshold settings. Use `<AIGATEWAY_MAX_*>` integers from Task 1 Step 4.

- [ ] **Step 2: Confirm green** — `cd apps/aigateway && uv run ruff check src --no-fix` exits 0.

- [ ] **Step 3: Create `apps/aigateway/docs/complexity-baseline.md`** with the aigateway-specific numbers and the same template.

- [ ] **Step 4: Commit**:
```bash
git add apps/aigateway/pyproject.toml apps/aigateway/docs/complexity-baseline.md
git commit -m "SF-218: enforce ruff complexity rules for apps/aigateway (day-1 baseline)"
```

---

## Task 4: Wire rules + baseline doc for apps/scoreboard

**Files:**
- Modify: `apps/scoreboard/pyproject.toml`
- Create: `apps/scoreboard/docs/complexity-baseline.md`

Same as Task 2/3 but for scoreboard.

- [ ] **Step 1:** Extend `[tool.ruff.lint]` with the same select list and 4 thresholds. Use `<SCOREBOARD_MAX_*>` from Task 1 Step 5.

- [ ] **Step 2:** `cd apps/scoreboard && uv run ruff check src --no-fix` exits 0.

- [ ] **Step 3:** Create `apps/scoreboard/docs/complexity-baseline.md`.

- [ ] **Step 4:** Commit:
```bash
git add apps/scoreboard/pyproject.toml apps/scoreboard/docs/complexity-baseline.md
git commit -m "SF-218: enforce ruff complexity rules for apps/scoreboard (day-1 baseline)"
```

---

## Task 5: Verify pre-commit hook picks up the new rules

**Files:** none (verification only — no commit).

- [ ] **Step 1: Construct a canary file that violates C901**

```bash
cd /Users/sergey/work/openmind/screamingface
cat > apps/server/src/screamingface/__canary__.py <<'PY'
"""Intentionally complex — SF-218 canary, DO NOT MERGE."""

def tangled(a, b, c, d):
    total = 0
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    for i in range(a):
                        for j in range(b):
                            if i + j > c:
                                total += i * j
                            elif i - j > d:
                                total -= i
                            else:
                                total += 1
                                if total > 100:
                                    total -= 50
    return total
PY
git add apps/server/src/screamingface/__canary__.py
```

- [ ] **Step 2: Attempt commit — expect rejection**

```bash
git commit -m "SF-218: canary — DO NOT MERGE" 2>&1 | tail -20
```

Expected: pre-commit hook runs ruff, which fires on the canary with `C901` (and likely also `PLR0912`, `PLR1702`). Commit is rejected. If the commit goes through, the gate isn't wired — STOP and investigate.

- [ ] **Step 3: Clean up the canary**

```bash
git reset HEAD apps/server/src/screamingface/__canary__.py
rm apps/server/src/screamingface/__canary__.py
git status --short
```

Expected: no canary file, no staged changes. (The pre-commit hook should also have left no `--fix` modifications since the canary is a brand-new file.)

---

## Task 6: Push branch and open PR

**Files:** none (process).

- [ ] **Step 1: Confirm clean working tree and pushable history**

```bash
cd /Users/sergey/work/openmind/screamingface
git log --oneline origin/main..HEAD
git status --short
```

Expected: 4 commits ahead of main (one plan + three "enforce ruff complexity rules" commits, one per app). No uncommitted changes.

- [ ] **Step 2: Push**

```bash
git push -u origin SF-218-python-complexity-precommit
```

- [ ] **Step 3: Open PR (do not merge)**

```bash
gh pr create --base main --head SF-218-python-complexity-precommit \
  --title "SF-218: Python code complexity analysis on pre-commit" \
  --body "$(cat <<'EOF'
## Summary
Mirror of SF-210 (#208) for the Python side. Enable McCabe + Pylint-refactor complexity rules in ruff for the three Python apps, with day-1 thresholds set just above each app's current high-water mark so the existing tree passes; future regressions are blocked through the existing ruff pre-commit hook.

- Extend `[tool.ruff.lint] select` in each of `apps/server`, `apps/aigateway`, `apps/scoreboard` with: `C901, PLR0911, PLR0912, PLR0915, PLR1702`.
- Per-app `[tool.ruff.lint.mccabe]` and `[tool.ruff.lint.pylint]` sections set the thresholds.
- Per-app baseline doc at `apps/<name>/docs/complexity-baseline.md` listing top offenders + the tightening roadmap.

The rules ride through the existing `astral-sh/ruff-pre-commit` hook in `apps/server/.pre-commit-config.yaml` — no new hook plumbing.

## Per-app day-1 thresholds
| App | C901 | PLR0915 | PLR0912 | PLR0911 |
|---|---:|---:|---:|---:|
| apps/server | <SERVER_C901> | <SERVER_PLR0915> | <SERVER_PLR0912> | <SERVER_PLR0911> |
| apps/aigateway | <AIGW_C901> | <AIGW_PLR0915> | <AIGW_PLR0912> | <AIGW_PLR0911> |
| apps/scoreboard | <SCORE_C901> | <SCORE_PLR0915> | <SCORE_PLR0912> | <SCORE_PLR0911> |

Top offenders in each app's `docs/complexity-baseline.md`.

## Tightening roadmap (each = separate PR)
1. C901 max-complexity → 10 (industry default).
2. PLR0915 max-statements → 50.
3. PLR0912 max-branches → 12.
4. PLR0911 max-returns → 6.
5. Promote PLR0913 (too-many-arguments) to enforced once FastAPI/Pydantic dependency-injection patterns are audited.

## Test plan
- [x] `uv run ruff check src --no-fix` exits 0 in each of the 3 apps with the new config.
- [x] Canary file violating C901 was rejected by the pre-commit hook — confirmed gate works.
- [x] `git status` clean after canary removal.
- [ ] Reviewer: spot-check each baseline doc against a fresh local `uv run ruff check src --select <rule> --statistics`.

Asana: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215118841850238
Plan: docs/superpowers/plans/SF-218-python-complexity-precommit.md
Companion: SF-210 (#208)
EOF
)"
```

Fill in the table from the real numbers measured in Task 1. Stop here. Per project rules: do not merge.

---

## Self-Review Notes

- **Spec coverage:**
  - Step 1 of ticket (inventory): Task 1 Steps 2-5 baseline each app.
  - Step 2 (baseline + thresholds that pass today): Task 1 Step 6 picks thresholds == observed max.
  - Step 3 (wire into pre-commit): no new wiring — the existing `astral-sh/ruff-pre-commit` hook reads each app's pyproject.toml. Adding rules in pyproject is the wiring. Task 5 verifies via a canary.
  - Step 4 (tighten in steps): roadmap captured in PR body and in each baseline doc.
- **No placeholders:** `<SERVER_MAX_*>` / `<AIGATEWAY_MAX_*>` / `<SCOREBOARD_MAX_*>` are intentional — they are real integers the engineer reads from the Task 1 extraction output and substitutes. Each has an explicit fallback rule (industry default) if Task 1 produces zero violations for that rule in that app.
- **Type consistency:** Rule codes used consistently (`C901`, `PLR0915`, `PLR0912`, `PLR0911`, `PLR1702`). The TOML section names (`[tool.ruff.lint.mccabe]`, `[tool.ruff.lint.pylint]`) and setting names (`max-complexity`, `max-statements`, `max-branches`, `max-returns`) match ruff's documented config schema.
- **Per-app scope:** Each app gets its own pyproject + its own baseline doc, mirroring the existing per-app convention. No shared root config.
- **Pre-commit hook location:** `apps/server/.pre-commit-config.yaml` runs ruff. The hook reads each Python file's enclosing pyproject (via ruff's config-file discovery), so per-app settings apply correctly even though the hook config lives in apps/server. Sanity-check this assumption holds in Task 5 — if the canary in `apps/server/src/...` doesn't trip the server-specific threshold, the discovery path is broken and we need to either move the hook config or use `--config` arg.
