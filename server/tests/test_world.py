from app.models import MaterialSnapshot, Vec2, WorldObject
from app.world import WorldResolver


def intent(**overrides):
    value = {
        "power": 1.0,
        "coherence": 0.9,
        "matter": {},
        "actions": {},
        "movement": {},
        "geometry": {},
        "targets": {},
        "properties": {},
        "timing": {},
        "logic": {},
        "duration": 1.0,
        "spatial": {
            "origin": {"x": 0.0, "y": 0.0},
            "direction": {"x": 1.0, "y": 0.0},
            "radius": 1.0,
            "range": 6.0,
        },
    }
    value.update(overrides)
    return value


def obj(name: str, **material):
    return WorldObject(
        id=name,
        kind="prop",
        tags=[name],
        position=Vec2(x=2, y=0),
        material=MaterialSnapshot(name=name, **material),
    )


def action_types(actions):
    return [action.type for action in actions]


def test_water_and_cold_become_ice() -> None:
    actions, rules = WorldResolver().resolve(
        intent(matter={"cold": 1.0}, actions={"freeze": 1.0}),
        [obj("water", temperature=0.5, wetness=1.0)],
    )
    assert any(action.material == "ice" for action in actions)
    assert "RULE_WATER_FREEZES: cold water becomes ice" in rules


def test_ice_and_heat_become_water() -> None:
    actions, _ = WorldResolver().resolve(
        intent(matter={"heat": 1.0}), [obj("ice", temperature=0.2, hardness=0.75)]
    )
    assert any(action.material == "water" for action in actions)


def test_water_and_strong_heat_become_steam() -> None:
    actions, _ = WorldResolver().resolve(
        intent(matter={"fire": 1.0}, power=1.2),
        [obj("water", temperature=0.5, wetness=1.0)],
    )
    assert any(action.material == "steam" for action in actions)
    assert "APPLY_FORCE" in action_types(actions)


def test_wood_ignites() -> None:
    actions, _ = WorldResolver().resolve(
        intent(matter={"fire": 0.9}, actions={"ignite": 1.0}),
        [obj("wood", flammability=0.9)],
    )
    assert any(action.state == "burning" for action in actions)


def test_wet_target_conducts_more_electricity() -> None:
    resolver = WorldResolver()
    dry, _ = resolver.resolve(
        intent(matter={"electricity": 1.0}), [obj("organic", conductivity=0.2, wetness=0.0)]
    )
    wet, _ = resolver.resolve(
        intent(matter={"electricity": 1.0}), [obj("organic", conductivity=0.2, wetness=1.0)]
    )
    dry_damage = next(action.amount for action in dry if action.type == "DAMAGE")
    wet_damage = next(action.amount for action in wet if action.type == "DAMAGE")
    assert wet_damage > dry_damage


def test_force_respects_mass() -> None:
    resolver = WorldResolver()
    light, _ = resolver.resolve(intent(matter={"force": 1.0}), [obj("wood", mass=0.5)])
    heavy, _ = resolver.resolve(intent(matter={"force": 1.0}), [obj("stone", mass=3.0)])
    light_force = next(action.strength for action in light if action.type == "APPLY_FORCE")
    heavy_force = next(action.strength for action in heavy if action.type == "APPLY_FORCE")
    assert light_force > heavy_force

