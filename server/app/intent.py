from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .config import spell_settings
from .models import AnchorScore, CasterSnapshot


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class SpellIntentBuilder:
    def __init__(self) -> None:
        self.settings = spell_settings()

    def build(
        self,
        anchors: list[AnchorScore],
        coherence: float,
        gesture: dict[str, Any],
        caster: CasterSnapshot,
    ) -> dict[str, Any]:
        families: dict[str, dict[str, float]] = defaultdict(dict)
        family_names = {
            "matter": "matter",
            "action": "actions",
            "movement": "movement",
            "geometry": "geometry",
            "target": "targets",
            "property": "properties",
            "timing": "timing",
            "logic": "logic",
        }
        for anchor in anchors:
            families[family_names[anchor.family]][anchor.id.lower()] = anchor.score

        geometry = families["geometry"]
        movement = families["movement"]
        properties = families["properties"]
        if gesture["straightness"] > 0.72:
            geometry["line"] = max(geometry.get("line", 0.0), gesture["straightness"])
        if gesture["closedness"] > 0.58 and gesture["curvature"] > 0.35:
            geometry["circle"] = max(geometry.get("circle", 0.0), gesture["closedness"])
            geometry["ring"] = max(geometry.get("ring", 0.0), gesture["closedness"] * 0.85)
        if gesture["curvature"] > 0.35:
            geometry["arc"] = max(geometry.get("arc", 0.0), gesture["curvature"])
        if gesture["radial_out"] > 0.18:
            movement["push"] = max(movement.get("push", 0.0), gesture["radial_out"])
            movement["spread"] = max(movement.get("spread", 0.0), gesture["radial_out"] * 0.8)
        if gesture["radial_in"] > 0.18:
            movement["pull"] = max(movement.get("pull", 0.0), gesture["radial_in"])
            movement["converge"] = max(movement.get("converge", 0.0), gesture["radial_in"] * 0.8)
        if gesture["speed"] > 0.58:
            properties["fast"] = max(properties.get("fast", 0.0), gesture["speed"])
        gesture_size = math.hypot(gesture["bounding_width"], gesture["bounding_height"])
        if gesture_size > 3.2:
            properties["large"] = max(properties.get("large", 0.0), min(1.0, gesture_size / 6.0))

        direction_data = gesture["dominant_direction"]
        direction_length = math.hypot(direction_data["x"], direction_data["y"])
        if gesture["total_length"] <= 0.01 or direction_length <= 0.01:
            direction = {"x": caster.facing.x, "y": caster.facing.y}
        else:
            direction = direction_data

        power = self.settings["base_power"] * (0.35 + coherence * 0.55)
        power += properties.get("strong", 0.0) * 0.38
        power -= properties.get("weak", 0.0) * 0.3
        power += gesture["gesture_energy"] * 0.2
        power = clamp(power, 0.12, 1.65)
        duration = 0.65 + families["timing"].get("duration", 0.0) * 2.5
        duration += properties.get("persistent", 0.0) * 3.0
        radius = clamp(max(0.65, gesture_size * 0.5), 0.65, 6.0)
        if properties.get("large", 0.0):
            radius *= 1.0 + properties["large"] * 0.6
        if properties.get("small", 0.0):
            radius *= 1.0 - properties["small"] * 0.45

        return {
            "coherence": coherence,
            "matter": families["matter"],
            "actions": families["actions"],
            "movement": movement,
            "geometry": geometry,
            "targets": families["targets"],
            "properties": properties,
            "timing": families["timing"],
            "logic": families["logic"],
            "spatial": {
                "origin": {"x": caster.position.x, "y": caster.position.y},
                "direction": direction,
                "radius": round(radius, 4),
                "range": round(clamp(max(4.0, gesture["displacement"] * 1.5), 4.0, 12.0), 4),
            },
            "power": round(power, 4),
            "duration": round(duration, 4),
        }

