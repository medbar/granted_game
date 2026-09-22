## Context

Godot уже умеет применять `WorldAction`, серверная simulation — мутировать `GameSession`, а observer — читать runtime artifacts. Главный разрыв в том, что геометрия/миссия клиента и server eval world являются разными моделями. Новый дизайн делает level JSON общим контрактом и добавляет доказательства на границах: model → server world → client node state → screenshot.

Визуальная грамматика ориентируется на Monaco: top-down floor plan, раскрывающиеся насыщенные комнаты, крупные подписи, яркие охранные конусы и золотая добыча. Ассеты и конкретная карта не копируются.

## Goals / Non-Goals

**Goals:** один JSON-источник уровня; полный world round-trip; реальный client-in-loop для frozen wishes; воспроизводимый PNG; стартовый playthrough; hot plugin toggle; regression-safe prompt evolution.

**Non-goals:** generic level editor, production art pipeline, pixel-perfect клон Monaco, unbounded autonomous code execution.

## Decisions

### Shared level contract lives under `client/levels`

Godot импортирует JSON как ресурс из `res://levels/monaco_start.json`; сервер читает тот же файл относительно repository root. Сервер валидирует документ Pydantic-моделями и переносит layout в `WorldSnapshot.level`, поэтому agent request содержит полный контекст.

Альтернатива — две копии JSON. Отклонена из-за дрейфа visual и eval worlds.

### Runtime state is separate from immutable definition

Level definition задаёт layout/initial entities/mission. `GameSession` хранит immutable definition snapshot плюс mutable world, inventory, mission progress, controls и events. Public serialization вычищает `secret_*`, но не выкидывает удалённые комнаты/объекты.

### Declarative capability plugins wrap trusted handlers

Plugin manifest не загружает произвольный Python. Он владеет списком известных trusted Monty handlers. Registry валидирует уникальность, вычисляет revision и управляет enabled state; runtime проверяет registry перед каждым capability call. Это даёт hot toggle без превращения plugin system в удалённый code execution.

Плагины: `perception`, `physical`, `creation`, `social`, `world-control`, `heist`. Prompt fragment генерируется из enabled capabilities, а статический prompt перестаёт быть единственным allow-list.

### JSON and screenshot share an artifact id

Godot eval runner после action feedback сохраняет `before.json`, `after.json`, `result.json` и PNG в одном case directory. Screenshot снимается только после `after.json`; result содержит SHA-256 JSON и image metadata. Ручное visual review дополняет structural screenshot checks.

### Start-level completion has explicit mechanics

Mission definition перечисляет required loot ids, extraction door/zone и threat policy. Server simulation и Godot вычисляют progress одинаково. Heist plugin предоставляет доверенные `collect`/`unlock` interactions через общий `interact`, а не скрытый «complete level» shortcut.

### Prompt evolution uses a frozen product oracle

Fast routes допускаются для latency, но проходят тот же world/client oracle. Candidate prompt принимается только при 100% сохранении frozen cases и успешном playthrough; aggregate score не маскирует регрессии.

## Risks / Trade-offs

- [Godot отсутствует на машине] → скачать официальный 4.7.2 console executable в project-local tools и зафиксировать checksum/source; не пропускать visual gate.
- [40 live client cases дороги] → использовать fast route там, где желание однозначно, но всё равно применять реальные actions к Godot и проверять after state.
- [Сложность синхронизации server/client] → schema version, shared ids и contract tests на обеих сторонах.
- [Plugin toggle ломает eval] → manifest состояния сбрасываются к defaults для каждого eval run; disabled capability даёт явный failure.
- [Скриншот может существовать, но быть неверным] → structural assertions + ручной review изображения + связь с after JSON.

## Migration Plan

1. Добавить failing contract tests и frozen playthrough definition.
2. Ввести typed level loader и JSON definition на сервере.
3. Перевести Godot construction/draw на JSON, сохранив существующие action handlers.
4. Добавить plugin registry и API, затем подключить prompt/runtime enforcement.
5. Добавить artifact/screenshot runners и 40-case client eval.
6. Настроить agent/prompt по провалам frozen suites.
7. Пройти стартовый уровень, провести JSON/PNG review и запустить все gates.

Откат: вернуть прежний hardcoded constructor и отключить registry integration; shared JSON и новые тесты останутся как диагностический артефакт до повторной реализации.
