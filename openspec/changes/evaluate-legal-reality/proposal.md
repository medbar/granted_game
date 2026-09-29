## Why

Основной набор до сих пор оценивает магического джина, хотя канон — Bureaucracy of Reality. Двенадцать новых smoke cases проверяют отдельные поля, но не законность, границы нормы, отказы и последствия прецедентов.

## What Changes

- Frozen/live правовые сценарии с независимыми world-state oracles, допустимым diff и поведенческими проверками.
- Проверки оснований, целей, прав игрока/NPC, отказов, retry, повторного применения, загрузки и идемпотентности.
- Основные quality gates и verify.ps1 используют legal; старые genie gates сохраняются в явном legacy_genie profile.
- Отчёт сохраняет попытки, before/after, несовпадения, покрытие и отдельно выбранные/исключённые live cases.
- Production-правила и промпт не меняются. Найденные gameplay-дефекты остаются FAIL.

## Capabilities

### New Capabilities
- `legal-evaluation`: воспроизводимые юридические сценарии и проверка фактических последствий.

### Modified Capabilities
- `development-workflow`: основной правовой профиль проверок вместо джина.

## Impact

Классы tooling, observability. Eval data/runner, policy, verify.ps1, тесты и документация.
Канон: Bureaucracy of Reality, Precedents, ADR-002/003. Jurisdictions и Applications and Advocacy — proposal, не готовые обязательные правила.
