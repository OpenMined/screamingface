# -*- coding: utf-8 -*-
"""
calculate_accuracy.py

This module is evaluated on the URL4 node, not run as a standalone process.
The node defines it in a sandbox and calls main() with the $checks collection
passed as a single argument. Because the collection is structured, it arrives
as a stringified JSON array — not via argv or stdin.

stringified JSON of the $checks collection, e.g.
  '[{"index":0,"correct":true,"predicted":"A", "ground_truth":"A"}, ...]'

returns the accuracy report:
  { "accuracy_pct", "stderr_pct", "n", "n_correct", "summary" }

Accuracy = n_correct / n; binomial standard error = sqrt(p(1-p)/n), mirroring
HLE's "Accuracy: X% +/- Y% | n = N" line.

The iteration runs with ;foreach.on_error=collect, so a failed row may appear
in the collection as an error element rather than a verdict. An element without
a boolean `correct` is counted as an error and excluded from the denominator,
so attrition cannot silently inflate accuracy.

A malformed `checks` string raises (JSONDecodeError / ValueError), which the
node maps to intent_error.
"""

import json
import math


def main(checks: str) -> dict:
    rows = json.loads(checks) if isinstance(checks, (str, bytes, bytearray)) else checks
    if not isinstance(rows, list):
        raise ValueError("checks must decode to a JSON array (the $checks collection)")

    n_correct = n_graded = n_errors = 0
    for r in rows:
        if isinstance(r, dict) and isinstance(r.get("correct"), bool):
            n_graded += 1
            n_correct += int(r["correct"])
        else:
            n_errors += 1

    acc = n_correct / n_graded if n_graded else 0.0
    se = math.sqrt(acc * (1 - acc) / n_graded) if n_graded else 0.0
    report = {
        "accuracy_pct": round(acc * 100, 2),
        "stderr_pct": round(se * 100, 2),
        "n": n_graded,
        "n_correct": n_correct,
        "summary": f"Accuracy: {acc * 100:.2f}% +/- {se * 100:.2f}% | n = {n_graded}"
        + (f" | errors = {n_errors}" if n_errors else ""),
    }
    if n_errors:
        report["n_errors"] = n_errors
    return report


# --- local verification only; ---
def _self_test() -> int:
    verdicts = [
        {"index": 0, "correct": True, "predicted": "A", "ground_truth": "A"},
        {"index": 1, "correct": False, "predicted": "B", "ground_truth": "C"},
        {"index": 2, "correct": True, "predicted": "D", "ground_truth": "D"},
    ]
    r = main(json.dumps(verdicts))  # passed as stringified JSON
    ok = r["n"] == 3 and r["n_correct"] == 2 and abs(r["accuracy_pct"] - 66.67) < 0.01
    print(f"[{'PASS' if ok else 'FAIL'}] {r['summary']}")

    with_error = verdicts + [{"index": 3, "error": {"code": "intent_error"}}]
    r2 = main(json.dumps(with_error))
    ok2 = r2["n"] == 3 and r2.get("n_errors") == 1
    print(
        f"[{'PASS' if ok2 else 'FAIL'}] on_error=collect element excluded: {r2['summary']}"
    )

    allok = ok and ok2
    print("ALL PASS" if allok else "SOME FAILED")
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(_self_test())
