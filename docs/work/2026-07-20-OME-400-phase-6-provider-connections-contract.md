---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 6 provider connections contract

## Intent

Record the owner-reviewed model-provider connection boundary before changing the SDK, development
engine, Docker topology, or notebooks. Resolve ownership, routes, privacy, dataset separation,
stage-specific preflight, OAuth/API-key behavior, and notebook UX as one coherent contract.

## Planned changes

- Add a normative Phase 6 provider-connections spec.
- Add an implementation plan split into reviewed 6A SDK, 6B engine, and 6C UX/preflight slices.
- Reconcile the benchmark architecture plan, benchmark contract, and OME-400 task mirror.
- Change no runtime, test, notebook, URL4, or AI Gateway behavior.

## Test plan

- Check Markdown formatting and links mechanically.
- Search the reconciled docs for superseded claims that authentication remains wholly deferred.
- Confirm the approved API, routes, schemas, statuses, security rules, and implementation phases
  agree across the records.
- Confirm no runtime file changed.

## Acceptance

- Model-provider connections and researcher-local dataset access are unambiguously separate.
- The SDK, engine, and Gateway each have one credential responsibility.
- Public provider capabilities and private user status are distinct.
- The exact public Python API and protected engine routes are recorded.
- Stage-specific preflight does not gate benchmark loading.
- Local-only anonymous operation and future hosted identity are not conflated.
- Implementation remains blocked on explicit owner approval for each phase.

## Outcome

- **Actual files:** added the Phase 6 normative spec, phased implementation plan, and this work
  record; reconciled the benchmark architecture plan, benchmark contract, and OME-400 task mirror.
  No runtime, test, notebook, URL4, or AI Gateway file changed.
- **Commits:** pending owner commit for this documentation-only unit.
- **Gates:** `git diff --check`, trailing-whitespace scan, Markdown fence-parity checks, focused
  stale-contract search, and relative target existence checks passed. All changed paths are under
  `docs/`; runtime gates were not run for this documentation-only unit.
- **Deviations:** none.
