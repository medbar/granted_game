from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SERVER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_ROOT))

from app.agent import GenieAgentService
from app.curses import CurseManager
from app.models import CastOptions, CastRequest, CasterSnapshot
from app.sim_world import GameSession, create_level
from app.telemetry import TelemetryStore


def state_names(session: GameSession, target_id: str) -> set[str]:
    target = session.entity(target_id)
    if target is None:
        return set()
    return {state if isinstance(state, str) else state.name for state in target.states}


def created_with_prototype(session: GameSession, prototype: str) -> list[Any]:
    return [
        item for item in session.world.objects
        if item.properties.get("created_by") == "genie"
        and item.properties.get("prototype") == prototype
        and not item.properties.get("hidden", False)
    ]


def verify_environment(session: GameSession, expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for spec in expected.get("objects", []):
        objects = created_with_prototype(session, spec["prototype"])
        if len(objects) < int(spec.get("count", 1)):
            failures.append(f"visible {spec['prototype']} count {len(objects)} < {spec.get('count', 1)}")
        if spec.get("near") and objects:
            target = session.entity(spec["near"])
            if target is None or all(
                (item.position.x - target.position.x) ** 2 + (item.position.y - target.position.y) ** 2 > 1.0
                for item in objects
            ):
                failures.append(f"{spec['prototype']} is not near {spec['near']}")
    for spec in expected.get("states", []):
        if spec["name"] not in state_names(session, spec["target"]):
            failures.append(f"{spec['target']} missing state {spec['name']}")
    for spec in expected.get("properties", []):
        target = session.entity(spec["target"])
        actual = target.properties.get(spec["name"]) if target else None
        if actual != spec["value"]:
            failures.append(f"{spec['target']}.{spec['name']}={actual!r}, expected {spec['value']!r}")
    for spec in expected.get("wetness", []):
        target = session.entity(spec["target"])
        actual = target.material.wetness if target else 0.0
        if actual < float(spec["minimum"]):
            failures.append(f"{spec['target']} wetness {actual} < {spec['minimum']}")
    for spec in expected.get("aggro", []):
        actor = session.entity(spec["actor"])
        actual = actor.properties.get("aggro_target") if actor else None
        if actual != spec["target"]:
            failures.append(f"{spec['actor']} aggro target {actual!r} != {spec['target']!r}")
    for spec in expected.get("inventory", []):
        found = any(
            item.id in session.inventory
            and item.properties.get("inventory_owner") == spec["owner"]
            and item.properties.get("prototype") == spec["prototype"]
            for item in session.world.objects
        )
        if not found:
            failures.append(f"{spec['prototype']} missing from {spec['owner']} inventory")
    for target_id in expected.get("destroyed", []):
        target = session.entity(target_id)
        if target is not None and not target.properties.get("destroyed") and not (
            target.health is not None and target.health <= 0
        ):
            failures.append(f"{target_id} was not destroyed")
    return failures


async def run_case(
    service: GenieAgentService, case: dict[str, Any], generation: int
) -> dict[str, Any]:
    session = create_level("sandbox", f"evolution-g{generation}-{case['id']}")
    request = CastRequest(
        request_id=f"evolution-g{generation}-{case['id']}",
        wish_text=case["wish"],
        seed=generation,
        caster=CasterSnapshot(id="player", position=session.entity("player").position),
        world=session.public_world(),
        options=CastOptions(debug=True),
    )
    started = time.perf_counter()
    try:
        response = await service.run(request, session=session, progress_curses=False)
        payload = response.model_dump(mode="json")
        failures = verify_environment(session, case["expected"])
        return {
            "id": case["id"],
            "wish": case["wish"],
            "passed": not failures,
            "failures": failures,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "program": payload["agent"]["program_code"],
            "program_attempts": payload["agent"].get("program_attempts", []),
            "actions": payload["agent"]["actions"],
            "world_after": session.world.model_dump(mode="json"),
            "inventory_after": session.inventory,
        }
    except Exception as error:
        return {
            "id": case["id"], "wish": case["wish"], "passed": False,
            "failures": [f"{type(error).__name__}: {error}"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }


async def async_main(args: argparse.Namespace) -> int:
    suite = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    output_dir = SERVER_ROOT / "runtime" / "evolution"
    output_dir.mkdir(parents=True, exist_ok=True)
    service = GenieAgentService(
        curse_manager=CurseManager(output_dir / f"generation-{args.generation}-state.json"),
        telemetry=TelemetryStore(output_dir / f"generation-{args.generation}-telemetry"),
    )
    results = []
    for case in suite["cases"]:
        result = await run_case(service, case, args.generation)
        results.append(result)
        print(
            f"[{case['id']}] {'PASS' if result['passed'] else 'FAIL'} "
            f"{result['latency_ms'] / 1000:.2f}s"
            + (f" -- {'; '.join(result['failures'])}" if result["failures"] else ""),
            flush=True,
        )
    passed = sum(result["passed"] for result in results)
    latencies = [float(result["latency_ms"]) for result in results]
    report = {
        "schema_version": 1,
        "suite_version": suite["version"],
        "generation": args.generation,
        "prompt_version": service.prompt_config["version"],
        "created_at": datetime.now(UTC).isoformat(),
        "passed": passed,
        "total": len(results),
        "pass_rate": passed / len(results),
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 3),
            "median": round(statistics.median(latencies), 3),
            "max": round(max(latencies), 3),
        },
        "results": results,
    }
    path = output_dir / f"generation-{args.generation}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"SUMMARY generation={args.generation}: {passed}/{len(results)} report={path}", flush=True)
    return 0 if passed == len(results) else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--cases", default=str(SERVER_ROOT / "evals" / "agent_evolution_cases.json"))
    raise SystemExit(asyncio.run(async_main(parser.parse_args())))


if __name__ == "__main__":
    main()
