"""Run the real DRACO-Lite vertical slice against the local SF Engine demo."""

import screamingface as sf

print(sf.benchmarks.list())
print(sf.models.list())

ANSWER_INSTRUCTIONS = """Answer the research question completely.
Compare the estimators and their assumptions precisely, address pre-trend testing, and cite
specific papers and evidence where useful."""


candidate = sf.Model(
    "anthropic/claude-haiku-4-5",
    instructions=ANSWER_INSTRUCTIONS,
    max_output_tokens=4096,
)

with sf.Client() as client:
    report = client.evaluate(
        candidate,
        benchmark="draco-lite",
        limit=1,
        on_event=lambda event: print(f"{event.sequence:02d} {event.kind}"),
    )

print(report)
print(report.candidates.only.url4)
print(report.to_json())
