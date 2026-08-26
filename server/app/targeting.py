from __future__ import annotations

import math
from typing import Any

from .config import spell_settings
from .models import CasterSnapshot, WorldObject


MATERIAL_TAGS = {
    "water": {"water", "wet"},
    "ice": {"ice", "frozen"},
    "stone": {"stone", "rock"},
    "earth": {"earth", "ground"},
    "wood": {"wood", "wooden"},
    "plant": {"plant", "tree", "bush"},
    "metal": {"metal"},
}


class TargetResolver:
    def __init__(self) -> None:
        self.settings = spell_settings()["targeting"]

    def resolve(
        self,
        intent: dict[str, Any],
        caster: CasterSnapshot,
        objects: list[WorldObject],
    ) -> list[WorldObject]:
        origin = caster.position
        direction = intent["spatial"]["direction"]
        radius = intent["spatial"]["radius"]
        max_range = intent["spatial"]["range"]
        target_terms = intent["targets"]
        matter = intent["matter"]
        geometry = intent["geometry"]
        logic = intent["logic"]
        around = target_terms.get("around", 0.0) > self.settings["around_semantic_threshold"] or geometry.get("ring", 0.0) > self.settings["ring_threshold"]
        self_is_origin = target_terms.get("self", 0.0) > self.settings["self_threshold"] and (
            target_terms.get("enemy", 0.0) > self.settings["explicit_target_threshold"]
            or max(
                intent["movement"].get("push", 0.0),
                intent["movement"].get("pull", 0.0),
                intent["movement"].get("spread", 0.0),
                intent["movement"].get("lift", 0.0),
            ) > self.settings["explicit_target_threshold"]
        ) and max(
            intent["actions"].get("heal", 0.0), intent["matter"].get("life", 0.0)
        ) < self.settings["healing_self_lock"]
        explicit_tags: set[str] = set()
        for name, tags in MATERIAL_TAGS.items():
            if matter.get(name, 0.0) > self.settings["material_target_threshold"]:
                explicit_tags.update(tags)
        if target_terms.get("enemy", 0.0) > self.settings["explicit_target_threshold"]:
            explicit_tags.add("enemy")
        if target_terms.get("living", 0.0) > self.settings["explicit_target_threshold"]:
            explicit_tags.add("living")
        if target_terms.get("inanimate", 0.0) > self.settings["explicit_target_threshold"]:
            explicit_tags.add("inanimate")
        if target_terms.get("self", 0.0) > 0.45 and not self_is_origin:
            explicit_tags.add("player")

        scored: list[tuple[float, WorldObject]] = []
        for obj in objects:
            dx, dy = obj.position.x - origin.x, obj.position.y - origin.y
            distance = math.hypot(dx, dy)
            if distance > max(12.0, max_range + obj.radius):
                continue
            tags = {tag.lower() for tag in obj.tags} | {obj.material.name.lower()}
            semantic = 0.0
            if explicit_tags:
                matches = len(tags & explicit_tags)
                if not matches:
                    continue
                semantic = 2.4 + matches
            if obj.id == caster.id and ("player" not in explicit_tags or self_is_origin):
                if intent["logic"].get("except", 0.0) or intent["targets"].get("enemy", 0.0):
                    continue
                if not around:
                    continue
            dot = 1.0
            if distance > 0.001:
                dot = (dx / distance) * direction["x"] + (dy / distance) * direction["y"]
            spatial = max(0.0, dot) * 1.6 + max(0.0, 1.0 - distance / 12.0)
            if around:
                spatial = max(0.0, 2.0 - distance / max(radius * 1.8, 1.0))
                if distance > radius * 2.0 + obj.radius:
                    continue
            elif geometry.get("line", 0.0) > self.settings["line_threshold"] and dot < self.settings["line_minimum_dot"]:
                continue
            scored.append((semantic + spatial, obj))

        scored.sort(key=lambda item: (-item[0], self._distance(origin, item[1].position), item[1].id))
        if logic.get("all", 0.0) > 0.3:
            limit = int(self.settings["maximum_all_targets"])
        elif logic.get("one", 0.0) > 0.3 or target_terms.get("nearest", 0.0) > 0.3:
            limit = 1
        elif explicit_tags:
            limit = 6 if around else 3
        elif intent["matter"].get("air", 0.0) > self.settings["distributed_air_threshold"] and max(
            intent["matter"].get("force", 0.0), intent["movement"].get("push", 0.0)
        ) > self.settings["distributed_air_threshold"]:
            limit = int(self.settings["maximum_distributed_targets"])
        else:
            limit = 4 if around else 1
        return [item[1] for item in scored[:limit]]

    @staticmethod
    def _distance(left: Any, right: Any) -> float:
        return math.hypot(right.x - left.x, right.y - left.y)
