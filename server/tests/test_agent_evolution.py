from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent import GenieAgentService
from app.models import CastOptions, CastRequest, CasterSnapshot
from app.monty_runtime import MontyGenieRuntime
from app.sim_world import create_level
from scripts.run_agent_evolution import verify_environment
from scripts.run_agent_levels import level_passed


CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "agent_evolution_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
STRATEGIES_PATH = Path(__file__).resolve().parents[1] / "evals" / "strategies.json"
STRATEGIES = json.loads(STRATEGIES_PATH.read_text(encoding="utf-8"))["strategies"]
AGENT_LEVEL_CASES = [
    pytest.param(strategy[level], level, id=f"{strategy['id']}-{level}")
    for strategy in STRATEGIES
    for level in ("closed_door", "three_enemies", "whispering_gate")
]


def sandbox_request(wish: str, session) -> CastRequest:
    return CastRequest(
        request_id="agent-evolution-regression",
        wish_text=wish,
        caster=CasterSnapshot(id="player", position=session.entity("player").position),
        world=session.public_world(),
        options=CastOptions(debug=True),
    )


def test_evolution_suite_contains_exactly_forty_distinct_wishes() -> None:
    assert len(CASES) == 40
    assert len({case["id"] for case in CASES}) == 40
    assert len({case["wish"] for case in CASES}) == 40


def test_agent_level_eval_rejects_completed_world_with_failed_visible_conclusion() -> None:
    assert level_passed(
        {"status": "completed"},
        [{"conclusion": {"status": "impossible"}}],
    ) is False
    assert level_passed(
        {"status": "completed"},
        [{"conclusion": {"status": "completed"}}],
    ) is True


@pytest.mark.parametrize(("wish", "level"), AGENT_LEVEL_CASES)
def test_every_frozen_agent_level_wish_has_a_deterministic_world_program(
    wish: str, level: str
) -> None:
    session = create_level(level, f"deterministic-{level}")
    program = GenieAgentService._compile_fast_program(wish)
    assert program is not None, f"missing deterministic route: {wish}"

    result = MontyGenieRuntime().execute(
        program.code,
        sandbox_request(wish, session),
        session=session,
    )

    assert result.error is None, result.error
    assert result.actions
    assert session.status == "completed", program.code


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_fast_agent_program_changes_authoritative_environment_as_requested(case) -> None:
    session = create_level("sandbox", f"test-{case['id']}")
    program = GenieAgentService._compile_fast_program(case["wish"])
    assert program is not None, f"missing fast route for {case['id']}"
    result = MontyGenieRuntime().execute(
        program.code,
        sandbox_request(case["wish"], session),
        session=session,
    )
    assert result.error is None
    assert result.actions
    assert verify_environment(session, case["expected"]) == []


def test_inventory_item_is_owned_and_not_spawned_as_visible_world_prop() -> None:
    session = create_level("sandbox", "inventory-regression")
    result = MontyGenieRuntime().execute(
        "give_item('sword', owner='player')",
        sandbox_request("Создай меч в рюкзаке", session),
        session=session,
    )
    assert result.error is None
    item = session.entity(session.inventory[0])
    assert item.properties["inventory_owner"] == "player"
    assert item.properties["hidden"] is True
    assert item.properties["prototype"] == "sword"


def test_aggro_capability_changes_actor_target_in_environment() -> None:
    session = create_level("sandbox", "aggro-regression")
    result = MontyGenieRuntime().execute(
        "set_aggro('enemy_01', 'player')",
        sandbox_request("Заставь врага агриться на игрока", session),
        session=session,
    )
    assert result.error is None
    assert session.entity("enemy_01").properties["aggro_target"] == "player"
    assert "aggressive" in {
        state if isinstance(state, str) else state.name
        for state in session.entity("enemy_01").states
    }
