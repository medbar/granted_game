from app.models import MaterialSnapshot, ObjectState, Vec2, WorldObject
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


def test_water_extinguishes_burning_material() -> None:
    target = obj("wood", flammability=0.9)
    target.states = [ObjectState(name="burning", remaining_duration=4.0)]
    actions, rules = WorldResolver().resolve(intent(matter={"water": 1.0}), [target])
    assert any(action.type == "REMOVE_STATE" and action.state == "burning" for action in actions)
    assert any("EXTINGUISHES" in rule for rule in rules)


def test_extreme_cold_freezes_living_target() -> None:
    target = obj("organic", flammability=0.35)
    target.tags.extend(["living", "enemy"])
    actions, _ = WorldResolver().resolve(
        intent(matter={"cold": 1.0}, actions={"freeze": 1.0}, power=1.2), [target]
    )
    states = {action.state for action in actions if action.type == "ADD_STATE"}
    assert {"slowed", "frozen"} <= states


def test_poison_adds_damage_over_time_state_to_living_target() -> None:
    target = obj("organic")
    target.tags.append("living")
    actions, rules = WorldResolver().resolve(intent(matter={"poison": 1.0}), [target])
    assert any(action.state == "poisoned" for action in actions)
    assert any("POISON_LIVING" in rule for rule in rules)


def test_explicit_destroy_intent_destroys_selected_target() -> None:
    target = obj("organic")
    target.tags.extend(["living", "enemy"])
    actions, rules = WorldResolver().resolve(
        intent(actions={"destroy": 0.98}),
        [target],
    )
    assert any(action.type == "DESTROY_OBJECT" for action in actions)
    assert any("RULE_DESTROY" in rule for rule in rules)


def test_lift_creates_levitating_state() -> None:
    actions, rules = WorldResolver().resolve(intent(movement={"lift": 1.0}), [obj("stone")])
    assert any(action.state == "levitating" for action in actions)
    assert any("RULE_LIFT" in rule for rule in rules)


def test_sharp_force_prefers_soft_matter() -> None:
    resolver = WorldResolver()
    soft, _ = resolver.resolve(
        intent(matter={"force": 1.0}, properties={"sharp": 1.0}),
        [obj("organic", hardness=0.15)],
    )
    hard, _ = resolver.resolve(
        intent(matter={"force": 1.0}, properties={"sharp": 1.0}),
        [obj("metal", hardness=0.9)],
    )
    soft_damage = sum(action.amount or 0.0 for action in soft if action.type == "DAMAGE")
    hard_damage = sum(action.amount or 0.0 for action in hard if action.type == "DAMAGE")
    assert soft_damage > hard_damage


def test_crush_uses_hardness_and_brittleness() -> None:
    resolver = WorldResolver()
    brittle, _ = resolver.resolve(
        intent(actions={"crush": 1.0}), [obj("stone", hardness=0.55, brittleness=0.95)]
    )
    tough, _ = resolver.resolve(
        intent(actions={"crush": 1.0}), [obj("metal", hardness=0.95, brittleness=0.1)]
    )
    brittle_damage = next(action.amount for action in brittle if action.type == "DAMAGE")
    tough_damage = next(action.amount for action in tough if action.type == "DAMAGE")
    assert brittle_damage > tough_damage


def test_electricity_propagates_from_water_to_immersed_target() -> None:
    water = obj("water", temperature=0.5, wetness=1.0, conductivity=0.65)
    water.radius = 2.0
    living = obj("organic", conductivity=0.2, wetness=0.0)
    living.id = "dwarf_in_pool"
    living.tags.extend(["living", "enemy"])
    living.position = Vec2(x=2.5, y=0.0)
    actions, rules = WorldResolver().resolve(
        intent(matter={"electricity": 1.0}), [water], [water, living]
    )
    assert any(action.target_id == "dwarf_in_pool" and action.type == "DAMAGE" for action in actions)
    assert any("ELECTRICITY_SPREADS" in rule for rule in rules)
