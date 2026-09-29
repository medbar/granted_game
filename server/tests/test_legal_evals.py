from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from evals.legal_suite import assess, evaluate_case, load_suite, run_suite, select_cases, validate_suite

SUITE = load_suite()
CASES = SUITE["cases"]


def case_named(name):
    return copy.deepcopy(next(case for case in CASES if case["id"] == name))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_frozen_law_scenarios(tmp_path, case):
    result = asyncio.run(evaluate_case(case, tmp_path, mode="frozen"))
    assert result["passed"], result
    assert all(Path(step["before_path"]).is_file() for step in result["steps"])
    assert all(Path(step["after_path"]).is_file() for step in result["steps"])


def test_suite_covers_accepted_laws_and_negative_cases():
    assert len(CASES) == 32
    assert sum(case["live_model"] for case in CASES) == 21
    assert {law for case in CASES for law in case["laws"]} == {
        "life_safety", "document_correction", "identity_review", "non_aggression",
        "classification_amendment", "property_registration", "environment_exception",
    }
    assert {"refusal", "precedent", "access_scope", "idempotency", "persistence", "retry"} <= {
        case["category"] for case in CASES
    }


@pytest.mark.parametrize("mutation", ["unchanged", "wrong_basis", "collateral"])
def test_oracle_rejects_false_success(mutation):
    before = {"objects": {"door": {"open": False}}}
    after = {"objects": {"door": {"open": True}}}
    result = {"status": "completed", "basis": "life_safety", "message": "Исполнено", "argument": "Эвакуация"}
    expected = {"status": "completed", "basis": "life_safety",
                "state": {"objects.door.open": True}, "require_mutation": True}
    assert all(c["passed"] for c in assess(before, after, result, expected, ["objects.door.open"]))
    if mutation == "unchanged":
        after = before
    elif mutation == "wrong_basis":
        result["basis"] = "invented"
    else:
        after["objects"]["gift"] = {"kind": "crate"}
    assert not all(c["passed"] for c in assess(before, after, result, expected, ["objects.door.open"]))


def test_missing_state_field_is_not_null():
    checks = assess({}, {}, {"status": "failed", "message": "Отказ"},
                    {"status": "failed", "state": {"missing": None}}, [])
    assert not all(c["passed"] for c in checks)


def test_live_uses_real_answer_without_fixture_fallback(tmp_path):
    calls = []
    async def wrong_lawyer(wish, world, error):
        calls.append(wish)
        return {"effect": "protect", "target": "player", "basis": "non_aggression",
                "argument": "Другой допустимый, но не запрошенный эффект."}
    result = asyncio.run(evaluate_case(case_named("emergency_exit"), tmp_path,
                                      mode="live", planner=wrong_lawyer))
    assert calls and not result["passed"]
    assert result["steps"][0]["result"]["effect"] == "protect"


def test_live_infrastructure_failure_is_not_a_correct_refusal(tmp_path):
    async def unavailable(wish, world, error):
        raise ConnectionError("model unavailable")
    result = asyncio.run(evaluate_case(case_named("unsupported_retroactive_contract"), tmp_path,
                                      mode="live", planner=unavailable))
    assert not result["passed"]
    assert any(c["name"] == "planner_available" and not c["passed"]
               for c in result["steps"][0]["checks"])


def test_live_semantic_refusal_is_evaluated_as_refusal(tmp_path):
    async def refuses(wish, world, error):
        return {"effect": "unsupported", "target": "player", "basis": "none",
                "argument": "Нет нормы для изменения прошлого."}
    result = asyncio.run(evaluate_case(case_named("unsupported_retroactive_contract"), tmp_path,
                                      mode="live", planner=refuses))
    assert result["passed"], result
    assert result["decision_status"] == "failed"
    assert len(result["steps"][0]["attempts"]) == 3


def test_selection_never_counts_excluded_live_cases_as_passed():
    selected, excluded = select_cases(SUITE, "live")
    assert len(selected) == 21
    assert len(excluded) == 11
    assert all(item["reason"] == "frozen_only" for item in excluded)
    for case_ids in (["missing"], ["invented_law"], []):
        with pytest.raises(ValueError):
            select_cases(SUITE, "live", case_ids)


def test_suite_schema_rejects_duplicate_ids():
    invalid = copy.deepcopy(SUITE)
    invalid["cases"].append(copy.deepcopy(invalid["cases"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        validate_suite(invalid)


def test_report_separates_eval_success_from_wish_fulfillment(tmp_path):
    report = asyncio.run(run_suite(tmp_path, mode="frozen",
                                   case_ids=["emergency_exit", "invented_law"]))
    assert report["passed"] == 2 and report["total"] == 2
    assert report["decision_outcomes"] == {"completed": 1, "failed": 1}
    assert report["mode"] == "frozen" and len(report["suite_sha256"]) == 64
    assert len(report["excluded"]) == 30
    saved = json.loads((Path(report["directory"]) / "summary.json").read_text(encoding="utf-8"))
    assert saved["passed"] == 2
    assert saved["by_law"]["life_safety"]["total"] == 2
    assert all(Path(row["artifact_path"]).is_file() for row in saved["results"])


def test_report_preserves_runtime_failure_and_continues_other_cases(tmp_path, monkeypatch):
    import evals.legal_suite as suite_module
    original = suite_module.evaluate_case

    async def intermittent_failure(case, directory, **kwargs):
        if case["id"] == "emergency_exit":
            raise PermissionError("temporary save is locked")
        return await original(case, directory, **kwargs)

    monkeypatch.setattr(suite_module, "evaluate_case", intermittent_failure)
    report = asyncio.run(run_suite(tmp_path, case_ids=["emergency_exit", "invented_law"]))
    assert report["total"] == 2 and report["passed"] == 1
    failed = report["results"][0]
    assert failed["decision_status"] == "error" and not failed["passed"]
    assert failed["error"]["type"] == "PermissionError"
    assert any(not item["passed"] for item in failed["before_checks"])
    assert Path(failed["artifact_path"]).is_file()
    assert report["results"][1]["passed"]
