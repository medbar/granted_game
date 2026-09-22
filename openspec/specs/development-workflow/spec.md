# development-workflow Specification

## Purpose
Определяет обязательный проверяемый процесс разработки Granted, чтобы изменения поведения джина оценивались по фактическому состоянию игрового мира и пользовательскому опыту.

## Requirements

### Requirement: OpenSpec is the primary change workflow
Каждое изменение наблюдаемого поведения системы SHALL иметь OpenSpec change с proposal, delta specs, eval plan, design и tasks до изменения production-кода или промпта. Чистая документация и механический рефакторинг MAY использовать `skip_specs`, но всё равно SHALL проходить применимые quality gates.

#### Scenario: Behavior change starts with artifacts
- **WHEN** разработчик или кодинговый агент начинает менять поведение сервера, агента или клиента
- **THEN** активный OpenSpec change содержит все планирующие артефакты схемы `granted-eval-first` до первой production-правки

### Requirement: Evaluation is defined before implementation
Для каждого изменяемого сценария eval plan SHALL заранее задавать наблюдаемый oracle, регрессионный тест, применимые eval-кейсы, ожидаемый RED и обязательные GREEN gates.

#### Scenario: Agent behavior is changed
- **WHEN** change затрагивает промпт, инструменты, планирование, retry loop или применение действий джина
- **THEN** соответствующий eval-кейс с oracle по итоговому world state добавлен до реализации
- **THEN** generated code, action label, HTTP 200 и речь джина не считаются доказательством исполнения

### Requirement: TDD order is enforced
Изменение поведения SHALL следовать порядку baseline → failing test/eval → observed RED → minimal implementation → GREEN → refactor → relevant full gates.

#### Scenario: Regression fix is implemented
- **WHEN** исправляется неисполненное или неверно исполненное желание
- **THEN** сначала существует тест или eval, который воспроизводимо падает по ожидаемой причине
- **THEN** production-поведение меняется только после фиксации RED evidence

### Requirement: Gates depend on change class
Проект SHALL хранить версионируемую матрицу обязательных проверок для `deterministic_server`, `agent_behavior`, `player_visible`, `observability` и `tooling` изменений.

#### Scenario: Player-visible agent change is verified
- **WHEN** change одновременно классифицирован как `agent_behavior` и `player_visible`
- **THEN** проходят deterministic server tests, environment eval, live-model eval, Godot smoke, client-in-loop test и ручное ревью реальной траектории

### Requirement: Failed wishes remain failed
Eval oracle SHALL проверять запрошенные постусловия авторитетного мира и SHALL NOT засчитывать постороннее fallback-действие как успех.

#### Scenario: Model cannot fulfill a wish
- **WHEN** ни одна попытка агента не создаёт требуемое постусловие мира
- **THEN** eval остаётся красным и игрок получает видимый честный failure outcome

### Requirement: Archive requires evidence
Change SHALL архивироваться только после успешной OpenSpec validation, проверки quality policy и прохождения всех обязательных gates с записанными путями к отчётам.

#### Scenario: Completed change is reviewed
- **WHEN** все implementation tasks отмечены выполненными
- **THEN** eval plan содержит RED/GREEN evidence и завершённый trajectory review для всех применимых player-visible изменений
- **THEN** только после этого delta specs синхронизируются и change архивируется
