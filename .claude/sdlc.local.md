---
stacks:
  - name: aigateway
    root: apps/aigateway
    skill: sdlc-python
    test_globs: ["tests/**"]
    gates:
      - uv run ruff check
      - uv run ruff format --check
      - uv run pyright
      - uv run python scripts/check_no_enterprise.py
      - uv run pytest --cov=aigateway --cov-fail-under=80 -q
  - name: scoreboard
    root: apps/scoreboard
    skill: sdlc-python
    test_globs: ["tests/**"]
    gates:
      - uv run ruff check
      - uv run ruff format --check
      - uv run pyright
      - uv run pytest --cov=scoreboard --cov-fail-under=80 -q
  - name: url4
    root: packages/url4
    skill: sdlc-python
    test_globs: ["tests/**"]
    gates:
      - uv run ruff check
      - uv run ruff format --check
      - uv run pyright
      - uv run pytest --cov=url4 --cov-fail-under=95 -q
  - name: screamingface
    root: packages/screamingface
    skill: sdlc-python
    test_globs: ["tests/**"]
    gates:
      - uv run ruff check
      - uv run ruff format --check
      - uv run pyright
      - uv run pytest --cov=screamingface --cov-fail-under=95 -q
      - uv run --extra notebook python scripts/check_notebooks.py
      - uv build
      - uv run python scripts/check_distribution.py
  - name: url4-cloud
    root: apps/url4-cloud
    skill: sdlc-python
    test_globs: ["tests/**"]
    gates:
      - uv run ruff check
      - uv run ruff format --check
      - uv run pyright
      # One venv holds every distribution, so no runtime check can prove the boundaries —
      # this gate keeps url4.streaming conceptual and every concrete adapter in its own deployable.
      - python3 ../../.claude/scripts/check_layering.py
      - uv run pytest --cov=url4_cloud --cov=url4.streaming --cov-fail-under=80 -q
  # The first non-Python stack. run_gates.py is stack-agnostic — it shells this `gates:` list with
  # cwd = root — so nothing in the runner needed changing. `npm ci` (not `install`) is deliberate:
  # it installs FROM the lockfile and fails when package.json disagrees, which is this stack's
  # equivalent of `uv lock --check`.
  - name: aigateway-ui
    root: apps/aigateway-ui
    skill: sdlc-react
    test_globs: ["src/**/*.test.ts", "src/**/*.test.tsx"]
    gates:
      - npm ci
      - npm run lint
      # SFDS v2's own enforcement gate, vendored with the tokens: no raw hex, no named color, no
      # rgb()/hsl() literal on a color property. Token discipline as a merge blocker, not a nit.
      - npm run lint:css
      - npm run typecheck
      # aigateway-ui-tests.yml runs this as a SECOND job ("Build the app"), so a card without it
      # mirrors only half the workflow. `tsc --noEmit` does NOT cover the same ground: it never
      # exercises Turbopack module resolution, static generation, or the `output: "standalone"`
      # bundle the Dockerfile ships — so a build-only break (bad turbopack root, a server/client
      # boundary violation, an unserializable prop crossing into a Server Component) passes every
      # other gate and first surfaces in CI, or on a release tag in the image build.
      # Ordered before test:ci deliberately: the build is ~5s against test:ci's ~60s, and the
      # runner stops at the first red gate — so the cheap signal should come first.
      - npm run build
      - npm run test:ci
commit_refs: "Refs: OME-N"
extra_anchors: []
companion_skills:
  - skill: tortoise-dev  # https://github.com/sergio-bershadsky/ai/tree/main/plugins/tortoise-dev — propose install if absent
    when: "any Tortoise ORM work in a python stack — models, querysets, migrations, transactions, signals, lifespan wiring"
    mandatory: true
ledger_dir: docs/work/
---

# Stack conventions

## aigateway (python)

- INVARIANTS: credentials only via ORMStore/`credential_blobs` (AES-256-GCM through
  SecretStoreMixin); no OS keychain; `AIGATEWAY_SECRET_KEY` never stored/logged; never
  import litellm-enterprise (gate-guarded by `scripts/check_no_enterprise.py`).
- Providers/secrets backends implement the port + register in the factory; never edit
  ORMStore or its call sites.

## aigateway-ui (typescript · next.js)

- INVARIANTS: **BFF only** — every call to aigateway's `/v1/admin` surface happens server-side
  (`output: "standalone"`, never `"export"`); the browser never holds the admin API's address
  and never sees `X-User-Email`. Modules that reach aigateway carry `import "server-only"`.
- The UI holds **no** copy of the admin allowlist — `AIGATEWAY_ADMIN_EMAILS` lives in aigateway,
  which is the sole authority; the UI renders whatever the API returns (403 → not-an-admin page).
- API keys are **write-only**: submitted, never rendered back, never logged.
- Brand law is the **`screamingface-design` skill — SFDS v2**, vendored at `src/brand/tokens/`
  from `brand.screamingface.ai` (version string in `src/brand/README.md`). This REPLACED the
  OpenMined Design System in `OME-716` — an owner decision reversed by an owner decision. **Do
  not reintroduce OMDS**, and do not mix the two: they genuinely conflict on radius, shadows,
  gradients and colour semantics.
- **This console is the `app` register**, which is v2's default. `[data-brand="marketing"]` swaps
  the accent family to gold; everything else takes **blue**. So `--accent-*` carries every
  interaction, `--success-*` marks a healthy account, `--danger-*` marks destructive actions, and
  `--brand-*`/`--gain-*` (gold) appear **nowhere** — gold is rationed to the win, and an admin
  console has no win. `src/app/design-system.test.ts` asserts this; do not weaken it to land a
  change.
- **`--gain` is a trap.** The v1→v2 bridge keeps it resolving, but it now resolves to **gold**
  where v1 had it green — a surface using it to mean "success" silently changed meaning. Use
  `--success-*`.
- **Never hardcode a color.** Literal palette values live only in `src/brand/tokens/tokens.css`;
  everything else is `var(--…)`. `npm run lint:css` fails the build otherwise. If a colour you
  need does not exist, the fix goes **upstream into the system**, not into the vendored copy —
  that is v2's own round-trip rule.
- **Never hardcode a font stack either.** It is invisible to the colour gate, which is how
  `Consolas, Monaco, "Andale Mono"…` survived two files under the previous system. Use
  `--f-sans` / `--f-mono`; `design-system.test.ts` enforces it.
- Re-syncing the brand means re-applying the documented font-family divergence — see
  `src/brand/README.md`.
- `npm ci`, never `npm install`, in gates and CI: it installs from the lockfile and fails on
  drift, which is this stack's equivalent of `uv lock --check`.

## scoreboard (python)

- INVARIANTS: public artifact allowlist in `src/scoreboard/portal.py` (PUBLIC_ARTIFACTS /
  FORBIDDEN_ARTIFACTS — forbidden routes must stay 404); portal + artifacts stay app-local
  (`portal/`, `artifacts/`).

## ledger naming (D8)

`docs/work/YYYY-MM-DD-<ticket-id>-<short-description>.md` — created at work START
(date = start), frontmatter `status: planned|in_progress|done|blocked` + `finished:` filled
at close. Template: copy `docs/work/TEMPLATE.md`.
