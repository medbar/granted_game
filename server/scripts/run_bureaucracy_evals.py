"""Historical 12-effect smoke suite; use run_legal_evals.py for current law evaluation."""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from app.reality import Campaign, Lawyer, Petition


def lookup(state, dotted):
    for part in dotted.split("."):
        state = state[part]
    return state


async def run(args):
    cases = json.loads((ROOT / "evals/bureaucracy_cases.json").read_text(encoding="utf-8"))["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            raise SystemExit("Unknown case")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    directory = ROOT / "runtime/evals" / f"bureaucracy-{stamp}"
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    lawyer = Lawyer()
    startup = time.monotonic()
    if not args.frozen:
        lawyer.prepare()
    startup_ms = round((time.monotonic() - startup) * 1000, 3)
    for case in cases:
        async def fixture(wish, snapshot, error):
            return Petition(**case["decision"])
        game = Campaign(directory / case["id"], planner=fixture if args.frozen else lawyer)
        sid = game.create()["id"]
        for action in ("eat", "sleep", "commute", "work", "work", "home", "sign", "leave"):
            game.command(sid, action)
        start = time.monotonic()
        result = await game.wish(sid, case["wish"], case["id"])
        state = game.get(sid)
        issues = []
        if result["status"] != "completed":
            issues.append(result.get("error", result["status"]))
        for key, expected in case["expected"].items():
            try:
                actual = lookup(state, key)
            except KeyError:
                actual = None
            if actual != expected:
                issues.append(f"{key}: expected={expected!r}, actual={actual!r}")
        rows.append({"id": case["id"], "wish": case["wish"], "passed": not issues,
                     "issues": issues, "result": result, "seconds": round(time.monotonic() - start, 3)})
        print(f"{case['id']}: {'PASS' if not issues else 'FAIL'} ({rows[-1]['seconds']}s)", flush=True)
    report = {"suite": "bureaucracy-v1", "startup_ms": startup_ms, "mode": "frozen" if args.frozen else "live_model",
              "total": len(rows), "passed": sum(r["passed"] for r in rows), "results": rows}
    path = directory / "summary.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"REPORT: {path}", flush=True)
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen", action="store_true")
    parser.add_argument("--case")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
