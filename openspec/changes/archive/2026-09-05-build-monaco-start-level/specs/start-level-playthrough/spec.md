## Purpose

Определяет воспроизводимый end-to-end сценарий прохождения стартового ограбления через реальные возможности джина и авторитетную модель мира.

## ADDED Requirements

### Requirement: Start level has a frozen completion strategy
Eval suite SHALL содержать последовательность естественных желаний, которая из начального JSON состояния приводит к выполненной миссии через реальные capabilities и client-applied actions.

#### Scenario: Genie-assisted heist succeeds
- **WHEN** frozen playthrough нейтрализует активную охрану, забирает обязательную добычу и открывает extraction door
- **THEN** final JSON содержит всю обязательную добычу в collected/inventory state, открытый выход и `mission.status=completed`
- **THEN** финальный screenshot визуально показывает завершённую миссию

### Requirement: Failure is not masked by retry
Каждый шаг playthrough SHALL проверяться после применения; retry SHALL перепланировать только неполученное postcondition и SHALL завершиться failure после bounded attempts.

#### Scenario: Loot was not collected
- **WHEN** action receipt успешен, но after snapshot оставляет обязательную ценность несобранной
- **THEN** loop не переходит к следующей цели и playthrough остаётся failed или retrying
