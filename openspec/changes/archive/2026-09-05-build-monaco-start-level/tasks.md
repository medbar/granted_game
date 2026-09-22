## 0. Baseline

- [x] 0.1 Зафиксировать расхождение hardcoded Godot level, server sandbox, 40 server cases и 3 client cases в `eval-plan.md`
- [x] 0.2 Зафиксировать Monaco visual grammar по референсам и текущий визуальный дефицит без копирования ассетов

## 1. RED — tests and evals first

- [x] 1.1 Добавить server contract tests для typed start-level JSON, full public round-trip, mission и remote agent context; записать RED
- [x] 1.2 Добавить plugin registry/API/prompt/runtime tests для hot disable-enable-reload; записать RED
- [x] 1.3 Добавить frozen start-level playthrough eval и server postcondition tests; записать RED
- [x] 1.4 Добавить Godot level contract, 40-case client eval и screenshot artifact runners; записать недостающий Godot/contract RED

## 2. GREEN — minimal implementation

- [x] 2.1 Создать и валидировать `client/levels/monaco_start.json`; загрузить его в server GameSession/WorldSnapshot без потерь
- [x] 2.2 Перевести Godot rooms, walls, doors, entities, mission и rendering на shared JSON ids
- [x] 2.3 Реализовать declarative trusted plugin registry, manifests, hot API и dynamic prompt/runtime allow-list
- [x] 2.4 Реализовать before/after/result/PNG artifact bundle и observer links
- [x] 2.5 Реализовать start-level completion mechanics и client/server agreement

## 3. Refactor

- [x] 3.1 Удалить дублирующую hardcoded level geometry и централизовать postcondition evaluators
- [x] 3.2 Сделать visual primitives/palette читаемыми и устойчивыми к reset/transform/spawn
- [x] 3.3 Обновить документацию и диагностические сообщения plugins/visual eval

## 4. Full evaluation and review

- [x] 4.1 Довести server pytest и 40 environment cases до 100% без false-green fallback
- [x] 4.2 Довести live Monty и agent-level suites, включая start playthrough, до всех обязательных postconditions
- [x] 4.3 Прогнать Godot smoke, все 40 client-in-loop cases и сохранить JSON/PNG artifacts
- [x] 4.4 Визуально проверить baseline/final/representative wish screenshots и завершить trajectory checklist
- [x] 4.5 Запустить quality policy, strict OpenSpec validation, аудит всех требований, затем sync/archive
