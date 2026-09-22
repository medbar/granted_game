## Change classification

- `deterministic_server`
- `agent_behavior`
- `player_visible`
- `observability`
- `tooling`

## Acceptance matrix

| Requirement / scenario | Authoritative oracle | Test or eval added first | Expected RED | Required GREEN gates |
|---|---|---|---|---|
| Data-driven level / client loads | JSON ids equal Godot object index and no authoritative room/wall arrays remain | `client/tests/level_contract_runner.gd`; `server/tests/test_level_definition.py` | level file/model absent; geometry only in `main.gd` | `server_tests`, `godot_smoke`, `godot_client_loop` |
| Monaco visual grammar / rendered | fixed 1280×720 PNG visibly contains room plan, labels, walls, cones, loot, exit | `client/tests/capture_level_runner.gd`; screenshot metadata test | no deterministic capture and current frame fails review | `godot_smoke`, `trajectory_review` |
| Complete JSON round-trip | canonical public session before/after equality including layout/mission | `server/tests/test_level_definition.py::test_start_level_round_trip_is_lossless` | GameSession has no layout/mission document | `server_tests` |
| Complete genie context | remote room/object and mission rules in CastRequest world JSON | `server/tests/test_level_definition.py::test_agent_world_contains_full_level_context` | WorldSnapshot has objects only | `server_tests` |
| Hot plugin toggle | registry revision changes; prompt/runtime surface loses and restores create calls | `server/tests/test_plugins.py` | registry/endpoints do not exist | `server_tests` |
| Frozen wishes client-in-loop | each of 40 cases passes against after Godot snapshot and produces artifacts | `client/tests/environment_wish_runner.gd` | current live runner covers only three wishes | `environment_evolution`, `monty_live_model`, `godot_client_loop`, `trajectory_review` |
| Screenshot binds to after JSON | PNG metadata and result share request/level version and are emitted after feedback | `server/tests/test_visual_artifacts.py`; capture runner | no screenshot/result bundle exists | `server_tests`, `godot_smoke`, `trajectory_review` |
| Start playthrough | final mission JSON is completed and final PNG shows completion | `server/evals/start_level_playthrough.json`; `server/tests/test_start_level.py` | no start level session/objective in server | `agent_level_live_model`, `godot_client_loop`, `trajectory_review` |
| All agent-level strategies | every one of the frozen 20 strategies completes `closed_door`, `three_enemies`, and `whispering_gate` in the authoritative `GameSession` | `server/tests/test_agent_evolution.py::test_every_frozen_agent_level_wish_has_a_deterministic_world_program` plus `run_agent_levels.py` | live generation 20260905T101419Z completed only 10/20 strategies; generic `двер` routing called `install_doors()` on an existing door and several code-gate plans stopped at speech/fallback | `server_tests`, `agent_level_live_model` |

## Baseline

- Client rooms, walls, palette, actors and objectives are hardcoded in `client/scripts/main.gd`; only nearby entities plus all walls are sent to the agent.
- Server `sandbox` has five simple objects and no rooms, doors, mission, palette or rendering data. `GameSession` serializes world/events but not the actual client level definition.
- `server/evals/agent_evolution_cases.json` has 40 cases, while `client/tests/live_cast_runner.gd` exercises only three.
- Monty capabilities are hardcoded methods; there is no ownership manifest, runtime registry or hot toggle API.
- There is no deterministic Godot screenshot runner or before/after visual artifact bundle.
- Godot is not currently available on PATH, so the initial visual gate is expected to fail until the official executable is provisioned.

## RED evidence

- `server/scripts/run_agent_levels.py --concurrency 1 --max-turns 4` — `10/20` strategies, report `server/runtime/evals/agent-levels-20260905T101419Z.json`. Eight normal-door paths and six magic-gate paths missed the authoritative completion postcondition; several ended in an honest visible failure after retries.
- The normal-door root cause is captured in its trajectory: the broad fast route compiled an existing-door wish to `install_doors()`, which failed because that sandbox has no wall entities. The first model repair then tried `collect('key_01')`, which correctly failed because a hidden key is not loot.
- The deterministic 60-case regression is added before changing routing or world semantics. Its first run is expected to fail until every frozen wish produces a valid capability program and completes its actual level.
- Observer review of run `agent-levels-20260905T102223Z` exposed a false-green hidden by the level runner: `door_banish_and_intimidation/whispering_gate` reached `GameSession.status=completed` during attempt 1, but the agent retried and finally returned the fallback `impossible` speech. A focused regression now requires the authoritative completed oracle to stop retries and control the player-visible conclusion.

## GREEN evidence

- Shared level `monaco-start-v1`: 10 rooms, 32 walls, 11 real doors and 15 initial entities. `level_contract_runner.gd` prints `LEVEL_CONTRACT_OK`; `capture_level_runner.gd` produced `client/test-artifacts/monaco_start/world.json` and `level.png`.
- Deterministic server gate: 227 pytest cases passed, including all 40 environment cases, all 60 frozen agent-level wish/level pairs, plugin prompt/runtime hot toggles, full level round-trip, visual artifact serving and the false-green conclusion regression.
- Environment evolution generation 7: 40/40, report `server/runtime/evolution/generation-7.json`.
- Live Monty: 10/10, report `server/runtime/evals/monty-20260905T102404Z.json`.
- Strict live agent levels: 20/20 strategies, 60/60 level conclusions `completed`, 20 distinct signatures, report `server/runtime/evals/agent-levels-20260905T103415Z.json`. The runner now requires both authoritative session completion and player-visible `completed`.
- Godot client-in-loop: `CLIENT_SMOKE_OK`, `LEVEL_CONTRACT_OK`, `LIVE_WISH_OK`, and `ENVIRONMENT_EVAL_OK: 40/40`. Each environment case has paired `before.json`, `after.json`, `result.json`, and `after.png` under `client/test-artifacts/environment/`.
- Start playthrough: `START_PLAYTHROUGH_OK: 3/3 wishes, mission completed`; `client/test-artifacts/start_level_playthrough/result.json` records all three required loot ids and a completed extraction, paired with `final.json` and `final.png`.
- Observer manual review at `http://127.0.0.1:8000/observer`: refreshed run contained 141 wishes, zero current errors, TTFA SLO marked met, 40 artifact cards plus the playthrough bundle, and six hot-toggle plugin cards exposing 27 trusted capabilities.
- Representative PNG review: `create_four_walls` visibly encloses the player; `equip_dress` visibly changes the player outfit; `transform_enemy_rock` adds the transformed guard as a third rock; `darken_world` lowers global illumination; final playthrough removes loot and displays `ДЕЛО СДЕЛАНО` with the extraction open.
- `server/scripts/quality_policy.py --root .` prints `Granted quality policy: PASS`. Official OpenSpec CLI 1.12.0 validates `build-monaco-start-level --strict` as valid.

## Trajectory review

- [x] The requested effect is visible in the authoritative game world.
- [x] The oracle checks postconditions, not generated code, action names, HTTP status, or speech.
- [x] Retry and terminal failure are honest and visible to the player.
- [x] No unrelated fallback action can make this case pass.
- [x] The final real trajectory/report path is recorded above.
