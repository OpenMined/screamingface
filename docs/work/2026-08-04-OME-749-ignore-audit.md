---
ticket: OME-749
stack: repo
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-749 — audit Dependabot ignore rules so they expire

Authored in an isolated worktree branched from `origin/main` at `b787cf5d`.

## Intent

This epic added `ignore` rules to `.github/dependabot.yml`. Each is justified and each names its
lifting condition **in a comment** — and that is precisely the weakness. When
`typescript-eslint` ships TS 7 support, nothing in this repo notices. The ignore quietly becomes
permanent.

Same failure shape as everything else this epic surfaced: `apps/server` alerts accruing against a
deleted tree, `public-docs` lint red for months because nothing ran it, the stack card claiming
OMDS after the migration. **Unverified state drifting because no mechanism checks it.**

An ignore is defensible only if it is *verifiable* and *expiring*. The current set is verifiable
but does not expire.

## Design

Two files plus a CI hook.

**`.github/dependabot-ignores.yml`** — a companion registry. Every ignore in `dependabot.yml` gets
an entry naming a **machine-checkable** blocker, not prose. Two blocker kinds cover the current
set:

- `npm_peer` — the blocking package's peer range for some dependency. The audit reads it live from
  the registry and asks: does it now admit the ignored range?
- `ci_matrix` — a workflow's version matrix. Asks: does it now cover the ignored version?

The second kind exists because one ignore is **not upstream-blocked at all**. `python >=3.14` is
blocked by *our own* CI matrices only covering 3.12/3.13. Python 3.14 works fine; we declined to
test it. The registry should say that honestly rather than dressing it as unsupported.

**`.claude/scripts/audit_dependabot_ignores.py`** — the checker. `.claude/scripts/**` is already a
`repo-checks.yml` trigger path, so it gains CI coverage without touching the workflow's filters.

## Failure semantics — deliberate, and the important design decision

- **Drift FAILS.** An ignore with no registry entry, or a registry entry with no ignore, is *our
  own* inconsistency — always fixable on the spot. This is what stops an undocumented ignore ever
  landing again.
- **A liftable ignore WARNS only.** Failing there would break someone's unrelated PR because
  *upstream published a release*. That trains people to disable the check, which is strictly worse
  than the rot it was meant to catch. Visibility comes from the scheduled run, not from blocking.

Getting this backwards would make the tool self-defeating, so it is stated here rather than left
implicit in an exit code.

## Ordering dependency

`origin/main` carries **5** ignore entries. #503 (`OME-748`, open) adds a sixth — `typescript >=7`
on `/public-docs`.

**Revised during the unit.** The plan was to cover all six here and merge after #503. That would
have created an ordering dependency and, in effect, a stacked pair — and this repo squash-merges,
where a stacked PR has already caused a branch to miss main once. Instead the registry covers
exactly the **5 on main**, so this PR is self-consistent in any merge order, and #503 carries its
own registry entry alongside its own ignore. A comment sits at that position in the registry with
the blocker already worked out.

## Planned changes

- `.github/dependabot-ignores.yml` — new registry, one entry per ignore on main (5)
- `.claude/scripts/audit_dependabot_ignores.py` — new checker
- `.github/workflows/repo-checks.yml` — add the audit step + a weekly `schedule:` trigger, since
  the whole point is detecting upstream change while our repo sits still

## Test plan

The audit is the artifact, so verification is behavioural — and the meaningful test is the
**negative** one:

1. **Green path** — run against the real config; every blocker must report *still blocking*,
   matching what was verified by hand on 2026-08-04.
2. **Detects a lift** — temporarily point one entry at a condition that is already satisfied, and
   confirm the audit reports it liftable. Without this, a check that always prints green is
   indistinguishable from one that works.
3. **Detects drift both ways** — remove an ignore from `dependabot.yml` (registry orphan), then
   remove a registry entry (undocumented ignore), and confirm each fails.

A check that has never been seen to fail is not a check.

## Acceptance

- Every ignore on main reports still-blocking against live data.
- The audit provably detects a lift, a registry orphan, and an undocumented ignore.
- Drift exits non-zero; a liftable ignore does not.
- Runs in `repo-checks.yml`, including on a weekly schedule.

## Outcome

- **Actual files:** as planned — the registry, the checker, and the `repo-checks.yml` wiring, plus
  this ledger and its `docs/tasks/` mirror.

- **Gates — all four planned tests, including the negatives:**

  | test | expected | result |
  |---|---|---|
  | green path against real config | exit 0, all blocking | ✅ 5/5 still blocking |
  | detects a lift | warn, exit **0** | ✅ `LIFTABLE` + GH annotation, exit 0 |
  | drift: undocumented ignore | exit **1** | ✅ `UNDOCUMENTED`, exit 1 |
  | drift: orphaned registry entry | exit **1** | ✅ `ORPHANED`, exit 1 |

  `check_loop_parity.py` still green (this unit touches `repo-checks.yml`). Config restored
  byte-identical after each destructive test — `git diff` clean.

  **A check that has never been seen to fail is not a check.** Tests 2–4 exist so this one has.

### It found a real bug on its first run — mine

The `ci_matrix` probe reads the workflow and prints what it sees, which exposed:

```
scoreboard-tests.yml python-version = ['3.12']
aigateway-tests.yml  python-version = ['3.12', '3.13']
url4-cloud-tests.yml python-version = ['3.12', '3.13']
```

`OME-747` moved `apps/scoreboard/Dockerfile` to Python **3.13**, justified by "every Python matrix
in the repo runs 3.12/3.13". True of two apps out of three — `scoreboard-tests.yml` pins a
**scalar** `"3.12"` with no matrix at all. So scoreboard now **ships 3.13 and tests 3.12**: exactly
the failure mode `OME-747` set out to prevent, caused by `OME-747`. I generalised from two
workflows without reading the third.

Filed as `OME-750`.

### The near-miss inside that finding

The probe's first version handled only **list**-shaped matrices. For scoreboard it fell through to
"no matrix found → still blocking" — the correct verdict, reached by accident, which would have
hidden the mismatch permanently. Fixed to read scalars too, with an `AIDEV-NOTE:` recording why
both shapes matter. A check that is right for the wrong reason is a check that will be wrong
later.

### Deliberate limits, recorded rather than hidden

- **Majors only, not full semver.** Every ignore we write is a major-boundary hold (`>=6`, `>=10`,
  `>=3.14`); a full semver implementation is a lot of surface to get subtly wrong for no gain. The
  `AIDEV-NOTE:` names the function to replace if that ever changes.
- **Unrecognised ranges return "liftable".** A false warning costs a glance; false silence costs
  the entire point of the script. Fails toward noise, never toward quiet.
- **Template expressions filtered.** `python-version: ${{ matrix.python-version }}` is the
  *consumer* of a matrix, not a version.

### Ordering

`origin/main` carries 5 ignores; the registry here covers exactly those 5. #503 (`OME-748`) adds a
sixth (`typescript >=7` on `/public-docs`) and **must add its registry entry in the same change** —
there is a comment in the registry at that position saying so, with the blocker already worked
out. Deliberately not stacked: this repo squash-merges and a stacked PR has missed main before.
