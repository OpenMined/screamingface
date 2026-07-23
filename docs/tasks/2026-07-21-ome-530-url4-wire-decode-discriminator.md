---
id: OME-530
linear_url: https://linear.app/openmined/issue/OME-530/url4-dual-convention-wire-decode-mis-parses-fully-encoded-non-group
status: Done
type: Bug
priority: P2
labels: [url4-engine, autonomous, agentic]
created: 2026-07-21
closed: 2026-07-21
---

# url4: dual-convention wire decode mis-parses fully-encoded non-group heads

`_fully_encoded` only recognized a `%28` head, so a standard client's
fully-encoded relative (`%2F`) or remote (`url4%3A`) payload fell into the raw
decoder mangled to `()!<text>`; the raw branch of `decode_expression_http`
assumed the `(context)!intent` envelope, truncating paren-collection
iterations. Fixed with a paren-based discriminator (a raw `(` is always
structural) + envelope-only part-unquoting. Spec §3.4: a node accepts over
HTTP exactly what it accepts in-process. Under OME-500.

See `docs/work/2026-07-21-OME-530-wire-decode-discriminator.md`.
