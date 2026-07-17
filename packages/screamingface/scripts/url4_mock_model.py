"""Command wrapper around ScreamingFace's deterministic URL4 model routes."""

from __future__ import annotations

import sys

from screamingface._mock_engine import mock_model_answer


def main() -> None:
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("usage: url4_mock_model.py MODEL_ID [PROMPT]")
    if len(sys.argv) == 3:
        intent = sys.argv[2]
        context = sys.stdin.read()
    else:
        intent = sys.stdin.read()
        context = ""
    try:
        result = mock_model_answer(sys.argv[1], intent, context)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    print(result)


if __name__ == "__main__":
    main()
