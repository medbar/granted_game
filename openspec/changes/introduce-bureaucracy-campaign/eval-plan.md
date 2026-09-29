## Change classification

deterministic_server, agent_behavior, player_visible, observability.
Required GREEN gates: quality_policy, server_tests, environment_evolution, monty_live_model, agent_level_live_model, godot_smoke, godot_client_loop, trajectory_review; дополнительно новые bureaucracy frozen/live cases и Godot bureaucracy runner.

## Acceptance matrix

| Requirement / scenario | Authoritative oracle | Test or eval added first | Expected RED | Required GREEN gates |
|---|---|---|---|---|
| Clerk signs or declines | contract.signed=false до подписи, действия рутины, выход после подписи | test_reality.py prologue | отсутствующий модуль/API | server_tests, bureaucracy client |
| Emergency exit | door.open=true, door.legal_status, проходимость | bureaucracy_cases.json emergency_exit | отсутствующая правовая система | server_tests, live cases, trajectory_review |
| Invalid petition | нет эффектов, видимый failed после 3 попыток | retry/invalid basis tests | отсутствующий validator | server_tests |
| Reuse a precedent | один precedent, два uses, reload идентичен | precedent reuse/persistence tests | отсутствующий реестр | server_tests |
| Wish during pursuit | tick меняет позицию во время ожидающего model | concurrent tick test | отсутствующий independent loop | server_tests, client |
| Inspect and replay | один receipt, snapshot before/after | idempotency/telemetry tests | отсутствующая квитанция | server_tests, trajectory_review |
| Launch new campaign | новый entrypoint, JSON world и рисунок | bureaucracy_runner.gd | новая сцена не существует | godot_smoke, client PNG |
| Observer understands legal cases | основание, попытки, фактическая разница before/after | test_observer.py legal cases | KeyError bureaucracy, отсутствующий summary | server_tests, браузер /observer |

## Baseline

22.09.2026: checkpoint 27f9fa5 сохранён на GitHub. Сервер: 232 passed in 20.53s. OpenSpec: 7/7 strict. Quality policy PASS.
Существующие client/test-artifacts/start_level_playthrough/result.json и before/after показывают джина и heist; новый пролог и юридический реестр отсутствуют.

## RED evidence

22.09.2026 до production-изменений: pytest tests/test_reality.py завершился с ModuleNotFoundError: app.reality (1 collection error). Godot --headless --path client --script res://tests/bureaucracy_runner.gd завершился exit 1: новая сцена res://scenes/bureaucracy.tscn отсутствует. Frozen suite содержит 12 желаний с независимыми ожидаемыми полями мира.

Дополнительные RED перед соответствующими исправлениями:
- Проверка default entrypoint не прошла до переключения project.godot.
- Два теста выявили отклонение числового value модели и потерю rejected petition в траектории.
- Первый live suite: 7/12, server/runtime/evals/bureaucracy-20260922T205557Z/summary.json. Модель путала статус скорой помощи с transform и меняла числовые значения света/темпа; числовой ноль отклонялся схемой. Исправлены prompt/schema, frozen ожидания не ослаблялись.
- Два графических прогона нового клиента: ответ completed пришёл, но tick-запросы зависали и мир на экране не обновлялся. Повтор без конкурирующих eval подтвердил проблему. На llvmpipe отключены worker threads HTTPRequest, сохранены независимые асинхронные запросы. Headless и графический прогон затем прошли.
- Observer показывал «действий не было» для правового дела. Два новых теста завершились KeyError bureaucracy / AttributeError summarize_bureaucracy до добавления адаптера.

## GREEN evidence

22–23.09.2026, команды из server либо корня согласно quality-gates.json:

| Gate | Result / evidence |
|---|---|
| Server tests | .venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider --basetemp ../.verification/final-<unique>: 259 passed, exit 0. Изолированная временная папка нужна из-за ACL старых pytest temp. |
| New frozen suite | scripts/run_bureaucracy_evals.py --frozen: 12/12; runtime/evals/bureaucracy-20260922T212732Z/summary.json |
| New live suite | scripts/run_bureaucracy_evals.py: 12/12; runtime/evals/bureaucracy-20260922T212511Z/summary.json, Qwen qwen3-35-36, не фикстура |
| New actual client | Godot --audio-driver Dummy --path client --script res://tests/bureaucracy_runner.gd: BUREAUCRACY_OK, exit 0; .verification/bureau-final.log |
| Environment evolution | generation 8: 40/40; server/runtime/evolution/generation-8.json |
| Monty live | 10/10; server/runtime/evals/monty-20260922T210201Z.json |
| Agent levels | 20/20 различных стратегий, все три уровня; server/runtime/evals/agent-levels-20260922T210439Z.json |
| Godot regressions | smoke_runner, level_contract_runner, live_cast_runner: PASS; ttfa_runner: 3/3 реальных client mutations <=2000 ms, client/test-artifacts/ttfa/summary.json |
| Graphical legacy loop | environment_wish_runner: 40/40; start_level_playthrough_runner: 3/3 и mission completed; JSON/PNG в client/test-artifacts/environment и start_level_playthrough |
| Observer review | /observer: у bor-ea51086a387b-wish_8027693 видны life_safety, BOR-0001, open_exit/checkpoint, open false → true и legal_status restricted → emergency_exit. Нет выдуманной программы джина. |
| OpenSpec/policy | openspec validate --all --strict: 8/8; server/scripts/quality_policy.py --root .: PASS |

Ограничения измерений: cold SDK preparation в последнем live suite 9765 ms; первый запрос 5.141 s, остальные 0.313–0.828 s. Это серверное время решения, не client TTFA; универсальное обещание <=2 s не заявляется. В графическом legacy environment suite на llvmpipe сохранены 13 timing warnings (ttfa_gate_applicable=false). Это визуальная проверка, не доказательство performance SLO; отдельный headless TTFA gate прошёл. При параллельном тяжёлом прогоне также наблюдался старый MontyCrashedError/display в legacy сервере; новый правовой домен Monty не использует. Итоговые обязательные регрессии завершились успешно.

## Trajectory review

- [x] Изменение действительно видно в работающем мире клиента: дверь исчезла из прохода, персонаж пересёк кордон, экран показывает завершение первого дела.
- [x] Проверяется состояние мира, не реплика, HTTP-статус или выбранное действие: checkpoint.open, legal_status, player.recognizable, player.x и status=escaped.
- [x] Повторная попытка и окончательный отказ видимы и честны: желание отменить существование договора в прошлом получило failed после трёх попыток; refused.png показывает отказ, objects не изменились.
- [x] Посторонний эффект не даёт ложный успех в проверяемых сценариях: frozen поля заданы до реализации, failure case отдельно сравнивает мир. Это не гарантия интерпретации любого свободного текста.
- [x] client/test-artifacts/bureaucracy: before.json/png, after.json/png, escaped.json, final.png, refused.json/png, result.json. Реальные траектории: server/runtime/trajectories/*bor-92ba6ef832c6-*.json (два успеха и отказ); предыдущая просмотренная в браузере сессия bor-ea51086a387b.
