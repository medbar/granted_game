from __future__ import annotations

from typing import Any

from .config import visual_mapping
from .models import Vec2, VisualDescriptor, WorldObject


class VisualResolver:
    def __init__(self) -> None:
        self.config = visual_mapping()

    def resolve(self, intent: dict[str, Any], targets: list[WorldObject]) -> list[VisualDescriptor]:
        geometry = intent["geometry"]
        primitive = "BURST"
        for key, candidate in self.config["geometry_priority"]:
            if geometry.get(key, 0.0) > 0.24:
                primitive = candidate
                break
        if not geometry and intent["movement"].get("push", 0.0) > 0.25:
            primitive = "RING" if intent["targets"].get("around", 0.0) > 0.2 else "BEAM"
        appearance = sorted(intent["matter"], key=intent["matter"].get, reverse=True)[:2]
        if not appearance:
            appearance = ["force"]
        target_position = targets[0].position if targets else None
        return [
            VisualDescriptor(
                primitive=primitive,
                appearance=appearance,
                origin=Vec2(**intent["spatial"]["origin"]),
                direction=Vec2(**intent["spatial"]["direction"]),
                radius=intent["spatial"]["radius"],
                speed=3.5 + intent["properties"].get("fast", 0.0) * 5.5,
                intensity=min(1.0, intent["power"]),
                turbulence=max(0.04, 1.0 - intent["coherence"]),
                lifetime=intent["duration"],
                target=target_position,
            )
        ]

