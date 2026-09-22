## Change classification

- `tooling`
- `observability`

## Acceptance matrix

| Requirement / scenario | Authoritative oracle | Test or eval added first | Expected RED | Required GREEN gates |
|---|---|---|---|---|
| OpenSpec is primary / behavior change starts with artifacts | Default schema is `granted-eval-first`; schema requires `eval-plan` before tasks | `server/tests/test_quality_policy.py::test_repository_quality_policy_is_valid` | Policy validator or manifest is absent | `quality_policy`, `server_tests` |
| Evaluation is defined before implementation / agent behavior is changed | Custom schema contains eval-plan artifact and world-state oracle rules | same policy regression test | Schema lacks required eval-plan dependency and oracle language | `quality_policy`, `server_tests` |
| TDD order is enforced / regression fix is implemented | Tasks template orders RED before production implementation | same policy regression test | Required task headings/order are missing | `quality_policy`, `server_tests` |
| Gates depend on change class / player-visible agent change is verified | Manifest maps each class to explicit gate ids | same policy regression test | Gate manifest is absent or references unknown gates | `quality_policy`, `server_tests` |
| Archive requires evidence / completed change is reviewed | Validator rejects completed changes without RED/GREEN evidence | `server/tests/test_quality_policy.py::test_completed_change_requires_evidence` | Synthetic completed change without evidence is accepted | `quality_policy`, `server_tests` |

## Baseline

До change в репозитории не было `openspec/`, общей матрицы gates, обязательного eval plan и автоматической проверки порядка TDD. Существующие pytest и eval-скрипты запускались независимо и не определяли, какой набор обязателен для конкретного типа изменения.

## RED evidence

2026-09-05 до добавления validator был выполнен
`server/.venv/Scripts/python.exe -m pytest tests/test_quality_policy.py -q -p no:cacheprovider`.
Collection завершился с кодом 1 и ожидаемым `ModuleNotFoundError: No module named
'scripts.quality_policy'`. После первой минимальной реализации тот же тест обнаружил вторую
конкретную ошибку контракта: `AGENTS.md missing policy marker world state`.

## GREEN evidence

2026-09-05 узкий policy-набор прошёл: `3 passed`. Затем обязательные для классов `tooling` и
`observability` gates дали:

- `quality_policy`: `Granted quality policy: PASS`;
- `server_tests`: `149 passed in 7.13s`;
- `openspec schema validate granted-eval-first --verbose`: schema valid;
- `openspec validate adopt-eval-first-methodology --strict`: change valid;
- `git diff --check`: ошибок whitespace нет (только предупреждения Git о будущем LF→CRLF).

## Trajectory review

- [x] Не применимо: change не меняет поведение джина или клиентский игровой опыт.
