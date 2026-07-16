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

## scoreboard (python)

- INVARIANTS: public artifact allowlist in `src/scoreboard/portal.py` (PUBLIC_ARTIFACTS /
  FORBIDDEN_ARTIFACTS — forbidden routes must stay 404); portal + artifacts stay app-local
  (`portal/`, `artifacts/`).

## ledger naming (D8)

`docs/work/YYYY-MM-DD-<ticket-id>-<short-description>.md` — created at work START
(date = start), frontmatter `status: planned|in_progress|done|blocked` + `finished:` filled
at close. Template: copy `docs/work/TEMPLATE.md`.
