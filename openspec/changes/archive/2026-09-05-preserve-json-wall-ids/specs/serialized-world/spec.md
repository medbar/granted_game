## MODIFIED Requirements

### Requirement: Complete level state round-trips through JSON
Сериализованное состояние SHALL включать schema/version, level id, bounds, palette, rooms, walls, doors, fixtures, actors, objects, states, materials, inventory, mission progress, world controls и event history. Сохранение и загрузка SHALL сохранять все публичные поля без потерь. Идентификатор каждого объекта SHALL читаться из canonical JSON и не MUST зависеть от позиции объекта в массиве.

#### Scenario: Session is saved and loaded
- **WHEN** изменённая start-level session сохраняется и загружается из JSON
- **THEN** повторно сериализованный публичный документ эквивалентен исходному по layout и runtime state
- **THEN** секретные свойства отсутствуют в публичной версии

#### Scenario: Wall order or identifier is non-sequential
- **WHEN** canonical JSON содержит переставленную стену или wall id, не совпадающий с индексом массива
- **THEN** Godot object index, snapshot и rendering используют точный JSON id
- **THEN** команда джина по этому id воздействует на ту же стену
