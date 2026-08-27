# Granted: Your Wish, My Magic

Playable top-down prototype where an adventurer asks their floating genie for any wish in natural language. The player is not a mage and never casts a spell themselves:

`free-form wish text + genie origin + current world state → genie magic → universal world actions`

The genie is a visible companion that follows the player, listens in slow motion, and becomes the origin of every magical effect. There are no canned wish or spell classes: the backend activates hidden semantic anchors from text, selects targets from the live world, applies fixed material rules, and returns a generic plan for the genie to enact.

## What is implemented

- Real-time top-down arena with an adventurer, their hovering genie, six chasing/attacking gnomes, walls, rocks, crates, a tree, a metal conductor, and a water pool.
- Separate physical combat: `LMB` swings the adventurer's sword through a short frontal arc, damages and knocks back enemies, and can kill them after repeated hits.
- `SPACE` asks the genie for a wish at `Engine.time_scale = 0.35`; the world never pauses.
- Unicode/Cyrillic wish input, up to 300 characters, with `Enter` to ask and `Esc` to reconsider.
- Wishes are text-only: mouse motion, sword state, and attack data never enter the `/wish` request; the sword is disabled while the wish input is open.
- Deterministic FastAPI `/wish` pipeline with exactly 100 configurable hidden anchors; `/cast` remains as a compatibility alias.
- Geometry, scale, movement, and targets are derived from words such as `стена`, `кольцо`, `всех`, and `передо мной`, plus the genie's position/facing and the world snapshot.
- Universal target resolution, material rules, world actions, persistent-effect descriptions, and ten visual primitives.
- Water ↔ ice, water → steam, ignition/burning, wet electrical conduction, mass-aware force, heat/cold damage, slow, harm, and healing.
- Lift/levitation, deep freeze, poison, sharp-force and crush/material interactions, water extinguishing, and electrical propagation through a pool.
- Gameplay-capable projectile, beam, wall, ring, and field entities that continue resolving contacts after `/wish`.
- F3 genie-wish view for anchors, direction features, intent, selected targets, fired world rules, and REST latency.
- Backend failure recovery: time returns to normal and the genie visibly fails near its own position.
- 42 automated semantic, text-intent, world-rule, service-log, golden-scenario, and API tests.

## Requirements

- [Godot 4.7.2 Standard](https://godotengine.org/download/archive/4.7.2-stable/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.11+ (uv can install/manage it)

## Run

The simplest launch starts both processes and shuts the backend down when the game closes:

```powershell
./run_all.ps1 -GodotPath "C:\path\to\Godot_v4.7.2-stable_win64.exe"
```

Or open two terminals from this folder.

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
| Mouse | Aim the adventurer and sword |
| `LMB` | Swing the sword |
| `Space` | Ask the genie for a wish |
| `Enter` | Ask the genie to fulfill the wish |
| `Esc` | Reconsider the wish |
| `F3` | Toggle developer wish interpretation |
| `R` | Reset the sandbox |

Useful first wishes:

- `назад`
- `сильно отбрось всех врагов от меня`
- `заморозь воду`
- `подожги дерево`
- `электричество по воде`
- `маленькое солнце`
- `создай огонь под водой`

## Test the backend

```powershell
cd server
uv sync
uv run pytest
```

To run the backend suite, isolated Godot gameplay smoke test, and live Godot↔FastAPI cast scenarios together:

```powershell
./verify.ps1 -GodotPath "C:\path\to\Godot_v4.7.2-stable_win64_console.exe"
```

If `uv` is not on `PATH`, the PowerShell scripts also accept `-UvPath "C:\path\to\uv.exe"`.
On an already-synchronized checkout, `verify.ps1 -SkipSync` reuses `server/.venv`.

Health and interactive API documentation are available at:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/debug/anchors`
- `http://127.0.0.1:8000/debug/config`

## Where to tune wish interpretation

| Concern | File |
|---|---|
| 100 concepts, synonyms, thresholds, gameplay mappings | `server/config/anchors.yaml` |
| Wish slow-motion, influence weights, top-K, power, semantic model | `server/config/spell_settings.yaml` |
| Mass, conductivity, flammability, hardness | `server/config/materials.yaml` |
| Phase, ignition, conduction, force thresholds | `server/config/reactions.yaml` |
| Geometry → primitive and appearance colors | `server/config/visual_mapping.yaml` |
| Client backend URL, wish-time scale, snapshot radius, timeout | `client/config/gameplay.json` |

The `.yaml` files use JSON-compatible YAML so the backend can load them with Python's standard library and keep startup lean.

## Architecture

```text
Godot world snapshot + genie origin
        │
wish text ── SemanticResolver ── 100 continuous anchor activations
genie position/facing ────────── text-only direction and origin
        │
        ▼
Wish interpretation (compatible SpellIntentBuilder)
        │
        ├── TargetResolver
        ├── WorldResolver ── universal material/reaction rules
        └── VisualResolver ── generic visual descriptors
        │
        ▼
Plan → genie-origin world actions + runtime visuals
```

The default semantic model is a deterministic multilingual character n-gram embedding over rich anchor descriptions. It starts instantly, handles Russian inflection and configured synonyms, and is reproducible. The resolver is configurable: set `semantic_backend` to `sentence_transformer`, run `uv sync --extra embeddings`, and it loads `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` plus cached anchor embeddings without changing the REST contract.

## Scope intentionally excluded

No campaign, progression, inventory, mana economy, procedural generation, multiplayer, production art/audio, voice input, accounts, or generative LLM game master. The prototype is focused on whether asking a persistent genie for free-form wishes under real-time pressure produces understandable, discoverable laws and entertaining unintended consequences.
