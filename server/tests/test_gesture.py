import math

from app.gesture import GestureResolver
from app.models import Vec2
from conftest import circle_gesture, stroke


def test_horizontal_line() -> None:
    features = GestureResolver().resolve(stroke([(0, 0), (2, 0), (4, 0)], 400), Vec2())
    assert features["straightness"] > 0.98
    assert features["dominant_direction"]["x"] > 0.98
    assert abs(features["dominant_direction"]["y"]) < 0.02


def test_vertical_line() -> None:
    features = GestureResolver().resolve(stroke([(0, 0), (0, -2), (0, -4)], 400), Vec2())
    assert features["straightness"] > 0.98
    assert features["dominant_direction"]["y"] < -0.98


def test_circle_is_closed_and_curved() -> None:
    features = GestureResolver().resolve(circle_gesture((0, 0), 2.0), Vec2())
    assert features["closedness"] > 0.9
    assert features["curvature"] > 0.8
    assert abs(features["signed_rotation"]) > math.pi


def test_outward_and_inward_motion() -> None:
    outward = GestureResolver().resolve(stroke([(0.1, 0), (2, 0), (4, 0)]), Vec2())
    inward = GestureResolver().resolve(stroke([(4, 0), (2, 0), (0.1, 0)]), Vec2())
    assert outward["radial_out"] > 0.8
    assert inward["radial_in"] > 0.8


def test_fast_jab_has_more_energy_than_slow_arc() -> None:
    jab = GestureResolver().resolve(stroke([(0, 0), (2, 0), (4, 0)], 120), Vec2())
    arc = GestureResolver().resolve(stroke([(0, 0), (1, 1), (2, 1.5), (3, 1)], 1500), Vec2())
    assert jab["speed"] > arc["speed"]
    assert jab["gesture_energy"] > arc["gesture_energy"]

