from __future__ import annotations

import hashlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query

from .agent import GenieAgentService
from .agent_jobs import AgenticWishJobManager, WishFeedback, WishJobManager
from .agent_models import AgentWishResponse
from .config import anchors_config
from .config import materials_config, reactions_config, spell_settings, visual_mapping
from .models import CastOptions, CastRequest, CastResponse, CasterSnapshot, Vec2
from .observer import router as observer_router
from .plugins import PluginToggleRequest
from .service import SpellService
from .sim_world import (
    CreateSessionRequest,
    SessionStore,
    SessionWishRequest,
    session_view,
)
from .telemetry import TelemetryStore


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Construct the local agent, Monty runtime and plugin registry before readiness.
    # This keeps one-time initialization out of the player's first wish latency.
    if agent_mode_enabled():
        agent_service()
    yield


app = FastAPI(title="Granted Game Wish Interpreter", version="0.2.0", lifespan=lifespan)
app.include_router(observer_router)
_spell_service: SpellService | None = None
_agent_service: GenieAgentService | None = None
_session_store = SessionStore()
_telemetry = TelemetryStore()
_legacy_wish_jobs = WishJobManager(_telemetry)
_agentic_wish_jobs = AgenticWishJobManager(_telemetry)


def bounded_request_id(value: str) -> str:
    if len(value) <= 80:
        return value
    return value[:55] + "-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def spell_service() -> SpellService:
    global _spell_service
    if _spell_service is None:
        _spell_service = SpellService(
            log_path=Path(__file__).resolve().parents[1] / "cast_debug.jsonl"
        )
    return _spell_service


def agent_service() -> GenieAgentService:
    global _agent_service
    if _agent_service is None:
        _agent_service = GenieAgentService(telemetry=_telemetry)
    return _agent_service


def agent_mode_enabled() -> bool:
    return os.getenv("GRANTED_AGENT_MODE", "true").lower() not in {"0", "false", "no"}


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "mode": "agent" if agent_mode_enabled() else "spell_compiler",
        "agent_model": os.getenv(
            "GENIE_AGENT_MODEL",
            os.getenv("AITUNNEL_AGENT_MODEL", "qwen3-35-36"),
        ),
        "agent_base_url": os.getenv(
            "GENIE_AGENT_BASE_URL",
            os.getenv("AITUNNEL_BASE_URL", "https://api.aitunnel.ru/v1"),
        ),
        "anchors": len(anchors_config()["anchors"]),
        "semantic_backend": os.getenv(
            "GRANTED_SEMANTIC_BACKEND", spell_settings().get("semantic_backend", "char_ngram")
        ),
        "semantic_model": os.getenv(
            "AITUNNEL_EMBEDDING_MODEL", spell_settings().get("semantic_model", "")
        ),
    }


@app.post("/cast", response_model=CastResponse)
def cast(request: CastRequest) -> CastResponse:
    return spell_service().cast(request)


@app.post("/wish", response_model=AgentWishResponse | CastResponse)
async def wish(request: CastRequest) -> AgentWishResponse | CastResponse:
    """Interpret a requester's free-form wish and let the genie enact it."""
    if agent_mode_enabled():
        return await agent_service().run(request)
    return spell_service().cast(request)


@app.post("/wish/jobs", status_code=202)
async def start_wish_job(request: CastRequest) -> dict[str, Any]:
    """Start a wish; agent mode exposes one verified world action at a time."""

    if agent_mode_enabled():
        first_plan = True

        async def planner(current_request: CastRequest) -> AgentWishResponse:
            nonlocal first_plan
            progress_curses = first_plan
            first_plan = False
            return await agent_service().run(current_request, progress_curses=progress_curses)

        return _agentic_wish_jobs.start(request, planner)

    async def runner() -> AgentWishResponse | CastResponse:
        return spell_service().cast(request)

    return _legacy_wish_jobs.start(
        request.request_id,
        runner,
        visible_object_count=len(request.world.objects),
    )


@app.get("/wish/jobs/{job_id}")
def get_wish_job(
    job_id: str,
    client_ttfa_ms: float | None = Query(default=None, ge=0.0, le=60_000.0),
) -> dict[str, Any]:
    try:
        if job_id in _agentic_wish_jobs.jobs:
            return _agentic_wish_jobs.get(job_id, client_ttfa_ms)
        return _legacy_wish_jobs.get(job_id, client_ttfa_ms)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="wish job not found") from error


@app.post("/wish/jobs/{job_id}/feedback")
async def submit_wish_feedback(job_id: str, feedback: WishFeedback) -> dict[str, Any]:
    """Accept the post-action world snapshot and advance or replan the wish."""
    try:
        return _agentic_wish_jobs.feedback(job_id, feedback)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="wish job not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/genie/state")
def genie_state() -> dict[str, Any]:
    service = agent_service()
    return {
        "public_curses": [item.model_dump(mode="json") for item in service.curses.public()],
        "counters": service.curses.state.model_dump(mode="json", exclude={"active_curse_ids"}),
        "prompt_version": service.prompt_config["version"],
        "model": service.model_name,
        "plugins": service.plugins.public_state(),
    }


@app.get("/genie/plugins")
def genie_plugins() -> dict[str, object]:
    return agent_service().plugins.public_state()


@app.put("/genie/plugins/{plugin_id}")
def set_genie_plugin(plugin_id: str, request: PluginToggleRequest) -> dict[str, object]:
    try:
        agent_service().plugins.set_enabled(plugin_id, request.enabled)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="genie plugin not found") from error
    return agent_service().plugins.public_state()


@app.post("/genie/plugins/reload")
def reload_genie_plugins() -> dict[str, object]:
    agent_service().plugins.reload()
    return agent_service().plugins.public_state()


@app.post("/agent/sessions")
def create_agent_session(request: CreateSessionRequest) -> dict[str, Any]:
    session = _session_store.create(request.level_id, request.session_id)
    return session_view(session)


@app.get("/agent/sessions/{session_id}")
def get_agent_session(session_id: str) -> dict[str, Any]:
    try:
        session = _session_store.load(session_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="agent session not found") from error
    return session_view(session)


@app.post("/agent/sessions/{session_id}/wish")
async def run_agent_session_wish(
    session_id: str, request: SessionWishRequest
) -> dict[str, Any]:
    try:
        session = _session_store.load(session_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="agent session not found") from error
    if session.status != "active":
        raise HTTPException(status_code=409, detail=f"session is already {session.status}")
    player = session.entity("player")
    raw_request_id = request.request_id or f"{session_id}-turn-{session.turn + 1:03d}"
    safe_request_id = bounded_request_id(raw_request_id)
    cast_request = CastRequest(
        request_id=safe_request_id,
        wish_text=request.wish_text,
        seed=session.turn + 1,
        caster=CasterSnapshot(
            id="player",
            position=player.position if player else Vec2(),
            facing=Vec2(x=1, y=0),
        ),
        world=session.public_world(),
        options=CastOptions(debug=request.debug),
    )
    response = await agent_service().run(
        cast_request,
        session=session,
        progress_curses=request.progress_curses,
    )
    session.turn += 1
    _session_store.save(session)
    return {
        "agent_response": response.model_dump(mode="json"),
        "session": session_view(session),
    }


@app.get("/debug/anchors")
def debug_anchors() -> dict[str, object]:
    return {"anchors": spell_service().semantic.anchor_details()}


@app.get("/debug/config")
def debug_config() -> dict[str, object]:
    return {
        "spell": spell_settings(),
        "materials": materials_config(),
        "reactions": reactions_config(),
        "visuals": visual_mapping(),
    }


@app.get("/world/config")
def world_config() -> dict[str, object]:
    return {
        "spell": spell_settings(),
        "materials": materials_config(),
        "reactions": reactions_config(),
        "visuals": visual_mapping(),
    }
