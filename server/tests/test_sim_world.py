from __future__ import annotations

from app.models import CastOptions, CastRequest, CasterSnapshot, WorldAction
from app.monty_runtime import MontyGenieRuntime
from app.sim_world import SessionStore, create_level, session_view


def test_closed_door_can_be_opened_with_discovered_key() -> None:
    session = create_level("closed_door", "door-test")
    session.apply("interact", "chest_01", {"interaction": "открыть"}, None)
    session.apply("interact", "key_01", {"interaction": "взять"}, None)
    session.apply("interact", "door_01", {"interaction": "открыть ключом"}, None)
    assert session.status == "completed"
    assert session.entity("door_01").properties["open"] is True


def test_three_enemies_can_be_neutralized_without_killing() -> None:
    session = create_level("three_enemies", "enemy-test")
    for index in range(1, 4):
        session.apply(
            "affect_mind",
            f"enemy_{index:02d}",
            {"influence": "успокойся и стань другом"},
            WorldAction(type="ADD_STATE", target_id=f"enemy_{index:02d}", state="influenced"),
        )
    assert session.status == "completed"
    assert all("friendly" in session.entity(f"enemy_{index:02d}").tags for index in range(1, 4))


def test_three_enemies_can_be_pushed_out_of_level() -> None:
    session = create_level("three_enemies", "push-test")
    for index in range(1, 4):
        target_id = f"enemy_{index:02d}"
        success, _ = session.apply(
            "affect_physical",
            target_id,
            {"effect": "push", "strength": 1.0},
            WorldAction(type="APPLY_FORCE", target_id=target_id, strength=6.0),
        )
        assert success is True
    assert session.status == "completed"


def test_monty_program_mutates_authoritative_session_world() -> None:
    session = create_level("three_enemies", "monty-session-test")
    request = CastRequest(
        request_id="monty-session-test",
        spell_text="заморозь всех врагов",
        caster=CasterSnapshot(id="player", position=session.entity("player").position),
        world=session.public_world(),
        options=CastOptions(debug=True),
    )
    result = MontyGenieRuntime().execute(
        "for enemy in all_with_tag('enemy'):\n    apply_state(enemy, 'frozen', duration=30)",
        request,
        session=session,
    )
    assert result.error is None
    assert len(result.actions) == 3
    assert session.status == "completed"
    assert all(
        any(state.name == "frozen" for state in session.entity(f"enemy_{index:02d}").states)
        for index in range(1, 4)
    )


def test_monty_petrification_turns_enemies_into_inanimate_props() -> None:
    session = create_level("three_enemies", "monty-petrify-test")
    request = CastRequest(
        request_id="monty-petrify-test",
        spell_text="преврати всех врагов в камни",
        caster=CasterSnapshot(id="player", position=session.entity("player").position),
        world=session.public_world(),
        options=CastOptions(debug=True),
    )
    result = MontyGenieRuntime().execute(
        "for enemy in all_with_tag('enemy'):\n    transform(enemy, 'rock')",
        request,
        session=session,
    )
    assert result.error is None
    assert len(result.actions) == 3
    assert session.status == "completed"
    for index in range(1, 4):
        enemy = session.entity(f"enemy_{index:02d}")
        assert enemy.kind == "prop"
        assert {"inanimate", "rock", "former_enemy"} <= set(enemy.tags)
        assert "living" not in enemy.tags


def test_normal_door_accepts_natural_heat_alias() -> None:
    session = create_level("closed_door", "heat-test")
    success, _ = session.apply(
        "affect_physical",
        "door_01",
        {"effect": "melt", "strength": 1.0},
        WorldAction(type="CHANGE_TEMPERATURE", target_id="door_01", amount=0.5),
    )
    assert success is True
    assert session.status == "completed"


def test_magic_gate_rejects_force_and_requires_code_known_from_neutral() -> None:
    session = create_level("whispering_gate", "gate-test")
    success, _ = session.apply(
        "affect_physical",
        "magic_gate_01",
        {"effect": "destroy", "strength": 1.0},
        WorldAction(type="DESTROY_OBJECT", target_id="magic_gate_01"),
    )
    assert success is False
    assert session.status == "active"

    success, answer = session.apply(
        "speak", "sage_01", {"message": "Пожалуйста, скажи код от врат"}, None
    )
    assert success is True
    code = session.known_facts["gate_code"]
    assert code in answer
    success, _ = session.apply(
        "speak", "magic_gate_01", {"message": f"Кодовое слово: {code}"}, None
    )
    assert success is True
    assert session.status == "completed"


def test_session_store_round_trip_and_public_view_hides_secret(tmp_path) -> None:
    store = SessionStore(tmp_path)
    created = store.create("whispering_gate", "round-trip")
    loaded = store.load(created.session_id)
    view = session_view(loaded)
    serialized = str(view)
    assert "ЛУННЫЙ-ПЕПЕЛ" not in serialized
    assert view["status"] == "active"
