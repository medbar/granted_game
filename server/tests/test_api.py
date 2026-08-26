from fastapi.testclient import TestClient

from app.main import app
from conftest import cast_request, line_gesture


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["anchors"] == 100


def test_cast_contract(world) -> None:
    payload = cast_request("оттолкни врага", line_gesture(), world).model_dump(mode="json")
    response = client.post("/cast", json=payload)
    assert response.status_code == 200
    assert response.json()["request_id"] == "test-cast"
    assert response.json()["spell_plan"]["world_actions"]


def test_malformed_request_returns_validation_error() -> None:
    response = client.post("/cast", json={"spell_text": ""})
    assert response.status_code == 422
