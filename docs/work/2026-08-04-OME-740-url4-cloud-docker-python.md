---
ticket: OME-740
stack: url4-cloud
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-740 — move the url4-cloud image's Python across both build stages

## Intent

Replace Dependabot's #439, the one PR in the epic's set that is **broken rather than
redundant**, and take the base-image bump properly.

## Root cause of #439

`apps/url4-cloud/Dockerfile` is a two-stage build:

```
line 22:  FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
line 40:  FROM python:3.12-slim-bookworm AS runtime
```

Dependabot's `docker` ecosystem tracks `FROM` lines independently, and it only recognised the
runtime one as the `python` image — `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` is a
*different* image whose Python version happens to live in the tag. So it bumped the runtime to
3.14 and left the builder on 3.12.

That cannot work here. The builder runs `uv sync` to create a venv at
`/app/apps/url4-cloud/.venv`, and the runtime stage copies that directory wholesale
(`COPY --from=builder … /app/apps/url4-cloud`). A venv is version-keyed: its `site-packages`
sits under `lib/python3.12/`, and its `pyvenv.cfg` and `bin/python` point at the interpreter
that built it. Drop that into a 3.14 image and there is no 3.12 interpreter to resolve, so the
`ENV PATH=".../.venv/bin:$PATH"` entrypoint resolves to a broken venv:

```
ModuleNotFoundError: No module named 'url4_cloud'
```

Note this is an **import-time** fault, not a build-time one. The image builds; it just cannot
run. Only CI's `Smoke both modes` step caught it.

**AIDEV-NOTE:** any future base-image bump here must move BOTH `FROM` lines together.
Dependabot structurally cannot do this — the two images are different products, so no grouping
setting will pair them. Treat docker bumps on this file as always needing a human.

## Decision — 3.13, not Dependabot's 3.14

`requires-python = ">=3.12"` permits 3.14, but the repo's Python matrices — `url4-cloud-tests.yml`
and `url4-tests.yml` — run **3.12 and 3.13 only**. Shipping a 3.14 runtime would mean the
deployed interpreter is a version no test in the repo has ever exercised.

3.13 is the version the tests actually cover. Going to 3.14 is a separate decision that has to
extend the CI matrix in the same change, and that is not this unit.

## Planned changes

- `apps/url4-cloud/Dockerfile` — builder `uv:python3.12-bookworm-slim` → `python3.13`, runtime
  `python:3.12-slim-bookworm` → `python:3.13-slim-bookworm`, plus a comment recording why the
  two must move together
- Close #439 with the reason

No Python source, dependency or lockfile change: `requires-python = ">=3.12"` already admits
3.13, so `uv.lock` is unaffected.

## Test plan

The failing signal is #439's own CI: `Build the image` → `ModuleNotFoundError`.

Verification is **CI's `Smoke both modes` step**, which is stronger than a plain build:

```sh
docker run --rm url4-cloud:ci url4-cloud --help
docker run --rm url4-cloud:ci url4-cloud run --help
```

Both argv modes must start from the built image. That executes the entrypoint through the
copied venv, which is precisely what the stage mismatch breaks — a green build alone would not
prove anything.

⚠️ **No Docker daemon is available on this machine**, so the image cannot be built locally. This
unit's image verification rests entirely on CI. Stated plainly rather than implied.

The Python gates (`run_gates.py url4-cloud`) still run locally and must stay green, though they
exercise the source rather than the image.

## Acceptance

- Both `FROM` lines on the same Python minor.
- CI `Build the image` green, including `Smoke both modes`.
- `run_gates.py url4-cloud` green.
- #439 closed with its reason recorded.

## Outcome

- **Actual files:** as planned — `apps/url4-cloud/Dockerfile` only, plus this ledger and its
  `docs/tasks/` mirror. No source, dependency or lockfile change.

  ```
  FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
  FROM python:3.13-slim-bookworm AS runtime
  ```

- **Gates:** `run_gates.py url4-cloud` — **ALL GATES GREEN**. append-only check ✓ ·
  ruff check ✓ · ruff format --check ✓ · pyright ✓ · `check_layering.py` ✓ ·
  pytest with `--cov-fail-under=80` ✓.

- **Deviations:** none from the plan.

- **Verification gap, stated plainly:** no Docker daemon is available on this machine, so the
  image was **not** built locally. The image-level proof rests entirely on CI's
  `Build the image` job and its `Smoke both modes` step, which runs
  `docker run --rm url4-cloud:ci url4-cloud --help` and the `run` variant. That step is what
  caught #439's fault in the first place, so it is the right check — but it is CI's, not mine.

- **Documented the trap in the Dockerfile itself.** Added an `INVARIANT:` explaining that the
  builder and runtime Python minors must match because the venv is copied wholesale and is
  version-keyed, and an `AIDEV-NOTE:` recording that **Dependabot structurally cannot keep the
  two in step** — `ghcr.io/astral-sh/uv` and `python` are different images, so no grouping
  setting will ever pair them. That is why #439 happened and why it will happen again unless the
  next person reads it there.

  This one does not get fixed by `OME-737`'s config rewrite. It is a genuine limit of the tool,
  and the mitigation is the comment plus CI's smoke step, not configuration.
