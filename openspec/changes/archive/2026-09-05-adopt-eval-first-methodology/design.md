## Context

Существующие pytest, Godot smoke/live тесты и три eval-runner уже дают несколько уровней проверки, но не связаны с жизненным циклом change. OpenSpec 1.12 поддерживает project-local custom schemas, поэтому eval-first можно сделать обязательной зависимостью артефактов, а не рекомендацией в README.

## Goals / Non-Goals

**Goals:** единый путь от требования до проверенного изменения; world-state oracle для поведения джина; машинная проверка структуры; понятные gates по классу change.

**Non-goals:** менять runtime игры; автоматически вызывать платный live model в каждом локальном verify; доказывать качество одним агрегированным процентом.

## Decisions

### Project-local custom schema

Форкаем официальный `spec-driven` в `granted-eval-first` и добавляем `eval-plan` между specs и design. Это сохраняет штатные OpenSpec команды и одновременно делает acceptance/eval design обязательным до tasks.

Альтернатива — только правила в `config.yaml`. Она отклонена: operation guidance в OpenSpec advisory и не является enforceable check.

### Versioned gate manifest

`openspec/quality-gates.json` хранит классы изменений, обязательные gate ids и команды. JSON выбран, чтобы policy validator работал только на Python stdlib и не добавлял runtime-зависимости.

### Structural validator plus real test runners

Validator проверяет схему, manifest и завершённые change artifacts. Он не симулирует pytest/evals; настоящие команды остаются отдельными gates. `verify.ps1` запускает policy check перед существующими тестами.

### Evidence lives with the change

RED/GREEN команды, результаты и пути к runtime reports записываются в `eval-plan.md`. Runtime-файлы остаются игнорируемыми, но change сохраняет воспроизводимую ссылку и итоговые числа.

## Risks / Trade-offs

- [Процесс станет тяжелее для мелких правок] → `skip_specs` разрешён только для изменений без нового наблюдаемого поведения; gates всё равно выбираются по классу.
- [Live endpoint недоступен] → change остаётся неготовым к архиву либо явно классифицируется так, чтобы live gate не требовался; fixture не подменяет live gate.
- [Markdown evidence можно сфальсифицировать] → validator обеспечивает структуру, а ревьюер проверяет реальные команды/отчёты; в будущем можно подписывать машинные summary.
- [Custom schema API экспериментальный] → схема хранится в репозитории и валидируется локально; обновление OpenSpec выполняется отдельным change.

## Migration Plan

1. Инициализировать OpenSpec и Codex skills.
2. Добавить и валидировать custom schema.
3. Добавить policy regression test и зафиксировать RED.
4. Реализовать manifest, validator и документацию.
5. Получить GREEN, встроить validator в общий verify и архивировать bootstrap change.

Откат: вернуть `schema: spec-driven`, удалить policy hook из `verify.ps1`; существующие тесты и runtime не зависят от OpenSpec.
