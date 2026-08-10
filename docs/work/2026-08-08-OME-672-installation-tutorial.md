---
ticket: OME-672
stack: repo
status: done
started: 2026-08-08
finished: 2026-08-08
---

# OME-672 — Add installation tutorial

## Intent

Fourth sub-issue of `OME-666`. `InstallationPage.vue` is an 18-line stub reading "Stub page —
replace with real content", while the sidebar has listed it under Get Started since `OME-667`.
A reader arriving from the Overview or from the Learn section's Architecture page finds nothing.

Nothing on the site currently says how to get a working environment: not how to install the
client, not how to reach an engine, not what a self-hosted stack needs.

## Planned changes

- `public-docs/src/pages/sf-client/InstallationPage.vue` — replace the stub
- this ledger and `docs/tasks/2026-08-08-installation-tutorial.md`

## Test plan

`public-docs` has no test suite. Verification is the gates CI runs, plus manual checks:

- `npx oxlint .` · `npx eslint .` — bare, as CI runs them
- `npm run build`
- `npx prettier --check` on the touched files
- Every command on the page run against a real local stack before it is written down
- Light and dark theme, and at 400px with no horizontal page scroll

## Acceptance

- The page covers two paths, in this order: a hosted engine, then running your own
- It uses the Learn section's vocabulary — bundled / self-hosted / hosted
- Every command is one we have actually run
- Python version, the `[notebook]` extra, and the fact that `screamingface` is not yet on PyPI
  are all stated
- The self-hosted path names what actually blocked us: migrations, `AIGW_AUTH_MODE=disabled`,
  `AIGW_OPENROUTER_ENABLED=true`, benchmark asset preparation
- No invented engine address — the placeholder constant is used
- Gates green: lint, build, format on touched files

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** 4 changed, +335 / −2.
  - `public-docs/src/pages/sf-client/InstallationPage.vue` — the page
  - `public-docs/src/components/ui/Note.vue` — new inline callout
  - this ledger and the `docs/tasks` mirror
- **Commits:**
  - `7f3e2f09` — feat(public-docs): write the Installation page
- **Gates:** `oxlint` and `eslint` clean, run bare as CI does · `build` succeeds ·
  `prettier --check` clean on the touched files. `public-docs` has no test suite.
- **Verification:** every install command was executed in a throwaway venv before being written
  down. `uv build` produces `screamingface-0.2.0-py3-none-any.whl`; it installs into a clean
  Python 3.12 and imports 36 public names, resolving `url4` from PyPI. The `[notebook]` extra
  resolves `ipywidgets 8.1.8`. The one-line git install works and pins `e387aefd`, the commit the
  sidebar stamps — though it resolves `url4` from the same repository rather than PyPI, so the two
  routes do not produce identical dependency sets.
- **Deviations:**
  - **Restructured from the parent's spec.** `OME-666` describes Installation as local-first, with
    `sf.config(engine=…)` and port `4404`. Both are wrong against the current client, and hosted is
    now the primary path, so the page leads with hosted and keeps self-hosting as section 3.
  - **A `Note` component was added.** The source docs repeat the callout as inline Tailwind on each
    use; here it is a component so the styling stays in one place.
  - **The FAQ uses `Collapsible`**, following the pattern and the "Frequently Asked Questions"
    heading used on eleven pages of `syft-space-hub-docs`.
  - **Em-dashes were removed from this page only**, at the owner's request. The rest of the section
    still uses them, so this page reads slightly differently from its neighbours.
  - **`CodeBlock` does not respect the theme** — it is hardcoded `bg-zinc-900` and renders dark in
    light mode. Left alone deliberately: it is shared with the Learn pages, which are owned
    elsewhere, and terminal chrome staying dark is defensible.
