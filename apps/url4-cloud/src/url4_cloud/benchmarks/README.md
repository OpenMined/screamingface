# Benchmark authoring

Each benchmark family is a self-contained Python package. The package exports exactly one
`Benchmark` value for each installed tier; URL4, REST discovery, and subprocess wiring remain
shared infrastructure.

```text
benchmarks/
├── __main__.py        # the single /benchmark command entrypoint
├── registry.py        # explicit installed-benchmark list
├── _types.py          # shared runtime and wire helpers
└── draco/
    ├── __init__.py    # exports DRACO_LITE
    ├── definition.py  # identity, manifest, and action wiring
    ├── cases.py       # pinned cases or dataset loading
    ├── prompts.py     # answer, synthesis, and judge instructions
    └── grading.py     # judge preparation, parsing, scoring, and aggregation
```

## Add a benchmark

1. Create `benchmarks/<family>/`.
2. Put pinned cases or lazy dataset loading in `cases.py`.
3. Put benchmark-owned instructions in `prompts.py`.
4. Implement the deterministic `load`, `grading_inputs`, `grade`, and `aggregate` actions in
   `grading.py`. Model calls do not belong here: Candidate, synthesis, and judge calls remain
   explicit URL4 model nodes.
5. Construct and export one `Benchmark` from `definition.py`.
6. Re-export it from the family’s `__init__.py`.
7. Add one explicit import and value to `registry.py`.

## Evaluation lifecycle

Researchers see four stages: **Load → Run → Grade → Aggregate**.

The `/benchmark` command exposes implementation actions, not additional lifecycle stages.
`grading_inputs` creates the judge work consumed by URL4 inside Grade; it is not shown as a
separate stage.
8. Test the installed value only through `Benchmark.execute(...)` and the catalogue routes.

Do not add a benchmark-specific URL4 command or edit `url4.toml`. Every benchmark uses the one
`/benchmark` command and is selected by its registry ID.

## When to share code

Keep benchmark-specific grading inside its family. Extract shared grading machinery only after
two implemented benchmarks demonstrate identical behavior. This keeps the authoring interface
small without forcing unlike benchmarks into a growing set of generic modes.
