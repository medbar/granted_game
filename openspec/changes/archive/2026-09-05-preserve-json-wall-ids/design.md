## Context

`load_level_definition()` keeps wall rectangles but discards wall ids. `create_arena()` and `_draw()` reconstruct ids from the array index, while the server retains canonical ids.

## Goals / Non-Goals

Сохранить exact object identity through the client pipeline. Не менять JSON schema, geometry или visuals.

## Decisions

### Keep a parallel typed wall-id array

Добавить `WALL_IDS: Array[String]`, заполнять его одновременно с `WALLS` и использовать во всех index/draw loops. Это минимальное изменение, сохраняющее существующую геометрию и порядок отрисовки.

Альтернатива — заменить оба массива массивом Dictionary. Она шире по риску и не нужна для исправления identity drift.

## Risks / Trade-offs

- [Duplicate/missing JSON ids] → existing server validation remains authoritative; Godot contract runner also checks uniqueness/count equality.
- [Rendering regression] → rerun actual 40-case and playthrough PNG gates.

## Migration Plan

Добавить RED assertion, сохранить ids при load, заменить оба generated-id lookup и прогнать полный client loop. Откат — вернуть прежнее вычисление индекса; JSON не мигрируется.
