from __future__ import annotations

import os

import pytest
from app.models import (
    CastOptions,
    CastRequest,
    CasterSnapshot,
    MaterialSnapshot,
    Vec2,
    WorldObject,
    WorldSnapshot,
)


os.environ["GRANTED_SEMANTIC_BACKEND"] = "char_ngram"
os.environ["GRANTED_AGENT_MODE"] = "false"


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


def cast_request(
    text: str,
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
        world=world,
        options=CastOptions(debug=debug),
    )
