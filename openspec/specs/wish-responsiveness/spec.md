# wish-responsiveness Specification

## Purpose
Гарантировать, что скорость джина измеряется по первому реальному изменению игрового мира, которое видит игрок, а не по внутреннему решению модели или сетевому ответу.

## Requirements

### Requirement: Client-observed first world action SLO
Для любого поддерживаемого fast-path желания система MUST применить первую относящуюся к желанию мутацию авторитетного Godot-мира не позднее 2000 мс после подтверждения желания игроком.

#### Scenario: Supported wish changes the world in time
- **WHEN** игрок подтверждает поддерживаемое fast-path желание в работающем клиенте
- **THEN** соответствующее свойство или множество объектов serialized world изменяется не позднее 2000 мс
- **AND** `client_ttfa_ms` измеряется в момент этой мутации монотонными часами

#### Scenario: Feedback and animation are not first action
- **WHEN** джин произносит фразу, растворяется, сервер отвечает HTTP 202 или публикует action label без мутации мира
- **THEN** система MUST NOT завершать измерение `client_ttfa_ms`

### Requirement: Teleport animation does not delay the world mutation
Система MUST сохранять визуальный переход джина длительностью приблизительно одну секунду, но MUST NOT последовательно блокировать готовую мутацию на всю анимацию.

#### Scenario: Ready action and teleport overlap
- **WHEN** клиент получает готовое действие с целью для телепортации
- **THEN** телепортация и применение действия исполняются как перекрывающиеся части одной сцены
- **AND** serialized world отражает действие до завершения полного визуального перехода

### Requirement: TTFA stage diagnostics
Система SHALL сохранять для каждого желания добавочные длительности этапов initial response, action ready и client world mutation, достаточные для локализации задержки.

#### Scenario: Successful wish reports timing breakdown
- **WHEN** клиент применил первое действие
- **THEN** trajectory/eval result содержит `submit_to_initial_response_ms`, `submit_to_action_ready_ms`, `action_ready_to_mutation_ms` и `client_ttfa_ms`
- **AND** значения неотрицательны и `client_ttfa_ms` соответствует суммарной наблюдаемой задержке до мутации

#### Scenario: SLO violation remains visible
- **WHEN** `client_ttfa_ms` превышает 2000
- **THEN** latency eval или аппаратный visual eval MUST завершиться ошибкой и telemetry MUST увеличить client-observed violation counter
- **AND** система MUST NOT подменять значение более быстрым server-side timing

#### Scenario: Software renderer is not a latency oracle
- **WHEN** visual artifact eval работает через CPU software renderer
- **THEN** report MUST пометить timing profile как неавторитетный, сохранить каждое превышение как warning и продолжить world/PNG oracle
- **AND** отдельный renderer-independent TTFA eval MUST оставаться обязательным hard gate

### Requirement: Retry does not duplicate the first mutation
Повторное планирование или повторная доставка того же шага MUST NOT применять уже подтверждённую мутацию второй раз.

#### Scenario: Delayed feedback causes a retry
- **WHEN** первый world action уже применён, а feedback задержан или повторён
- **THEN** идентификатор шага позволяет серверу отклонить несовпадающий или повторный feedback
- **AND** клиент не создаёт дубликат объекта и не повторяет необратимую мутацию
