"""Frozen legal scenarios: an independent oracle over the real Campaign."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
import os
import re
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError
from app.config import ROOT
from app.reality import Campaign, Lawyer, RealityError

SUITE_PATH = ROOT / "evals/legal_cases.json"
META = {"revision", "message", "case_status", "receipts", "elapsed"}
MISSING = object()

def fs_path(path):
    resolved = str(Path(path).resolve())
    # Nested pytest/run/case/session paths exceed legacy Win32 MAX_PATH.
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        resolved = ("\\\\?\\UNC\\" + resolved[2:] if resolved.startswith("\\\\")
                    else "\\\\?\\" + resolved)
    return Path(resolved)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_suite(suite):
    if suite.get("schema_version") != 2 or not suite.get("cases"):
        raise ValueError("A non-empty schema_version=2 legal suite is required")
    seen = set()
    for case in suite["cases"]:
        name = case["id"]
        if name in seen:
            raise ValueError(f"duplicate case id: {name}")
        seen.add(name)
        if not re.fullmatch(r"[a-z0-9_]{1,64}", name):
            raise ValueError(f"unsafe case id: {name}")
        if not isinstance(case.get("live_model"), bool) or not case.get("steps"):
            raise ValueError(f"{name}: live_model and steps are required")
        steps = set()
        for step in case["steps"]:
            if not re.fullmatch(r"[a-z0-9_]{1,32}", step["id"]) or step["id"] in steps:
                raise ValueError(f"{name}: invalid or duplicate step")
            steps.add(step["id"])
            if step["operation"] not in {"petition", "reload", "replay"}:
                raise ValueError(f"{name}: unknown operation")
            if step["operation"] == "petition" and (not step.get("fixtures") or not step.get("wish")):
                raise ValueError(f"{name}: petition needs a wish and frozen decisions")
            if not isinstance(step.get("allowed_changes"), list) or not step.get("expected", {}).get("status"):
                raise ValueError(f"{name}: explicit outcome and allowed diff required")


def load_suite():
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    validate_suite(suite)
    return suite


def select_cases(suite, mode, case_ids=None):
    if mode not in {"frozen", "live"}:
        raise ValueError("mode must be frozen or live")
    all_ids = {case["id"] for case in suite["cases"]}
    if case_ids is not None and (not case_ids or set(case_ids) - all_ids):
        raise ValueError("empty or unknown case selection")
    selected, excluded = [], []
    for case in suite["cases"]:
        if case_ids is not None and case["id"] not in case_ids:
            excluded.append({"id": case["id"], "reason": "not_selected"})
        elif mode == "live" and not case["live_model"]:
            excluded.append({"id": case["id"], "reason": "frozen_only"})
        else:
            selected.append(case)
    if not selected:
        raise ValueError("selection contains no applicable cases")
    return selected, excluded


def lookup(state, dotted):
    try:
        for key in dotted.split("."):
            state = state[int(key)] if isinstance(state, list) else state[key]
        return state
    except (KeyError, IndexError, TypeError, ValueError):
        return MISSING


def same(expected, actual):
    if expected is MISSING or actual is MISSING:
        return expected is actual
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(expected, actual, abs_tol=1e-6, rel_tol=1e-9)
    return expected == actual


def display(value):
    return {"missing": True} if value is MISSING else value


def check(name, expected, actual):
    return {"name": name, "passed": same(expected, actual),
            "expected": display(expected), "actual": display(actual)}


def differences(before, after, prefix=""):
    rows = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            if not prefix and key in META:
                continue
            rows.extend(differences(before.get(key, MISSING), after.get(key, MISSING),
                                    f"{prefix}.{key}" if prefix else key))
    elif not same(before, after):
        rows.append({"path": prefix, "before": display(before), "after": display(after)})
    return rows


def assess(before, after, result, expected, allowed):
    checks = [check("decision_status", expected["status"], result.get("status")),
              check("visible_explanation", True, bool(result.get("message")))]
    if "basis" in expected:
        checks.append(check("legal_basis", expected["basis"], result.get("basis")))
        checks.append(check("legal_argument_present", True, bool(result.get("argument"))))
    for path, value in expected.get("state", {}).items():
        checks.append(check("state:" + path, value, lookup(after, path)))
    if "attempts" in expected:
        checks.append(check("attempt_count", expected["attempts"], result.get("attempts")))
    if "precedents" in expected:
        actual = after.get("precedents", [])
        checks.append(check("precedent_count", len(expected["precedents"]), len(actual)))
        for index, wanted in enumerate(expected["precedents"]):
            for key, value in wanted.items():
                checks.append(check(f"precedent:{index}:{key}", value,
                                    lookup(after, f"precedents.{index}.{key}")))
            for field in ("id", "title", "rule"):
                value = lookup(after, f"precedents.{index}.{field}")
                checks.append(check(f"precedent:{index}:{field}:readable", True,
                                    value is not MISSING and isinstance(value, str) and bool(value.strip())))
    diff = differences(before, after)
    unexpected = [row["path"] for row in diff if not any(
        row["path"] == path or row["path"].startswith(path + ".") for path in allowed)]
    checks.append(check("no_collateral_changes", [], unexpected))
    if expected.get("require_mutation"):
        effect_changes = [row for row in diff if row["path"].split(".")[0]
                          in {"objects", "player", "lighting", "pace"}]
        checks.append(check("requested_world_mutation", True, bool(effect_changes)))
    return checks


def probe_world(snapshot, definition, root):
    state = copy.deepcopy(snapshot)
    kind = definition["kind"]
    if kind == "cross":
        state["player"]["driving"] = definition.get("driving", False)
        return Campaign._cross(state, definition["door"], definition["actor"])
    if kind == "detection":
        actor = state["objects"][definition["actor"]]
        state["player"].update(x=actor["x"] + definition.get("distance", 20), y=actor["y"])
        return Campaign._detected(state, definition["actor"])
    if kind == "damage":
        Campaign._damage(state, definition["amount"])
        return state["player"]["health"]
    if kind == "motion":
        game = Campaign(root / "probe")
        sid = state["id"]
        game.sessions[sid] = state
        game.last_save[sid] = time.monotonic()
        start = state["player"]["x"]
        return game.tick(sid, 1, 0, definition.get("dt", .1))["player"]["x"] - start
    raise ValueError(f"unknown probe: {kind}")


async def evaluate_case(case, directory, *, mode="frozen", planner=None):
    validate_suite({"schema_version": 2, "cases": [case]})
    if mode not in {"frozen", "live"} or (mode == "live" and not case["live_model"]):
        raise ValueError("case is not applicable to requested mode")
    root = fs_path(directory) / case["id"]
    root.mkdir(parents=True, exist_ok=True)
    dump(root / "scenario.json", case)
    attempts, current_step = [], None
    lawyer = planner if planner is not None else (Lawyer() if mode == "live" else None)

    async def planned(wish, snapshot, error):
        entry = {"attempt": len(attempts) + 1, "previous_error": error}
        attempts.append(entry)
        try:
            if mode == "frozen":
                fixtures = current_step["fixtures"]
                proposal = copy.deepcopy(fixtures[min(len(attempts) - 1, len(fixtures) - 1)])
            else:
                proposal = await lawyer(wish, snapshot, error)
            entry["proposal"] = proposal.model_dump() if hasattr(proposal, "model_dump") else proposal
            return proposal
        except ValidationError as exc:
            # A real model answer rejected by the petition schema is not a network outage.
            entry["validation_rejection"] = str(exc)[:2000]
            raise
        except asyncio.CancelledError:
            entry["planner_error"] = "planner cancelled or timed out"
            raise
        except Exception as exc:
            entry["planner_error"] = f"{type(exc).__name__}: {exc}"[:2000]
            raise

    game = Campaign(root / "runtime", planner=planned)
    sid = game.create()["id"]
    if case.get("contracted", True):
        for action in ("eat", "sleep", "commute", "work", "work", "home", "sign", "leave"):
            game.command(sid, action)
    before_checks = [check("before_probe:" + str(i), p["expected"], probe_world(game.get(sid), p, root))
                     for i, p in enumerate(case.get("before_probes", []))]
    rows, replies, request_ids = [], {}, {}
    for index, step in enumerate(case["steps"]):
        current_step = step
        attempts = []
        before = game.get(sid)
        request_id = f"legal_{index}_{uuid.uuid4().hex}"
        start = time.monotonic()
        if step["operation"] == "reload":
            game = Campaign(root / "runtime", planner=planned)
            result = {"status": "reloaded", "message": "Сессия загружена с диска."}
        else:
            if step["operation"] == "replay":
                request_id = request_ids[step["replay_of"]]
            try:
                result = await game.wish(sid, step["wish"], request_id)
            except RealityError as exc:
                result = {"status": "rejected", "attempts": len(attempts), "message": str(exc)}
        elapsed_ms = (time.monotonic() - start) * 1000
        after = game.get(sid)
        checks = assess(before, after, result, step["expected"], step["allowed_changes"])
        checks.append(check("planner_available", True, not any("planner_error" in a for a in attempts)))
        if step["expected"].get("feedback_received"):
            checks.append(check("retry_receives_rejection", True,
                                len(attempts) > 1 and all(a["previous_error"] for a in attempts[1:])))
        if step["operation"] == "replay":
            checks.append(check("replay_receipt", replies[step["replay_of"]], result))
            checks.append(check("replay_model_calls", 0, len(attempts)))
        if step["operation"] == "reload":
            checks.append(check("reload_entire_snapshot", before, after))
        for i, definition in enumerate(step.get("probes", [])):
            checks.append(check(f"probe:{i}:{definition['kind']}", definition["expected"],
                                probe_world(after, definition, root)))
        stem = f"{index + 1:02d}-{step['id']}"
        before_path, after_path = root / f"{stem}-before.json", root / f"{stem}-after.json"
        dump(before_path, before)
        dump(after_path, after)
        rows.append({"id": step["id"], "operation": step["operation"], "request_id": request_id,
                     "wish": step.get("wish"), "result": result, "attempts": copy.deepcopy(attempts),
                     "checks": checks, "changes": differences(before, after),
                     "passed": all(c["passed"] for c in checks), "latency_ms": round(elapsed_ms, 3),
                     "before_path": str(before_path), "after_path": str(after_path)})
        replies[step["id"]], request_ids[step["id"]] = result, request_id
    outcome = {"id": case["id"], "category": case["category"], "laws": case["laws"],
               "mode": mode, "passed": all(c["passed"] for c in before_checks) and all(r["passed"] for r in rows),
               "decision_status": rows[-1]["result"]["status"], "before_checks": before_checks,
               "steps": rows, "artifact_path": str(root / "result.json")}
    dump(root / "result.json", outcome)
    return outcome


async def run_suite(output_root, *, mode="frozen", case_ids=None, planner=None):
    suite = load_suite()
    selected, excluded = select_cases(suite, mode, case_ids)
    directory = fs_path(output_root) / (
        "legal-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + mode)
    directory.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(suite, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    dump(directory / "suite.json", suite)
    lawyer = planner if planner is not None else (Lawyer() if mode == "live" else None)
    startup = time.monotonic()
    if isinstance(lawyer, Lawyer):
        lawyer.prepare()
    startup_ms = round((time.monotonic() - startup) * 1000, 3)
    results = []
    for case in selected:
        try:
            row = await evaluate_case(case, directory, mode=mode, planner=lawyer)
        except Exception as exc:
            # Do not retry away a persistence/runtime defect or lose other cases.
            case_root = directory / case["id"]
            dump(case_root / "scenario.json", case)
            row = {"id": case["id"], "category": case["category"], "laws": case["laws"],
                   "mode": mode, "passed": False, "decision_status": "error",
                   "before_checks": [check("scenario_execution", "completed", type(exc).__name__)],
                   "steps": [], "error": {"type": type(exc).__name__, "message": str(exc)[:2000]},
                   "artifact_path": str(case_root / "result.json")}
            dump(case_root / "result.json", row)
        results.append(row)
        print(f"{case['id']}: {'PASS' if row['passed'] else 'FAIL'} "
              f"(decision={row['decision_status']})", flush=True)
    def aggregate(key):
        stats = {}
        for row in results:
            values = row[key] if isinstance(row[key], list) else [row[key]]
            for value in values:
                item = stats.setdefault(value, {"total": 0, "passed": 0})
                item["total"] += 1
                item["passed"] += int(row["passed"])
        return stats
    report = {"suite": suite["suite_id"], "suite_sha256": hashlib.sha256(encoded).hexdigest(),
              "mode": mode, "directory": str(directory), "startup_ms": startup_ms,
              "total_available": len(suite["cases"]), "total": len(results),
              "passed": sum(row["passed"] for row in results),
              "selected_case_ids": [row["id"] for row in results], "excluded": excluded,
              "decision_outcomes": dict(Counter(row["decision_status"] for row in results)),
              "by_law": aggregate("laws"), "by_category": aggregate("category"), "results": results}
    dump(directory / "summary.json", report)
    return report
