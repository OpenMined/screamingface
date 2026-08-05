---
ticket: OME-547
stack: repo
status: in_progress
started: 2026-07-26
finished:
---

# OME-547 — Deploy the docs skeleton to a VM + GitHub Action

## Intent

Auto-deploy the `public-docs` static site to the docs VM on merge to `main`,
served over HTTPS at `docs.screamingface.ai`, so merged docs PRs can be reviewed
live. Gated for now behind a **temporary** password (shared privately) to keep the
skeleton out of public view; to be removed later. VM host/user/key are kept out of
the repo (Actions secrets `DOCS_VM_*`), since this repo may be made public.

## What was built (in the repo)

- **`.github/workflows/deploy-public-docs.yml`** — on push to `main` (paths
  `public-docs/**`) + `workflow_dispatch`: builds in the runner
  (`npm ci && npm run build`) and `rsync --delete`s `public-docs/dist/` to the VM
  at `~/screamingface/public-docs/dist`. Auth via secrets `DOCS_VM_HOST` /
  `DOCS_VM_USER` / `DOCS_VM_SSH_KEY`.

## Applied on the VM (owner action, not in the repo)

- Caddy site block: `docs.screamingface.ai` → `file_server` on
  `~/screamingface/public-docs/dist` + SPA fallback + gzip. Includes a **temporary**
  `basicauth` keep-out gate (login shared privately) — removable by deleting the
  `basicauth` block + reloading Caddy. (This VM runs Caddy < 2.8, so the directive is
  `basicauth`, one word.)
- Repo secrets set. DNS record + Caddy reload still pending.

## Test plan

- Local: `npm run build && npm run preview`.
- Transfer: run the Action → `ls ~/screamingface/public-docs/dist` on the VM.
- Live: point `docs.screamingface.ai` at the VM → Caddy auto-TLS → verify HTTPS + login.

## Acceptance

- Merge to `main` touching `public-docs/**` deploys the built site to the VM.
- `https://docs.screamingface.ai` serves the docs (temporary password gate active).

## Outcome (fill at close)

- **Files:** `.github/workflows/deploy-public-docs.yml`
- **Commits:** pending
- **Gates:** workflow YAML valid (ruby parse) + `bash -n` on the rsync step OK.
- **Deviations:** none — built as planned.
- **Status:** not live yet — pending commit + merge, DNS record, Caddy reload.
