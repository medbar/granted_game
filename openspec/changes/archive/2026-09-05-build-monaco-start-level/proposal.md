## Why

Стартовый уровень сейчас выглядит как раскрашенная сетка с несколькими прямоугольниками, а его геометрия и актёры зашиты в `main.gd`. Серверные evals проверяют упрощённый sandbox, поэтому зелёный JSON не доказывает, что желание действительно произошло и визуально проявилось в той же игре, которую видит игрок.

## What Changes

- Создать новый стартовый heist-уровень с читаемым планом здания, несколькими функциональными комнатами, дверными проёмами, мебелью, конусами зрения, золотой добычей и контрастной Monaco-подобной визуальной иерархией.
- Сделать единый JSON level definition источником геометрии, сущностей, миссии, цветов и начального состояния для Godot и серверной симуляции.
- Сериализовать полный уровень и его изменённое состояние, чтобы агент и observer видели те же комнаты, стены, двери, объекты и цели, что клиент.
- Добавить JSON-before/after artifacts и автоматическое создание реального скриншота после действий джина.
- Расширить client-in-loop eval так, чтобы все 40 environment wishes проверялись по фактическому состоянию Godot, а не только по server action names.
- Добавить воспроизводимый стартовый playthrough eval: нейтрализовать угрозы, собрать добычу, открыть выход и завершить уровень.
- Перевести capabilities джина на hot-plug registry с manifest-файлами, динамическим prompt fragment и API включения/выключения без рестарта.
- Настраивать prompt/fast path только по результатам frozen eval set, сохраняя реальные отчёты и скриншоты.

## Capabilities

### New Capabilities

- `monaco-start-level`: JSON-driven стартовый heist-уровень и его визуальная грамматика.
- `serialized-world`: полный round-trip уровня и runtime-состояния между Godot, API, session store и агентом.
- `genie-capability-plugins`: hot-plug registry функций джина с runtime enable/disable/reload.
- `wish-visual-validation`: совместная проверка желания по world-state JSON и фактическому Godot screenshot.
- `start-level-playthrough`: объективно завершаемый сценарий стартового ограбления.

### Modified Capabilities

- Нет: эти capability ещё не представлены в основной OpenSpec спецификации.

## Change classification

- `deterministic_server`
- `agent_behavior`
- `player_visible`
- `observability`
- `tooling`

## Non-goals

- Не копировать исходные ассеты, карты или UI Monaco; используется только визуальная грамматика top-down blueprint/heist.
- Не строить редактор уровней и production pipeline ассетов.
- Не добавлять multiplayer или полноценный stealth campaign.
- Не считать декоративный эффект или реплику джина исполнением желания.

## Impact

Затрагиваются Godot level construction/rendering/tests, Pydantic world/session models, agent prompt/runtime capabilities, API/observer, eval cases и локальные verification artifacts. JSON level definition становится версионируемым контрактом между клиентом и сервером.
