import pytest

from screamingface.plugins.python_runner.runner import run_script_main

TWO_ARG = """
def main(correct_answer, consensus):
    return {"correct": correct_answer.strip().casefold() == consensus.strip().casefold(),
            "predicted": consensus.strip()}

if __name__ == "__main__":
    raise SystemExit("self-test must NOT run under call-main")
"""

ONE_ARG = """
def main(checks):
    rows = checks if isinstance(checks, list) else []
    return {"n": sum(1 for r in rows if isinstance(r.get("correct"), bool))}
"""


@pytest.mark.asyncio
async def test_call_main_filters_to_declared_params_and_skips_self_test():
    out = await run_script_main(
        TWO_ARG, {"correct_answer": "B", "consensus": " b ", "question": "q", "expected": "B"}
    )
    assert out == {"correct": True, "predicted": "b"}


@pytest.mark.asyncio
async def test_call_main_single_param_takes_bare_list():
    out = await run_script_main(ONE_ARG, [{"correct": True}, {"correct": False}, {"x": 1}])
    assert out == {"n": 2}
