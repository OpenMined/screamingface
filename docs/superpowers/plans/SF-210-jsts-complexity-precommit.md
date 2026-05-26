# SF-210: JS/TS code complexity analysis on pre-commit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire JS/TS code-complexity analysis into the `apps/desktop` lint chain (and through it, the existing husky pre-commit hook) with thresholds set just above current high-water marks so day 1 is green and future regressions are blocked.

**Architecture:** Extend the existing ESLint flat config in `apps/desktop/eslint.config.mjs` with `eslint-plugin-sonarjs`. Use sonarjs's `cognitive-complexity` (preferred over plain cyclomatic — better signal for real-world code) plus a small set of structural-quality rules. Run an unrestricted baseline pass, document the worst-case values per metric, then set thresholds = ceil(worst-case). The husky pre-commit hook already runs `lint-staged` → `eslint --fix` on staged TS/TSX, so adding rules is enough — no hook plumbing changes.

**Tech Stack:** TypeScript 5 / React 19 / Electron / ESLint 9 (flat config) / `eslint-plugin-sonarjs` ^3.x / husky 9 / lint-staged 16 — all already installed except sonarjs.

**Asana:** [SF-210](https://app.asana.com/1/1185126988600652/task/1214965778747000), due 2026-05-25.

**Branch:** `SF-210-jsts-complexity-precommit` (already created from `origin/main`).

**Out of scope (separate tickets):** Python complexity (ruff `C901` / `xenon` at apps/server/.pre-commit-config.yaml), any `web-iterations/` JS/TS (archived demo iterations — see survey notes), gradual-tightening refactor PRs (one PR per tightening, opened once this baseline lands).

---

## File Structure

- Modify: `apps/desktop/package.json` — add `eslint-plugin-sonarjs` to devDependencies; add `lint:complexity` and `lint:complexity:report` npm scripts.
- Modify: `apps/desktop/eslint.config.mjs` — register the sonarjs plugin; add a rules block with the thresholds plus the small complementary rule set.
- Create: `apps/desktop/docs/complexity-baseline.md` — snapshot of worst-case values per metric so future tightening PRs have a "from → to" reference.
- Create: `docs/superpowers/plans/SF-210-jsts-complexity-precommit.md` — this plan (already created).

That's it. No husky/lint-staged config changes — the new rules ride on the existing eslint pre-commit invocation.

## Rule choice rationale

`eslint-plugin-sonarjs` is the standard for SonarSource-derived rules in JS/TS-land, used by SonarQube/SonarCloud. Picked over alternatives:
- **vs. ESLint's built-in `complexity` rule:** sonarjs's `cognitive-complexity` correlates better with what humans actually find hard to read (nesting + flow-breaking constructs weighted higher than simple branching). Built-in `complexity` is cyclomatic only.
- **vs. `ts-complex` / `code-complexity` / `madge` CLI tools:** those run out-of-band and need separate plumbing to enforce; sonarjs runs through the existing `eslint --fix` step on staged files, no new orchestration.
- **vs. `eslint-plugin-complexity`:** smaller scope, not maintained as actively.

Initial enforced rules (all sonarjs):
- `sonarjs/cognitive-complexity` — function-level cognitive load
- `sonarjs/no-identical-functions` — dedup
- `sonarjs/no-duplicate-string` — copy-paste detector
- `sonarjs/no-collapsible-if` — flatten unnecessary nesting

Everything else from sonarjs's recommended set goes to **warn** for now so we get signal without breaking commits.

---

## Task 1: Add sonarjs dependency and validate it loads

**Files:**
- Modify: `apps/desktop/package.json`

- [ ] **Step 1: Install the plugin**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/desktop
npm install --save-dev eslint-plugin-sonarjs
```

Expected: `package.json` gets a new line in `devDependencies` like `"eslint-plugin-sonarjs": "^3.0.x"`, `package-lock.json` updated.

- [ ] **Step 2: Verify plugin loads via a sentinel rule**

Temporarily add to `apps/desktop/eslint.config.mjs` after the existing imports:

```js
import sonarjsPlugin from 'eslint-plugin-sonarjs';
```

And inside the config object, add to `plugins`:
```js
sonarjs: sonarjsPlugin,
```

And to `rules`:
```js
'sonarjs/no-collapsible-if': 'error',
```

Run:
```bash
cd /Users/sergey/work/openmind/screamingface/apps/desktop
npx eslint src --max-warnings 0 --no-fix 2>&1 | tail -30
```

Expected: ESLint loads without "plugin not found" errors. May report sonarjs findings — that's fine for now, we're only checking the plugin loads.

- [ ] **Step 3: Commit the dependency**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/desktop/package.json apps/desktop/package-lock.json
git commit -m "SF-210: add eslint-plugin-sonarjs to apps/desktop"
```

---

## Task 2: Run unrestricted baseline to find worst-case values

**Files:**
- Modify: `apps/desktop/eslint.config.mjs` (temporary baseline config)

- [ ] **Step 1: Switch to baseline-mode config**

Replace the temporary single-rule block from Task 1 with this rules-section (still inside the same config block):

```js
rules: {
  ...tsPlugin.configs.recommended.rules,
  ...reactHooksPlugin.configs.recommended.rules,
  ...sonarjsPlugin.configs.recommended.rules,
  'react/react-in-jsx-scope': 'off',
  '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
  // Baseline collection: turn the metrics we care about to strict thresholds
  // so we see every violation. We'll relax these in Task 3.
  'sonarjs/cognitive-complexity': ['error', 5],
  'sonarjs/no-duplicate-string': ['error', { threshold: 3 }],
},
```

- [ ] **Step 2: Run lint and capture the violations**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/desktop
npx eslint src --no-fix --format json > /tmp/sf210-baseline.json 2>&1 || true
```

The `|| true` keeps the shell happy when there are errors (expected).

- [ ] **Step 3: Extract worst-case values per metric**

```bash
python3 <<'PY'
import json, re
data = json.load(open('/tmp/sf210-baseline.json'))
cc = []       # cognitive-complexity values
dup = []      # duplicate-string values
other = {}    # other sonarjs rule -> count
for f in data:
    for m in f.get('messages', []):
        rule = m.get('ruleId') or ''
        if rule == 'sonarjs/cognitive-complexity':
            # Message looks like: 'Refactor this function to reduce its Cognitive Complexity from 23 to the 5 allowed.'
            mm = re.search(r'from (\d+) to the', m['message'])
            if mm: cc.append((int(mm.group(1)), f['filePath'], m.get('line')))
        elif rule == 'sonarjs/no-duplicate-string':
            mm = re.search(r'(\d+) times', m['message'])
            if mm: dup.append((int(mm.group(1)), f['filePath'], m.get('line')))
        elif rule.startswith('sonarjs/'):
            other[rule] = other.get(rule, 0) + 1

cc.sort(reverse=True)
dup.sort(reverse=True)
print('=== cognitive-complexity worst 10 ===')
for v, f, l in cc[:10]:
    print(f'  {v:4d}  {f.split("apps/desktop/")[-1]}:{l}')
print('  max:', cc[0][0] if cc else 0)
print()
print('=== no-duplicate-string worst 10 ===')
for v, f, l in dup[:10]:
    print(f'  {v:4d}  {f.split("apps/desktop/")[-1]}:{l}')
print('  max:', dup[0][0] if dup else 0)
print()
print('=== other sonarjs rule counts ===')
for r, c in sorted(other.items(), key=lambda x: -x[1]):
    print(f'  {c:4d}  {r}')
PY
```

Expected: a list of worst offenders. Record the **max** cognitive-complexity and **max** duplicate-string count — those become the day-1 thresholds.

- [ ] **Step 4: Don't commit yet** — the baseline rules are intentionally too strict and will fail the commit hook. Move straight to Task 3.

---

## Task 3: Write the baseline doc and set day-1 thresholds

**Files:**
- Create: `apps/desktop/docs/complexity-baseline.md`
- Modify: `apps/desktop/eslint.config.mjs`

- [ ] **Step 1: Write the baseline doc**

Create `apps/desktop/docs/complexity-baseline.md` with the actual numbers captured in Task 2 Step 3. Template:

```markdown
# Complexity Baseline — apps/desktop (SF-210)

Captured on YYYY-MM-DD from commit `<short-sha-of-the-current-HEAD>`.

These are the high-water marks the day-1 thresholds were set to accommodate. Each tightening PR (one rule, one ratchet at a time) should reference this file and the file:line below it's reducing.

## sonarjs/cognitive-complexity

- **Day-1 threshold:** <max + 0, since we want exact ceiling — the file at the max value IS at the limit>
- **Top offenders:**
  | Cognitive complexity | File:line |
  |---:|---|
  | <N> | `<relative-path>:<line>` |
  | <N-1> | ... |
  | ... | up to 10 rows |

## sonarjs/no-duplicate-string

- **Day-1 threshold:** <max literal-count + 0>
- **Top offenders:**
  | Duplicate count | File:line |
  |---:|---|
  | ... |

## Other sonarjs/* rules (`warn` only, baseline counts)

| Rule | Count at baseline |
|---|---:|
| sonarjs/<rule-id> | <N> |
| ... |

## Tightening roadmap

The intent is to ratchet thresholds down one rule at a time:
1. cognitive-complexity: target 15 (industry default), then 10
2. no-duplicate-string: target 5
3. Promote one warn-level rule to error per follow-up PR

Each tightening is its own ticket + PR. See SF-210's PR body for the tracked sequence.
```

Use exact numbers from Task 2.

- [ ] **Step 2: Set day-1 thresholds in eslint.config.mjs**

Replace the rules block from Task 2 with the production version. The thresholds use the worst values you observed; the recommended set goes to `warn`.

```js
rules: {
  ...tsPlugin.configs.recommended.rules,
  ...reactHooksPlugin.configs.recommended.rules,
  // sonarjs recommended set as warnings — baseline visibility, no commit blocking
  ...Object.fromEntries(
    Object.entries(sonarjsPlugin.configs.recommended.rules).map(([k, v]) => [
      k,
      Array.isArray(v) ? ['warn', ...v.slice(1)] : 'warn',
    ]),
  ),
  'react/react-in-jsx-scope': 'off',
  '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
  // Hard-enforced complexity gates — set just above current worst-case so
  // day 1 passes. See apps/desktop/docs/complexity-baseline.md for current
  // high-water marks and the tightening roadmap.
  'sonarjs/cognitive-complexity': ['error', <WORST_CC>],
  'sonarjs/no-duplicate-string': ['error', { threshold: <WORST_DUP> }],
  'sonarjs/no-identical-functions': 'error',
  'sonarjs/no-collapsible-if': 'error',
},
```

Replace `<WORST_CC>` and `<WORST_DUP>` with the integers captured in Task 2. If for some unlikely reason there are zero violations of either, use industry defaults: 15 for cognitive-complexity, 5 for duplicate-string.

- [ ] **Step 3: Run lint to confirm day-1 passes**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/desktop
npx eslint src --no-fix
```

Expected: exit code 0. Warnings allowed (these are the recommended-set rules in warn mode); errors must be zero. If errors exist, the threshold isn't high enough — bump it up by one or investigate which file was missed.

- [ ] **Step 4: Run npm run lint to confirm it integrates cleanly**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/desktop
npm run lint
```

Expected: completes without exiting non-zero. `eslint . --fix` may auto-fix some sonarjs findings (e.g. `no-collapsible-if` could merge `if (a) { if (b) ... }`). Inspect any auto-fixes via `git diff`; if they look correct keep them, otherwise revert and add the affected file to `.eslintignore` for now (note in the baseline doc).

- [ ] **Step 5: Commit the config + baseline doc**

```bash
cd /Users/sergey/work/openmind/screamingface
git add apps/desktop/eslint.config.mjs apps/desktop/docs/complexity-baseline.md
# Include any clean auto-fixes from Step 4:
git add -u apps/desktop/src
git commit -m "SF-210: enforce sonarjs complexity gates in apps/desktop eslint"
```

---

## Task 4: Validate the pre-commit hook picks up the new rules

**Files:** none (verification only)

- [ ] **Step 1: Stage a deliberately-bad TS file and try to commit**

```bash
cd /Users/sergey/work/openmind/screamingface
cat > /tmp/sf210-canary.ts <<'TS'
// Intentionally exceeds cognitive complexity to verify the pre-commit hook blocks it.
export function tangled(a: number, b: number, c: number, d: number): number {
  let total = 0;
  if (a > 0) { if (b > 0) { if (c > 0) { if (d > 0) { for (let i = 0; i < a; i++) { for (let j = 0; j < b; j++) { if (i + j > c) { total += i * j; } else if (i - j > d) { total -= i; } else { total += 1; } } } } } } }
  return total;
}
TS
cp /tmp/sf210-canary.ts apps/desktop/src/renderer/src/__canary__.ts
git add apps/desktop/src/renderer/src/__canary__.ts
git commit -m "SF-210: canary — DO NOT MERGE" 2>&1 | tail -20
```

Expected: commit is rejected by the husky pre-commit hook with a sonarjs/cognitive-complexity error pointing at `__canary__.ts`.

- [ ] **Step 2: Clean up the canary**

```bash
cd /Users/sergey/work/openmind/screamingface
git reset HEAD apps/desktop/src/renderer/src/__canary__.ts
rm apps/desktop/src/renderer/src/__canary__.ts
git status --short
```

Expected: no canary file remaining, no staged changes left over from it.

- [ ] **Step 3: Confirm the existing CI test workflow still passes locally**

```bash
cd /Users/sergey/work/openmind/screamingface/apps/desktop
npm test 2>&1 | tail -10
```

If `npm test` isn't defined or runs unrelated work, skip; the gate that actually matters is the next commit going through pre-commit cleanly.

- [ ] **Step 4: Make a no-op commit to confirm the hook is green on healthy code**

If steps 1-3 left no changes, skip. Otherwise, make one trivial whitespace-touch in a low-complexity file and try a real commit (then immediately undo it). The point is to see lint-staged report green on real code.

---

## Task 5: Push and open PR

**Files:** none (process).

- [ ] **Step 1: Push branch**

```bash
cd /Users/sergey/work/openmind/screamingface
git push -u origin SF-210-jsts-complexity-precommit
```

- [ ] **Step 2: Open PR (do not merge)**

```bash
gh pr create --base main --head SF-210-jsts-complexity-precommit \
  --title "SF-210: JS/TS code complexity analysis on pre-commit" \
  --body "$(cat <<'EOF'
## Summary
- Add `eslint-plugin-sonarjs` to `apps/desktop`.
- Hard-enforce `sonarjs/cognitive-complexity`, `sonarjs/no-duplicate-string`, `sonarjs/no-identical-functions`, `sonarjs/no-collapsible-if` at the day-1 high-water mark.
- Run the rest of the sonarjs recommended set at warn level for visibility.
- Commit a baseline doc (`apps/desktop/docs/complexity-baseline.md`) listing the worst current offenders so each follow-up tightening PR has a clear "from → to" target.

The rules run through the existing lint-staged → eslint --fix chain in the husky pre-commit hook — no new hook plumbing.

## Scope
- IN: `apps/desktop` (the only active JS/TS surface in the repo).
- OUT: `web-iterations/*` (archived demo iterations, no CI, no recent commits). Python complexity is a separate ticket.

## Tightening roadmap
Each ratchet is a separate PR:
1. cognitive-complexity → 15 (industry default), then → 10.
2. no-duplicate-string → 5.
3. Promote one warn-level rule to error per follow-up.

See `apps/desktop/docs/complexity-baseline.md` for the current numbers.

## Test plan
- [x] `npm run lint` exits 0 on current `apps/desktop/src`.
- [x] Canary file with cognitive-complexity > threshold is rejected by the pre-commit hook.
- [ ] Reviewer checks the baseline doc reflects reality (worst values match a fresh local lint run).

Asana: https://app.asana.com/1/1185126988600652/task/1214965778747000
Plan: docs/superpowers/plans/SF-210-jsts-complexity-precommit.md
EOF
)"
```

Stop here. Per project rules: do not merge.

---

## Self-Review Notes

- **Spec coverage:**
  - Step 1 of the ticket (inventory): the pre-plan survey already covered this; result was "scope = apps/desktop only".
  - Step 2 (baseline + thresholds the code passes today): Task 2 + Task 3 Steps 1-3.
  - Step 3 (wire into pre-commit): no new wiring needed — the existing husky → lint-staged → eslint chain in `apps/desktop/.husky/pre-commit` picks up the new rules automatically. Task 4 verifies this.
  - Step 4 (tighten in steps, each becomes a refactor PR): out of scope for this PR per the "Out of scope" note up top; the roadmap and baseline doc set the structure so each future PR knows what to target.
- **No placeholders:** The only `<WORST_CC>` / `<WORST_DUP>` placeholders are intentional — they're real integers the engineer reads off the Task 2 Step 3 output and substitutes in Task 3 Step 2. Each placeholder has an explicit fallback rule (industry default) if Task 2 produces zero violations.
- **Type consistency:** Plugin name `sonarjsPlugin`, npm package `eslint-plugin-sonarjs`, rule prefix `sonarjs/*` used consistently throughout.
- **Scope discipline:** No edits outside `apps/desktop/{package.json,package-lock.json,eslint.config.mjs,docs/}` and the plan file. Husky/lint-staged configs untouched. No `web-iterations/` changes.
