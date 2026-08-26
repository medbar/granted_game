from __future__ import annotations

import math

import pytest

from app.models import (
    CastOptions,
    CastRequest,
    CasterSnapshot,
    GestureData,
    GesturePoint,
    GestureStroke,
    MaterialSnapshot,
    Vec2,
    WorldObject,
    WorldSnapshot,
)


@pytest.fixture
def world() -> WorldSnapshot:
    return WorldSnapshot(
        objects=[
            WorldObject(
                id="dwarf_01",
                kind="creature",
                tags=["living", "enemy", "dwarf", "organic"],
                position=Vec2(x=4.0, y=0.0),
                health=72,
                material=MaterialSnapshot(
                    name="organic", mass=1.0, flammability=0.35, conductivity=0.2
                ),
            ),
            WorldObject(
                id="water_pool_01",
                kind="terrain",
                tags=["water", "surface", "wet"],
                position=Vec2(x=3.0, y=2.0),
                radius=2.2,
                material=MaterialSnapshot(
                    name="water", mass=1.0, temperature=0.5, wetness=1.0, conductivity=0.65
                ),
            ),
            WorldObject(
                id="tree_01",
                kind="prop",
                tags=["plant", "wood", "inanimate"],
                position=Vec2(x=5.0, y=1.0),
                material=MaterialSnapshot(name="wood", mass=1.2, flammability=0.9),
            ),
            WorldObject(
                id="rock_01",
                kind="prop",
                tags=["stone", "rock", "inanimate"],
                position=Vec2(x=2.0, y=-1.0),
                material=MaterialSnapshot(name="stone", mass=2.5, hardness=0.9),
            ),
        ]
    )


def stroke(points: list[tuple[float, float]], duration_ms: int = 500) -> GestureData:
    denominator = max(1, len(points) - 1)
    return GestureData(
        strokes=[
            GestureStroke(
                points=[
                    GesturePoint(
                        t_ms=int(index * duration_ms / denominator),
                        screen_x=0.5 + x / 20,
                        screen_y=0.5 + y / 20,
                        world_x=x,
                        world_y=y,
                    )
                    for index, (x, y) in enumerate(points)
                ]
            )
        ]
    )


def line_gesture() -> GestureData:
    return stroke([(0.2, 0.0), (1.5, 0.0), (3.0, 0.0)], 260)


def circle_gesture(center: tuple[float, float] = (3.0, 2.0), radius: float = 1.4) -> GestureData:
    points = [
        (
            center[0] + math.cos(index * math.tau / 16) * radius,
            center[1] + math.sin(index * math.tau / 16) * radius,
        )
        for index in range(17)
    ]
    return stroke(points, 900)


def cast_request(
    text: str,
    gesture: GestureData,
    world: WorldSnapshot,
    debug: bool = True,
) -> CastRequest:
    return CastRequest(
        request_id="test-cast",
        spell_text=text,
        seed=42,
        caster=CasterSnapshot(
            id="player",
            position=Vec2(x=0.0, y=0.0),
            facing=Vec2(x=1.0, y=0.0),
        ),
        gesture=gesture,
        world=world,
        options=CastOptions(debug=debug),
    )

