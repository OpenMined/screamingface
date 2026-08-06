"""COPIED third-party code — the official IFEval checker. Do not edit.

What this is
    The files under `vendor/` are the copy of files from https://github.com/josejg/instruction_following_eval
    at commit 0c495b2f95155e8b10acb919ae283bfb4d5be6e2 (2025-01-16):
    ``instructions.py``, ``instructions_util.py``, ``instructions_registry.py``.
    License: Apache-2.0 (the LICENSE file here is copied from the same repo).

Why a copy instead of pip
    The package is not on PyPI, and a Runner Job cannot reach GitHub at run time.
    This fork (not Google's original) is the one inspect_evals pins — the
    community-standard checker.

The ONLY changes we made
    1. A "VENDORED COPY" banner at the top of each file linking to its exact
       source file at the pinned commit.
    2. Two import lines rewritten from ``from instruction_following_eval
       import x`` to ``from . import x`` so the copy works inside this
       package (one in ``instructions.py``, one in ``instructions_registry.py``).
    Everything else is byte-identical to the fork.

Protocol oracle
    ``evaluation_lib.py`` is the strict/loose checking excerpt from Google's official
    evaluator at the commit named in ``..definition``. It is used only during benchmark
    preparation to prove ``..grading`` agrees on every prepared Case and all four global
    metrics. The dataset file is downloaded from HuggingFace at a pinned revision and its
    one divergent prompt is repaired explicitly in ``..prepare``.

INVARIANT: please do not edit these files. This checker IS the exam — changing it
changes every published IFEval score. Any intentional update must also update
VERIFIER_REVISION in ``..definition`` so the exam's REVISION hash changes.

AIDEV-NOTE: never call the fork's nltk download helper. The Job is offline with
a read-only disk; tokenizer data comes from the prepared assets directory via
``..grading.configure_nltk``.
"""
