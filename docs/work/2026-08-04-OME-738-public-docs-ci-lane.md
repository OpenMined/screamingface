---
ticket: OME-738
stack: repo
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-738 — give public-docs a CI lane

## Intent

`public-docs/` has **no CI**. No workflow `paths:` filter matches it, so a PR touching it shows
only unrelated checks and merges with nothing verifying it.

That is not hypothetical: during `OME-734` two Dependabot PRs — #460 (brace-expansion) and #432
(postcss) — merged into this tree on the strength of a single check that had nothing to do with
`public-docs`. Both were security fixes and both were correct, but nothing in the repo could have
told us if they weren't.

This is also a precondition for `OME-737`: the dependabot config gains a `/public-docs` npm entry,
and that entry should not exist before there is a lane to verify what it produces.

## Design

Mirror `.github/workflows/aigateway-ui-tests.yml`, which is the repo's established shape for a
path-filtered npm lane: same trigger pair, same `concurrency` group, same
`setup-node` + `cache: npm` + `npm ci` discipline.

Two deliberate divergences, both forced by what `public-docs` actually is:

**No test job.** `public-docs` has no test suite — `78331eb8` ("prune scaffolding, drop tests")
removed it, and there is no `test` script, no test file, and no vitest dependency. So there is no
`dorny/test-reporter` step and no `orgoro/coverage` step; wiring either would fail on a missing
`results.xml`. A lane that lints and builds is the honest maximum here.

**Lint is invoked directly, not through the package script.** This is the trap in this unit:

```json
"lint:oxlint": "oxlint . --fix",
"lint:eslint": "eslint . --fix --cache"
```

Both carry `--fix`. Running `npm run lint` in CI would **mutate the checked-out tree** and then
report success on code that differs from what the author pushed — a lint gate that cannot fail
for anything auto-fixable. So the workflow calls `oxlint .` and `eslint .` directly.

**`npm run build` covers typecheck too.** It is `run-p type-check "build-only {@}" --`, i.e.
`vue-tsc --noEmit` in parallel with `vite build`, so one step gates both. No separate typecheck
step is needed.

**Node version.** `public-docs` has no `.nvmrc`, unlike `aigateway-ui`. Its `package.json`
declares `engines: node ^22.18.0 || >=24.12.0`. Adding a `.nvmrc` pinned to `22` matches the
sibling lane's `node-version-file:` pattern, satisfies the engine range, and keeps the version in
one place rather than inline in YAML.

## Planned changes

- `.github/workflows/public-docs-tests.yml` — new, path-filtered on `public-docs/**`
- `public-docs/.nvmrc` — new, `22`

## Test plan

No unit test to write; the workflow **is** the artifact. Verification is behavioural and in two
parts:

1. **Locally, run exactly what the lane will run** — `npm ci`, `oxlint .`, `eslint .`,
   `npm run build` — and confirm each passes against current `public-docs`. If the tree is
   already failing one of these, the lane must not be merged green-washed; that is a finding.
2. **On the PR**, confirm the new lane actually appears as a check. That is the direct proof the
   `paths:` filter matches, and it is the whole point of the unit — the current failure mode is a
   filter that matches nothing.

## Acceptance

- The four commands above pass locally against `public-docs`.
- The new lane appears as a check on this PR (which touches `.github/workflows/` and therefore
  its own filter).
- No `--fix` variant is invoked anywhere in the workflow.

## Outcome

- **Actual files — one more than planned:**

  | File | Planned? | Why |
  |---|---|---|
  | `.github/workflows/public-docs-tests.yml` | yes | the lane |
  | `public-docs/.nvmrc` | yes | `22`, for `node-version-file:` |
  | `public-docs/eslint.config.ts` | **no** | see the deviation below |

- **Gates — the lane's own commands, run locally, all exit 0:**

  ```
  npm ci          exit 0
  npx oxlint .    exit 0
  npx eslint .    exit 0
  npm run build   exit 0     (vue-tsc --noEmit + vite build)
  ```

  YAML parses; `paths:` resolves to `public-docs/**` + the workflow's own path; steps are
  checkout → setup-node → npm ci → oxlint → eslint → build.

### Deviation — the tree was already failing lint, and had been silently

The ledger's test plan anticipated this ("if the tree is already failing one of these, the lane
must not be merged green-washed; that is a finding"). It was.

`npx eslint .` exited **1** on three pre-existing `vue/multi-word-component-names` errors:
`src/components/ui/Collapsible.vue`, `src/pages/sdk/Index.vue`, `src/pages/sf-client/Index.vue`.

`npm run lint` fails too — `--fix` cannot repair a component name, so the script has been exiting
1 for however long these have existed. Nothing noticed, because nothing ran it. That is the
verification gap this unit exists to close, demonstrating itself.

**Owner-approved fix: scope the rule rather than rename the components.** The rule guards against
a user component shadowing a real HTML element. Neither directory can:

- `src/components/ui/` holds shadcn-style primitives (`Collapsible`, `CodeBlock`, `ApiBlock`,
  `ImageCarousel`) — single-word names are that library's convention, not an oversight.
- `src/pages/**/Index.vue` is a section-root **route** component (`/sdk`, `/sf-client`), named for
  its route and never written as a tag, so it has no template identity to clash.

**Verified the exemption is scoped, not a blanket disable.** Dropped a single-word `Probe.vue`
into `src/components/layout/` — a directory the exemption does not cover — and `eslint` still
flagged it and exited 1. Removed it; `eslint .` back to 0. So the rule remains live everywhere a
component genuinely could collide.

### Design notes

- **No test job.** `public-docs` has no test suite (`78331eb8` removed it; its `CLAUDE.md` states
  "There is no automated test setup in this project"). So no `dorny/test-reporter` and no
  `orgoro/coverage` — both would fail on a `results.xml` that is never produced. The sibling
  lanes' test+build split collapses to one job here.
- **Lint binaries are invoked directly.** `npm run lint` carries `--fix`, which in CI would
  mutate the checked-out tree and then pass on code differing from what was pushed. Recorded as
  an `INVARIANT:` in the workflow so nobody "simplifies" it back to the script.
- **`npm run build` covers typecheck** — it is `run-p type-check "build-only {@}" --`, so
  `vue-tsc --noEmit` and `vite build` both run. No separate typecheck step.
- Carries the `cost` job like all five existing lanes, for consistency.
