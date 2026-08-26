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

