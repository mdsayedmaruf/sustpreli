"""Run the new edge/adversarial case pack against the real reasoning engine.

Usage (from repo root):
    cd backend && python ../tests/new_cases/run_new_cases.py
"""
from __future__ import annotations

import json
import os
import sys

# Make `app` importable whether run from repo root or backend/.
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.reasoning import analyze  # noqa: E402
from app.schemas import AnalyzeTicketRequest  # noqa: E402

CASES_PATH = os.path.join(HERE, "SUST_New_Hidden_Cases.json")

_BENGALI = lambda s: any("ঀ" <= ch <= "৿" for ch in s)


def check(case: dict) -> list[str]:
    exp = case["expected"]
    req = AnalyzeTicketRequest(**case["input"])
    res = analyze(req)
    fails: list[str] = []

    def eq(field: str):
        if field in exp and getattr(res, field) != exp[field]:
            fails.append(f"{field}: got {getattr(res, field)!r}, expected {exp[field]!r}")

    for f in ("relevant_transaction_id", "evidence_verdict", "case_type",
              "severity", "department", "human_review_required"):
        eq(f)

    reply = res.customer_reply
    for bad in exp.get("reply_must_not_contain", []):
        if bad.lower() in reply.lower():
            fails.append(f"reply_must_not_contain: found forbidden {bad!r}")
    needed = exp.get("reply_must_contain_any")
    if needed and not any(n.lower() in reply.lower() for n in needed):
        fails.append(f"reply_must_contain_any: none of {needed} present")
    if exp.get("reply_is_bangla") and not _BENGALI(reply):
        fails.append("reply_is_bangla: reply is not Bangla")

    return fails


def main() -> int:
    with open(CASES_PATH, encoding="utf-8") as fh:
        pack = json.load(fh)

    total = passed = 0
    for case in pack["cases"]:
        total += 1
        fails = check(case)
        if fails:
            print(f"[FAIL] {case['id']} {case['label']}")
            for f in fails:
                print(f"         - {f}")
        else:
            passed += 1
            print(f"[PASS] {case['id']} {case['label']}")

    print(f"\n{passed}/{total} new cases passed.")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
