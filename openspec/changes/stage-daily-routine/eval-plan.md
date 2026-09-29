## Change classification

player_visible. Обязательны quality_policy, server_tests, legal_smoke, legal_client, trajectory_review.
Дополнительно frozen legal для контроля сохранения существующих условий входа в город.
Agent behavior не меняется; legal_client всё равно использует настоящую модель.

## Acceptance matrix

| Requirement / scenario | Authoritative oracle | Test or eval added first | Expected RED | Required GREEN gates |
|---|---|---|---|---|
| Isolated apartment | видимые объекты/кнопки и rendered PNG | daily_routine_runner.gd | нет routine view | smoke, client |
| Spatial exit / duplicate input | реальное движение и одна HTTP-команда | daily_routine_runner.gd | удалённые кнопки | client |
| Metro to office | фактическая phase office, метро >= 2.8 s | daily_routine_runner.gd | нет перехода | client |
| One work button / return | processed +2, phase apartment, PNG | daily_routine_runner.gd | две кнопки и нет автопоездки | client |
| Network refusal/retry | исходная комната, ошибка, повтор успешен | daily_routine_runner.gd | нет нового контроллера | client |
| Contract/city regression | voluntary contract, gate crossing | bureaucracy_runner.gd + pytest | существующий baseline | server, legal client, frozen |

## Baseline

Прочитан текущий renderer: он рисует все level.rooms и state.objects во всех фазах;
office UI имеет «ОБРАБОТАТЬ», «Вернуться домой», «Реестр» и «Новая сессия».
Существующий legal_smoke_runner.gd: LEGAL_SMOKE_OK, exit 0 до изменений production.

## RED evidence

23.09.2026: Godot --headless --path client --script res://tests/daily_routine_runner.gd,
exit 1: DAILY ROUTINE: separate routine presentation must exist. Production ещё не менялся.

Дополнительные обнаруженные RED: smoke раньше возвращал 0 при ошибке компиляции зависимости.
Проверка Script.reload/can_instantiate теперь дала ожидаемый exit 1; конфликт с native
draw_ellipse устранён. Mouse-retry сначала дал FAIL: синтетический input был в canvas,
а не window координатах; тест учитывает stretch, игровой hit-test использует координаты события.

## GREEN evidence

23.09.2026:

- Новый daily_routine_runner: сначала headless DAILY_ROUTINE_OK, затем реальный графический
  прогон с обеими формами ввода (E и mouse) DAILY_ROUTINE_OK, exit 0. Финальный повтор после
  визуальных правок также exit 0. `client/test-artifacts/daily-routine/result.json`:
  passed=true, issues=[]; команды commute, work, work, home, неуспешный commute, успешный commute.
- Просмотрены PNG и JSON 01-apartment, 02-metro, 03-office, 04-home, 05-failed-trip, 06-recovered.
  Квартира не содержит город/полицию, поезд виден >=2.8 s, в офисе одна кнопка,
  processed увеличивается на 2, после возвращения contract_ready=true/contract_signed=false.
  Ошибка остаётся видимой и не открывает неподтверждённую работу; повтор мышью успешен.
- Существующий реальный bureaucracy_runner с настоящим адвокатом: BUREAUCRACY_OK, exit 0,
  `client/test-artifacts/bureaucracy/result.json`: passed=true/без issues; открытие двери,
  движение во время запроса, выход за кордон и отказ после трёх попыток сохранены.
- Полный pytest: **305 passed in 32.67 s**. После изменения manifest/verify/docs:
  tests/test_quality_policy.py — **5 passed**.
- Frozen legal: **32/32**, отчёт
  `server/runtime/evals/legal-20260923T045934941772Z-frozen/summary.json`.
- legal_smoke: LEGAL_SMOKE_OK; quality_policy: PASS; OpenSpec strict --all: **10 passed, 0 failed**.
- Сервер :8003 был создан только для тестов; сохранение пользователя не сбрасывалось.
  Model/правила/серверная схема не менялись. Полный отдельный legal live 21-case набор повторно
  не требовался для player_visible: настоящий модельный gate выполнен в городском клиенте.

Темп двух документов сохранён как ранее; вопрос об одном нажатии на всю смену оставлен
предпочтением пользователя, а не молча принятой сменой правил.

## Trajectory review

- [x] В квартире видна только комната, а не квартал.
- [x] Есть вагон метро с движением, затем отдельная работа с одной кнопкой.
- [x] Счётчик и возвращение соответствуют серверу, контракт доброволен.
- [x] Сетевой отказ не телепортирует в неподтверждённую локацию.
- [x] JSON и PNG реального клиента просмотрены.
