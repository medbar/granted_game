"""Evaluate current legal reality, not the archived genie."""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from evals.legal_suite import load_suite, run_suite, select_cases


def main():
    parser = argparse.ArgumentParser(description="Legal reality world-state evaluations")
    parser.add_argument("--mode", choices=("frozen", "live"), default="frozen")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--output-root", type=Path, default=ROOT / "runtime/evals")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    try:
        selected, excluded = select_cases(load_suite(), args.mode, args.case_ids)
        if args.list:
            print(json.dumps({"mode": args.mode, "selected": [c["id"] for c in selected],
                              "excluded": excluded}, ensure_ascii=False, indent=2))
            return 0
        report = asyncio.run(run_suite(args.output_root, mode=args.mode, case_ids=args.case_ids))
    except ValueError as exc:
        parser.error(str(exc))
    for row in report["results"]:
        if not row["passed"]:
            checks = row["before_checks"] + [c for step in row["steps"] for c in step["checks"]]
            failed = [c["name"] for c in checks if not c["passed"]]
            print(f"FAIL {row['id']}: {', '.join(failed)}")
    print(f"LEGAL {report['mode']}: {report['passed']}/{report['total']} checks passed; "
          f"excluded={len(report['excluded'])}; decisions={report['decision_outcomes']}")
    print(f"REPORT: {Path(report['directory']) / 'summary.json'}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
