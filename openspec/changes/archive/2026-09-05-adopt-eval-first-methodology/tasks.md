## 0. Baseline

- [x] 0.1 Зафиксировать отсутствие OpenSpec/eval-first policy и описать baseline в `eval-plan.md`

## 1. RED — tests and evals first

- [x] 1.1 Добавить `server/tests/test_quality_policy.py` для schema, manifest и завершённых change evidence; запустить отдельно и записать ожидаемый RED

## 2. GREEN — minimal implementation

- [x] 2.1 Добавить `openspec/quality-gates.json` и policy validator; проверить новым узким тестом
- [x] 2.2 Добавить `AGENTS.md`, `CONTRIBUTING.md` и README workflow; проверить policy validator
- [x] 2.3 Включить policy validator в `verify.ps1`; проверить узким тестом ожидаемую команду

## 3. Refactor

- [x] 3.1 Устранить дублирование правил между файлами, сохранив schema и policy tests зелёными

## 4. Full evaluation and review

- [x] 4.1 Запустить `quality_policy` и полный `server_tests`, записать результаты в `eval-plan.md`
- [x] 4.2 Запустить строгую OpenSpec validation для change и custom schema
- [x] 4.3 Синхронизировать delta spec и архивировать change после успешного ревью evidence
