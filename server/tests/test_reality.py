from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.reality import Campaign, Petition, RealityError

CASES = json.loads((Path(__file__).parents[1] / "evals/bureaucracy_cases.json").read_text(encoding="utf-8"))["cases"]


def contracted(game):
    state = game.create()
    sid = state["id"]
    for action in ("eat", "sleep", "commute", "work", "work", "home", "sign", "leave"):
        game.command(sid, action)
    return sid


def lookup(state, dotted):
    for part in dotted.split("."):
        state = state[part]
    return state


def test_voluntary_contract_and_routine(tmp_path):
    game = Campaign(tmp_path)
    sid = game.create()["id"]
    with pytest.raises(RealityError):
        game.command(sid, "sign")
    with pytest.raises(RealityError):
        game.command(sid, "leave")
    for action in ("eat", "sleep", "commute", "work", "work", "home"):
        game.command(sid, action)
    state = game.get(sid)
    assert state["contract_ready"] and not state["contract_signed"]
    game.command(sid, "sleep")
    game.command(sid, "commute")
    game.command(sid, "work")
    game.command(sid, "home")
    assert not game.get(sid)["contract_signed"]
    state = game.command(sid, "sign")
    assert state["contract_signed"]
    assert state["phase"] == "apartment"
    assert "после смерти" in state["contract_terms"]
    assert game.command(sid, "leave")["phase"] == "city"


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_frozen_legal_effects(tmp_path, case):
    async def planner(wish, snapshot, error):
        return Petition(**case["decision"])

    game = Campaign(tmp_path, planner=planner)
    sid = contracted(game)
    result = asyncio.run(game.wish(sid, case["wish"], case["id"]))
    assert result["status"] == "completed", result
    state = game.get(sid)
    for dotted, expected in case["expected"].items():
        assert lookup(state, dotted) == expected
    assert len(state["precedents"]) == 1
    assert state["precedents"][0]["scope"]
    assert result["basis"] == case["decision"]["basis"]


def test_reuses_precedent_persists_and_opens_for_npcs(tmp_path):
    game = Campaign(tmp_path)
    sid = contracted(game)
    decision = Petition(**CASES[0]["decision"])
    first = game.resolve(sid, decision, "first")
    second = game.resolve(sid, decision.model_copy(update={"target": "side_gate"}), "second")
    assert first["precedent_id"] == second["precedent_id"]
    state = game.get(sid)
    assert len(state["precedents"]) == 1 and state["precedents"][0]["uses"] == 2
    assert game.can_cross(sid, "checkpoint", "police_1")
    assert Campaign(tmp_path).get(sid) == state


def test_invalid_decision_does_not_mutate_world(tmp_path):
    game = Campaign(tmp_path)
    sid = contracted(game)
    before = game.get(sid)
    for patch in ({"basis": "invented"}, {"target": "missing"}, {"target": "car"}, {"basis": "non_aggression"}):
        with pytest.raises(RealityError):
            game.resolve(sid, Petition(**(CASES[0]["decision"] | patch)), "bad")
        assert game.get(sid) == before


def test_retry_receives_error_and_verifies_effect(tmp_path):
    errors = []
    async def planner(wish, snapshot, error):
        errors.append(error)
        return Petition(**(CASES[0]["decision"] | ({"target": "missing"} if len(errors) == 1 else {})))

    game = Campaign(tmp_path, planner=planner)
    sid = contracted(game)
    result = asyncio.run(game.wish(sid, "Пусть дверь станет аварийным выходом", "retry"))
    assert result["status"] == "completed" and result["attempts"] == 2
    assert errors[1] and game.get(sid)["objects"]["checkpoint"]["open"]


def test_failed_wish_is_visible_and_has_no_fallback(tmp_path):
    async def planner(wish, snapshot, error):
        return Petition(**(CASES[0]["decision"] | {"basis": "invented"}))
    game = Campaign(tmp_path, planner=planner)
    sid = contracted(game)
    before = game.get(sid)
    result = asyncio.run(game.wish(sid, "невозможное основание", "failed"))
    after = game.get(sid)
    assert result["status"] == "failed" and result["attempts"] == 3
    assert result["message"] and after["message"] == result["message"]
    assert after["objects"] == before["objects"] and not after["precedents"]


def test_idempotence_and_trajectory(tmp_path):
    calls = []
    async def planner(wish, snapshot, error):
        calls.append(wish)
        return Petition(**CASES[6]["decision"])
    game = Campaign(tmp_path, planner=planner)
    sid = contracted(game)
    one = asyncio.run(game.wish(sid, "Создай дерево", "same"))
    two = asyncio.run(game.wish(sid, "Создай дерево", "same"))
    assert one == two and len(calls) == 1
    traces = list((tmp_path / "trajectories").glob("*.json"))
    assert len(traces) == 1
    trace = json.loads(traces[0].read_text(encoding="utf-8"))
    assert "registered_1" not in trace["before"]["objects"]
    assert trace["after"]["objects"]["registered_1"]["kind"] == "tree"


def test_simulation_continues_while_lawyer_waits(tmp_path):
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def planner(wish, snapshot, error):
            entered.set()
            await release.wait()
            return Petition(**CASES[3]["decision"])
        game = Campaign(tmp_path, planner=planner)
        sid = contracted(game)
        task = asyncio.create_task(game.wish(sid, "Защити меня", "concurrent"))
        await entered.wait()
        before = game.get(sid)["player"]["x"]
        game.tick(sid, 1, 0, 0.2)
        moved = game.get(sid)["player"]["x"]
        assert moved > before
        release.set()
        result = await task
        assert result["status"] == "completed"
        assert game.get(sid)["player"]["x"] == moved
    asyncio.run(scenario())


def test_precontract_wish_rejected_and_no_spoilers(tmp_path):
    game = Campaign(tmp_path)
    sid = game.create()["id"]
    with pytest.raises(RealityError):
        asyncio.run(game.wish(sid, "Открой дверь", "before"))
    public = json.dumps(game.get(sid), ensure_ascii=False)
    assert "занять её вершину" not in public and "active_curse_ids" not in public


def test_law_changes_damage_recognition_and_collision(tmp_path):
    game = Campaign(tmp_path)
    sid = contracted(game)
    assert not game.can_cross(sid, "checkpoint", "player")
    game.resolve(sid, Petition(**CASES[2]["decision"]), "pass")
    assert game.can_cross(sid, "checkpoint", "player")
    game.resolve(sid, Petition(**CASES[3]["decision"]), "protect")
    assert game.damage(sid, 50)["player"]["health"] == 100
    game.resolve(sid, Petition(**CASES[1]["decision"]), "identity")
    assert not game.detected(sid, "police_1")


def test_campaign_is_default_entrypoint():
    config = (Path(__file__).parents[2] / "client/project.godot").read_text(encoding="utf-8")
    assert 'run/main_scene="res://scenes/bureaucracy.tscn"' in config
    assert 'config/name="Bureaucracy of Reality"' in config


def test_numeric_model_value_is_not_rejected_or_changed():
    decision = Petition(**(CASES[9]["decision"] | {"value": 0.0}))
    assert float(decision.value) == 0


def test_rejected_petition_remains_in_trajectory(tmp_path):
    async def planner(wish, snapshot, error):
        return Petition(**(CASES[0]["decision"] | {"target": "missing"}))
    game = Campaign(tmp_path, planner=planner)
    sid = contracted(game)
    asyncio.run(game.wish(sid, "Открой дверь", "missing"))
    trace = json.loads(next((tmp_path / "trajectories").glob("*.json")).read_text(encoding="utf-8"))
    assert trace["attempts"][0]["petition"]["target"] == "missing"


def test_http_campaign_contract_and_movement(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import reality_api
    from app.main import app
    monkeypatch.setattr(reality_api, "campaign", Campaign(tmp_path))
    with TestClient(app) as client:
        created = client.post("/bureau/sessions")
        assert created.status_code == 201
        sid = created.json()["id"]
        assert client.post(f"/bureau/sessions/{sid}/wish", json={"text": "Открой дверь"}).status_code == 409
        for action in ("eat", "sleep", "commute", "work", "work", "home", "sign", "leave"):
            result = client.post(f"/bureau/sessions/{sid}/command", json={"action": action})
            assert result.status_code == 200
        start = result.json()["player"]["x"]
        moved = client.post(f"/bureau/sessions/{sid}/tick", json={"dx": 1, "dt": .2}).json()
        assert moved["player"]["x"] > start
        assert client.post(f"/bureau/sessions/{sid}/tick", json={"dx": 999}).status_code == 422
        assert client.get("/bureau/sessions/unknown").status_code == 409
