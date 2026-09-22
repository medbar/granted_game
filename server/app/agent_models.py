from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .models import CastRequest, DebugInfo, Interpretation, SpellPlan, WorldAction


ActionKind = Literal[
    "observe_area",
    "inspect_entity",
    "affect_physical",
    "create_item",
    "create_object",
    "interact",
    "affect_mind",
    "speak",
]


class PublicCurse(BaseModel):
    id: str
    title: str
    sigil: str
    public_hint: str
    severity: int = Field(ge=1, le=5)


class CurseDefinition(PublicCurse):
    trigger: str
    threshold: int = Field(ge=1)
    instruction: str


class GenieState(BaseModel):
    version: int = 1
    wish_count: int = 0
    completed_wishes: int = 0
    violent_wishes: int = 0
    mind_actions: int = 0
    created_objects: int = 0
    active_curse_ids: list[str] = Field(default_factory=list)


class AgentAction(BaseModel):
    sequence: int
    kind: ActionKind
    target_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    observation: str
    success: bool = True
    teleport_to_target: bool = False
    world_action: WorldAction | None = None


class AgentConclusion(BaseModel):
    status: Literal["completed", "partial", "impossible"]
    summary: str


class GenieProgram(BaseModel):
    """Python source selected by the model for execution inside Monty."""

    code: str = Field(min_length=1, max_length=6_000)
    summary: str = Field(min_length=1, max_length=600)

    @field_validator("code")
    @classmethod
    def strip_markdown_fence(cls, value: str) -> str:
        source = value.strip()
        if source.startswith("```python") and source.endswith("```"):
            return source[len("```python") : -3].strip()
        if source.startswith("```") and source.endswith("```"):
            return source[3:-3].strip()
        return source


class PlannedAction(BaseModel):
    """One ordered action inside a model-selected batch."""

    kind: ActionKind
    target_id: str | None = None
    effect: Literal[
        "damage",
        "heal",
        "destroy",
        "push",
        "pull",
        "freeze",
        "burn",
        "heat",
        "melt",
        "bind",
        "sleep",
        "pacify",
        "teleport",
        "banish",
        "transform",
        "phase",
        "change_temperature",
        "add_state",
    ] | None = None
    strength: float = 0.5
    state: str | None = None
    prototype: str | None = None
    near_target_id: str | None = None
    interaction: str | None = None
    influence: str | None = None
    message: str | None = None


class AgentRunInfo(BaseModel):
    model: str
    prompt_version: str
    execution_engine: str = "monty"
    program_code: str = ""
    program_output: Any = None
    execution_ms: float = 0.0
    execution_error: str | None = None
    first_world_action_ms: float | None = None
    conclusion: AgentConclusion
    actions: list[AgentAction]
    public_curses: list[PublicCurse]
    latency_ms: float
    usage: dict[str, Any] = Field(default_factory=dict)


class AgentWishResponse(BaseModel):
    request_id: str
    interpretation: Interpretation = Field(
        default_factory=lambda: Interpretation(coherence=1.0, anchors=[])
    )
    spell_plan: SpellPlan
    debug: DebugInfo | None = None
    agent: AgentRunInfo


class AgentDeps(BaseModel):
    request: CastRequest
    actions: list[AgentAction] = Field(default_factory=list)
    session: Any | None = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}
