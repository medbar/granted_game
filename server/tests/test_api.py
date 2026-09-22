from fastapi.testclient import TestClient

from app.main import app, bounded_request_id
from conftest import cast_request


client = TestClient(app)


def test_long_session_request_ids_are_shortened_stably() -> None:
    original = "eval-" + "very-long-strategy-and-level-name-" * 4
    shortened = bounded_request_id(original)
    assert len(shortened) <= 80
    assert shortened == bounded_request_id(original)
    assert shortened != bounded_request_id(original + "different")


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["anchors"] == 100
    assert response.json()["semantic_backend"] == "char_ngram"


def test_cast_contract(world) -> None:
    payload = cast_request("оттолкни врага", world).model_dump(mode="json")
    response = client.post("/cast", json=payload)
    assert response.status_code == 200
    assert response.json()["request_id"] == "test-cast"
    assert response.json()["spell_plan"]["world_actions"]


def test_wish_contract_accepts_wish_text(world) -> None:
    payload = cast_request("заморозь воду", world).model_dump(mode="json")
    payload["wish_text"] = payload.pop("spell_text")
    payload["request_id"] = "test-wish"
    response = client.post("/wish", json=payload)
    assert response.status_code == 200
    assert response.json()["request_id"] == "test-wish"
    assert response.json()["spell_plan"]["world_actions"]


def test_wish_rejects_removed_gesture_input(world) -> None:
    payload = cast_request("заморозь воду", world).model_dump(mode="json")
    payload["gesture"] = {"strokes": []}
    response = client.post("/wish", json=payload)
    assert response.status_code == 422


def test_malformed_request_returns_validation_error() -> None:
    response = client.post("/cast", json={"spell_text": ""})
    assert response.status_code == 422


def test_world_config_exposes_runtime_source_of_truth() -> None:
    response = client.get("/world/config")
    assert response.status_code == 200
    assert {"spell", "materials", "reactions", "visuals"} <= response.json().keys()
