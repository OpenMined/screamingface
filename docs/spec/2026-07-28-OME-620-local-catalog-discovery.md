# OME-620 — Local catalogue discovery vertical slice

## Scope

The isolated DRACO demo exposes the intended Client discovery interface against the real
OME-587 local Engine:

```python
sf.models.list()
sf.benchmarks.list()

client.models.list()
client.benchmarks.list()
```

`AsyncClient` exposes the same names as awaitable operations. Module-level operations delegate to
the existing lazy default Client.

## Contract used by this demo

- `GET /v1/models` returns the Engine-proxied OpenAI-style model catalogue.
- `GET /v1/benchmarks` matches the OpenAI-style list envelope used by `GET /v1/models`, with
  minimal entries:

  ```json
  {
    "object": "list",
    "default": "draco",
    "data": [
      {"id": "draco", "object": "benchmark"},
      {"id": "healthbench-lite", "object": "benchmark"}
    ]
  }
  ```
- Model rows decode to frozen `sf.ModelInfo(id, provider)` values.
- Benchmark discovery returns an immutable ordered sequence of strings.
- Benchmark evaluation without an override resolves the catalog's explicit `default`; list order
  is presentation-only.
- The public DRACO identifier is `draco`; manifests remain reproducibly pinned by their
  digest rather than by exposing an `@1` suffix in the user-facing name.
- The Client calls only the configured SF Engine.
- Trusted loopback local mode may use its configured AI Gateway credential when the caller sends
  none. Hosted mode continues to require and forward caller authentication.
- The Engine advertises only IDs whose execution routes are installed. An Engine with no
  registered Benchmarks returns `{"object": "list", "default": null, "data": []}`.
- Invalid payloads and transport failures raise typed ScreamingFace errors.

This is conformance evidence for the proposed catalogue interface, not a claim that the production
catalogue schemas or hosted authentication contract have been finalized.

## Explicit URL4 benchmark execution

The cloud runner accepts URL4's existing `[commands]` table in its declared world. Command routes
are registered on the same `Url4Node` as AI Gateway model routes and preserve the established
`url4 serve` substitutions:

- `{context}` — resolved call context, also supplied on stdin.
- `{intent}` — resolved call intent.
- `{params}` — all decoded protocol parameters as stable JSON.
- `{param:<name>}` — one decoded parameter, or an empty string when absent.

The MVP registers one deterministic benchmark leaf:

```toml
[commands]
"/benchmark" = [
  "python3",
  "-m",
  "url4_cloud.benchmarks",
  "--intent",
  "{intent}",
]
```

Benchmark commands may load cases, prepare or parse grading values, calculate deterministic
scores, and aggregate results. They must not call candidate or judge Models. Every paid Model,
Fusion synthesis, and judge operation remains an explicit URL4 model route so normal spans,
usage, cost, failures, and results describe the whole evaluation.

Command configuration is operator-owned and baked into the same image used by both serving and
Job modes. Unknown keys, malformed argv, reserved paths, and collisions with declared Model routes
fail before execution. Local and hosted runs build the same declared URL4 world.
