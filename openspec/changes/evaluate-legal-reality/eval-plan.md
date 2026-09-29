## Change classification

tooling, observability. Обязательны quality_policy и полный server_tests; дополнительно legal_frozen, legal_live, legal client и profile selection.

## Acceptance matrix

| Requirement / scenario | Authoritative oracle | Test or eval added first | Expected RED | Required GREEN gates |
|---|---|---|---|---|
| Legal oracle | поля, допустимый diff, физические probes | test_legal_evals.py | модуль отсутствует | server_tests, frozen |
| Refusal/scope/precedent | отсутствие мутаций, роли, reuse/reload/replay | legal_cases.json | runner отсутствует | frozen/live |
| Real live evidence | неверный ответ модели не заменяется fixture | injected planner test | runner отсутствует | server_tests, live |
| Coverage/report | hash, selected/excluded, statistics, artifacts | report tests | старый формат | server_tests |
| Main profile | legal default, explicit legacy | policy/verify tests | старые genie gates | policy, client |

## Baseline

Предыдущий live report server/runtime/evals/bureaucracy-20260922T212511Z/summary.json: 12/12 простых эффектов; нет отрицательных и последовательных сценариев. Матрица и verify.ps1 требуют старые Monty/environment/heist проверки. Узкий baseline: 27 tests passed; policy test увидел временно пустую новую папку change во время подготовки документов, а не дефект production.

## RED evidence

23.09.2026: pytest tests/test_legal_evals.py до реализации завершился ModuleNotFoundError: evals.legal_suite (1 collection error, 16.23 s). pytest tests/test_quality_policy.py -k 'default_gates or defaults_to' дал два FAIL: select_gates отсутствует и verify.ps1 не имеет legal default. Набор из 32 cases и независимые expected/allowed_changes добавлены до evaluator и до изменения матрицы.

Дополнительный RED: test_report_preserves_runtime_failure_and_continues_other_cases падает
с PermissionError (1 failed, 4.85 s). После этого runner научен сохранять FAIL/error и продолжать
другие cases, без автоматического повтора или подмены fixtures.

## GREEN evidence

23.09.2026 (имена отчётов содержат UTC 22.09):

- Узкие legal/profile тесты: 48 passed; после добавления runtime-error regression полный
  `pytest -p no:cacheprovider --tb=short --basetemp ../.verification/fi-<unique>`:
  **305 passed in 97.58 s**. До дополнительного теста полный повтор дал 304 passed.
- Frozen: **32/32**, excluded=0. Отчёт:
  `server/runtime/evals/legal-20260922T223836694268Z-frozen/summary.json`.
  Конечные исходы cases: completed=20, reloaded=1, failed=10, rejected=1.
- Live: **21/21**, excluded=11 (frozen_only), без fixture fallback. Отчёт:
  `server/runtime/evals/legal-20260922T223902553846Z-live/summary.json`.
  Конечные исходы: completed=19, reloaded=1, failed=1. Это НЕ «21 исполненное желание».
- Оба отчёта используют suite SHA-256
  `61b5782e49d9d66911797296a203328d247890ca0ab71693c7f476b567487ab4`.
- Godot `legal_smoke_runner.gd`: LEGAL_SMOKE_OK, exit 0.
- Реальный `bureaucracy_runner.gd` на изолированном сервере :8003: BUREAUCRACY_OK, exit 0;
  `client/test-artifacts/bureaucracy/result.json`: passed=true, issues=[].
  Проверены before/after/escaped/refused JSON и rendered refused.png: открытый проход,
  выход за кордон и читаемый отказ адвоката в нижней панели. Сервер теста остановлен,
  игровая сессия пользователя на :8000 не использовалась.
- OpenSpec strict --all: 9 passed, 0 failed. Проверка whitespace diff — без ошибок.

### Harness corrections and limitations

- Длинные Windows-пути временных сессий потребовали extended-path prefix внутри eval harness.
  Это не изменение gameplay/persistence кода.
- В составном personal_then_public oracle учтено уже выданное личное право: игрок проходит
  и соседнюю закрытую дверь, полиция — нет. Проверка неизменности самой двери сохранена;
  добавлены отдельные role probes, а не удалено постусловие.
- Smoke сначала использовал ошибочный id `npc`; исправлен на существующий в level JSON `npc_1`.
- Монолитные попытки `verify.ps1` обнаружили нестабильный WinError 5 при атомарном сохранении
  сессии: сначала 1 failed / 303 passed, затем 304 passed, но frozen CLI остановился на 32-м
  сценарии (незавершённый каталог `legal-20260922T223544342005Z-frozen`).
  После добавления явной обработки ошибок финальные gates выполнены отдельно:
  305 pytest, frozen 32/32, live 21/21, smoke/client. Причина внешней файловой блокировки
  не установлена и production `Campaign._save` не изменён; не заявляется устранение этого
  риска или успешный непрерывный запуск всего verify.ps1.
- Любая будущая ошибка исполнения case остаётся FAIL/error в summary, остальные cases продолжаются.
  Никакого retry-until-green внутри evaluator нет.
- Live startup SDK занял 20063 ms на этой машине; latency шага не является TTFA.
  Набор доказывает эти фиксированные сценарии, не качество всех свободных формулировок.
- Генерация адвоката/правила мира не менялись. Предложения о юрисдикциях не повышались до канона.

## Trajectory review

- [x] Проверены дверь, права игрока/NPC и неизменность соседних объектов.
- [x] Просмотрены reuse/reload и отказ: один BOR-0001, uses=2; reload без diff; отказ после 3 попыток без мутации.
- [x] Live и frozen не смешаны, исключённые cases не засчитаны.
- [x] Зафиксированы отчёты и клиентский прогон.

Delta specs готовы к ревью; change оставлен открытым, без автоматического архивирования.
