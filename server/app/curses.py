from __future__ import annotations

import json
from pathlib import Path

from .agent_models import CurseDefinition, GenieState, PublicCurse
from .config import CONFIG_DIR, ROOT


class CurseManager:
    def __init__(self, state_path: Path | None = None) -> None:
        raw = json.loads((CONFIG_DIR / "curses.json").read_text(encoding="utf-8"))
        self.definitions = {
            item.id: item for item in (CurseDefinition.model_validate(row) for row in raw["curses"])
        }
        self.state_path = state_path or ROOT / "runtime" / "genie_state.json"
        self.state = self._load_state()

    def _load_state(self) -> GenieState:
        if not self.state_path.exists():
            return GenieState()
        return GenieState.model_validate_json(self.state_path.read_text(encoding="utf-8"))

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(self.state.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.state_path)

    def active(self) -> list[CurseDefinition]:
        return [self.definitions[item] for item in self.state.active_curse_ids if item in self.definitions]

    def public(self) -> list[PublicCurse]:
        return [PublicCurse.model_validate(item.model_dump()) for item in self.active()]

    def prompt_fragment(self) -> str:
        active = self.active()
        if not active:
            return "На тебе пока нет поведенческих проклятий."
        lines = ["На тебе лежат проклятия. Следуй каждому из этих внутренних импульсов:"]
        lines.extend(f"- {item.instruction}" for item in active)
        return "\n".join(lines)

    def record_wish(self, wish_text: str, action_kinds: list[str], completed: bool) -> list[PublicCurse]:
        state = self.state
        state.wish_count += 1
        if completed:
            state.completed_wishes += 1
        lowered = wish_text.lower()
        if any(word in lowered for word in ("убей", "убить", "уничтож", "атак", "сломай")):
            state.violent_wishes += 1
        state.mind_actions += sum(kind == "affect_mind" for kind in action_kinds)
        state.created_objects += sum(kind in {"create_item", "create_object"} for kind in action_kinds)

        newly_active: list[PublicCurse] = []
        for definition in self.definitions.values():
            if definition.id in state.active_curse_ids:
                continue
            value = int(getattr(state, definition.trigger, 0))
            if value >= definition.threshold:
                state.active_curse_ids.append(definition.id)
                newly_active.append(PublicCurse.model_validate(definition.model_dump()))
        self.save()
        return newly_active
