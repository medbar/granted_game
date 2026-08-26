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
        gesture_mapping = self.settings["gesture_mapping"]
        if gesture["straightness"] > gesture_mapping["line_straightness"]:
            geometry["line"] = max(geometry.get("line", 0.0), gesture["straightness"])
        if gesture["closedness"] > gesture_mapping["circle_closedness"] and gesture["curvature"] > gesture_mapping["curve_minimum"]:
            geometry["circle"] = max(geometry.get("circle", 0.0), gesture["closedness"])
            geometry["ring"] = max(geometry.get("ring", 0.0), gesture["closedness"] * gesture_mapping["ring_multiplier"])
        if gesture["curvature"] > gesture_mapping["curve_minimum"]:
            geometry["arc"] = max(geometry.get("arc", 0.0), gesture["curvature"])
        if gesture["radial_out"] > gesture_mapping["radial_minimum"]:
            movement["push"] = max(movement.get("push", 0.0), gesture["radial_out"])
            movement["spread"] = max(movement.get("spread", 0.0), gesture["radial_out"] * gesture_mapping["spread_multiplier"])
        if gesture["radial_in"] > gesture_mapping["radial_minimum"]:
            movement["pull"] = max(movement.get("pull", 0.0), gesture["radial_in"])
            movement["converge"] = max(movement.get("converge", 0.0), gesture["radial_in"] * gesture_mapping["spread_multiplier"])
        if gesture["speed"] > gesture_mapping["fast_speed"]:
            properties["fast"] = max(properties.get("fast", 0.0), gesture["speed"])
        gesture_size = math.hypot(gesture["bounding_width"], gesture["bounding_height"])
        if gesture_size > gesture_mapping["large_extent"]:
            properties["large"] = max(properties.get("large", 0.0), min(1.0, gesture_size / gesture_mapping["large_normalizer"]))

        direction_data = gesture["dominant_direction"]
        direction_length = math.hypot(direction_data["x"], direction_data["y"])
        if gesture["total_length"] <= 0.01 or direction_length <= 0.01:
            direction = {"x": caster.facing.x, "y": caster.facing.y}
        else:
            direction = direction_data

        power_settings = self.settings["power"]
        power = self.settings["base_power"] * (
            power_settings["coherence_base"] + coherence * power_settings["coherence_scale"]
        )
        power += properties.get("strong", 0.0) * power_settings["strong_bonus"]
        power -= properties.get("weak", 0.0) * power_settings["weak_penalty"]
        power += gesture["gesture_energy"] * power_settings["gesture_energy_bonus"]
        power = clamp(power, power_settings["minimum"], power_settings["maximum"])
        duration_settings = self.settings["duration"]
        duration = duration_settings["base"] + families["timing"].get("duration", 0.0) * duration_settings["semantic_scale"]
        duration += properties.get("persistent", 0.0) * duration_settings["persistent_scale"]
        spatial_settings = self.settings["spatial"]
        radius = clamp(
            max(spatial_settings["minimum_radius"], gesture_size * spatial_settings["gesture_radius_scale"]),
            spatial_settings["minimum_radius"],
            spatial_settings["maximum_radius"],
        )
        if properties.get("large", 0.0):
            radius *= 1.0 + properties["large"] * spatial_settings["large_radius_bonus"]
        if properties.get("small", 0.0):
            radius *= 1.0 - properties["small"] * spatial_settings["small_radius_penalty"]

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
                        max(spatial_settings["minimum_range"], gesture["displacement"] * spatial_settings["gesture_range_scale"]),
                        spatial_settings["minimum_range"],
                        spatial_settings["maximum_range"],
                    ),
                    4,
                ),
            },
            "power": round(power, 4),
            "duration": round(duration, 4),
        }
