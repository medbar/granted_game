from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .config import ROOT


router = APIRouter(prefix="/observer", include_in_schema=False)
RUNTIME_ROOT = ROOT / "runtime"
EVENTS_PATH = RUNTIME_ROOT / "logs" / "agent-events.jsonl"
METRICS_PATH = RUNTIME_ROOT / "metrics" / "granted_game.prom"
TRAJECTORY_DIR = RUNTIME_ROOT / "trajectories"
PAGE_PATH = Path(__file__).with_name("observer.html")
CLIENT_ARTIFACT_ROOT = ROOT.parent / "client" / "test-artifacts"
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def _artifact_url(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return "/observer/artifacts/" + relative


def list_visual_artifacts(root: Path | None = None) -> dict[str, Any]:
    root = root or CLIENT_ARTIFACT_ROOT
    cases: list[dict[str, Any]] = []
    if not root.exists():
        return {"root_available": False, "case_count": 0, "cases": []}
    for result_path in sorted(root.rglob("result.json")):
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(result, dict):
            continue
        case_dir = result_path.parent
        relative_parts = case_dir.relative_to(root).parts
        suite = relative_parts[0] if relative_parts else "artifacts"
        png_path = next(
            (candidate for candidate in (case_dir / "after.png", case_dir / "final.png", case_dir / "level.png") if candidate.exists()),
            None,
        )
        before_path = next(
            (candidate for candidate in (case_dir / "before.json", case_dir / "00-before.json") if candidate.exists()),
            None,
        )
        after_path = next(
            (
                candidate
                for candidate in (
                    case_dir / "after.json",
                    case_dir / "03-after.json",
                    case_dir / "world.json",
                )
                if candidate.exists()
            ),
            None,
        )
        cases.append(
            {
                "suite": suite,
                "case_id": result.get("case_id", case_dir.name),
                "wish": result.get("wish", "Стартовое прохождение" if suite == "start_level_playthrough" else ""),
                "passed": bool(result.get("passed", False)),
                "issues": result.get("issues", []),
                "level_version": result.get("level_version", ""),
                "result_json_url": _artifact_url(result_path, root),
                "before_json_url": _artifact_url(before_path, root) if before_path else None,
                "after_json_url": _artifact_url(after_path, root) if after_path else None,
                "png_url": _artifact_url(png_path, root) if png_path else None,
            }
        )
    return {"root_available": True, "case_count": len(cases), "cases": cases}


def read_events(path: Path = EVENTS_PATH, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: deque[dict[str, Any]] | list[dict[str, Any]]
    records = deque(maxlen=limit) if limit else []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    return list(records)


def read_metrics(path: Path = METRICS_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    metrics: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            name, raw_value = line.rsplit(None, 1)
            value = float(raw_value)
        except (ValueError, TypeError):
            continue
        metrics.append({"name": name, "value": value})
    return metrics


def summarize_requests(events: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    requests: dict[str, dict[str, Any]] = {}
    for event in events:
        request_id = str(event.get("request_id", ""))
        if not request_id:
            continue
        if event.get("event") == "agent.run.started" or request_id not in requests:
            # The Godot client restarts its counter, so the same request id can occur in
            # several play sessions. The dashboard intentionally presents the newest run.
            requests[request_id] = {
                "request_id": request_id,
                "wish": "",
                "status": "running",
                "started_at": None,
                "finished_at": None,
                "latency_ms": None,
                "ttfa_ms": None,
                "action_count": 0,
                "error": None,
                "program_source": None,
                "trajectory_available": False,
            }
        item = requests[request_id]
        kind = event.get("event")
        if kind == "agent.run.started":
            item["wish"] = event.get("wish", "")
            item["started_at"] = event.get("timestamp")
        elif kind == "agent.program.fast_path":
            item["program_source"] = "fast_path"
        elif kind in {
            "agent.first_world_action",
            "agent.first_action",
            "agent.first_action.client_observed",
        }:
            item["ttfa_ms"] = event.get("time_to_first_action_ms")
        elif kind == "agent.action":
            item["action_count"] += 1
        elif kind == "agent.run.completed":
            item["status"] = event.get("status", "completed")
            item["finished_at"] = event.get("timestamp")
            item["latency_ms"] = event.get("latency_ms")
            item["action_count"] = max(item["action_count"], int(event.get("action_count", 0)))
            item["trajectory_available"] = bool(event.get("trajectory_path"))
        elif kind == "agent.run.failed":
            item["status"] = "failed"
            item["finished_at"] = event.get("timestamp")
            item["error"] = event.get("error")
        elif kind == "agent.loop.planning":
            item["status"] = "planning"
        elif kind == "agent.loop.started":
            item["status"] = "running"
        elif kind == "agent.loop.action_ready":
            item["status"] = "action_ready"
        elif kind == "agent.loop.feedback":
            item["status"] = "running" if event.get("verified") else "replanning"
        elif kind == "agent.loop.replanning":
            item["status"] = "replanning"
        elif kind == "agent.loop.completed":
            item["status"] = "completed"
            item["finished_at"] = event.get("timestamp")
            item["action_count"] = max(
                item["action_count"], int(event.get("verified_steps", 0))
            )
        elif kind == "agent.loop.failed":
            item["status"] = "failed"
            item["finished_at"] = event.get("timestamp")
            item["error"] = event.get("error")
    ordered = sorted(
        requests.values(),
        key=lambda item: item.get("started_at") or item.get("finished_at") or "",
        reverse=True,
    )
    return ordered[:limit]


def load_trajectory(request_id: str, directory: Path = TRAJECTORY_DIR) -> dict[str, Any] | None:
    if not SAFE_REQUEST_ID.fullmatch(request_id):
        raise ValueError("invalid request id")
    if not directory.exists():
        return None
    matches = sorted(directory.glob(f"*_{request_id}.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in matches:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("request", {}).get("request_id") == request_id:
            payload["_observer"] = {"filename": path.name}
            return payload
    return None


@router.get("", response_class=HTMLResponse)
def observer_page() -> HTMLResponse:
    return HTMLResponse(PAGE_PATH.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@router.get("/api/overview")
def observer_overview(limit: int = Query(default=80, ge=10, le=500)) -> JSONResponse:
    events = read_events()
    payload = {
        "requests": summarize_requests(events, limit),
        "metrics": read_metrics(),
        "event_count": len(events),
    }
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.get("/api/artifacts")
def observer_artifacts() -> JSONResponse:
    return JSONResponse(list_visual_artifacts(), headers={"Cache-Control": "no-store"})


@router.get("/artifacts/{artifact_path:path}")
def observer_artifact_file(artifact_path: str) -> FileResponse:
    root = CLIENT_ARTIFACT_ROOT.resolve()
    candidate = (root / artifact_path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    if candidate.suffix.lower() not in {".json", ".png"}:
        raise HTTPException(status_code=400, detail="unsupported artifact type")
    media_type = "image/png" if candidate.suffix.lower() == ".png" else "application/json"
    return FileResponse(candidate, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.get("/api/requests/{request_id}")
def observer_request(request_id: str) -> JSONResponse:
    if not SAFE_REQUEST_ID.fullmatch(request_id):
        raise HTTPException(status_code=400, detail="invalid request id")
    events = [event for event in read_events() if event.get("request_id") == request_id]
    if not events:
        raise HTTPException(status_code=404, detail="request not found")
    loop_starts = [
        index for index, event in enumerate(events) if event.get("event") == "agent.loop.started"
    ]
    latest_start = loop_starts[-1] if loop_starts else max(
        (index for index, event in enumerate(events) if event.get("event") == "agent.run.started"),
        default=0,
    )
    events = events[latest_start:]
    failed = any(event.get("event") in {"agent.run.failed", "agent.loop.failed"} for event in events)
    return JSONResponse(
        {
            "request_id": request_id,
            "events": events,
            "trajectory": None if failed else load_trajectory(request_id),
        },
        headers={"Cache-Control": "no-store"},
    )
