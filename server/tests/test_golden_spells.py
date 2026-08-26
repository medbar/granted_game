from app.models import MaterialSnapshot, Vec2, WorldObject, WorldSnapshot
from app.service import SpellService
from conftest import cast_request, circle_gesture, line_gesture, stroke


def ids(response) -> set[str]:
    return {anchor.id for anchor in response.interpretation.anchors}


def test_fire_with_jab_is_directional(world) -> None:
    response = SpellService().cast(cast_request("огонь", line_gesture(), world))
    assert "FIRE" in ids(response)
    assert response.interpretation.gesture_features["straightness"] > 0.8
    assert response.spell_plan.visuals[0].primitive in {"TRAIL", "BEAM", "PROJECTILE"}


def test_fire_wall_with_horizontal_line(world) -> None:
    response = SpellService().cast(cast_request("стена огня передо мной", line_gesture(), world))
    assert {"FIRE", "WALL"} <= ids(response)
    assert response.spell_plan.visuals[0].primitive == "LINE"


def test_freeze_water_circle(world) -> None:
    response = SpellService().cast(cast_request("заморозь воду", circle_gesture(), world))
    assert {"FREEZE", "WATER"} <= ids(response)
    assert response.debug and "water_pool_01" in response.debug.selected_targets
    assert any(action.material == "ice" for action in response.spell_plan.world_actions)


def test_push_all_enemies_from_self(world) -> None:
    gesture = stroke([(0.1, 0), (2.0, 0), (4.0, 0)], 350)
    response = SpellService().cast(
        cast_request("оттолкни всех врагов от меня", gesture, world)
    )
    assert {"PUSH", "ALL", "ENEMY", "SELF"} <= ids(response)
    assert response.debug and response.debug.selected_targets == ["dwarf_01"]
    assert any(action.type == "APPLY_FORCE" for action in response.spell_plan.world_actions)


def test_ignite_tree_prefers_tree(world) -> None:
    response = SpellService().cast(cast_request("подожги дерево", line_gesture(), world))
    assert response.debug and response.debug.selected_targets[0] == "tree_01"
    assert any(action.state == "burning" for action in response.spell_plan.world_actions)


def test_electricity_through_water_uses_conduction(world) -> None:
    response = SpellService().cast(cast_request("электричество по воде", line_gesture(), world))
    assert {"ELECTRICITY", "WATER"} <= ids(response)
    assert response.debug and any("WET_CONDUCTS" in rule for rule in response.debug.world_rules)


def test_small_sun_is_composed_not_named(world) -> None:
    response = SpellService().cast(cast_request("маленькое солнце", circle_gesture((1.0, 0.0), 0.4), world))
    assert {"LIGHT", "SMALL", "SPHERE"} <= ids(response)
    assert not hasattr(response.spell_plan, "spell")


def test_fire_underwater_uses_world_rules(world) -> None:
    response = SpellService().cast(cast_request("создай огонь под водой", circle_gesture(), world))
    assert response.debug and "water_pool_01" in response.debug.selected_targets
    assert any(action.material == "steam" for action in response.spell_plan.world_actions)


def test_gibberish_succeeds_with_unstable_effect(world) -> None:
    response = SpellService().cast(
        cast_request("абракадабра курица великолепие", line_gesture(), world)
    )
    assert response.interpretation.coherence < 0.6
    assert response.spell_plan.visuals


def test_same_fire_text_changes_shape_with_gesture(world) -> None:
    line = SpellService().cast(cast_request("огонь", line_gesture(), world, debug=False))
    circle = SpellService().cast(cast_request("огонь", circle_gesture(), world, debug=False))
    assert line.spell_plan.visuals[0].primitive != circle.spell_plan.visuals[0].primitive


def test_same_seed_and_inputs_are_reproducible(world) -> None:
    service = SpellService()
    request = cast_request("маленькое солнце", line_gesture(), world, debug=False)
    first = service.cast(request).model_dump(mode="json")
    second = service.cast(request).model_dump(mode="json")
    assert first == second


def test_self_is_origin_when_pushing_enemies(world) -> None:
    player = WorldObject(
        id="player",
        kind="creature",
        tags=["living", "player", "mage", "organic"],
        position=Vec2(x=0, y=0),
        health=100,
        material=MaterialSnapshot(name="organic"),
    )
    second_enemy = WorldObject(
        id="dwarf_02",
        kind="creature",
        tags=["living", "enemy", "dwarf", "organic"],
        position=Vec2(x=5, y=0.5),
        health=60,
        material=MaterialSnapshot(name="organic"),
    )
    expanded = WorldSnapshot(objects=[player, *world.objects, second_enemy])
    response = SpellService().cast(
        cast_request("оттолкни всех врагов от меня", line_gesture(), expanded)
    )
    assert response.debug
    assert "player" not in response.debug.selected_targets
    assert {"dwarf_01", "dwarf_02"} <= set(response.debug.selected_targets)


def test_precise_wording_changes_target_set_without_length_power_bonus(world) -> None:
    second_enemy = WorldObject(
        id="dwarf_02",
        kind="creature",
        tags=["living", "enemy", "dwarf", "organic"],
        position=Vec2(x=5, y=0.5),
        health=60,
        material=MaterialSnapshot(name="organic"),
    )
    expanded = WorldSnapshot(objects=[*world.objects, second_enemy])
    service = SpellService()
    simple = service.cast(cast_request("толкни", line_gesture(), expanded))
    precise = service.cast(
        cast_request("толкни всех врагов передо мной", line_gesture(), expanded)
    )
    assert simple.debug and precise.debug
    assert len(simple.debug.selected_targets) == 1
    assert {"dwarf_01", "dwarf_02"} <= set(precise.debug.selected_targets)
    assert precise.spell_plan.power <= simple.spell_plan.power + 0.35


def test_self_remains_target_for_healing(world) -> None:
    player = WorldObject(
        id="player",
        kind="creature",
        tags=["living", "player", "mage", "organic"],
        position=Vec2(x=0, y=0),
        health=50,
        material=MaterialSnapshot(name="organic"),
    )
    expanded = WorldSnapshot(objects=[player, *world.objects])
    response = SpellService().cast(cast_request("исцели меня", line_gesture(), expanded))
    assert response.debug and response.debug.selected_targets == ["player"]
    assert any(action.type == "HEAL" and action.target_id == "player" for action in response.spell_plan.world_actions)


def test_fire_in_air_and_fire_in_water_resolve_differently(world) -> None:
    air_world = WorldSnapshot(objects=[item for item in world.objects if item.id != "water_pool_01"])
    air = SpellService().cast(cast_request("создай огонь", line_gesture(), air_world))
    water = SpellService().cast(cast_request("создай огонь в воде", circle_gesture(), world))
    assert not any(action.material == "steam" for action in air.spell_plan.world_actions)
    assert any(action.material == "steam" for action in water.spell_plan.world_actions)
