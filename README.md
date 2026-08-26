# Granted: A Language of Magic

Playable v0 prototype of a top-down arena game where a spell is compiled from:

`natural-language text + staff gesture + current world state → universal world actions`

There are no `FireballSpell` or `IceWallSpell` classes. The backend activates hidden semantic anchors, merges them with continuous gesture geometry, selects targets from a world snapshot, applies fixed material rules, and returns a generic `SpellPlan` for Godot to execute.

## What is implemented

- Real-time top-down arena with a mage, six chasing/attacking gnomes, walls, rocks, crates, a tree, a metal conductor, and a water pool.
- `SPACE` enters cast mode at `Engine.time_scale = 0.35`; the world never pauses.
- Unicode/Cyrillic spell input, up to 300 characters, with `Enter` to cast and `Esc` to cancel.
- Multi-stroke LMB gesture capture, a visible magical trail, and request downsampling capped at 256 points.
- Deterministic FastAPI `/cast` pipeline with exactly 100 configurable hidden anchors.
- Continuous gesture features: duration, length, displacement, speed, straightness, curvature, closedness, rotation, area, radial movement, direction, strokes, direction changes, angular velocity, and energy.
- Universal target resolution, material rules, world actions, persistent-effect descriptions, and ten visual primitives.
- Water ↔ ice, water → steam, ignition/burning, wet electrical conduction, mass-aware force, heat/cold damage, slow, harm, and healing.
- F3 developer view for anchors, gesture features, `SpellIntent`, selected targets, fired world rules, and REST latency.
- Backend failure recovery: time returns to normal and the cast visibly fizzles.
- 28 automated semantic, gesture, world-rule, golden-scenario, and API tests.

## Requirements

- [Godot 4.7.2 Standard](https://godotengine.org/download/archive/4.7.2-stable/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.11+ (uv can install/manage it)

## Run

Open two terminals from this folder.

Backend:

```powershell
./run_backend.ps1
```

Client:

```powershell
./run_game.ps1
```

Alternatively, import `client/project.godot` in the Godot Project Manager and press F6/F5 after the backend reports that it is listening on `127.0.0.1:8000`.

## Controls

| Input | Action |
|---|---|
| `WASD` | Move |
| Mouse | Aim the staff |
| `Space` | Start casting |
| Hold `LMB` and move | Draw one or more gesture strokes |
| `Enter` | Compile and cast non-empty text |
| `Esc` | Cancel cast |
| `F3` | Toggle developer magic view |
| `R` | Reset the sandbox |

Useful first experiments:

- `назад` + a fast forward jab
- `сильно отбрось всех врагов от меня` + an outward sweep
- `заморозь воду` + a circle over the pool
- `подожги дерево`
- `электричество по воде`
- `маленькое солнце` + a small circle and forward stroke
- `создай огонь под водой`

## Test the backend

```powershell
cd server
uv sync
uv run pytest
```

Health and interactive API documentation are available at:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/debug/anchors`
- `http://127.0.0.1:8000/debug/config`

## Where to tune the magic

| Concern | File |
|---|---|
| 100 concepts, synonyms, thresholds, gameplay mappings | `server/config/anchors.yaml` |
| Cast slow-motion, influence weights, top-K, power, semantic model | `server/config/spell_settings.yaml` |
| Mass, conductivity, flammability, hardness | `server/config/materials.yaml` |
| Phase, ignition, conduction, force thresholds | `server/config/reactions.yaml` |
| Geometry → primitive and appearance colors | `server/config/visual_mapping.yaml` |
| Client cast scale and backend URL | `client/scripts/main.gd` |

The `.yaml` files use JSON-compatible YAML so the backend can load them with Python's standard library and keep startup lean.

## Architecture

```text
Godot world snapshot
        │
text ── SemanticResolver ── 100 continuous anchor activations
gesture ─ GestureResolver ── geometry, motion, scale, direction
        │
        ▼
SpellIntentBuilder
        │
        ├── TargetResolver
        ├── WorldResolver ── universal material/reaction rules
        └── VisualResolver ── generic visual descriptors
        │
        ▼
SpellPlan → Godot world actions + runtime visuals
```

The default semantic model is a deterministic multilingual character n-gram embedding over rich anchor descriptions. It starts instantly, handles Russian inflection and configured synonyms, and is reproducible. `spell_settings.yaml` also records the intended neural upgrade (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`); the REST contract remains unchanged when that resolver is swapped in.

## Scope intentionally excluded

No campaign, progression, inventory, mana economy, procedural generation, multiplayer, production art/audio, voice input, accounts, or generative LLM game master. The prototype is focused on whether free formulation under real-time pressure produces understandable, discoverable magical laws.
