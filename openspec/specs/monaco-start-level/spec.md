# monaco-start-level Specification

## Purpose
Определяет читаемый Monaco-подобный стартовый heist-уровень, построенный из данных и одинаково представленный в клиенте, сервере и инструментах проверки.

## Requirements

### Requirement: Level is data-driven
Стартовый уровень SHALL полностью строиться из одного versioned JSON definition, содержащего bounds, rooms, walls, doors, fixtures, actors, loot, water, extraction zone, palette и mission rules. Production-код SHALL NOT содержать параллельную авторитетную копию геометрии.

#### Scenario: Client loads the start level
- **WHEN** Godot открывает main scene
- **THEN** комнаты, стены, двери, сущности и mission objective создаются из JSON definition
- **THEN** все JSON ids доступны в runtime object index

### Requirement: Visual grammar resembles a Monaco heist map
Уровень SHALL иметь не менее восьми подписанных комнат, связанную сеть коридоров и дверей, толстые тёмные стены с ярким контуром, различные насыщенные цветовые зоны, свет/туман видимости, конусы охраны, золотые цели и различимые интерактивные объекты.

#### Scenario: Start level is rendered
- **WHEN** снимается кадр стартового состояния при 1280×720
- **THEN** план здания, подписи комнат, двери, охрана, vision cones, добыча и выход различимы без debug overlay
- **THEN** UI не перекрывает основную игровую область и сохраняет читаемую иерархию

### Requirement: Mission is completable
Миссия SHALL завершаться только после сбора всей обязательной добычи и достижения/открытия выхода согласно JSON mission rules.

#### Scenario: Automated playthrough completes
- **WHEN** игрок или джин нейтрализует препятствия, собирает три обязательные ценности и открывает путь к выходу
- **THEN** авторитетное состояние уровня становится `completed`
- **THEN** клиент визуально показывает завершение ограбления
