from __future__ import annotations

import json

from fastapi.testclient import TestClient

import app.observer as observer
from app.main import app


def test_visual_artifact_index_pairs_result_json_and_png(tmp_path) -> None:
    case_dir = tmp_path / "environment" / "create_wall"
    case_dir.mkdir(parents=True)
    (case_dir / "result.json").write_text(
        json.dumps(
            {
                "case_id": "create_wall",
                "wish": "Создай стену",
                "passed": True,
                "level_version": "monaco-start-v1",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (case_dir / "before.json").write_text("{}", encoding="utf-8")
    (case_dir / "after.json").write_text("{}", encoding="utf-8")
    (case_dir / "after.png").write_bytes(b"fake-png")

    payload = observer.list_visual_artifacts(tmp_path)

    assert payload["case_count"] == 1
    assert payload["cases"][0]["passed"] is True
    assert payload["cases"][0]["png_url"].endswith("/environment/create_wall/after.png")
    assert payload["cases"][0]["after_json_url"].endswith("/environment/create_wall/after.json")


def test_visual_artifact_api_serves_safe_files_and_rejects_traversal(tmp_path, monkeypatch) -> None:
    case_dir = tmp_path / "start_level_playthrough"
    case_dir.mkdir()
    (case_dir / "result.json").write_text('{"passed":true}', encoding="utf-8")
    (case_dir / "final.png").write_bytes(b"png")
    monkeypatch.setattr(observer, "CLIENT_ARTIFACT_ROOT", tmp_path)
    client = TestClient(app)

    index = client.get("/observer/api/artifacts")
    image = client.get("/observer/artifacts/start_level_playthrough/final.png")
    traversal = client.get("/observer/artifacts/%2e%2e/server/.env")

    assert index.status_code == 200
    assert index.json()["case_count"] == 1
    assert image.status_code == 200
    assert traversal.status_code in {400, 404}
