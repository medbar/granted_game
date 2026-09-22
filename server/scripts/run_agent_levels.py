from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


SERVER_ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("closed_door", "three_enemies", "whispering_gate")


def level_passed(final_world: dict[str, Any], turns: list[dict[str, Any]]) -> bool:
    """Require both the authoritative oracle and the player-visible agent conclusion."""
    return bool(
        final_world.get("status") == "completed"
        and turns
        and turns[-1].get("conclusion", {}).get("status") == "completed"
    )


def build_strategy_result(strategy_id: str, levels: list[dict[str, Any]]) -> dict[str, Any]:
    signature = "||".join(result["signature"] for result in levels)
    return {
        "strategy_id": strategy_id,
        "passed": len(levels) == len(LEVELS) and all(result["passed"] for result in levels),
        "signature": signature,
        "signature_hash": hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16],
        "levels": levels,
    }


def write_checkpoint(
    path: Path, run_id: str, results: dict[str, dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "updated_at": datetime.now(UTC).isoformat(),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    attempts: int = 4,
    **kwargs: Any,
) -> httpx.Response:
    """Retry only transport errors and transient HTTP responses."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = await client.request(method, url, **kwargs)
            if response.status_code not in {408, 429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response
            response.raise_for_status()
        except (httpx.TransportError, httpx.HTTPStatusError) as exception:
            last_error = exception
            if attempt == attempts:
                raise
            await asyncio.sleep(min(2 ** (attempt - 1), 8))
    assert last_error is not None
    raise last_error


def action_signature(actions: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for action in actions:
        parameters = action.get("parameters", {})
        discriminator = (
            parameters.get("effect")
            or parameters.get("interaction")
            or parameters.get("prototype")
            or parameters.get("influence")
            or parameters.get("message")
            or ""
        )
        parts.append(
            f"{action.get('kind')}:{action.get('target_id')}:{str(discriminator).lower()[:80]}:{action.get('success')}"
        )
    return "|".join(parts)


def follow_up(level: str, session: dict[str, Any]) -> str:
    if level == "closed_door":
        return "Уровень ещё не пройден. Проверь результат прошлых действий и доведи открытие или обход обычной двери до конца."
    if level == "three_enemies":
        return "Уровень ещё не пройден. Осмотри текущее состояние и нейтрализуй всех оставшихся активных врагов выбранным способом."
    if "gate_code" in session.get("known_fact_keys", []):
        return "Ты уже узнал кодовое слово у хранителя. Немедленно произнеси сохранённый точный код волшебным вратам."
    return "Уровень ещё не пройден. Узнай точное кодовое слово у нейтрального хранителя и произнеси его волшебным вратам."


async def run_level(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    run_id: str,
    strategy: dict[str, str],
    level: str,
    max_turns: int,
) -> dict[str, Any]:
    async with semaphore:
        session_id = f"eval-{run_id}-{strategy['id']}-{level}"
        created = await request_with_retry(
            client,
            "POST",
            "/agent/sessions", json={"level_id": level, "session_id": session_id}
        )
        session = created.json()
        prompt = strategy[level]
        turns: list[dict[str, Any]] = []
        all_actions: list[dict[str, Any]] = []
        started = time.perf_counter()
        error: str | None = None
        for turn in range(1, max_turns + 1):
            try:
                response = await request_with_retry(
                    client,
                    "POST",
                    f"/agent/sessions/{session_id}/wish",
                    json={
                        "wish_text": prompt,
                        "request_id": (
                            f"eval-{run_id}-"
                            f"{hashlib.sha256(session_id.encode('utf-8')).hexdigest()[:12]}-"
                            f"{turn:02d}"
                        ),
                        "debug": True,
                        "progress_curses": False,
                    },
                )
                payload = response.json()
            except Exception as exception:
                error = f"{type(exception).__name__}: {exception}"
                break
            session = payload["session"]
            agent = payload["agent_response"]["agent"]
            actions = agent["actions"]
            all_actions.extend(actions)
            turns.append(
                {
                    "turn": turn,
                    "prompt": prompt,
                    "conclusion": agent["conclusion"],
                    "actions": actions,
                    "latency_ms": agent["latency_ms"],
                    "world_after": session,
                }
            )
            if session["status"] == "completed":
                break
            prompt = follow_up(level, session)

        observed = await request_with_retry(
            client, "GET", f"/agent/sessions/{session_id}"
        )
        final_world = observed.json()
        return {
            "level": level,
            "session_id": session_id,
            "passed": level_passed(final_world, turns),
            "status": final_world["status"],
            "turn_count": len(turns),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "signature": action_signature(all_actions),
            "turns": turns,
            "final_world": final_world,
            "error": error,
        }


async def run_strategy(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    run_id: str,
    strategy: dict[str, str],
    max_turns: int,
    checkpoint_results: dict[str, dict[str, Any]],
    checkpoint_path: Path,
    checkpoint_lock: asyncio.Lock,
) -> dict[str, Any]:
    previous = checkpoint_results.get(strategy["id"], {})
    previous_levels = {
        result["level"]: result
        for result in previous.get("levels", [])
        if result.get("passed")
    }
    levels: list[dict[str, Any]] = []
    for level in LEVELS:
        if level in previous_levels:
            result = previous_levels[level]
            print(f"[{strategy['id']}] {level}: RESUME PASS", flush=True)
        else:
            result = await run_level(client, semaphore, run_id, strategy, level, max_turns)
        levels.append(result)
        if level not in previous_levels:
            print(
                f"[{strategy['id']}] {level}: {'PASS' if result['passed'] else 'FAIL'} "
                f"({result['turn_count']} turn(s), {result['duration_ms'] / 1000:.1f}s)",
                flush=True,
            )
        partial = build_strategy_result(strategy["id"], levels)
        async with checkpoint_lock:
            checkpoint_results[strategy["id"]] = partial
            write_checkpoint(checkpoint_path, run_id, checkpoint_results)
    return build_strategy_result(strategy["id"], levels)


async def async_main(args: argparse.Namespace) -> int:
    strategies = json.loads(Path(args.strategies).read_text(encoding="utf-8"))["strategies"]
    if args.only:
        selected = set(args.only.split(","))
        strategies = [strategy for strategy in strategies if strategy["id"] in selected]
    output_dir = SERVER_ROOT / "runtime" / "evals"
    checkpoint_path = output_dir / "agent-levels-checkpoint.json"
    checkpoint_results: dict[str, dict[str, Any]] = {}
    if args.resume and checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        run_id = checkpoint["run_id"]
        checkpoint_results = checkpoint.get("results", {})
    else:
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        write_checkpoint(checkpoint_path, run_id, checkpoint_results)
    semaphore = asyncio.Semaphore(args.concurrency)
    checkpoint_lock = asyncio.Lock()
    timeout = httpx.Timeout(args.timeout)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout) as client:
        tasks = [
            run_strategy(
                client,
                semaphore,
                run_id,
                item,
                args.max_turns,
                checkpoint_results,
                checkpoint_path,
                checkpoint_lock,
            )
            for item in strategies
        ]
        results = await asyncio.gather(*tasks)
    passed = sum(result["passed"] for result in results)
    distinct = len({result["signature_hash"] for result in results if result["passed"]})
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url,
        "strategy_count": len(results),
        "passed_strategy_count": passed,
        "distinct_passed_signature_count": distinct,
        "all_passed": passed == len(results),
        "twenty_distinct_passed": passed >= 20 and distinct >= 20,
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"agent-levels-{run_id}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"SUMMARY: {passed}/{len(results)} strategies passed; "
        f"{distinct} distinct successful signatures; report={output_path}",
        flush=True,
    )
    return 0 if report["twenty_distinct_passed"] else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the three agent levels with many strategies.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--strategies", default=str(SERVER_ROOT / "evals" / "strategies.json"))
    parser.add_argument("--only", help="Comma-separated strategy ids")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse passed levels from runtime/evals/agent-levels-checkpoint.json",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(async_main(args)))


if __name__ == "__main__":
    main()
