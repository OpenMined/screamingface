"""Phase 0 contract example: a tiny benchmark with no ingestion abstraction."""

import screamingface as sf

benchmark = sf.Benchmark(
    "arithmetic-smoke-test",
    title="Arithmetic smoke test",
    cases=[
        sf.Case(
            id="addition",
            input="What is 2 + 2?\n\nA. 3\nB. 4\n\nReply with only A or B.",
            reference="B",
        ),
        sf.Case(
            id="multiplication",
            input="What is 3 × 3?\n\nA. 9\nB. 6\n\nReply with only A or B.",
            reference="A",
        ),
    ],
    grader=sf.graders.ExactChoice(),
    aggregator=sf.aggregators.Mean(),
)
