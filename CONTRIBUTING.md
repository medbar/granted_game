# Разработка Granted

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
   `openspec/quality-gates.json`. Запустите каждый gate и запишите результаты/пути к отчётам.
7. Для видимых игровых изменений проверьте реальную траекторию через игру и `/observer`.
8. Выполните `openspec validate <change> --strict` и policy check. После ревью синхронизируйте
   specs и архивируйте change.

Для агентных изменений минимальный полный набор означает: frozen pytest-oracle, 40 environment
cases, 10 Monty wishes, 20×3 agent levels, Godot client-in-loop и ручной просмотр связанных
before/after/result/PNG. Успех серверной сессии и player-visible conclusion проверяются вместе.
Изменения wish pipeline дополнительно обязаны пройти `client/tests/ttfa_runner.gd`: временем первого
действия считается только фактическая мутация Godot world, а лимит каждого поддерживаемого кейса —
2000 мс. Реплика, HTTP-ответ и начало анимации не являются oracle.

## Что считается выполнением желания

Только требуемое постусловие в авторитетном состоянии мира и его видимое отражение в клиенте.
Сгенерированный код, имя действия, ответ HTTP 200, слова джина или посторонний fallback не являются
успехом. Невыполненное после retry желание остаётся красным в eval и явно показывается игроку.

## Уровни проверки

- `deterministic_server`: policy validator и весь pytest.
- `agent_behavior`: дополнительно 40 environment cases, live Monty cases и live agent levels.
- `player_visible`: дополнительно Godot smoke, client-in-loop и ручное trajectory review.
- `observability` и `tooling`: policy validator и pytest; добавляйте более узкие проверки в
  acceptance matrix конкретного change.

Команды и ожидаемые evidence хранятся в `openspec/quality-gates.json`. Полный локальный серверный
цикл начинается так:

```powershell
server\.venv\Scripts\python.exe server\scripts\quality_policy.py --root .
server\.venv\Scripts\python.exe -m pytest server\tests -p no:cacheprovider
```

Для стандартного server + Godot набора используйте `verify.ps1`. Установка CLI для разработки:

```powershell
npm install -g @fission-ai/openspec@latest
openspec --version
```

OpenSpec требует Node.js 20.19 или новее. Проект игры от Node.js не зависит; он нужен только для
команд методологии.
