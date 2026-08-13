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
