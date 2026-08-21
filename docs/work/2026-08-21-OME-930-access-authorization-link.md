---
ticket: OME-930
stack: screamingface
status: planned
started: 2026-08-21
finished:
---

# OME-930 — present the Access authorization URL in the panel

## Intent

Clicking **Log in** in Colab does nothing visible: the authorization URL is written to
stdout from a worker thread inside a widget callback, and `_running_in_notebook()` does not
recognise Colab so the client also opens a browser on the Colab VM. Give the panel the URL
so it can render a real anchor, which is the only thing that can reach the user's own
browser from a remote kernel.

FEATURE: hosted-Engine connection panel (`sf.connect()`) — Cloudflare Access login.
STORY: as a Colab user clicking Log in, I get a link I can click that opens Cloudflare
Access in my own browser, and the panel then shows me as authenticated.

Blocks onboarding: `sf.connect()` is the entrypoint in six shipped notebooks including the
quickstart, and the only auth surface a non-power user meets.

## Planned changes

Per `docs/plan/2026-08-21-OME-930-access-authorization-link.md`:

- `_access/auth.py` — `subscribe_authorization()` on `_CloudflareAccessAuth`; notify
  subscribers at the existing `_present_browser` call site (`:439`), additively, so the
  terminal and existing tests are untouched. A raising subscriber must not fail the login.
- `_access/base.py` — declare it on the `_ClientAuth` protocol.
- `client.py` — `_subscribe_authorization()` on `Client` **and** `AsyncClient`, mirroring
  `_subscribe_auth`. No public surface change; `login()`'s signature is untouched.
- `_ui/connection_state.py` — `access_authorization_url: str | None`.
- `_ui/connections.py` — register the presenter in `widget()`, route it through
  `self._dispatcher` (it arrives on the login worker thread), unsubscribe in `close()`,
  clear the URL on success/cancel/error.
- `_ui/connection_view.py` — render an `Authorize ↗` anchor beside Cancel, reusing the
  OAuth row's `target="_blank" rel="noopener noreferrer"` treatment.
- `_access/contract.py` — `_running_in_notebook()` also recognises `google.colab`.

No schema or model change, so S1 does not apply.

## Test plan

RED first, append-only. Reuse the `browser_presenter=` fixture style already in
`tests/test_authentication.py`.

- Anchor carrying the authorization URL appears in the widget while login is pending.
- The presenter fires from a worker thread and still reaches the widget.
- URL cleared on success, on cancel, and on error.
- A presenter that raises does not fail the login.
- `_running_in_notebook()` parametrized over `google.colab._shell`, `ipykernel.*`, neither.
- Terminal path unchanged — `webbrowser.open` still called outside a notebook.
- The URL is HTML-escaped in the anchor.
- `_access` does not import `_ui`.

## Acceptance

The spec's eight acceptance criteria, and
`uv run .claude/scripts/run_gates.py screamingface` green including the 95% coverage floor.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** TBD
- **Commits:** TBD
- **Gates:** TBD
- **Deviations:** TBD
