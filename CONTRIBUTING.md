# Разработка Bureaucracy of Reality

Основной процесс проекта — OpenSpec с project-local схемой `granted-eval-first`. Её отличие от
обычного spec-driven процесса: после требований и до дизайна обязательно создаётся `eval-plan.md`.

## Рабочий цикл

1. Создайте change: в Codex — `$openspec-propose "описание"`, в CLI —
   `openspec new change <name>` и следуйте `openspec instructions`.
2. Согласуйте `proposal.md` и проверяемые сценарии в `specs/`.
3. В `eval-plan.md` сопоставьте каждому сценарию world/UI/API oracle, тест, eval-кейс, ожидаемый RED
   и GREEN gates.
4. Добавьте тест и eval-кейс, запустите их и убедитесь, что они падают по ожидаемой причине.
5. Только после RED меняйте production-код или промпт; доведите узкую проверку до GREEN и
   отрефакторьте.
6. Выберите все классы change и объедините их `required_gates` из
   `openspec/quality-gates.json` в профиле `legal` (по умолчанию). Запустите каждый gate и
   запишите результаты/пути к отчётам.
7. Для видимых игровых изменений проверьте реальную траекторию через игру и `/observer`.
8. Выполните `openspec validate <change> --strict` и policy check. После ревью синхронизируйте
   specs и архивируйте change.

Для текущего адвоката обязательны полный pytest, 32 frozen-сценария законов и 21 live-сценарий.
Ещё 11 frozen-only сценариев не засчитываются как live-успехи. Для видимых изменений дополнительно
нужны legal smoke, реальный клиентский прогон и просмотр before/after/result/PNG.
Старые 40 environment / 10 Monty / 20×3 agent levels и старый TTFA-runner относятся к профилю
`legacy_genie`: это регрессии архивного режима, а не критерии исполнения законов новой кампании.
Текущий юридический отчёт измеряет длительность шага, но не обещает измерение TTFA.

## Что считается выполнением желания

Только требуемое постусловие в авторитетном состоянии мира и его видимое отражение в клиенте.
Сгенерированный код, имя действия, ответ HTTP 200, слова адвоката или посторонний fallback не являются
успехом. Невыполненное после retry желание остаётся красным в eval и явно показывается игроку.

Проверяются также основание, область действия, права игрока/NPC, отсутствие побочных изменений,
запись и повторное использование прецедента. PASS теста ожидаемого отказа не означает исполнение:
для этого отчёт отдельно хранит `passed` и `decision_status`. Сетевая ошибка не считается отказом.
Ожидаемые значения фиксируются независимо от production `LAWS`; live-ответ нельзя подменить fixture.

## Уровни проверки

- `deterministic_server`: policy validator, весь pytest, legal frozen.
- `agent_behavior`: policy validator, весь pytest, legal frozen и live.
- `player_visible`: policy validator, весь pytest, legal smoke/client и ручное trajectory review.
- `observability`: policy validator и pytest.
- `tooling`: policy validator, pytest и legal frozen.

Классы объединяются: изменение поведения адвоката в игре требует как `agent_behavior`, так и
`player_visible`. Явный `-Profile legacy_genie` выбирает прежнюю матрицу архивного режима.

Команды и ожидаемые evidence хранятся в `openspec/quality-gates.json`. Полный локальный серверный
цикл начинается так:

```powershell
server\.venv\Scripts\python.exe server\scripts\quality_policy.py --root .
server\.venv\Scripts\python.exe -m pytest server\tests -p no:cacheprovider
server\.venv\Scripts\python.exe server\scripts\run_legal_evals.py --mode frozen
server\.venv\Scripts\python.exe server\scripts\run_legal_evals.py --mode live
```

Для полного legal + Godot набора используйте `verify.ps1 -GodotPath <exe> -SkipSync`:
тестовый сервер запускается отдельно на 8003, текущий сервер игры на 8000 не затрагивается.
Формат сценариев и артефактов описан в `server/evals/README.md`. Установка CLI для разработки:

```powershell
npm install -g @fission-ai/openspec@latest
openspec --version
```

OpenSpec требует Node.js 20.19 или новее. Проект игры от Node.js не зависит; он нужен только для
команд методологии.
