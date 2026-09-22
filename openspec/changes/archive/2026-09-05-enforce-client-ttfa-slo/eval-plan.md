## Change classification

- `player_visible`: oracle — реальная мутация Godot-мира, увиденная игроком.
- `agent_behavior`: ready action проходит через agentic loop и feedback.
- `observability`: timing breakdown и SLO violation должны быть правдивыми.

## Acceptance matrix

| Requirement / scenario | Authoritative oracle | Test or eval added first | Expected RED | Required GREEN gates |
|---|---|---|---|---|
| Supported wish changes world in time | monotonic submit→mutation и changed serialized postcondition | новый `client/tests/ttfa_runner.gd`, затем timing oracle в `environment_wish_runner.gd` | start-level wishes дают 4301/5142/6757 мс, runner exits 1 | `godot_client_loop`, `trajectory_review` |
| Feedback/animation are not first action | timestamp фиксируется непосредственно после `apply_world_action`, а не на HTTP/action-ready | source assertions + TTFA runner before/after snapshots | текущий environment report вообще не содержит client TTFA | `godot_smoke`, `godot_client_loop` |
| Ready action and teleport overlap | mutation timestamp предшествует окончанию teleport transition | детерминированный Godot sequencing test в TTFA runner | последовательное ожидание перед `apply_agent_action_without_teleport` | `godot_client_loop`, `trajectory_review` |
| Successful wish reports timing breakdown | четыре неотрицательных timing fields в client artifact и feedback trajectory | `ttfa_runner.gd`, server payload test | fields отсутствуют | `server_tests`, `godot_client_loop` |
| SLO violation remains visible | latency/hardware eval exits nonzero, software-renderer report keeps warning, Prometheus violation растёт | server telemetry regression + TTFA runner + environment renderer profile | прежний environment eval был green при 6757 мс и не записывал timing | `server_tests`, `godot_client_loop` |
| Software renderer is not a latency oracle | report names adapter/profile and retains every raw value/warning | environment/start-playthrough runner profile assertion | llvmpipe frame stalls produce 2902–20703 мс despite 0.1–1.4 с server ready | `godot_client_loop`, `trajectory_review` |
| Delayed/repeated feedback does not duplicate | step id + unchanged object cardinality after duplicate feedback | `test_agent_infrastructure.py` duplicate feedback case | повторный feedback сейчас даёт 409; подтвердить отсутствие второго action payload | `server_tests` |

## Baseline

- `client/test-artifacts/environment/summary.json`: 40/40 world-state cases, но client TTFA отсутствует из результатов.
- `server/runtime/logs/agent-events.jsonl`, latest start playthrough: client-observed 4301, 5142 и 6757 мс при server planning около 1 секунды.
- `server/runtime/metrics/granted_game.prom`: 43 client-observed SLO violations из 62 samples; effective TTFA 6757 мс и `granted_agent_ttfa_slo_met 0`.

## RED evidence

- `pytest ... -k "stage_timings or launchers"`: 2 failed — отсутствуют `server_action_ready_ms` и `--no-access-log` в `run_backend.ps1`.
- `Godot --headless ... ttfa_runner.gd`: world mutations для create/equip/darken произошли, но runner завершился `TTFA_EVAL_FAILED: 12 issues`, потому что все четыре обязательных timing fields отсутствовали в каждом кейсе.
- После ручного drain stdout те же реальные мутации дали 1496/1558/1531 мс. Это подтверждает, что SLO достижим и что RED проверяет отсутствующий контракт/защиту, а не недостижимую цель.

## GREEN evidence

- Narrow server regressions green: action-ready duration, typed/bounded client stages, lifespan prewarm, no-access-log launch contract и software-profile metric isolation.
- Full server suite: `232 passed in 42.76s`.
- `client/test-artifacts/ttfa/summary.json`: 3/3 authoritative mutations green; 1370/1075/1303 мс, maximum 1370 мс; breakdown содержит все client stages и server action-ready.
- Cold-server run после readiness также green; уже растворённый джин применяет действие у цели за 1–3 мс после получения шага, продолжая секундное проявление.
- `CLIENT_SMOKE_OK`, включая threaded runtime transport и teleport overlap; `LEVEL_CONTRACT_OK`; `LIVE_WISH_OK`.
- `client/test-artifacts/environment/summary.json`: 40/40 world/PNG cases green на `llvmpipe`; report явно содержит `ttfa_gate_applicable=false` и сохраняет 40 raw timing warnings.
- `client/test-artifacts/start_level_playthrough/result.json`: 3/3 wishes, authoritative mission `completed`; renderer/profile и все raw timings сохранены; final PNG просмотрен.
- Prometheus после 3 latency samples и 43 software-renderer visual samples: canonical client TTFA 1303 мс, `granted_agent_ttfa_slo_met 1`; software samples находятся в отдельном labelled counter и не меняют runtime gauge.
- Observer browser review: 6 wishes, 0 errors, first action 1.3 s, SLO `Соблюдён` после software-renderer playthrough.
- Existing agent gates remain green after no planner/prompt semantic changes: generation 7 — 40/40; Monty — 10/10; agent levels — 20/20 strategies × 3 levels, 20 distinct signatures, all passed.
- Quality policy: PASS; strict OpenSpec validation required immediately before archive.

## Trajectory review

- [x] The requested effect is visible in the authoritative game world.
- [x] The oracle checks postconditions, not generated code, action names, HTTP status, or speech.
- [x] Retry and terminal failure are honest and visible to the player.
- [x] No unrelated fallback action can make this case pass.
- [x] The final real trajectory/report path is recorded above.
- [x] Every client TTFA sample in the frozen runner is at most 2000 ms.
- [x] The one-second teleport remains visible while the mutation is no longer serialized behind it.
