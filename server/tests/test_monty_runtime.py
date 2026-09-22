from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import CastOptions, CastRequest, CasterSnapshot, MaterialSnapshot, Vec2, WorldObject, WorldSnapshot
from app.monty_runtime import MAX_ACTIONS, MontyGenieRuntime


CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "monty_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def eval_request(wish: str) -> CastRequest:
    organic = MaterialSnapshot(name="organic", mass=1.0, flammability=0.35)
    return CastRequest(
        request_id="monty-eval",
        spell_text=wish,
        seed=42,
        caster=CasterSnapshot(id="player", position=Vec2(x=0, y=0), facing=Vec2(x=1, y=0)),
        world=WorldSnapshot(
            objects=[
                WorldObject(id="player", kind="creature", tags=["living", "player", "requester"], position=Vec2(), health=40, material=organic),
                WorldObject(id="dwarf_01", kind="creature", tags=["living", "enemy"], position=Vec2(x=2, y=0), health=58, material=organic),
                WorldObject(id="npc_01", kind="creature", tags=["living", "friendly", "villager"], position=Vec2(x=-2, y=1), health=70, material=organic),
                WorldObject(id="water_pool_01", kind="terrain", tags=["water"], position=Vec2(x=3, y=2), material=MaterialSnapshot(name="water", wetness=1)),
                WorldObject(id="water_barrel_01", kind="container", tags=["water", "container"], position=Vec2(x=-3, y=2), material=MaterialSnapshot(name="water", wetness=1)),
                WorldObject(id="rock_01", kind="prop", tags=["rock", "stone"], position=Vec2(x=1, y=-2), material=MaterialSnapshot(name="stone", hardness=0.9)),
                WorldObject(id="wall_01", kind="structure", tags=["wall", "stone"], position=Vec2(x=4, y=0), material=MaterialSnapshot(name="stone", hardness=0.95)),
                WorldObject(id="wall_02", kind="structure", tags=["wall", "stone"], position=Vec2(x=0, y=4), material=MaterialSnapshot(name="stone", hardness=0.95)),
            ]
        ),
        options=CastOptions(debug=True),
    )


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_ten_monty_wish_eval_cases_compile_to_expected_world_actions(case) -> None:
    result = MontyGenieRuntime().execute(case["program"], eval_request(case["wish"]))
    assert result.error is None
    assert len(result.actions) == case["expected"]["count"]
    world_actions = [action.world_action for action in result.actions]
    assert all(action is not None for action in world_actions)
    assert [action.type for action in world_actions] == case["expected"]["types"]
    assert [action.target_id for action in world_actions] == case["expected"]["targets"]
    if states := case["expected"].get("states"):
        assert [action.state for action in world_actions if action.state] == states
    if materials := case["expected"].get("materials"):
        assert [action.material for action in world_actions if action.material] == materials
    if prototypes := case["expected"].get("prototypes"):
        assert [action.effect["prototype"] for action in world_actions if action.effect and "prototype" in action.effect] == prototypes


def test_monty_rejects_imports_before_execution() -> None:
    result = MontyGenieRuntime().execute("import os\nos.listdir('.')", eval_request("сломай песочницу"))
    assert result.actions == []
    assert result.error and "Import" in result.error


def test_monty_rejects_flattened_inline_comment_program() -> None:
    runtime = MontyGenieRuntime()
    try:
        runtime.validate_source("inspect('player') # rest damage('player', 10)")
    except ValueError as error:
        assert "single-line" in str(error)
    else:
        raise AssertionError("flattened program was accepted")


def test_monty_rejects_inspection_without_world_action() -> None:
    runtime = MontyGenieRuntime()
    try:
        runtime.validate_source("inspect('player')")
    except ValueError as error:
        assert "does not fulfill" in str(error)
    else:
        raise AssertionError("inspect-only program was accepted")


def test_monty_rejects_unbounded_while_loop() -> None:
    result = MontyGenieRuntime().execute("while True:\n    pass", eval_request("думай вечно"))
    assert result.actions == []
    assert result.error and "While" in result.error


def test_monty_limits_number_of_world_actions() -> None:
    code = "\n".join("spawn('sword')" for _ in range(MAX_ACTIONS + 1))
    result = MontyGenieRuntime().execute(code, eval_request("создавай мечи бесконечно"))
    assert len(result.actions) == MAX_ACTIONS
    assert result.error and "action limit" in result.error


def test_monty_rejects_unknown_state_instead_of_silently_ignoring_it() -> None:
    result = MontyGenieRuntime().execute(
        "apply_state('dwarf_01', 'totally_made_up')",
        eval_request("сделай неизвестное"),
    )
    assert result.actions == []
    assert result.error and "unsupported state" in result.error


def test_monty_transforms_all_rocks_into_visible_crates() -> None:
    result = MontyGenieRuntime().execute(
        "for rock in all_with_tag('rock'):\n    transform(rock, 'crate')",
        eval_request("преврати все камни в коробки"),
    )
    world_actions = [action.world_action for action in result.actions]
    assert result.error is None
    assert [action.type for action in world_actions] == ["TRANSFORM_OBJECT"]
    assert world_actions[0].target_id == "rock_01"
    assert world_actions[0].effect == {"prototype": "crate"}


def test_monty_installs_real_doors_in_all_visible_walls_with_one_action() -> None:
    result = MontyGenieRuntime().execute(
        "install_doors()",
        eval_request("сделай двери в каждой стене"),
    )
    assert result.error is None
    assert len(result.actions) == 1
    action = result.actions[0].world_action
    assert action.type == "INSTALL_DOORS"
    assert action.target_id == "wall_01"
    assert action.effect == {"wall_ids": ["wall_01", "wall_02"]}


def test_monty_batch_spawn_creates_real_actor_prototypes_in_one_action() -> None:
    result = MontyGenieRuntime().execute(
        "spawn_many('enemy', 20)\nspawn_many('npc', 10)",
        eval_request("заспавнь 20 врагов и 10 нпс"),
    )
    assert result.error is None
    assert [item.world_action.type for item in result.actions] == [
        "CREATE_OBJECT_BATCH",
        "CREATE_OBJECT_BATCH",
    ]
    assert result.actions[0].world_action.effect == {
        "kind": "object",
        "prototype": "enemy",
        "count": 20,
    }
    assert result.actions[1].world_action.effect["prototype"] == "npc"
    assert result.actions[1].world_action.effect["count"] == 10


def test_monty_has_direct_capabilities_for_destroy_outfit_and_shutdown() -> None:
    result = MontyGenieRuntime().execute(
        "destroy_all('enemy')\nequip_outfit('player', 'dress')\nshutdown_game()",
        eval_request("убей врагов, одень меня и выключи игру"),
    )
    assert result.error is None
    assert [item.world_action.type for item in result.actions] == [
        "DESTROY_OBJECTS",
        "EQUIP_OUTFIT",
        "SHUTDOWN_GAME",
    ]


def test_monty_has_direct_capabilities_for_time_and_lighting() -> None:
    result = MontyGenieRuntime().execute(
        "set_game_paused(True)\nset_game_speed(0.5)\nset_light_level(0.3)",
        eval_request("поставь игру на паузу, замедли и сделай темнее"),
    )
    assert result.error is None
    assert [item.world_action.type for item in result.actions] == [
        "SET_GAME_PAUSED",
        "SET_GAME_SPEED",
        "SET_LIGHT_LEVEL",
    ]
    assert result.actions[0].world_action.effect == {"paused": True}
    assert result.actions[1].world_action.effect == {"multiplier": 0.5}
    assert result.actions[2].world_action.effect == {"level": 0.3}


def test_monty_transforms_rocks_into_living_npcs() -> None:
    result = MontyGenieRuntime().execute(
        "for rock in all_with_tag('rock'):\n    transform(rock, 'npc')",
        eval_request("преврати все камни в нпс"),
    )
    assert result.error is None
    assert len(result.actions) == 1
    action = result.actions[0].world_action
    assert action.type == "TRANSFORM_OBJECT"
    assert action.target_id == "rock_01"
    assert action.effect == {"prototype": "npc"}


def test_monty_transforms_rocks_into_enemies() -> None:
    result = MontyGenieRuntime().execute(
        "for rock in all_with_tag('rock'):\n    transform(rock, 'enemy')",
        eval_request("преврати все камни во врагов"),
    )
    assert result.error is None
    assert len(result.actions) == 1
    action = result.actions[0].world_action
    assert action.type == "TRANSFORM_OBJECT"
    assert action.target_id == "rock_01"
    assert action.effect == {"prototype": "enemy"}


def test_monty_program_sees_a_newly_created_npc_as_living() -> None:
    result = MontyGenieRuntime().execute(
        "transform('rock_01', 'npc')\naffect_mind('rock_01', 'be cheerful')",
        eval_request("оживи и обрадуй камень"),
    )
    assert result.error is None
    assert len(result.actions) == 2


def test_monty_cannot_affect_the_mind_of_an_inanimate_rock() -> None:
    result = MontyGenieRuntime().execute(
        "affect_mind('rock_01', 'wake up')",
        eval_request("оживи камень мыслями"),
    )
    assert result.actions == []
    assert result.error and "has no mind" in result.error


@pytest.mark.parametrize("code", ["# do nothing", "target = nearest('enemy')"])
def test_monty_rejects_programs_without_game_actions(code: str) -> None:
    result = MontyGenieRuntime().execute(code, eval_request("сделай что-нибудь"))
    assert result.actions == []
    assert result.error and "at least one game capability" in result.error
