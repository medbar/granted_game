from __future__ import annotations

import math
from typing import Any

from .models import GestureData, Vec2


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _unit(x: float, y: float) -> dict[str, float]:
    length = math.hypot(x, y)
    return {"x": x / length, "y": y / length} if length else {"x": 1.0, "y": 0.0}


class GestureResolver:
    def resolve(self, gesture: GestureData, caster: Vec2) -> dict[str, Any]:
        strokes = [[(point.world_x, point.world_y, point.t_ms) for point in stroke.points] for stroke in gesture.strokes]
        strokes = [stroke for stroke in strokes if stroke]
        points = [point for stroke in strokes for point in stroke]
        if not points:
            return self._empty_features()

        segment_lengths: list[float] = []
        speeds: list[float] = []
        signed_rotation = 0.0
        direction_changes = 0
        for stroke in strokes:
            previous_angle: float | None = None
            for index in range(1, len(stroke)):
                prior, current = stroke[index - 1], stroke[index]
                distance = _distance(prior[:2], current[:2])
                segment_lengths.append(distance)
                elapsed = max(1, current[2] - prior[2]) / 1000.0
                speeds.append(distance / elapsed)
                angle = math.atan2(current[1] - prior[1], current[0] - prior[0])
                if previous_angle is not None:
                    delta = (angle - previous_angle + math.pi) % (2.0 * math.pi) - math.pi
                    signed_rotation += delta
                    if abs(delta) > math.radians(35):
                        direction_changes += 1
                previous_angle = angle

        first, last = points[0], points[-1]
        total_length = sum(segment_lengths)
        displacement = _distance(first[:2], last[:2])
        duration_ms = max(1, max(point[2] for point in points) - min(point[2] for point in points))
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        width, height = max(xs) - min(xs), max(ys) - min(ys)
        diagonal = math.hypot(width, height)
        start_end_ratio = displacement / max(diagonal, 0.001)
        closedness = clamp(1.0 - start_end_ratio)
        straightness = clamp(displacement / max(total_length, 0.001))
        average_speed = total_length / (duration_ms / 1000.0)
        maximum_speed = max(speeds, default=0.0)
        area = self._shoelace([(point[0], point[1]) for point in points])
        covered_area = clamp(area / max(width * height, 0.001))
        direction = _unit(last[0] - first[0], last[1] - first[1])
        start_radius = math.hypot(first[0] - caster.x, first[1] - caster.y)
        end_radius = math.hypot(last[0] - caster.x, last[1] - caster.y)
        radial_delta = (end_radius - start_radius) / max(total_length, 0.001)
        curvature = clamp(abs(signed_rotation) / (2.0 * math.pi))
        speed_norm = clamp(average_speed / 8.0)
        size_norm = clamp(diagonal / 6.0)

        return {
            "duration": round(duration_ms / 1000.0, 4),
            "total_length": round(total_length, 4),
            "displacement": round(displacement, 4),
            "average_speed": round(average_speed, 4),
            "maximum_speed": round(maximum_speed, 4),
            "speed": round(speed_norm, 4),
            "straightness": round(straightness, 4),
            "curvature": round(curvature, 4),
            "closedness": round(closedness, 4),
            "signed_rotation": round(signed_rotation, 4),
            "covered_area": round(covered_area, 4),
            "bounding_width": round(width, 4),
            "bounding_height": round(height, 4),
            "distance_from_caster": round(start_radius, 4),
            "radial_out": round(clamp(radial_delta), 4),
            "radial_in": round(clamp(-radial_delta), 4),
            "dominant_direction": direction,
            "number_of_strokes": len(strokes),
            "number_of_direction_changes": direction_changes,
            "angular_velocity": round(signed_rotation / (duration_ms / 1000.0), 4),
            "gesture_energy": round(clamp(speed_norm * 0.65 + size_norm * 0.35), 4),
        }

    @staticmethod
    def _shoelace(points: list[tuple[float, float]]) -> float:
        if len(points) < 3:
            return 0.0
        return abs(
            sum(
                points[index][0] * points[(index + 1) % len(points)][1]
                - points[(index + 1) % len(points)][0] * points[index][1]
                for index in range(len(points))
            )
        ) / 2.0

    @staticmethod
    def _empty_features() -> dict[str, Any]:
        return {
            "duration": 0.0,
            "total_length": 0.0,
            "displacement": 0.0,
            "average_speed": 0.0,
            "maximum_speed": 0.0,
            "speed": 0.0,
            "straightness": 0.0,
            "curvature": 0.0,
            "closedness": 0.0,
            "signed_rotation": 0.0,
            "covered_area": 0.0,
            "bounding_width": 0.0,
            "bounding_height": 0.0,
            "distance_from_caster": 0.0,
            "radial_out": 0.0,
            "radial_in": 0.0,
            "dominant_direction": {"x": 1.0, "y": 0.0},
            "number_of_strokes": 0,
            "number_of_direction_changes": 0,
            "angular_velocity": 0.0,
            "gesture_energy": 0.0,
        }

