"""DRACO — Perplexity's research-quality rubric benchmark (`perplexity-ai/draco`).

Ground truth is a WEIGHTED RUBRIC, not a reference answer: ~40 criteria grouped into sections,
where a NEGATIVE weight marks behaviour the answer must not show. Text-similarity metrics are
meaningless here; only a judge reading the rubric can produce a score.

Reference: arXiv:2602.11685 §4.2 · `screamingface-benchmarks/docs/draco-benchmark-anatomy.md`
"""
