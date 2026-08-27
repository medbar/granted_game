# v0.2 genie-wish specification compliance audit

This audit maps the mandatory v0 requirements in `spec.txt` to executable or source evidence. It intentionally does not claim campaign, production art/audio, progression, multiplayer, or the other features excluded by section 91.

## Client Definition of Done (§95)

| Requirement | Evidence |
|---|---|
| Godot arena starts | Godot 4.7.2 loads `client/scenes/main.tscn`; `client/tests/smoke_runner.gd` instantiates it. |
| WASD movement and top-down camera | `player.gd`; smoke runner injects `D` and verifies displacement and a `Camera2D` child. |
| Player is not a mage; visible genie companion | `player.gd` renders an adventurer without a staff; `genie.gd` follows and hovers beside the player; smoke runner verifies the relationship. |
| At least five moving, pursuing gnomes | Six `dwarf.gd` actors; smoke runner verifies count and movement during cast; live scenarios place and target multiple gnomes. |
| Gnome attacks damage the player | Smoke runner places a gnome in attack range and verifies health loss. |
| Water, physical objects, flammable object | Arena contains the pool, two rocks, two crates, a tree, and a metal box; smoke runner checks them. |
| Slow-motion wish request without pause | `begin_wish()` enters the compatible slow-time controller at `0.35`; smoke runner verifies continued enemy movement. |
| Unicode/Cyrillic wish input | `LineEdit` plus live JSON contract; smoke runner verifies `заморозь воду` survives exactly as `wish_text`. |
| Optional direction capture and rendering | Multi-stroke timestamped points in `main.gd`; `_draw()` renders golden/teal guidance strokes. |
| Enter sends `/wish` | Wish input submission posts to `/wish`; live runner performs real wishes. |
| Genie is the effect origin | Client request uses the genie's position and facing; smoke runner verifies the serialized origin. |
| Response execution | Live runner proves water→ice, water→steam, and multi-enemy push from real backend responses. |
| Ten universal VFX primitives | `magic_effect.gd`; smoke runner instantiates BURST, PROJECTILE, BEAM, LINE, RING, FIELD, CLOUD, TRAIL, TETHER, SURFACE_OVERLAY. |
| Persistent/runtime effects | `runtime_effect.gd` executes projectile, beam, wall, ring, and field contact payloads after `/wish`. |
| Time recovery and backend failure | Smoke runner verifies normal time after success and deliberate error/fizzle. |
| F3 debug information | Smoke runner toggles F3; panel shows text, anchors, gesture, intent, targets, rules, latency. |

## Backend Definition of Done (§96)

| Requirement | Evidence |
|---|---|
| Separate FastAPI process, `/health`, formal `/wish` schema | `app/main.py`, Pydantic alias validation, API tests, live Uvicorn/Godot runner; `/cast` remains compatible. |
| Configurable embedding model and 100 cached anchors | `SemanticResolver`; cached character n-gram embeddings by default, configurable SentenceTransformer backend; tests verify count/cache/backend. |
| Russian normalization, similarity, activation, top-K | `semantic.py`; golden phrase and synonym tests. |
| Gesture features | `gesture.py`; horizontal/vertical line, circle, inward/outward, jab/arc tests. |
| SpellIntent and WorldSnapshot | `intent.py`, Pydantic world models; API and golden tests. |
| Target resolution | `targeting.py`; tests cover material, enemy, self target, self as origin, nearest and multiple targets. |
| Material/world reactions | `world.py`; tests cover heat/cold phases, steam force, burning/extinguishing, conduction/propagation, mass force, lift, sharp force, crush, poison, harm, heal. |
| Universal SpellPlan and visuals | Pydantic `SpellPlan`, `WorldAction`, and `VisualDescriptor`; no spell ID field. |
| Debug output and structured logs | Debug model/UI plus JSONL service-log test. |
| Determinism | Same request/seed equality test with debug timing disabled; pipeline uses no uncontrolled randomness. |
| Validation and unknown text | API 422 test; gibberish succeeds with low coherence and a weak visual effect. |
| Unit and integration tests | Backend pytest suite plus headless client and live engine/server runners. |

## Concept requirements (§97)

| Requirement | Evidence |
|---|---|
| Same text + different gestures | Golden test proves `огонь` yields different line/circle primitives. |
| Synonyms converge | `толкни`, `отбрось`, `отшвырни`, `пни магией`, `заставь отлететь` all activate PUSH. |
| Precision changes targets, not merely length/power | Test compares `толкни` with `толкни всех врагов передо мной`; the precise phrase selects multiple enemies. |
| Environment matters | Golden/live tests distinguish fire in air from fire in water. |
| Combined physics | Tests prove water+cold→ice, water+heat→steam, and wet electricity amplification/propagation. |
| No canned spell catalog | Repository contains no Fireball/IceWall/Push spell classes; plans consist of continuous intent, actions, and visual descriptors. |

## Reproducible verification

Run all gates with:

```powershell
./verify.ps1 -GodotPath "C:\path\to\Godot_v4.7.2-stable_win64_console.exe"
```

Last audited on 2026-08-27 with Godot 4.7.2:

- backend: 46 tests passed;
- client headless smoke: `CLIENT_SMOKE_OK`;
- live engine/server scenarios: `LIVE_WISH_OK`;
- warmed 30-cast benchmark on the bundled desktop Python: median 112.30 ms, p95 124.71 ms, maximum 130.29 ms;
- local Git repository has a clean, reviewable history.

The only headless-host diagnostic was failure to read the restricted sandbox's Windows root certificate store; the game uses plain localhost HTTP and all client/server requests completed successfully.
