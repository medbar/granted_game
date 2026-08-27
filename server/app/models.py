from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class Vec2(BaseModel):
    x: float = 0.0
    y: float = 0.0


class CasterSnapshot(BaseModel):
    id: str = "player"
    position: Vec2
    velocity: Vec2 = Field(default_factory=Vec2)
    facing: Vec2 = Field(default_factory=lambda: Vec2(x=1.0, y=0.0))


class MaterialSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = "generic"
    mass: float = Field(default=1.0, gt=0.0)
    temperature: float = 0.5
    wetness: float = Field(default=0.0, ge=0.0, le=1.0)
    flammability: float = Field(default=0.0, ge=0.0, le=1.0)
    conductivity: float = Field(default=0.0, ge=0.0, le=1.0)
    hardness: float = Field(default=0.3, ge=0.0, le=1.0)
    brittleness: float = Field(default=0.2, ge=0.0, le=1.0)


class ObjectState(BaseModel):
    name: str
    strength: float = 1.0
    remaining_duration: float = 1.0
    source: str = "magic"


class WorldObject(BaseModel):
    id: str
    kind: str
    tags: list[str] = Field(default_factory=list)
    position: Vec2
    velocity: Vec2 = Field(default_factory=Vec2)
    radius: float = Field(default=0.5, gt=0.0)
    health: float | None = None
    material: MaterialSnapshot = Field(default_factory=MaterialSnapshot)
    states: list[ObjectState | str] = Field(default_factory=list)


class WorldSnapshot(BaseModel):
    objects: list[WorldObject] = Field(default_factory=list, max_length=128)


class CastOptions(BaseModel):
    debug: bool = False


class CastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=80)
    spell_text: str = Field(
        min_length=1,
        max_length=300,
        validation_alias=AliasChoices("wish_text", "spell_text"),
    )
    seed: int = 0
    caster: CasterSnapshot
    world: WorldSnapshot = Field(default_factory=WorldSnapshot)
    options: CastOptions = Field(default_factory=CastOptions)

    @field_validator("spell_text")
    @classmethod
    def reject_blank_spell(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("wish_text must not be blank")
        return value


class AnchorScore(BaseModel):
    id: str
    score: float
    family: str


class Interpretation(BaseModel):
    coherence: float
    anchors: list[AnchorScore]


class WorldAction(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    target_id: str | None = None
    direction: Vec2 | None = None
    strength: float | None = None
    amount: float | None = None
    state: str | None = None
    duration: float | None = None
    material: str | None = None
    effect: dict[str, Any] | None = None


class VisualDescriptor(BaseModel):
    primitive: str
    appearance: list[str]
    origin: Vec2
    direction: Vec2
    radius: float
    speed: float
    intensity: float
    turbulence: float
    lifetime: float
    target: Vec2 | None = None


class SpellPlan(BaseModel):
    duration: float
    power: float
    effects: list[dict[str, Any]] = Field(default_factory=list)
    world_actions: list[WorldAction] = Field(default_factory=list)
    visuals: list[VisualDescriptor] = Field(default_factory=list)


class DebugInfo(BaseModel):
    intent: dict[str, Any]
    selected_targets: list[str]
    world_rules: list[str]
    latency_ms: float


class CastResponse(BaseModel):
    request_id: str
    interpretation: Interpretation
    spell_plan: SpellPlan
    debug: DebugInfo | None = None
