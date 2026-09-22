from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .models import WorldObject


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEVELS_ROOT = PROJECT_ROOT / "client" / "levels"


class RectDefinition(BaseModel):
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class RoomDefinition(BaseModel):
    id: str
    name: str
    rect: RectDefinition
    color: str
    tags: list[str] = Field(default_factory=list)
    floor_pattern: str = "grid"


class WallDefinition(BaseModel):
    id: str
    rect: RectDefinition
    material: str = "stone"
    accent: str = "cyan"


class DoorDefinition(BaseModel):
    id: str
    rect: RectDefinition
    connects: tuple[str, str]
    locked: bool = False
    open: bool = False
    extraction: bool = False
    material: str = "metal"


class MissionDefinition(BaseModel):
    id: str
    title: str
    required_loot_ids: list[str]
    extraction_door_id: str
    require_threats_neutralized: bool = False


class MissionState(MissionDefinition):
    status: Literal["active", "completed", "failed"] = "active"
    collected_loot_ids: list[str] = Field(default_factory=list)
    threats_neutralized: bool = False


class LevelDefinition(BaseModel):
    schema_version: Literal[1]
    version: str
    id: str
    name: str
    unit_px: float = Field(gt=0)
    bounds: RectDefinition
    extraction_zone: RectDefinition
    palette: dict[str, str]
    rooms: list[RoomDefinition]
    walls: list[WallDefinition]
    doors: list[DoorDefinition]
    entities: list[WorldObject]
    mission: MissionDefinition
    rendering: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ids_and_references(self) -> "LevelDefinition":
        groups = {
            "rooms": [item.id for item in self.rooms],
            "walls": [item.id for item in self.walls],
            "doors": [item.id for item in self.doors],
            "entities": [item.id for item in self.entities],
        }
        all_ids = [item for values in groups.values() for item in values]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("level ids must be globally unique")
        room_ids = set(groups["rooms"])
        for door in self.doors:
            for room_id in door.connects:
                if room_id != "outside" and room_id not in room_ids:
                    raise ValueError(f"door {door.id} references unknown room {room_id}")
        entity_ids = set(groups["entities"])
        missing_loot = set(self.mission.required_loot_ids) - entity_ids
        if missing_loot:
            raise ValueError(f"mission references unknown loot: {sorted(missing_loot)}")
        if self.mission.extraction_door_id not in set(groups["doors"]):
            raise ValueError("mission extraction door is unknown")
        return self


@lru_cache(maxsize=16)
def load_level_definition(level_id: str) -> LevelDefinition:
    path = LEVELS_ROOT / f"{level_id}.json"
    if not path.is_file():
        raise KeyError(f"unknown level definition: {level_id}")
    return LevelDefinition.model_validate(json.loads(path.read_text(encoding="utf-8")))
