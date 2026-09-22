## Purpose

Обеспечивает полный наблюдаемый JSON-контракт уровня и изменённого мира, пригодный для команд джину, повторного запуска и независимой проверки результата.

## ADDED Requirements

### Requirement: Complete level state round-trips through JSON
Сериализованное состояние SHALL включать schema/version, level id, bounds, palette, rooms, walls, doors, fixtures, actors, objects, states, materials, inventory, mission progress, world controls и event history. Сохранение и загрузка SHALL сохранять все публичные поля без потерь.

#### Scenario: Session is saved and loaded
- **WHEN** изменённая start-level session сохраняется и загружается из JSON
- **THEN** повторно сериализованный публичный документ эквивалентен исходному по layout и runtime state
- **THEN** секретные свойства отсутствуют в публичной версии

### Requirement: Genie receives the complete public world
Каждый agent turn SHALL получать полный актуальный public level state, включая удалённые комнаты и mission rules, а не только сущности рядом с игроком.

#### Scenario: Genie is commanded about a remote object
- **WHEN** желание указывает на объект в другой комнате
- **THEN** объект и его room/door context присутствуют в request JSON
- **THEN** целевое действие автоматически проявляет джина возле объекта без pathfinding action

### Requirement: Before and after artifacts are inspectable
Каждый validation run SHALL сохранять canonical `before.json`, `after.json`, action trace и result summary с проверенными postconditions.

#### Scenario: Wish result is reviewed
- **WHEN** eval-желание завершилось
- **THEN** reviewer может открыть JSON до/после и увидеть конкретные поля, доказывающие или опровергающие исполнение
