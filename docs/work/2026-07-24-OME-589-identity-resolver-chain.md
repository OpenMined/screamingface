---
ticket: OME-589
stack: aigateway
status: in_progress
started: 2026-07-24
finished:
---

# OME-589 — Refactor current_account into an ordered IdentityResolver chain

## Intent

Behavior-preserving refactor. `current_account()` hard-codes one credential shape (local
HS256 bearer). Cloudflare Access (OME-591) and gateway API keys (OME-592) need to plug in
without touching that path, so replace the if-tree with an ordered chain of resolvers behind
a port, registry-wired in `main.py` (core never imports adapters — root `CLAUDE.md`).

## Design decisions

**Three-valued resolution.** A resolver returns `BaseAccount` (authenticated), `Rejection`
(recognized this credential and refused it), or `None` (not my credential — fall through).
The driver keeps the **first** `Rejection` and still tries later resolvers, so a credential
one resolver cannot verify can still be authenticated by another; only an exhausted chain
raises. This is what preserves the existing specific 401 bodies (`expired`,
`malformed subject`) that a naive "return None on failure" chain would flatten into a
generic message.

**Disjoint recognition via the JOSE `alg` header.** `LocalJwtResolver` claims a bearer token
only when its unverified JOSE header says `HS256`; anything else falls through (Cloudflare
signs RS256). Reading the *unverified* header is safe because it is used only for routing —
`decode_token` still pins `algorithms=["HS256"]`, so algorithm-confusion remains impossible.
Disjoint recognition is what makes "first rejection wins" unambiguous.

## Planned changes

- create `core/auth/resolvers/__init__.py`, `base.py` (`IdentityResolver`, `Rejection`),
  `local_jwt.py` (`LocalJwtResolver`)
- modify `core/auth/middleware.py` — `current_account()` drives `app.state.identity_resolvers`
- modify `main.py` — build + register the chain
- create `tests/unit/auth/test_resolver_chain.py`

No schema change → no migration this unit (S1 n/a).

## Test plan

- chain order: first resolver's account wins, later resolvers never invoked
- fall-through: `None` → next resolver
- a `Rejection` does not stop the chain; a later account still authenticates
- exhausted chain with a recorded rejection → that rejection's status/detail
- exhausted chain with no rejection → 401 "Missing bearer token"
- first rejection wins over a later one
- `auth_enabled=False` short-circuits ahead of the chain (resolvers never invoked)
- `LocalJwtResolver` falls through on an RS256 token, rejects an unparseable one

## Acceptance

- All 14 pre-existing `tests/unit/auth/` modules pass **unmodified**.
- `current_account` contains no credential-format knowledge.

## Outcome

- **Actual files:** as planned — `core/auth/resolvers/{__init__,base,local_jwt}.py` (new),
  `core/auth/middleware.py`, `main.py`, `tests/unit/auth/test_resolver_chain.py` (14 tests).
- **Commits:** NONE — see Deviations.
- **Gates:** `run_gates.py aigateway` ALL GREEN (append-only check · ruff check · ruff
  format · pyright · check_no_enterprise · pytest 80% cov). Auth suite 76 passed; all 14
  pre-existing `tests/unit/auth/` modules unmodified.
- **Deviations:**
  1. **COMMIT BLOCKED — owner decision required.** This worktree already carried
     *uncommitted, unrelated* work (the shared-credential-pools feature: `config.py`,
     `db.py`, `routes/chat_credentials.py`, `core/credential_pool/`, migrations `0008`/`0009`)
     that **modifies the same two files this unit touches** — `main.py` and
     `core/auth/middleware.py`. Any commit here either sweeps that unrelated feature in or
     needs a partial-hunk stage of files under active edit. Left in the working tree instead;
     branch `OME-588-cloudflare-access-auth` was created off the dirty tree.
  2. `Rejection.headers` was designed in, then removed during the wisdom review as
     speculative generality — no consumer in any of the five planned units.
  3. The `tortoise-dev` companion skill (`mandatory: true` in `.claude/sdlc.local.md`) is not
     installed in this environment. Not applicable to this unit (no schema change), but it
     binds OME-590 and OME-592.
