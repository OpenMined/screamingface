---
ticket: OME-736
stack: aigateway-ui
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-736 — land the aigateway-ui dependency group, hold TypeScript at 5

## Intent

Unblock the `aigateway-ui-npm` group PR, red since 2026-07-31 (now #477, previously #472 and
#457). It carries the `react`/`react-dom` 19.2.8 **security** bumps, which have been stuck
behind an unrelated conflict.

## Root cause — corrected

The first reading of this failure was wrong and is recorded here so the next agent does not
repeat it.

**Wrong:** "stylelint 17 / eslint 10 pull a TypeScript 6 peer." They do not. Checked directly —
none of `eslint@10.8.0`, `stylelint@17.14.1`, `@vitejs/plugin-react@6.0.5`,
`@vitest/coverage-v8@4.1.10`, `jsdom@30.0.1` or `@testing-library/jest-dom@7.0.0` constrains
TypeScript at all. `eslint-config-next@16.2.12` asks only for `>=3.3.1`.

**Actual:** the group itself bumps `typescript` `"^5"` → `"^7"`. `openapi-typescript@7.13.0`
declares peer `typescript@^5.x`, and **no release of it supports TS 6 or 7** — 7.13.0 is the
latest, last published 2026-06-15. So `npm ci` dies at install:

```
While resolving: openapi-typescript@7.13.0
Found: typescript@7.0.2
  dev typescript@"^7" from the root project
Could not resolve dependency:
peer typescript@"^5.x" from openapi-typescript@7.13.0
```

TypeScript 7 is the Go-based compiler rewrite — a real major, not a routine bump.

## Decision (owner-approved)

**Hold `typescript` at `^5`.** Everything else in the group lands.

TS 5→7 is a compiler migration that needs its own verification pass across the whole app plus
Next.js 16.3 compatibility. Letting it ride into a group PR alongside `react` security patches
is precisely the failure mode `OME-737` exists to fix — majors must not hold security bumps
hostage, and equally must not sneak in under cover of them.

`openapi-typescript` is worth noting for whoever takes the TS 7 ticket: it is **manual codegen**,
absent from every npm script, and its output `src/lib/aigateway/schema.d.ts` is committed. So it
does not need to sit in the install graph at all — `npx openapi-typescript` at schema-change time
would remove the blocker entirely. Deliberately not doing that here; it is a separate decision.

## Planned changes

- `apps/aigateway-ui/package.json` — take the group's versions for `react`, `react-dom`,
  `@testing-library/jest-dom`, `@types/node`, `@vitejs/plugin-react`, `@vitest/coverage-v8`,
  `eslint`, `eslint-config-next`, `jsdom`, `stylelint`, `vitest`; **hold `typescript` at `^5`**
- `apps/aigateway-ui/package-lock.json` — regenerated

No component or route change, so stack rule S1 (a11y-first design) has nothing to attach to
this iteration — no new UI surface is introduced.

## Test plan

The failing signal is at install: `npm ci` reproduces the ERESOLVE without running a test. That
is this unit's RED.

Tests are append-only and untouched. The whole existing suite must stay green under the new
majors — this is the real risk of the unit, since `vitest` 3→4, `jsdom` 26→30,
`@vitejs/plugin-react` 4→6 and `@testing-library/jest-dom` 6→7 are all breaking-change majors
that the test suite runs on. Any red there is a genuine finding, not a formality.

## Acceptance

- `npm ci` resolves with no ERESOLVE and no `--legacy-peer-deps`.
- Card gates green: `npm ci` · `npm run lint` · `npm run lint:css` · `npm run typecheck` ·
  `npm run test:ci`.
- `npm run build` succeeds (Next.js production build, `output: "standalone"`).
- The `react`/`react-dom` security bumps are in.
- #477 closed as superseded; a TS 7 migration ticket filed.

## Card defect to surface (sdlc-react rule 7)

The `aigateway-ui` stack in `.claude/sdlc.local.md` lists gates for typecheck, lint, format and
test but **no a11y gate**, which this skill names as a required gate category. Not introduced by
this unit and not fixed here — recorded so it is not lost.

## Outcome

- **Actual files:** as planned — `package.json` and `package-lock.json` only. No source file
  touched; **no test modified** (the append-only gate passed clean, unlike `OME-735`).

- **Gates:** all green.

  ```
  ✓ append-only test check
  ✓ npm ci          ← the ERESOLVE this unit exists to fix
  ✓ npm run lint
  ✓ npm run lint:css
  ✓ npm run typecheck
  ✓ npm run test:ci     13 files, 218 tests passed
  ```

  Plus `npm run build` — Next.js production build compiles, typechecks and prerenders all 5
  routes. `npm audit`: **0 vulnerabilities**.

- **Landed:** react + react-dom → 19.2.8 (the security bumps this unblocks),
  @testing-library/jest-dom → 7.0.0, @types/node → 26, @vitejs/plugin-react → 6.0.5
  (pulls vite 8.2.0), @vitest/coverage-v8 + vitest → 4.1.10, eslint-config-next → 16.2.12,
  jsdom → 30.0.1, stylelint → 17.14.1.

  Four breaking majors run the test suite — vitest 3→4, jsdom 26→30, @vitejs/plugin-react 4→6,
  jest-dom 6→7 — and all 218 tests pass unmodified.

### Deviation 1 — a second hold was required: eslint stays at ^9

The plan held only `typescript`. Landing `eslint@^10` produced a hard crash:

```
TypeError: Error while loading rule 'react/display-name':
  contextOrFilename.getFilename is not a function
  at resolveBasedir (eslint-config-next/node_modules/eslint-plugin-react/lib/util/version.js)
```

`eslint-plugin-react@7.37.5`, bundled inside `eslint-config-next`, calls an ESLint 9 API that
ESLint 10 removed. `eslint-config-next` declares peer `eslint: ">=9.0.0"` — the range is simply
**too permissive and wrong**; it claims ESLint 10 support it does not have. Checked 16.2.12 and
16.3.0 (latest): both declare the same range, so no version of the Next.js ESLint config works
with ESLint 10 today.

Not a product decision — the combination is broken, and shipping a crashing lint gate is not an
option. Held at `^9`, to be revisited when Next ships a genuinely ESLint-10-compatible config.

### Deviation 2 — the lockfile needed full regeneration

`npm install` alone kept resolving `@vitejs/plugin-react@4.7.0` from the stale lock and failed
on a *second* ERESOLVE (`plugin-react@6` needs `vite ^8`). Removing `node_modules` and
`package-lock.json` and reinstalling resolved cleanly — vite 8.2.0 satisfies both plugin-react 6
and vitest 4. Hence the large lockfile diff.

### Findings for the owner

- **Local Node is unsupported by jsdom 30.** `jsdom@30.0.1` requires
  `^22.22.2 || ^24.15.0 || >=26.0.0`; this machine runs v25.2.1, which matches none. CI is
  **fine** — `.nvmrc` pins 22 and `setup-node` resolves the latest 22.x. So the gates above ran
  on a Node version CI never uses. No version manager is installed locally to correct this.
- **`next` and `eslint-config-next` are skewed** — 16.3.0 vs 16.2.12. Pre-existing (main had
  16.3.0 vs 16.2.10) and not widened here, but worth aligning.
- **Card defect (sdlc-react rule 7):** the `aigateway-ui` stack in `.claude/sdlc.local.md`
  declares no **a11y** gate, which this skill lists as a required gate category. Pre-existing.

### Not applicable

No component or route added, so stack rule S1 (a11y assertions land with the component) has
nothing to attach to. No prior test touched, so rule 5 never triggered.
