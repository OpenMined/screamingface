---
ticket: OME-748
stack: repo
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-748 — unblock the public-docs major group, hold TypeScript at 6

Authored in an isolated worktree branched from `origin/main` at `563c905f`.

## Intent

#497 (`public-docs-npm-major`, 5 updates) is the **last open Dependabot PR** and is red. Close it
properly rather than leaving the queue at one.

## It failed twice, for two different reasons

**First failure — fixed by a sibling PR, not by us.** `npm ci` died on ERESOLVE: the group bumped
`pinia` 3→4, but `vue-router@5.1.0` declares `peerOptional pinia@^3.0.4` and `vue-router` was not
in the major group. #496 (`public-docs-npm-minor`) then carried `vue-router` to **5.2.0**, which
accepts `pinia ^3.0.4 || ^4.0.2`, and the conflict evaporated. `origin/main` now has
`vue-router ^5.2.0`.

That is the `OME-737` `-minor`/`-major` split paying off directly. Under the previous single-group
config both bumps would have sat in one permanently-red PR, and **the fix would have been trapped
inside the very thing it was fixing**.

**Second failure — the real blocker.** `npm ci` now passes; `eslint` fails instead:

```
Error: typescript-eslint does not support TS 7.0.
  at public-docs/node_modules/@vue/eslint-config-typescript/node_modules/typescript-eslint/dist/index.js:52:9
```

#497 bumps `typescript ~6.0.0 → ~7.0.2`, and `typescript-eslint` — bundled inside
`@vue/eslint-config-typescript@^14.8.0` — refuses TS 7 outright.

## The bound must be >=7, not >=6

Same class as the `aigateway-ui` hold (`OME-736`/`OME-737`: `ignore: typescript >=6`) — a
TypeScript major outrunning its tooling. But `public-docs` is **already on ~6.0.0**, a whole major
ahead of `aigateway-ui`'s `^5`. Copying that entry verbatim would freeze this tree below where it
already sits and silently block nothing that is actually broken.

**AIDEV-NOTE:** two trees, two different TypeScript ceilings, for two different reasons —
`aigateway-ui` is capped by `openapi-typescript` (peer `^5.x`), `public-docs` by `typescript-eslint`
(no TS 7). Do not unify them; they lift on unrelated triggers.

## Planned changes

- `.github/dependabot.yml` — `ignore: typescript >=7` on `/public-docs`, commented with the
  lifting condition
- `public-docs/package.json` + `package-lock.json` — land the group's **other four** majors
  directly, IF they verify green: `lucide-vue-next` 0.577→1.0.0, `markdown-it` 14→15,
  `pinia` 3→4, `@types/node` 24→26
- Close #497

Landing the four rather than waiting for Dependabot to regenerate is deliberate: they have to be
verified locally anyway to know the ignore is sufficient, so regenerating would repeat that work
and leave the queue non-empty in the meantime.

## Test plan

Run **exactly** what the `public-docs` lane runs (`OME-738`), since that lane is what caught this:

```
npm ci · npx oxlint . · npx eslint . · npm run build
```

The interesting assertion is negative: with `typescript` held at `~6.0.0`, `eslint` must **pass** —
proving TS 7 was the sole blocker and the other four majors are innocent. If eslint still fails,
one of them is also implicated and the ignore alone is not the fix.

`markdown-it` 14→15 and `pinia` 3→4 are the ones with real runtime surface here
(`NotebookViewer` renders markdown; the theme and code-lang stores are Pinia), so `npm run build`
matters as more than a typecheck.

## Acceptance

- `eslint` passes with typescript at ~6.
- All four lane commands exit 0.
- `ignore: typescript >=7` present on `/public-docs` with its lifting condition recorded.
- Config still structurally valid.
- #497 closed; **zero open Dependabot PRs**.

## Outcome

- **Actual files — two more than planned:**

  | File | Planned? | Why |
  |---|---|---|
  | `.github/dependabot.yml` | yes | `ignore: typescript >=7` on `/public-docs` |
  | `public-docs/package.json` + lock | yes | the four other majors |
  | `public-docs/src/components/ui/NotebookViewer.vue` | **no** | markdown-it 15 type widening |
  | (removal) `@types/markdown-it` | **no** | redundant once markdown-it 15 bundles types |

- **Gates — the public-docs lane's exact commands:**

  ```
  npm ci          exit 0
  npx oxlint .    exit 0
  npx eslint .    exit 0
  npm run build   exit 0    (vue-tsc --noEmit + vite build, 1762 modules)
  ```

  Config revalidated: 11 entries, every directory present, every group declares `applies-to`.

- **Landed:** `lucide-vue-next` 0.577→1.0.0 · `markdown-it` 14→15 · `pinia` 3→4 ·
  `@types/node` 24→26. `typescript` held at `~6.0.0`.

### The negative assertion held, then didn't

The test plan predicted: *"with typescript held at ~6, eslint must pass — proving TS 7 was the
sole blocker."* **eslint did pass** (exit 0), so TS 7 was indeed the only thing breaking lint.

But the plan's next clause — that the other four majors are therefore "innocent" — was **wrong**.
`npm run build` then failed on a type error the lint step never reaches:

```
src/components/ui/NotebookViewer.vue(50,27): error TS2339:
  Property 'match' does not exist on type 'string | number'.
```

Two gates, two different failures, and passing the first proved nothing about the second. Worth
remembering: `eslint` and `vue-tsc` are not the same check, and `npm run build` runs both
`type-check` and `vite build` in parallel — so a green lint says nothing about types.

### Root cause — a types ownership change, not a breaking API

First guess (`@types/markdown-it` widened the tuple) was **wrong**: that package is still at
14.1.2 and still declares `attrs: Array<[string, string]>`. The real cause:

**markdown-it 15 ships its own typings.** 14 had none, so DefinitelyTyped supplied them. The
bundled declaration widens a token attribute:

```ts
type TokenAttribute = [name: string, value: string | number]
```

which is *more accurate* — `attrSet`/`attrJoin`/`attrGet` genuinely accept and return numbers.

So the fix is two-part and both halves are correct on their own merits:

1. **Drop `@types/markdown-it`.** Redundant now, and worse than redundant — it is stale and
   *contradicts* the bundled types. Standard practice once upstream ships its own.
2. **Narrow at the single call site** with `typeof href === 'string'` rather than casting. A
   numeric attribute value cannot be a notebook link, so declining to match is the honest read;
   a cast would assert something the type deliberately stopped guaranteeing.

Only one call site existed (`NotebookViewer.vue:48–55`), verified by grepping every
`attrs`/`attrIndex`/`attrGet`/`attrSet` usage in `src/`.

### Why the ignore bound is >=7, not >=6

`aigateway-ui` holds `typescript >=6`; this tree holds `>=7`. They are capped by **different
packages for different reasons** — `aigateway-ui` by `openapi-typescript` (peer `^5.x`),
`public-docs` by `typescript-eslint` (no TS 7 support) — and `public-docs` already sits on ~6.0.0.
Copying the aigateway-ui entry verbatim would have frozen this tree a full major below where it
already was. Recorded in the config comment so the two are not "tidied" into one.

### Credit where due

This entire failure was caught by the `public-docs` lane added in `OME-738` (#484). Before that
lane existed — five hours ago — #497 would have merged into `public-docs` with **nothing checking
it**, exactly as #460 and #432 did.
