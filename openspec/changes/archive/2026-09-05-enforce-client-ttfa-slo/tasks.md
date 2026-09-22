## 0. Baseline

- [x] 0.1 Воспроизвести расхождение server/client TTFA и записать 4301/5142/6757 мс, 43/62 violations и эффект очистки stdout в `eval-plan.md`

## 1. RED — tests and evals first

- [x] 1.1 Добавить server regression на additive timing payload и устойчивый no-access-log launch contract; запустить узкий pytest до implementation и записать failure
- [x] 1.2 Добавить `client/tests/ttfa_runner.gd` и timing oracle в environment runner; запустить до production timing fields и записать failure

## 2. GREEN — minimal implementation

- [x] 2.1 Добавить монотонный client timing breakdown и server action-ready duration; получить green narrow pytest/Godot TTFA
- [x] 2.2 Отключить Uvicorn access log во всех штатных/verification launch paths, перезапустить сервер и подтвердить отсутствие stdout backpressure

## 3. Refactor

- [x] 3.1 Централизовать фиксацию первой мутации и timing snapshot без изменения action semantics; узкие gates остаются green
- [x] 3.2 Добавить TTFA runner в `verify.ps1`, quality gates и документацию; policy validation проходит

## 4. Full evaluation and review

- [x] 4.1 Прогнать все server tests, smoke, level contract, live cast, TTFA, 40-case environment и start playthrough; записать counts/reports
- [x] 4.2 Проверить actual JSON/PNG trajectory и Observer: релевантная мутация видима, client TTFA ≤2000 и teleport animation сохранена
- [x] 4.3 Выполнить quality policy и `openspec validate --all --strict`, затем sync/archive изменения
