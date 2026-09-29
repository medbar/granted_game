## Purpose

Оценивать законность изменения реальности и последствия прецедентов вместо магических действий архивного джина.

## ADDED Requirements

### Requirement: Legal scenarios have independent world oracles
Основной набор SHALL задавать основание, исход, постусловия и допустимые изменения независимо от production-таблицы законов. Слова и status=completed MUST NOT заменять фактический мир.

#### Scenario: Claimed success without consequence
- **WHEN** ответ заявляет открытие выхода, но дверь закрыта, основание неверно или изменился посторонний объект
- **THEN** eval даёт FAIL с конкретными несовпавшими полями

### Requirement: Laws are tested through scope and consequences
Набор SHALL покрывать нормы прототипа, персональный/общий доступ, отказ, reuse/reload прецедента, идемпотентность и retry. Проверяются проходимость, распознавание, урон и время.

#### Scenario: Emergency exit admits a pursuer
- **WHEN** дверь признана аварийным выходом
- **THEN** проверяется проход игрока и полиции, а соседняя закрытая дверь остаётся ограниченной

#### Scenario: Correct refusal is not fulfillment
- **WHEN** ходатайство использует выдуманный закон или недопустимую цель
- **THEN** отрицательный eval проходит только при отказе без мутаций и новых прецедентов; желание не объявляется исполненным

#### Scenario: Precedent survives reuse and reload
- **WHEN** решение применено к другой подходящей двери и сессия загружена заново
- **THEN** проверяются один прецедент, счётчик применений, область и последствия

### Requirement: Live evidence cannot be replaced with fixtures
Frozen и live SHALL быть отдельными режимами одного набора. Live использует настоящую модель без fixture fallback. Неприменимые live cases SHALL быть явно исключены и не засчитываться как PASS.

#### Scenario: Model chooses unrelated valid action
- **WHEN** модель выбирает допустимое, но не запрошенное изменение
- **THEN** независимый oracle даёт FAIL и сохраняет настоящий ответ/diff

#### Scenario: Empty selection
- **WHEN** фильтр не выбирает ни одного применимого сценария
- **THEN** команда завершается ненулевым кодом, а не 0/0 PASS

### Requirement: Reports preserve reviewable evidence
Отчёт SHALL содержать before/after, попытки, expected/actual, diff, mode, hash набора и покрытие по законам/категориям.

#### Scenario: Review a failed case
- **WHEN** проверка не проходит
- **THEN** отчёт показывает нарушенное постусловие без чтения скрытого рассуждения модели
