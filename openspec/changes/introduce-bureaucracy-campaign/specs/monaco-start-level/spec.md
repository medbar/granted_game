## MODIFIED Requirements

### Requirement: Level is data-driven
Архивный Monaco-прототип SHALL полностью строиться из одного versioned JSON definition, содержащего bounds, rooms, walls, doors, fixtures, actors, loot, water, extraction zone, palette и mission rules. Production-код SHALL NOT содержать параллельную авторитетную копию геометрии. Этот режим сохраняется для регрессий и явного запуска, но не является каноническим стартом Bureaucracy of Reality.

#### Scenario: Client loads the start level
- **WHEN** Godot явно открывает архивную сцену `res://scenes/main.tscn`
- **THEN** комнаты, стены, двери, сущности и mission objective создаются из JSON definition
- **THEN** все JSON ids доступны в runtime object index

