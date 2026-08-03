# OME-620 — Local catalogue discovery plan

1. Add failing Engine and Client tests for synchronous, asynchronous, and lazy-default Benchmark
   ID listing, malformed payloads, and Engine failures.
2. Add a narrow Engine composition input for registered Benchmark IDs and expose it at
   `GET /v1/benchmarks`.
3. Decode the OpenAI-style list envelope into an immutable Client sequence behind
   `Client.benchmarks`.
4. Export module-level `sf.models.list()` and `sf.benchmarks.list()` through the lazy Client.
5. Permit anonymous model discovery only in the isolated loopback Engine demo by using the
   Engine process's configured AI Gateway credential.
6. Align discovery fixtures and the generated demo notebook on the canonical unversioned
   `draco` identifier.
7. Validate Engine and Client tests, Ruff, Pyright, notebook structure, and a no-spend catalogue
   call.
8. Add failing runner configuration and execution tests for `[commands]`, including substitutions,
   malformed argv, and Model-route collisions.
9. Register command handlers beside AI Gateway handlers on the same `Url4Node`, using the exact
   `url4 serve` subprocess semantics without importing its private CLI module.
10. Add the internal benchmark registry and deterministic `/benchmark` command only after the
    generic command-route contract is green.
11. Compile candidate and judge calls as explicit URL4 Model routes; the benchmark command performs
    no paid execution.
