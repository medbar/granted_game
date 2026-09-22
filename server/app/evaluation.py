from __future__ import annotations

from pydantic import BaseModel, Field

from .agent_models import AgentAction, AgentConclusion


class TrajectoryEval(BaseModel):
    evaluator_version: str = "heuristic-v1"
    completed: bool
    valid_action_ratio: float = Field(ge=0.0, le=1.0)
    action_efficiency: float = Field(ge=0.0, le=1.0)
    observation_order: float = Field(ge=0.0, le=1.0)
    score: float = Field(ge=0.0, le=1.0)


def evaluate_trajectory(actions: list[AgentAction], conclusion: AgentConclusion) -> TrajectoryEval:
    """Cheap baseline saved with every run; future LLM judges can replace or augment it."""
    completed = conclusion.status == "completed"
    if actions:
        valid_ratio = sum(action.success for action in actions) / len(actions)
        efficiency = min(1.0, 4.0 / len(actions))
    else:
        valid_ratio = 0.0
        efficiency = 0.0
    mutating = {
        "affect_physical",
        "create_item",
        "create_object",
        "interact",
        "affect_mind",
        "speak",
    }
    first_mutation = next((index for index, action in enumerate(actions) if action.kind in mutating), None)
    post_mutation_inspections = (
        sum(action.kind in {"observe_area", "inspect_entity"} for action in actions[first_mutation + 1 :])
        if first_mutation is not None
        else 0
    )
    observation_order = 1.0 if post_mutation_inspections == 0 else max(0.0, 1.0 - 0.5 * post_mutation_inspections)
    score = (
        0.4 * float(completed)
        + 0.2 * valid_ratio
        + 0.15 * efficiency
        + 0.25 * observation_order
    )
    return TrajectoryEval(
        completed=completed,
        valid_action_ratio=round(valid_ratio, 4),
        action_efficiency=round(efficiency, 4),
        observation_order=round(observation_order, 4),
        score=round(score, 4),
    )
