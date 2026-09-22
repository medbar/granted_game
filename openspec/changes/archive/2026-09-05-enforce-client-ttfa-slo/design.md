## Context

См. `proposal.md`. Agentic endpoint возвращает job и клиент опрашивает его раз в 250 мс. Первая мутация выполняется в action sequence, после начала телепортации. Диагностический повтор после чтения накопившегося stdout показал 1132–1310 мс вместо 4301–6757 мс: главным источником деградации оказался backpressure подробного Uvicorn access log в долго живущем захваченном процессе, а не модель и не Monty.

## Goals / Non-Goals

**Goals:**

- Сделать запуск сервера устойчивым к невычитанному stdout, оставив структурированные JSONL-события и Prometheus-файл.
- Сделать client-observed TTFA частью обязательного Godot eval, а не ручной интерпретацией метрик.
- Разложить клиентскую задержку на локальные монотонные этапы и передавать breakdown вместе с первым feedback.
- Сохранить анимацию и authoritative post-action verification.

**Non-Goals:**

- Не вводить WebSocket/SSE, пока polling с 250 мс укладывается в SLO.
- Не удалять error-level вывод Uvicorn и не заменять JSONL telemetry access-log текстом.
- Не считать локальную очистку терминала допустимым production remedy.

## Decisions

### Отключить per-request Uvicorn access log во всех штатных и verification запусках

Тысячи строк `GET/POST` не несут доменной диагностики: те же переходы job уже записаны в `agent-events.jsonl`. `--no-access-log` устраняет возможность заполнить pipe/PTY и блокировать event loop. Error log остаётся.

Альтернатива — постоянно дренировать PTY или перенаправлять access log в ещё один файл. Это эксплуатационно хрупко и дублирует существующую telemetry.

### Timing breakdown принадлежит клиенту

Godot сохраняет monotonic offsets от подтверждения желания: первый HTTP response, первое получение `action_ready`, фактическая мутация. Сервер добавляет только собственное `server_action_ready_ms`; часы двух процессов не вычитаются друг из друга.

Альтернатива — реконструировать задержку по UTC JSONL timestamps. Она подвержена clock adjustments и не доказывает момент client mutation.

### Мутация остаётся внутри визуального action sequence

Готовое действие начинает телепортацию и применяется в середине перехода, а не после полного исчезновения/проявления. Это сохраняет причинную сцену и оставляет запас под SLO. Мы не применяем действие до получения server step id, чтобы feedback/retry оставались идемпотентными.

### Два уровня latency gate

Небольшой headless `ttfa_runner.gd` быстро проверяет репрезентативные fast-path категории и пишет самостоятельный hard-gate report. Полный 40-case environment eval также записывает timing; на hardware renderer он падает при превышении, а на `llvmpipe` сохраняет raw warning и продолжает проверять JSON/PNG. CPU software rendering блокирует сам main loop на секунды и не является измерением обычной игры.

## Risks / Trade-offs

- [Редкая long-tail команда пойдёт через внешнюю модель и превысит SLO] → gate явно относится к поддерживаемому fast-path; отчёт всё равно сохранит честное нарушение.
- [Шум Windows scheduler делает ровно 2000 мс flaky] → production limit остаётся 2000; fast path проектируется с фактическим запасом около 600–800 мс.
- [Access details понадобятся при сетевом сбое] → Uvicorn error log сохраняется, а request/job ids и состояния доступны в JSONL telemetry.
- [Повторный callback применит шаг дважды] → active step id фиксируется до queueing; feedback mismatch возвращает 409, client queue не добавляет известный step повторно.

## Migration Plan

Сначала добавить RED timing/report assertions, затем добавить client breakdown и устойчивые server launch flags, перезапустить backend штатной командой и прогнать narrow TTFA → full client loop → server tests. Откат не требует данных: удалить additive fields и флаг запуска.
