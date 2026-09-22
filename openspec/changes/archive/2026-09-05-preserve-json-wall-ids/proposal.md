## Why

Godot читает размеры стен из canonical level JSON, но заново вычисляет их идентификаторы по индексу массива. Текущий файл случайно использует последовательные `wall_01...`, поэтому перестановка или произвольный JSON id незаметно рассинхронизирует команды джина, сериализацию и визуальный объект.

## What Changes

- Сохранять каждый wall id непосредственно из level JSON во всех client indexes, snapshots, collision bodies и rendering paths.
- Добавить Godot contract regression, запрещающий производные wall ids.

## Capabilities

### New Capabilities

- Нет.

### Modified Capabilities

- `serialized-world`: идентичность объектов является частью lossless JSON round-trip, а не выводится из порядка массива.

## Change classification

- `player_visible`
- `deterministic_server`

## Impact

Затрагиваются только Godot level loader/rendering и level contract runner; wire format и canonical JSON не меняются.
