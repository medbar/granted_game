## MODIFIED Requirements

### Requirement: Gates depend on change class
Проект SHALL хранить версионируемую матрицу проверок для deterministic_server, agent_behavior, player_visible, observability и tooling. Основной профиль SHALL проверять правовой мир. Архивные проверки джина SHALL запускаться отдельным явно выбранным legacy_genie профилем.

#### Scenario: Player-visible agent change is verified
- **WHEN** change классифицирован как agent_behavior и player_visible
- **THEN** проходят полный deterministic suite, frozen/live legal eval, smoke нового режима, правовой client-in-loop и ручное ревью траектории

#### Scenario: Historical genie code is changed
- **WHEN** change затрагивает архивного джина
- **THEN** дополнительно выбираются legacy_genie gates по применимым классам; старые регрессии сохранены
