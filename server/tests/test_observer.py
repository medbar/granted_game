import json

from fastapi.testclient import TestClient

from app.main import app
from app.observer import load_trajectory, read_events, read_metrics, summarize_requests


def test_observer_page_and_api_are_available() -> None:
    client = TestClient(app)
    page = client.get("/observer")
    assert page.status_code == 200
    assert "ДЖИН" in page.text
    overview = client.get("/observer/api/overview")
    assert overview.status_code == 200
    assert {"requests", "metrics", "event_count"} <= overview.json().keys()


def test_observer_reads_and_summarizes_files(tmp_path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "1", "event": "agent.run.started", "request_id": "wish-1", "wish": "test"}),
                json.dumps({"timestamp": "2", "event": "agent.action", "request_id": "wish-1"}),
                json.dumps({"timestamp": "3", "event": "agent.run.completed", "request_id": "wish-1", "status": "completed", "action_count": 1}),
            ]
        ),
        encoding="utf-8",
    )
    metrics_path = tmp_path / "metrics.prom"
    metrics_path.write_text('requests_total 2\nactions_total{kind="speak"} 1\n', encoding="utf-8")
    summary = summarize_requests(read_events(events_path), 10)
    assert summary[0]["wish"] == "test"
    assert summary[0]["status"] == "completed"
    assert summary[0]["action_count"] == 1
    assert read_metrics(metrics_path)[1]["value"] == 1


def test_request_summary_replaces_reused_client_ids_with_newest_run() -> None:
    events = [
        {"timestamp": "1", "event": "agent.run.started", "request_id": "wish-1", "wish": "old"},
        {"timestamp": "2", "event": "agent.run.completed", "request_id": "wish-1", "status": "completed", "action_count": 3},
        {"timestamp": "3", "event": "agent.run.started", "request_id": "wish-1", "wish": "new"},
        {"timestamp": "4", "event": "agent.run.failed", "request_id": "wish-1", "error": "bad model output"},
    ]
    summary = summarize_requests(events, 10)
    assert summary == [
        {
            "request_id": "wish-1",
            "wish": "new",
            "status": "failed",
            "started_at": "3",
            "finished_at": "4",
            "latency_ms": None,
            "ttfa_ms": None,
            "action_count": 0,
            "error": "bad model output",
            "program_source": None,
            "trajectory_available": False,
        }
    ]


def test_trajectory_lookup_is_bounded_to_safe_request_ids(tmp_path) -> None:
    trajectory = tmp_path / "stamp_wish-1.json"
    trajectory.write_text(json.dumps({"request": {"request_id": "wish-1"}}), encoding="utf-8")
    assert load_trajectory("wish-1", tmp_path)["_observer"]["filename"] == trajectory.name
    try:
        load_trajectory("../secret", tmp_path)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe request id was accepted")
