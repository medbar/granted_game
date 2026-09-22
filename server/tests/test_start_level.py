from __future__ import annotations

import json
from pathlib import Path

from app.agent import GenieAgentService
from app.models import CastOptions, CastRequest, CasterSnapshot
from app.monty_runtime import MontyGenieRuntime
from app.sim_world import create_level, session_view


PLAYTHROUGH_PATH = Path(__file__).resolve().parents[1] / "evals" / "start_level_playthrough.json"


def test_frozen_start_level_playthrough_completes_real_mission() -> None:
    suite = json.loads(PLAYTHROUGH_PATH.read_text(encoding="utf-8"))
    session = create_level("monaco_start", "frozen-playthrough")
    runtime = MontyGenieRuntime()

    for index, step in enumerate(suite["steps"], 1):
        program = GenieAgentService._compile_fast_program(step["wish"])
        assert program is not None, step["wish"]
        request = CastRequest(
            request_id=f"playthrough-{index}",
            wish_text=step["wish"],
            caster=CasterSnapshot(id="player", position=session.entity("player").position),
            world=session.public_world(),
            options=CastOptions(debug=True),
        )
        result = runtime.execute(program.code, request, session=session)
        assert result.error is None, result.error
        assert result.actions

    view = session_view(session)
    assert view["status"] == "completed"
    assert view["mission"]["status"] == "completed"
    assert set(view["mission"]["collected_loot_ids"]) == {"loot_01", "loot_02", "loot_03"}
    exit_door = next(item for item in view["world"]["objects"] if item["id"] == "exit_door_01")
    assert exit_door["properties"]["open"] is True
    assert not [
        item
        for item in view["world"]["objects"]
        if "enemy" in item["tags"] and not item["properties"].get("neutralized", False)
    ]
