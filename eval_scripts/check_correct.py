# -*- coding: utf-8 -*-
"""
check_correct.py

This module is evaluated on the URL4 node, not run as a standalone process.
The node defines it in a sandbox and calls main() with the row's two bound
source values passed directly as arguments — not via argv or stdin.

Both inputs are nominally strings; the check is stripped, case-folded string
equality — the minimal normalization a deterministic compare needs. A value
that cannot be coerced raises, which the node maps to intent_error.
"""


def main(correct_answer: str, consensus: str) -> dict:
    ground_truth = "" if correct_answer is None else str(correct_answer).strip()
    predicted = "" if consensus is None else str(consensus).strip()
    correct = predicted != "" and predicted.casefold() == ground_truth.casefold()
    return {
        "correct": bool(correct),
        "predicted": predicted,
        "ground_truth": ground_truth,
    }


# --- local verification only; ---
def _self_test() -> int:
    cases = [
        (("A", "A"), True, "letter match"),
        (("A", "B"), False, "letter miss"),
        (("C", "c"), True, "case-fold"),
        (("D", " D "), True, "whitespace"),
        (("42", "42"), True, "exactMatch-style string"),
        (("A", ""), False, "empty consensus"),
    ]
    ok = True
    for (gt, pred), expected, label in cases:
        got = main(gt, pred)["correct"]
        ok &= got == expected
        print(
            f"[{'PASS' if got == expected else 'FAIL'}] {label}: "
            f"correct_answer={gt!r} consensus={pred!r} -> {got} (want {expected})"
        )
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_self_test())
