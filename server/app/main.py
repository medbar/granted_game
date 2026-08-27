from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from .config import materials_config, reactions_config, spell_settings, visual_mapping
from .models import CastRequest, CastResponse
from .service import SpellService


app = FastAPI(title="Granted Game Wish Interpreter", version="0.2.0")
service = SpellService(log_path=Path(__file__).resolve().parents[1] / "cast_debug.jsonl")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "anchors": len(service.semantic.anchors),
        "semantic_backend": service.semantic.backend,
        "semantic_model": service.semantic.model_name,
    }


@app.post("/cast", response_model=CastResponse)
def cast(request: CastRequest) -> CastResponse:
    return service.cast(request)


@app.post("/wish", response_model=CastResponse)
def wish(request: CastRequest) -> CastResponse:
    """Interpret a requester's free-form wish and let the genie enact it."""
    return service.cast(request)


@app.get("/debug/anchors")
def debug_anchors() -> dict[str, object]:
    return {"anchors": service.semantic.anchor_details()}


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
