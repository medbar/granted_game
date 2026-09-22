## 0. Baseline

- [x] 0.1 Зафиксировать source-аудитом производные wall ids и скрывающий проблему последовательный fixture

## 1. RED — tests and evals first

- [x] 1.1 Добавить в `level_contract_runner.gd` assertion exact JSON identity и получить RED на `wall_%02d`

## 2. GREEN — minimal implementation

- [x] 2.1 Сохранить `walls[*].id` при загрузке и использовать в construction/draw; получить `LEVEL_CONTRACT_OK`

## 3. Refactor

- [x] 3.1 Удалить оставшиеся generated wall ids и проверить uniqueness/count contract

## 4. Full evaluation and review

- [x] 4.1 Прогнать server tests, Godot smoke/live/40-case/playthrough, просмотреть representative PNG
- [x] 4.2 Заполнить evidence, выполнить quality policy и strict OpenSpec validation, sync/archive
