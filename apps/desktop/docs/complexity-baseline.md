# Complexity Baseline — apps/desktop (SF-210)

Captured on 2026-05-26 from commit `e33d215`.

These are the high-water marks the day-1 thresholds were set to accommodate.
Each tightening PR (one rule, one ratchet at a time) should reference this
file and the file:line below it's reducing.

Plugin: `eslint-plugin-sonarjs@4.0.3`. Rule names below are the v4 spelling.

## sonarjs/cognitive-complexity

- **Day-1 threshold:** `34` — set equal to the current worst file. The rule
  fires when a function's cognitive complexity exceeds the threshold, so
  the file at 34 sits exactly at the limit.
- **Top offenders:**

  | Cognitive complexity | File:line                                          |
  | -------------------: | -------------------------------------------------- |
  |                   34 | `src/main/services/oauth-launcher.ts:113`          |
  |                   33 | `src/main/services/oauth-launcher.ts:223`          |
  |                   28 | `src/main/services/runtime-config-migration.ts:73` |
  |                   24 | `src/main/services/backend-status.ts:441`          |
  |                   17 | `src/main/services/session-manager.ts:396`         |
  |                   15 | `src/main/services/venv-manager.ts:142`            |
  |                   14 | `src/main/services/backend-status.ts:171`          |
  |                   13 | `src/renderer/src/components/Url4Viewer.tsx:105`   |
  |                   12 | `src/main/services/runtime-config-migration.ts:22` |
  |                   11 | `src/main/services/external-url-policy.ts:60`      |

  Total functions over the strict baseline floor of 5: **44**.

## sonarjs/no-duplicate-string

- **Day-1 threshold:** `31` — one above the current worst-case literal-count.
  The v4 rule fires when occurrences are at-or-above the configured
  threshold, so the file at 30 needs `threshold: 31` to pass cleanly.
- **Top offenders:**

  | Duplicate count | File:line                                                                      |
  | --------------: | ------------------------------------------------------------------------------ |
  |              30 | `src/main/services/__tests__/oauth-launcher.test.ts:55`                        |
  |              18 | `src/main/services/__tests__/oauth-launcher.test.ts:95`                        |
  |              14 | `src/main/services/__tests__/oauth-launcher.test.ts:58`                        |
  |              10 | `src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx:293` |
  |              10 | `src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx:105` |
  |               9 | `src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx:291` |
  |               9 | `src/main/services/__tests__/oauth-launcher.test.ts:365`                       |
  |               8 | `src/main/services/__tests__/external-url-policy.test.ts:29`                   |
  |               7 | `src/main/services/__tests__/external-url-policy.test.ts:31`                   |
  |               6 | `src/renderer/src/components/server/__tests__/BackendStatusPanel.test.tsx:202` |

  Total duplicate-string sites above the strict baseline floor of 3: **41**.

## Other sonarjs/\* rules (`warn` only, baseline counts)

These ride along at warn-level for visibility. Promote to `error` one rule
per tightening PR.

| Rule                                    | Count at baseline |
| --------------------------------------- | ----------------: |
| `sonarjs/publicly-writable-directories` |                 8 |
| `sonarjs/no-os-command-from-path`       |                 7 |
| `sonarjs/no-nested-conditional`         |                 7 |
| `sonarjs/no-nested-functions`           |                 7 |
| `sonarjs/void-use`                      |                 4 |
| `sonarjs/no-nested-template-literals`   |                 3 |
| `sonarjs/no-extra-arguments`            |                 2 |
| `sonarjs/unused-import`                 |                 2 |
| `sonarjs/no-clear-text-protocols`       |                 1 |
| `sonarjs/constructor-for-side-effects`  |                 1 |
| `sonarjs/concise-regex`                 |                 1 |
| `sonarjs/slow-regex`                    |                 1 |
| `sonarjs/no-duplicated-branches`        |                 1 |

(Counts exclude `sonarjs/cognitive-complexity` and `sonarjs/no-duplicate-string`,
which are the hard-enforced gates above. The sonarjs v4 recommended set
contains 269 rules in total; rules with zero current violations are not
listed.)

## Tightening roadmap

The intent is to ratchet thresholds down one rule at a time, each as its own
ticket + PR referencing this baseline:

1. **cognitive-complexity:** 34 → 25 → 20 → 15 (industry default) → 10.
   First two ratchets need a refactor of `oauth-launcher.ts` (two functions
   at 33-34) and `runtime-config-migration.ts:73` (28).
2. **no-duplicate-string:** 31 → 15 → 10 → 5. First ratchet means extracting
   constants in the oauth-launcher test suite (30, 18, 14 hits there).
3. **Promote one warn-level rule to error per follow-up PR.** Recommended
   order based on count and refactor cost:
   - `sonarjs/no-nested-conditional` (7) — usually trivial to flatten.
   - `sonarjs/no-nested-functions` (7) — likely needs small extractions.
   - `sonarjs/void-use` (4).
   - `sonarjs/no-os-command-from-path` (7) — security-flavoured; needs care.
   - `sonarjs/publicly-writable-directories` (8) — Electron-specific paths,
     may justify a per-line `eslint-disable` rather than a refactor.

Each tightening PR should:

- Quote the "from N → to M" delta from this file.
- Update this file with the new high-water mark.
- Stay under ~10 files changed; if larger, split.
