## Purpose

Делает функциональность джина модульной и управляемой во время работы сервера без изменения монолитного prompt или перезапуска процесса.

## ADDED Requirements

### Requirement: Capabilities are owned by plugins
Каждая доступная Monty capability SHALL принадлежать ровно одному plugin manifest, содержащему id, version, description, capability names и default enabled state. Runtime SHALL строить доступный API и prompt fragment только из enabled plugins.

#### Scenario: Server starts with plugins
- **WHEN** registry загружает manifests
- **THEN** каждый exposed capability имеет владельца и описание
- **THEN** конфликт имён или невалидный manifest отклоняется с диагностируемой ошибкой

### Requirement: Plugins toggle without restart
API SHALL позволять включить, выключить и перечитать plugin manifests во время работы. Следующий agent turn SHALL увидеть новый набор функций без перезапуска FastAPI.

#### Scenario: Creation plugin is disabled
- **WHEN** оператор выключает creation plugin
- **THEN** creation capabilities исчезают из agent prompt и runtime allow-list
- **THEN** вызов отключённой capability возвращает честную unavailable ошибку и не меняет мир
- **THEN** повторное включение немедленно восстанавливает capability

### Requirement: Plugin state is observable
Публичный debug API SHALL показывать plugin id, version, enabled state и capabilities без раскрытия секретов или скрытых curse instructions.

#### Scenario: Observer requests plugin state
- **WHEN** вызывается plugin status endpoint
- **THEN** возвращается полный список загруженных plugins и текущая revision registry
