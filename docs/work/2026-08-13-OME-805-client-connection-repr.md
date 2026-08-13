---
ticket: OME-805
stack: screamingface
status: done   # planned | in_progress | done | blocked
started: 2026-08-13
finished: 2026-08-13
---

# OME-805 — Connection-card repr for the ScreamingFace client + a connection tutorial notebook

## Intent

`sf.configure(...)` / `sf.Client(...)` return a `Client` that renders in a notebook as the
opaque `<screamingface.client.Client at 0x…>`, while every other domain object already renders
as a branded SFDS card. Give the client a `_repr_html_` connection card so a user can see, at a
glance, which engine + scoreboard it is wired to (plus locally-derived status chips), and add a
tutorial notebook teaching how to point the client at an engine and how to supply credentials
(BYOK vs hosted credits). Improves first-run legibility of the Python client SDK.

## Planned changes

- `src/screamingface/_ui/cards.py` — new `client_card_html(client)` + a small no-network
  environment/chips helper, built from the existing `CARD_STYLE` + `_field`/`_mono`/`_chip`
  helpers, following the `model_card_html` skeleton (solid-gold accent, kicker `client`).
- `src/screamingface/client.py` — `_repr_html_(self)` on `Client` and `AsyncClient`, lazily
  importing `client_card_html` (mirrors `model.py`). No change to `configure()` or `__all__`.
- `tests/test_rich_display.py` — RED-first repr tests (existing `_client`/`MockTransport`).
- `examples/02_connection.ipynb` — new tutorial: (A) point-at-engine via env vars /
  `sf.configure` / explicit `sf.Client`; (B) credentials — BYOK vs hosted credits, mutually
  exclusive. Output-free, deterministic, Run All never spends/authenticates.

## Test plan

- `Client(...)._repr_html_()` is a `str` containing `sf-ui`, `sf-card`, kicker `client`, and
  both the engine and scoreboard URLs.
- Environment chip: `127.0.0.1` / `localhost` engine → `local`; a `*.screamingface.ai` engine
  → `hosted`.
- Lifecycle chip flips to `closed` after `client.close()`; auth chip reflects
  `client.authenticated`.
- URL/value HTML-escaping (no raw-string injection).
- `AsyncClient` exposes the same repr.

## Acceptance

- Both clients render the connection card in Jupyter.
- `examples/02_connection.ipynb` runs top-to-bottom without a running engine (construction
  opens no network) and never authenticates or spends (live cells guarded).
- `run_gates.py` green for the `screamingface` stack (ruff, ruff format, pyright,
  pytest `--cov-fail-under=95`, notebook check, `uv build`, distribution check).

## Outcome

- **Actual files (as planned):**
  - `src/screamingface/_ui/cards.py` — `client_card_html()` + `_ClientLike` Protocol +
    `_status_chips` / `_status_chip` / `_is_local_engine` (no-network, reuses `CARD_STYLE`,
    `_field`, `_mono`, `_section`).
  - `src/screamingface/client.py` — `_repr_html_` on `Client` and `AsyncClient` (lazy import).
  - `tests/test_rich_display.py` — 6 appended tests + `_FakeClient` stand-in.
  - `scripts/build_notebooks.py` — `_connection()` builder + registration; generated
    `examples/02_connection.ipynb` (14 cells). Other notebooks left untouched.
  - `docs/work/…` + `docs/tasks/…` — this ledger + mirror.
- **Commits:** filled in the Linear close comment (squash-merge sha).
- **Gates:** `run_gates.py screamingface` — ALL GREEN (append-only check, ruff check, ruff
  format, pyright, pytest `--cov-fail-under=95`, notebook check, `uv build`, distribution
  check). Full suite 711 passed / 1 skipped.
- **Deviations:**
  - The `authenticated` "signed in" branch and the HTML-escaping invariant are exercised at
    the renderer level (`client_card_html` + a structural `_FakeClient`) rather than through a
    live Cloudflare Access login or an HTML-metacharacter host (httpx rejects such hosts, and a
    live login needs a browser). The not-signed-in / open / closed / local / hosted branches are
    covered end-to-end through real `Client`/`AsyncClient` instances.
  - Status chips are neutral (`sf-chip--muted`), keeping gold rationed to the card accent per
    SFDS v2 (a client is not "the win"); zero new CSS was added.

## Follow-on folded into this unit (owner-approved during review)

Relabeled the hosted-login row in the `sf.connect()` panel and simplified the notebook's
hosted-credits section to lead with the `sf.connect()` panel (which drives the Cloudflare Access
login itself) rather than an explicit `session.login()` block.

The row label is **engine-aware**: ScreamingFace's own hosted Engine (the `*.screamingface.ai`
family) renders **"ScreamingFace Hosted Engine"** with the **😱** mark; any other remote Engine
renders a neutral **"Hosted Engine"** with the monogram fallback (no brand logo). This keeps the
brand honest — a user's self-hosted engine isn't mislabeled as ScreamingFace's.

- `src/screamingface/_ui/connection_state.py` — new `_is_screamingface_engine()` classifier;
  `_ConnectionPanelState` gains an `engine_url` field.
- `src/screamingface/_ui/connections.py` — pass `engine_url` when building the panel state.
- `src/screamingface/_ui/connection_view.py` — `_access_meta_html(status, engine_url)` picks the
  label + icon; new `_screaming_mark_html()` renders the 😱 mark (system emoji, per SFDS).
- `src/screamingface/_ui/assets/provider_icons/NOTICE.md` — descriptive reference updated.
- `tests/test_connection_panel.py` — 3 prior assertions (lines 162/532/810) updated to the new
  labels + 😱, plus a new appended test for the non-ScreamingFace hosted engine (neutral label,
  no mark). **The 3 prior-assertion edits modify prior tests (sdlc rule 5).** The owner approved
  the relabel explicitly, so the change is authorized; the local `append-only` gate was passed
  with the sanctioned `--skip-append-only` override. CI (`screamingface-tests.yml`) does not run
  that meta-check and is unaffected — all 19 panel tests pass.
- `scripts/build_notebooks.py` / `examples/02_connection.ipynb` — Option 2 rewritten (login is
  panel-driven; the row label is engine-specific, so the prose no longer hard-codes it).

This was folded here (rather than a new ticket) per the owner's standing preference to keep
small follow-on UI tweaks under the in-progress unit; OME-805's scope note was widened to match.
Re-ran `run_gates.py screamingface --skip-append-only` — all green.
