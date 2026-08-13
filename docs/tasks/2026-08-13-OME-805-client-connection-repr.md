---
id: OME-805
linear_url: https://linear.app/openmined/issue/OME-805/add-a-branded-connection-card-repr-to-the-screamingface-client-a
status: done
type: feature
priority: medium
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-13
closed: 2026-08-13
---

# Add a branded connection-card repr to the ScreamingFace client + a connection tutorial notebook

`sf.configure(...)` / `sf.Client(...)` render as the opaque `<screamingface.client.Client at
0x…>` while every other domain object renders as a branded SFDS card. Add a `_repr_html_`
connection card to `Client`/`AsyncClient` showing engine + scoreboard URLs plus no-network
status chips (local/hosted, open/closed, signed-in), built from the existing `CARD_STYLE`
helpers in `_ui/cards.py`. Add `examples/02_connection.ipynb` teaching how to point the client
at an engine (env vars / `sf.configure` / explicit `sf.Client`) and how to supply credentials
(BYOK vs hosted credits, mutually exclusive). No changes to `configure()`'s return type, the
`sf.connect` panel, the `Connection` schema, or the engine.
Ledger: `docs/work/2026-08-13-OME-805-client-connection-repr.md`.
