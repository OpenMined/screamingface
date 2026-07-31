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
      # OMDS's own enforcement gate, vendored with the tokens: no raw hex, no named color, no
      # rgb()/hsl() literal on a color property. Token discipline as a merge blocker, not a nit.
      - npm run lint:css
      - npm run typecheck
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
- Brand law is the **OpenMined Design System**, vendored at `src/brand/tokens/` from
  `OpenMined/brand.openmined.org` (SHA in `src/brand/brand-version.txt`). NOT the
  `screamingface-design` skill — this is internal operator tooling, so it wears the parent
  OpenMined brand. The two systems genuinely conflict (radius, shadows, gradients, purple,
  type), so do not mix them.
- **Never hardcode a color.** Literal palette values live only in `src/brand/tokens/tokens.css`;
  everything else is `var(--…)`. `npm run lint:css` fails the build otherwise.
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
