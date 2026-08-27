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
        direction_length = math.hypot(caster.facing.x, caster.facing.y)
        direction = (
            {"x": caster.facing.x / direction_length, "y": caster.facing.y / direction_length}
            if direction_length > 0.001
            else {"x": 1.0, "y": 0.0}
        )

        power_settings = self.settings["power"]
        power = self.settings["base_power"] * (
            power_settings["coherence_base"] + coherence * power_settings["coherence_scale"]
        )
        power += properties.get("strong", 0.0) * power_settings["strong_bonus"]
        power -= properties.get("weak", 0.0) * power_settings["weak_penalty"]
        power = clamp(power, power_settings["minimum"], power_settings["maximum"])
        duration_settings = self.settings["duration"]
        duration = duration_settings["base"] + families["timing"].get("duration", 0.0) * duration_settings["semantic_scale"]
        duration += properties.get("persistent", 0.0) * duration_settings["persistent_scale"]
        spatial_settings = self.settings["spatial"]
        radius = float(spatial_settings["base_radius"])
        if properties.get("large", 0.0):
            radius *= 1.0 + properties["large"] * spatial_settings["large_radius_bonus"]
        if properties.get("small", 0.0):
            radius *= 1.0 - properties["small"] * spatial_settings["small_radius_penalty"]
        radius = clamp(radius, spatial_settings["minimum_radius"], spatial_settings["maximum_radius"])
        effect_range = float(spatial_settings["base_range"])
        if properties.get("large", 0.0):
            effect_range *= 1.0 + properties["large"] * spatial_settings["large_range_bonus"]
        if properties.get("small", 0.0):
            effect_range *= 1.0 - properties["small"] * spatial_settings["small_range_penalty"]

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
                "range": round(
                    clamp(
                        effect_range,
                        spatial_settings["minimum_range"],
                        spatial_settings["maximum_range"],
                    ),
                    4,
                ),
            },
            "power": round(power, 4),
            "duration": round(duration, 4),
        }
