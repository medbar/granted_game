from __future__ import annotations

import json

from app.levels import load_level_definition
from app.sim_world import SessionStore, create_level, session_view


def test_monaco_start_definition_is_complete_and_connected() -> None:
    level = load_level_definition("monaco_start")

    assert level.schema_version == 1
    assert level.version == "monaco-start-v1"
    assert len(level.rooms) >= 8
    assert len(level.walls) >= 24
    assert len(level.doors) >= 6
    assert len(level.entities) >= 12
    assert len(level.mission.required_loot_ids) == 3
    assert level.mission.extraction_door_id in {door.id for door in level.doors}
    assert {room.id for room in level.rooms} >= {
        "entrance",
        "gallery",
        "security",
        "archives",
        "courtyard",
        "vault",
    }
    assert all(door.connects[0] != door.connects[1] for door in level.doors)


def test_start_level_round_trip_is_lossless(tmp_path) -> None:
    store = SessionStore(tmp_path)
    created = store.create("monaco_start", "monaco-round-trip")
    before = session_view(created)

    store.save(created)
    loaded = store.load(created.session_id)
    after = session_view(loaded)

    assert after == before
    assert after["level"]["rooms"]
    assert after["level"]["walls"]
    assert after["level"]["doors"]
    assert after["mission"]["required_loot_ids"] == ["loot_01", "loot_02", "loot_03"]
    assert "secret_" not in json.dumps(after, ensure_ascii=False)


def test_agent_world_contains_full_level_context() -> None:
    session = create_level("monaco_start", "monaco-agent-context")
    public = session.public_world().model_dump(mode="json")

    assert public["level"]["id"] == "monaco_start"
    assert len(public["level"]["rooms"]) >= 8
    assert public["level"]["mission"]["extraction_door_id"] == "exit_door_01"
    assert {item["id"] for item in public["objects"]} >= {
        "player",
        "guard_01",
        "loot_01",
        "loot_03",
        "exit_door_01",
    }


def test_start_level_mission_requires_loot_and_open_exit() -> None:
    session = create_level("monaco_start", "monaco-mission")

    for loot_id in ("loot_01", "loot_02", "loot_03"):
        success, _ = session.apply("interact", loot_id, {"interaction": "take"}, None)
        assert success is True
    assert session.status == "active"

    success, _ = session.apply("interact", "exit_door_01", {"interaction": "open"}, None)

    assert success is True
    assert session.status == "completed"
    assert session.mission.status == "completed"
    assert session.mission.collected_loot_ids == ["loot_01", "loot_02", "loot_03"]
