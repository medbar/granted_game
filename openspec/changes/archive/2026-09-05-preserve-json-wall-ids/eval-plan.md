## Change classification

- `player_visible`: wall id определяет видимый collision/render target действия джина.
- `deterministic_server`: shared contract должен оставаться эквивалентным серверной модели.

## Acceptance matrix

| Requirement / scenario | Authoritative oracle | Test or eval added first | Expected RED | Required GREEN gates |
|---|---|---|---|---|
| Wall id comes from canonical JSON | `arena_walls`, `object_index`, snapshot и draw lookup используют `walls[*].id` | `client/tests/level_contract_runner.gd` source/contract assertion | runner обнаруживает производное выражение `wall_%02d` и отсутствие списка JSON ids | `server_tests`, `godot_smoke`, `godot_client_loop`, `trajectory_review` |

## RED evidence

Post-archive source audit found `var wall_id := "wall_%02d" % (wall_index + 1)` in both construction and drawing. The current sequential fixture masks this drift, so the new contract assertion must fail before implementation.

## GREEN evidence

- RED: `level_contract_runner.gd` failed with `wall ids are never derived from array order` and `wall ids are read from canonical JSON` while construction/draw used `wall_%02d`.
- GREEN: `WALL_IDS` is populated from each `wall_data.get("id")`; construction, `arena_walls`, `object_index`, snapshots and drawing reuse that exact id. `LEVEL_CONTRACT_OK` verifies JSON wall ids equal runtime snapshot ids.
- Regression gates: `CLIENT_SMOKE_OK`, `LIVE_WISH_OK`, `ENVIRONMENT_EVAL_OK: 40/40`, and `START_PLAYTHROUGH_OK: 3/3 wishes, mission completed` on the updated client.
- Fresh `create_four_walls/after.png` visibly contains the spawned wall enclosure and the final playthrough PNG still shows the full room plan, removed loot, open extraction and `ДЕЛО СДЕЛАНО`.
- Server tests remain 227/227; quality policy and strict OpenSpec validation are required immediately before archive.

## Trajectory review

- [x] Wall snapshots retain the exact JSON ids.
- [x] Existing 40-case JSON/PNG artifacts remain green.
- [x] No generated action name or HTTP response substitutes for the world target check.
