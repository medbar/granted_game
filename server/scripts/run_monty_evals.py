from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_ROOT))

from app.agent import GenieAgentService
from app.curses import CurseManager
from app.models import (
    CastOptions,
    CastRequest,
    CasterSnapshot,
    MaterialSnapshot,
    Vec2,
    WorldObject,
    WorldSnapshot,
)


def eval_request(case: dict[str, Any], run_id: str) -> CastRequest:
    objects = [
        WorldObject(
            id="player",
            kind="creature",
            tags=["living", "player", "requester"],
            position=Vec2(x=0, y=0),
            health=40,
            material=MaterialSnapshot(name="organic"),
        ),
        WorldObject(
            id="dwarf_01",
            kind="creature",
            tags=["living", "enemy", "dwarf"],
            position=Vec2(x=3, y=0),
            health=58,
            material=MaterialSnapshot(name="organic"),
        ),
        WorldObject(
            id="npc_01",
            kind="creature",
            tags=["living", "friendly", "villager"],
            position=Vec2(x=2, y=2),
            health=70,
            material=MaterialSnapshot(name="organic"),
        ),
        WorldObject(
            id="water_pool_01",
            kind="terrain",
            tags=["water", "wet", "surface"],
            position=Vec2(x=4, y=2),
            material=MaterialSnapshot(name="water"),
        ),
        WorldObject(
            id="water_barrel_01",
            kind="prop",
            tags=["water", "wet", "container"],
            position=Vec2(x=5, y=-2),
            material=MaterialSnapshot(name="water"),
        ),
        WorldObject(
            id="rock_01",
            kind="prop",
            tags=["rock", "stone", "solid"],
            position=Vec2(x=1, y=-2),
            health=80,
            material=MaterialSnapshot(name="stone"),
        ),
    ]
    return CastRequest(
        request_id=f"monty-eval-{run_id}-{case['id']}",
        wish_text=case["wish"],
        caster=CasterSnapshot(id="player", position=Vec2(x=0, y=0)),
        world=WorldSnapshot(objects=objects),
        options=CastOptions(debug=True),
    )


def score_actions(
    case_id: str,
    actions: list[dict[str, Any]],
    expected: dict[str, Any],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    world_actions = [item.get("world_action") for item in actions if item.get("world_action")]
    def matches(**fields: Any) -> bool:
        return any(all(action.get(key) == value for key, value in fields.items()) for action in world_actions)

    if case_id == "kill_enemy":
        lethal = any(
            action.get("target_id") == "dwarf_01"
            and (
                action.get("type") == "DESTROY_OBJECT"
                or (action.get("type") == "DAMAGE" and float(action.get("amount", 0)) >= 58)
            )
            for action in world_actions
        )
        if not lethal:
            failures.append("enemy was not lethally damaged or destroyed")
        return not failures, failures

    required = {
        "burn_enemy": [{"type": "ADD_STATE", "target_id": "dwarf_01", "state": "burning"}],
        "bathe_enemy_in_blood": [
            {"type": "CREATE_OBJECT", "target_id": "dwarf_01"},
            {"type": "ADD_STATE", "target_id": "dwarf_01", "state": "blood_soaked"},
        ],
        "freeze_all_water": [
            {"type": "CHANGE_MATERIAL_STATE", "target_id": "water_pool_01", "material": "ice"},
            {"type": "CHANGE_MATERIAL_STATE", "target_id": "water_barrel_01", "material": "ice"},
        ],
        "push_enemy": [{"type": "APPLY_FORCE", "target_id": "dwarf_01"}],
        "heal_player": [{"type": "HEAL", "target_id": "player"}],
        "golden_rock": [{"type": "CHANGE_MATERIAL_STATE", "target_id": "rock_01", "material": "gold"}],
        "create_sword": [{"type": "CREATE_OBJECT", "target_id": "player"}],
        "pacify_enemy_mind": [{"type": "ADD_STATE", "target_id": "dwarf_01"}],
        "make_villager_speak": [{"type": "SPEAK", "target_id": "npc_01"}],
    }[case_id]
    for item in required:
        if not matches(**item):
            failures.append(f"missing world action {item}")

    if case_id == "bathe_enemy_in_blood" and not any(
        (action.get("effect") or {}).get("prototype") in {"blood", "blood_pool"}
        for action in world_actions
    ):
        failures.append("missing blood object")
    if case_id == "create_sword" and not any(
        (action.get("effect") or {}).get("prototype") == "sword" for action in world_actions
    ):
        failures.append("missing sword prototype")
    if case_id == "pacify_enemy_mind" and not any(
        action.get("state") in {"influenced", "pacified", "friendly"}
        for action in world_actions
        if action.get("target_id") == "dwarf_01"
    ):
        failures.append("enemy mind was not pacified or influenced")
    return not failures, failures


def score_fixture_exactly(actions: list[dict[str, Any]], expected: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    world_actions = [item.get("world_action") for item in actions if item.get("world_action")]
    if len(world_actions) != expected["count"]:
        failures.append(f"count {len(world_actions)} != {expected['count']}")
    for key, field in (
        ("types", "type"),
        ("targets", "target_id"),
        ("states", "state"),
        ("materials", "material"),
    ):
        if key not in expected:
            continue
        actual = [item.get(field) for item in world_actions if item.get(field) is not None]
        if actual != expected[key]:
            failures.append(f"{key} {actual!r} != {expected[key]!r}")
    if "prototypes" in expected:
        actual = [
            item.get("effect", {}).get("prototype")
            for item in world_actions
            if item.get("effect", {}).get("prototype") is not None
        ]
        if actual != expected["prototypes"]:
            failures.append(f"prototypes {actual!r} != {expected['prototypes']!r}")
    return not failures, failures


async def async_main(args: argparse.Namespace) -> int:
    suite = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = suite["cases"]
    output_dir = SERVER_ROOT / "runtime" / "evals"
    previous_results: dict[str, dict[str, Any]] = {}
    if args.resume and (output_dir / "monty-latest.json").exists():
        previous = json.loads((output_dir / "monty-latest.json").read_text(encoding="utf-8"))
        previous_results = {
            result["id"]: result for result in previous.get("results", []) if result.get("passed")
        }
        cases = [case for case in cases if case["id"] not in previous_results]
    if args.only:
        selected = set(args.only.split(","))
        cases = [case for case in cases if case["id"] in selected]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    service = GenieAgentService(
        curse_manager=CurseManager(output_dir / f"monty-{run_id}-genie-state.json")
    )
    results: list[dict[str, Any]] = list(previous_results.values())
    for case in cases:
        started = time.perf_counter()
        try:
            response = await service.run(
                eval_request(case, run_id),
                progress_curses=False,
            )
            payload = response.model_dump(mode="json")
            passed, failures = score_actions(
                case["id"], payload["agent"]["actions"], case["expected"]
            )
            result = {
                "id": case["id"],
                "wish": case["wish"],
                "passed": passed,
                "failures": failures,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "program": payload["agent"]["program_code"],
                "execution_error": payload["agent"]["execution_error"],
                "actions": payload["agent"]["actions"],
            }
        except Exception as error:
            result = {
                "id": case["id"],
                "wish": case["wish"],
                "passed": False,
                "failures": [f"{type(error).__name__}: {error}"],
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        results.append(result)
        print(
            f"[{case['id']}] {'PASS' if result['passed'] else 'FAIL'} "
            f"{result['latency_ms'] / 1000:.2f}s"
            + (f" — {'; '.join(result['failures'])}" if result["failures"] else ""),
            flush=True,
        )

    case_order = {case["id"]: index for index, case in enumerate(suite["cases"])}
    results.sort(key=lambda result: case_order[result["id"]])
    passed_count = sum(result["passed"] for result in results)
    report = {
        "schema_version": 1,
        "suite_version": suite["version"],
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "passed": passed_count,
        "total": len(results),
        "pass_rate": passed_count / len(results) if results else 0.0,
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"monty-{run_id}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if len(results) == len(suite["cases"]):
        (output_dir / "monty-latest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"SUMMARY: {passed_count}/{len(results)}; report={output_path}", flush=True)
    return 0 if passed_count == len(results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ten live-model Monty wish evals.")
    parser.add_argument("--cases", default=str(SERVER_ROOT / "evals" / "monty_cases.json"))
    parser.add_argument("--only", help="Comma-separated case ids")
    parser.add_argument(
        "--resume", action="store_true", help="Keep passed cases from monty-latest.json"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
