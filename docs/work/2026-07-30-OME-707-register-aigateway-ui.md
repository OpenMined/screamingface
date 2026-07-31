---
ticket: OME-707
stack: repo
status: done
started: 2026-07-30
finished: 2026-07-30
---

# OME-707 — Register aigateway-ui: CI lane, release lane, CODEOWNERS, dependabot, sdlc card

## Intent

Make `apps/aigateway-ui` a first-class component of the monorepo per the 6-step new-component
checklist in the `working-in-this-repo` skill, so the admin console (`OME-708`) lands into a lane
that already lints, typechecks, tests, releases, and assigns review. `aigateway-ui` is the repo's
**first non-Python stack**, so this is also where several single-stack assumptions get their first
exercise.

## Scope deviation (decided at start, recorded on the Linear issue)

The issue as filed registers a component that does not exist yet — `OME-708` was to scaffold it.
That ordering does not work: Dependabot errors on a `directory:` with no manifest, release-please
cannot resolve a `node` package with no `package.json`, and `run_gates.py aigateway-ui` would `cd`
into a missing directory. The issue's own acceptance criteria ("a PR touching only
`apps/aigateway-ui/**` triggers the lane"; "`run_gates.py aigateway-ui` runs the npm gates") are
unverifiable without the app.

`pre-push` is the one exception — its `run_stack` is guarded by `grep -q "^$root/"` against the
changed-file list, so a line for a non-existent root is inert.

**Resolution:** this unit lands a minimal-but-real Next.js skeleton — enough that every
registration resolves and every acceptance criterion is observable. The admin console proper (BFF
client, account/profile pages, the design system pass) stays in `OME-708`.

## Planned changes

**New app skeleton — `apps/aigateway-ui/`**
- `package.json` (name `aigateway-ui`, version `0.1.0`, scripts `dev`/`build`/`start`/`lint`/`test`)
- `package-lock.json` (npm — the repo's JS package manager)
- `tsconfig.json` (`strict`, `noEmit`, `paths: {"@/*": ["./src/*"]}`)
- `eslint.config.mjs` (flat config, `eslint-config-next`)
- `next.config.ts` (`output: "standalone"` — the BFF needs a server, unlike the studio's `export`)
- `vitest.config.ts` + `src/app/{layout,page}.tsx` + `src/app/healthz/route.ts`
- one real test so the lane's test step is not vacuous
- `README.md`, `CLAUDE.md`, `AGENTS.md`, `.gitignore`

**Registration**
- `.github/workflows/aigateway-ui-tests.yml` — path-filtered; `npm ci` → lint → `tsc --noEmit` →
  vitest with junit + cobertura; `dorny/test-reporter@v2`, `orgoro/coverage@v3.2`, `cost` job
- `release-please-config.json` + `.release-please-manifest.json`
- `.github/workflows/release-aigateway-ui.yml`
- `.github/CODEOWNERS`, `.github/dependabot.yml` (repo's first `npm` ecosystem)
- `.claude/sdlc.local.md` (fifth stack, `skill: sdlc-react`), `.githooks/pre-push`
- `CONTRIBUTING.md`, `.claude/skills/working-in-this-repo/SKILL.md`

## Test plan

- `src/app/healthz/route.ts` returns `{status: "ok"}` — RED first, then the route
- the skeleton page renders its heading (Testing Library)
- `npm run lint`, `npx tsc --noEmit`, `npm test` all green locally
- `uv run .claude/scripts/run_gates.py aigateway-ui` runs the npm gates via the card

## Acceptance

- A PR touching only `apps/aigateway-ui/**` triggers `aigateway-ui-tests.yml` and nothing else
- `run_gates.py aigateway-ui` resolves the stack and runs the npm gates
- `helm`/image lanes are not claimed here — the Dockerfile and chart ship with `OME-708`, which is
  what makes them verifiable
- Port 9107 reserved (9105 aigateway · 9106 scoreboard · 9108 url4-cloud)

## Outcome

- **Actual files:** as planned, plus the design-system work below. New tree `apps/aigateway-ui/`
  (package.json, package-lock.json, tsconfig.json, eslint.config.mjs, stylelint.config.mjs,
  next.config.ts, vitest.config.ts, vitest.setup.ts, .nvmrc, .gitignore, README.md, CLAUDE.md,
  `src/app/{layout,page,globals.css,icon.svg}`, `src/app/healthz/route.ts`, two test files,
  `src/brand/`). Registration touched `.github/workflows/aigateway-ui-tests.yml` (new),
  `release-please-config.json`, `.release-please-manifest.json`, `.github/CODEOWNERS`,
  `.github/dependabot.yml`, `.claude/sdlc.local.md`, `.githooks/pre-push`, `CONTRIBUTING.md`,
  `.claude/skills/working-in-this-repo/SKILL.md`.

- **Gates:** `run_gates.py aigateway-ui` — `npm ci` · `npm run lint` · `npm run lint:css` ·
  `npm run typecheck` · `npm run test:ci` → ALL GATES GREEN. 3 tests, coverage 100% on the
  non-excluded surface (floor 80). `npm run build` succeeds; routes `/`, `/_not-found`,
  `/healthz` (dynamic), `/icon.svg`. Verified in a browser at both themes — light
  `#fcfcfd`/`#353243`, dark `#2e2b3b`/`#cfcdd6`, Rubik headings, Inter body, 6px radius.

- **Deviations:**
  1. **Scope — a minimal app skeleton ships here**, not in OME-708. Recorded on the Linear issue
     at start. Registering a component that does not exist breaks Dependabot (no manifest),
     release-please (no `package.json`) and `run_gates.py` (missing cwd), and makes this issue's
     own acceptance criteria unverifiable. `pre-push` was the sole exception — its `run_stack` is
     guarded by a `grep` on the changed-file list, so a line for a missing root is inert.
  2. **Design system is OMDS, not `screamingface-design`.** Owner decision mid-implementation:
     this is internal operator tooling, so it wears the parent OpenMined brand. The two systems
     genuinely contradict each other (radius 0 vs 6px; no-shadow vs `--shadow-*`; no-gradient vs
     7 brand gradients; purple banned vs an 11-step violet family; IBM Plex + EB Garamond vs
     Inter + Rubik). Tokens vendored from `OpenMined/brand.openmined.org` @
     `af7d344318d4b0afb4493393c1b2ced52ac9facb` into `src/brand/tokens/`, with one documented
     divergence (font families aliased to CSS variables for `next/font`, which self-hosts and so
     cannot publish a chosen family name) — see `src/brand/README.md`.
  3. **A fifth gate, `npm run lint:css`,** was added on the owner's call: OMDS's own stylelint
     rules (`color-no-hex`, `color-named`, `declaration-strict-value`). Verified it actually
     blocks — a raw hex trips two rules and an `rgb()` literal trips one. Without this, "use
     semantic tokens" is a review note nobody enforces.
  4. **Tailwind was dropped** from the dependency set. It was scaffolded in by reflex from the
     studio frontend and nothing imports it; OMDS is plain CSS.
  5. **No `release-aigateway-ui.yml`.** The image and Helm chart ship with OME-708, so a release
     workflow pointing at a non-existent Dockerfile would be the same broken-config mistake as
     (1). release-please still bumps the version and tags; the tag is a version marker until then.
  6. **`CONTRIBUTING.md` had drifted** — the stacks table omitted `url4-cloud` entirely. Added
     alongside the `aigateway-ui` row rather than left visibly stale in a table being edited.

## Note for OME-708

`npm ci` caught real lockfile drift during this unit (removing Tailwind left transitive
`@emnapi/*` entries out of sync). That is the gate working as designed — regenerate the lock with
`npm install` and commit it, never work around the gate.
