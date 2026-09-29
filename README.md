# Bureaucracy of Reality

Текущий канон — Obsidian Vault в [docs/Bureaucracy_of_Reality_Obsidian_Vault/Home.md](docs/Bureaucracy_of_Reality_Obsidian_Vault/Home.md).
Обычный клерк заключает договор с дьяволом-адвокатом. Желания проходят через правовые основания,
изменяют действующий мир и оставляют прецеденты.

Новый стандартный запуск открывает первый игровой прототип: отдельная комната → метро → работа → добровольный
контракт → городской квартал с полицией → выход через кордон. Это начало переработки, а не готовая
открытая кампания. Конкретные нормы квартала — тестируемые правила прототипа; неутверждённые
proposal-заметки vault не считаются реализованным каноном.

## Запуск нового режима

Сервер: существующий run_backend.ps1 либо из server — .venv/Scripts/python.exe -m uvicorn
app.main:app --host 127.0.0.1 --port 8000 --no-access-log. Клиент: Godot 4.7.2 с --path client.

В квартире WASD — подойти к еде, кровати, письменному столу или двери; E или щелчок по ближайшему
предмету — взаимодействовать. Выход «Отправиться на работу» запускает короткую поездку в метро.
На работе одна кнопка «ОБРАБОТАТЬ»: после двух документов — автоматическая поездка домой.
Появившийся договор можно подписать у стола или игнорировать. После подписи выход ведёт в город.
Общий квартал до этого не показывается. Сохранения не сбрасываются: если вы уже в городе,
для просмотра нового пролога выберите «Новая сессия».
В городе: WASD — движение, Shift — красться, E — сесть в автомобиль/выйти, пробел — ввод желания,
Enter — отправить, Esc — вернуть управление движению, J — реестр. Во время рассмотрения желания
город продолжает жить. Состояние сессии сохраняется на сервере и восстанавливается при запуске.

Примеры: «Пусть эта дверь считается аварийным выходом», «Пусть полиция забудет моё описание»,
«Пусть мой пропуск считается действительным», «Пусть машина считается скорой помощью».
Также доступны регистрация/переклассификация rock/crate/tree/npc/police, изменение света и времени.
Неподдерживаемые эффекты отклоняются с видимым объяснением; список действий пока ограничен.

API нового режима: POST /bureau/sessions; GET /bureau/sessions/{id}; POST command, tick, wish
внутри этой сессии. Модель и ключи берутся из прежних GENIE_AGENT_* переменных server/.env.
Локальные сессии: server/runtime/bureaucracy/sessions. Траектории игрового API и события доступны
в прежнем /observer; новые frozen/live legal eval сохраняются в server/runtime/evals/legal-*.

## Проверка нового режима

Основной набор проверяет семь законов прототипа: основание, изменение мира, область действия,
права игрока/NPC, отсутствие побочных изменений, сохранение и повторное использование прецедентов.
В нём 32 frozen-сценария и 21 сценарий с настоящей моделью. Ещё 11 проверок намеренно повреждённых
решений/отказов выполняются только с фикстурами и явно отмечаются исключёнными из live, а не успешными.

```powershell
# Из корня репозитория
server\.venv\Scripts\python.exe server\scripts\run_legal_evals.py --mode frozen
server\.venv\Scripts\python.exe server\scripts\run_legal_evals.py --mode live
./verify.ps1 -GodotPath "C:\path\to\Godot_v4.7.2-stable_win64_console.exe" -SkipSync
```

`verify.ps1` по умолчанию запускает legal-профиль: весь pytest, оба eval-режима, smoke и реальный
клиентский прогон. Его отдельный сервер использует порт 8003 и не останавливает текущую игру на 8000.
Отчёт `summary.json` разделяет прохождение проверки и исход обращения (`completed`/`failed`/`rejected`),
сохраняет ожидаемые/фактические значения, попытки модели, before/after и hash набора.
Результаты пролога и PNG: `client/test-artifacts/daily-routine`;
городского client-in-loop: `client/test-artifacts/bureaucracy`.
Формат и выбор отдельных сценариев: [server/evals/README.md](server/evals/README.md).

Старые проверки джина доступны только явно: `verify.ps1 ... -Profile legacy_genie`.
`run_bureaucracy_evals.py` и его 12 простых cases оставлены как исторический smoke-набор,
но не заменяют юридические проверки.

OpenSpec change: introduce-bureaucracy-campaign. Текущие ограничения и результаты проверок
зафиксированы в его eval-plan.md. Переход эвалов: `evaluate-legal-reality`.
Архивный прототип ниже сохраняется для регрессий и сравнения; его проверки запускаются
с явным профилем `legacy_genie`, а не стандартным `verify.ps1`.

---


# Granted: Your Wish, My Magic — архивный прототип

Явный запуск: Godot --path client res://scenes/main.tscn. Следующее описание относится к старому режиму.

Playable top-down prototype where an adventurer asks their floating genie for any wish in natural language. The player is not a mage and never casts a spell themselves:

`free-form wish text + genie origin + current world state → genie magic → universal world actions`

The genie is a visible companion that follows the player, listens in slow motion, and becomes the origin of every magical effect. There are no canned wish or spell classes: the backend activates hidden semantic anchors from text, selects targets from the live world, applies fixed material rules, and returns a generic plan for the genie to enact.

## What is implemented

- Data-driven Monaco-like heist level with ten colour-coded rooms, eleven working doors, three guards, a civilian, patrol cones, required loot, extraction, walls, props, water, and a visible hovering genie.
- Separate physical combat: `LMB` swings the adventurer's sword through a short frontal arc, damages and knocks back enemies, and can kill them after repeated hits.
- `SPACE` asks the genie for a wish at `Engine.time_scale = 0.35`; the world never pauses.
- Unicode/Cyrillic wish input, up to 300 characters, with `Enter` to ask and `Esc` to reconsider.
- Wishes are text-only: mouse motion, sword state, and attack data never enter the `/wish` request; the sword is disabled while the wish input is open.
- Deterministic FastAPI `/wish` pipeline with exactly 100 configurable hidden anchors; `/cast` remains as a compatibility alias.
- Geometry, scale, movement, and targets are derived from words such as `стена`, `кольцо`, `всех`, and `передо мной`, plus the genie's position/facing and the world snapshot.
- Universal target resolution, material rules, world actions, persistent-effect descriptions, and ten visual primitives.
- Water ↔ ice, water → steam, ignition/burning, wet electrical conduction, mass-aware force, heat/cold damage, slow, harm, and healing.
- Lift/levitation, deep freeze, poison, sharp-force and crush/material interactions, water extinguishing, and electrical propagation through a pool.
- Gameplay-capable projectile, beam, wall, ring, and field entities that continue resolving contacts after `/wish`.
- F3 genie-wish view for anchors, direction features, intent, selected targets, fired world rules, and REST latency.
- Backend failure recovery: time returns to normal and the genie visibly fails near its own position.
- 227 automated semantic, Monty-sandbox, text-intent, world-rule, agent-infrastructure,
  simulation, frozen-eval, plugin, observability, level-contract, and API tests.

## Requirements

- [Godot 4.7.2 Standard](https://godotengine.org/download/archive/4.7.2-stable/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.11+ (uv can install/manage it)
- Node.js 20.19+ and OpenSpec CLI are needed only when planning/reviewing development changes

## Development methodology

OpenSpec is the primary workflow for this repository. Granted uses a project-local
`granted-eval-first` schema with five ordered artifacts:

```text
proposal → specs → eval plan → design → TDD tasks → apply → verify → archive
```

Every observable behavior change starts by defining the authoritative world/UI postcondition and
adding its test/eval case. The new case must produce the expected RED before production code or the
agent prompt changes; implementation then makes it GREEN, after which the change-specific gate set
and a real trajectory are reviewed. Generated code, an action label, HTTP success, or genie speech
alone never count as wish fulfillment.

The rules are in `AGENTS.md` and `CONTRIBUTING.md`; gate selection and commands are versioned in
`openspec/quality-gates.json`. In Codex, start planning with `$openspec-propose`, then apply the
reviewed artifacts with `$openspec-apply-change`. The generated skills live under `.agents/skills/`.

The canonical start level is `client/levels/monaco_start.json`. Both Godot and FastAPI load this
same document; rooms, walls, doors, actors, props, mission rules, palette, and initial state are not
maintained as a second hardcoded layout. Every player-visible agent change is accepted only after a
before/after world JSON comparison and, for the full client gate, a real rendered PNG.

## Run

The simplest launch starts both processes and shuts the backend down when the game closes:

```powershell
./run_all.ps1 -GodotPath "C:\path\to\Godot_v4.7.2-stable_win64.exe"
```

Or open two terminals from this folder.

Backend:

```powershell
./run_backend.ps1
```

Client:

```powershell
./run_game.ps1
```

Alternatively, import `client/project.godot` in the Godot Project Manager and press F6/F5 after the backend reports that it is listening on `127.0.0.1:8000`.

## Controls

| Input | Action |
|---|---|
| `WASD` | Move |
| Mouse | Aim the adventurer and sword |
| `LMB` | Swing the sword |
| `Space` | Ask the genie for a wish |
| `Enter` | Ask the genie to fulfill the wish |
| `Esc` | Reconsider the wish |
| `F3` | Toggle developer wish interpretation |
| `R` | Reset the sandbox |

Useful first wishes:

- `назад`
- `сильно отбрось всех врагов от меня`
- `заморозь воду`
- `подожги дерево`
- `электричество по воде`
- `маленькое солнце`
- `создай огонь под водой`

## Test the backend

```powershell
cd server
uv sync
uv run pytest
```

To run the backend suite, isolated Godot gameplay smoke test, and live Godot↔FastAPI cast scenarios together:

```powershell
./verify.ps1 -GodotPath "C:\path\to\Godot_v4.7.2-stable_win64_console.exe"
```

If `uv` is not on `PATH`, the PowerShell scripts also accept `-UvPath "C:\path\to\uv.exe"`.
On an already-synchronized checkout, `verify.ps1 -SkipSync` reuses `server/.venv`.

Health and interactive API documentation are available at:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/debug/anchors`
- `http://127.0.0.1:8000/debug/config`
- `http://127.0.0.1:8000/observer` — readable logs, traces, metrics, JSON/PNG eval artifacts, and hot plugin controls

## Where to tune wish interpretation

| Concern | File |
|---|---|
| 100 concepts, synonyms, thresholds, gameplay mappings | `server/config/anchors.yaml` |
| Wish slow-motion, influence weights, top-K, power, semantic model | `server/config/spell_settings.yaml` |
| Mass, conductivity, flammability, hardness | `server/config/materials.yaml` |
| Phase, ignition, conduction, force thresholds | `server/config/reactions.yaml` |
| Geometry → primitive and appearance colors | `server/config/visual_mapping.yaml` |
| Client backend URL, wish-time scale, snapshot radius, timeout | `client/config/gameplay.json` |

The `.yaml` files use JSON-compatible YAML so the backend can load them with Python's standard library and keep startup lean.

## Architecture

```text
Godot world snapshot + genie origin
        │
wish text ── SemanticResolver ── 100 continuous anchor activations
genie position/facing ────────── text-only direction and origin
        │
        ▼
Wish interpretation (compatible SpellIntentBuilder)
        │
        ├── TargetResolver
        ├── WorldResolver ── universal material/reaction rules
        └── VisualResolver ── generic visual descriptors
        │
        ▼
Plan → genie-origin world actions + runtime visuals
```

The default semantic backend is AITUNNEL with `pplx-embed-v1-0.6b`. Copy `server/.env.example` to `server/.env`, put the API key in `AITUNNEL_API_KEY`, and start the backend normally. Anchor embeddings are batched and cached for the lifetime of the server; each wish only embeds its query chunks. Set `GRANTED_SEMANTIC_BACKEND=char_ngram` for the deterministic offline fallback, or `sentence_transformer` to use the optional local MiniLM backend.

## Agent prototype

With `GRANTED_AGENT_MODE=true`, `/wish` is handled by a PydanticAI agent using the
OpenAI-compatible Aspen endpoint and `qwen3-35-36`. The model writes a short Python
program that is executed by Pydantic Monty, not CPython `exec`. Imports, unbounded loops,
dunder access, filesystem/network access, and unknown game capabilities are unavailable.
The genie has no locomotion function: a targeted action makes its image appear beside the
target automatically.

The interactive client uses the asynchronous `POST /wish/jobs` protocol, so GLM reasoning never
blocks player movement or combat. The server releases one action, the client applies it and posts
a fresh world snapshot to `POST /wish/jobs/{job_id}/feedback`. Only a verified change advances the
loop; a missing postcondition triggers replanning, up to three attempts. TTFA is measured when the
client actually applies the first mutation, not when the plan or acknowledgement is produced. The
client records submit-to-response, submit-to-action-ready, action-ready-to-mutation, and total TTFA
offsets. `client/tests/ttfa_runner.gd` fails if any supported representative wish exceeds 2000 ms.
The 40-case visual runner stores the same breakdown and enforces it on a hardware renderer; an
explicitly labelled llvmpipe run keeps raw warnings while the dedicated headless latency gate remains
authoritative.

The program may make several ordered capability calls in one model decision. Every call is still
validated, applied, timed, and logged as a separate world step. This supports multi-target wishes
and dependent logic without turning teleportation into a separate action. A fact such as the gate
code is only usable after an earlier action has learned it from the keeper.

Three authoritative server-side test levels exercise the current vertical slice:

- `closed_door` — an ordinary locked door with several physical and creative solutions;
- `three_enemies` — three hostiles that may be killed, restrained, displaced, transformed, or pacified;
- `whispering_gate` — an indestructible code-locked gate and a neutral keeper who knows the secret.

Create a session, send a wish, and inspect the resulting world with:

```powershell
cd server
.\.venv\Scripts\python.exe scripts\agent_cli.py new closed_door
.\.venv\Scripts\python.exe scripts\agent_cli.py wish <session-id> "Открой дверь"
.\.venv\Scripts\python.exe scripts\agent_cli.py show <session-id>
```

The reproducible multi-strategy evaluation saves a detailed JSON report under
`server/runtime/evals/` and succeeds only when all 20 strategies pass all three levels with 20
distinct action signatures. It also rejects a completed server world when the player-visible agent
conclusion still says `partial` or `impossible`:

```powershell
cd server
.\.venv\Scripts\python.exe scripts\run_agent_levels.py --concurrency 1 --max-turns 4
```

The focused Monty suite contains ten wishes resembling interactive play: kill or burn an enemy,
cover it in blood, freeze all water, push an enemy, heal the player, turn a rock to gold, create a
sword, pacify a mind, and make an NPC speak. Deterministic fixture programs are part of `pytest`;
the same semantic cases can be run through the live GLM model with:

```powershell
cd server
.\.venv\Scripts\python.exe scripts\run_monty_evals.py
```

The environment-level evolution suite contains exactly 40 wishes covering world objects, physical
walls, phase-through-wall states for every actor role, burning, wetness, invisibility, explicit
aggro targets, inventory items, traps, destruction, creation variants, outfits, transformations,
pause/resume, world speed, and lighting. It scores the mutated authoritative world, not the
generated code or action names. Run and evolve consecutive generations with:

```powershell
cd server
.\.venv\Scripts\python.exe scripts\run_agent_evolution.py --generation 1
.\.venv\Scripts\python.exe scripts\evolve_agent_prompt.py --from-report runtime\evolution\generation-1.json --next-generation 2
.\.venv\Scripts\python.exe scripts\run_agent_evolution.py --generation 2
```

Reports and prompt snapshots are stored under `server/runtime/evolution/`. The same 40
postconditions are permanent offline regression tests.

If the external model endpoint is temporarily unavailable, rerun the same evaluation with
`--resume`. Passed levels are restored from the atomic checkpoint and only incomplete or failed
levels are sent again.

Soft curses are defined in `server/config/curses.json`. Their hidden instructions are injected
into the agent prompt, while the client receives only a title, sigil, severity, and observable
symptom from `/genie/state` or the wish response.

Local observability artifacts are intentionally shaped for later production integrations:

- `server/runtime/logs/agent-events.jsonl` — structured events suitable for Alloy/Loki ingestion.
- `server/runtime/metrics/granted_game.prom` — Prometheus textfile-collector metrics.
- `server/runtime/trajectories/*.json` — complete agent trajectories, prompt versions, token
  usage, and baseline eval scores for offline analysis and future prompt evolution.
- `server/runtime/sessions/*.json` — authoritative world state after each agent turn.
- `server/runtime/evals/*.json` — cross-level evaluation reports with prompts, actions, latency,
  signatures, and world snapshots after every turn.
- `server/runtime/evolution/*.json` — per-generation 40-case environment results and evolved
  prompt snapshots.

The runtime directory is ignored by Git. Prompt changes are versioned in
`server/config/agent_prompt.json`, so trajectories from different variants can be compared.
TTFA observability includes server-side and client-observed gauges, a canonical
`granted_agent_time_to_first_action_milliseconds` gauge, the 2000 ms SLO, and a violation counter.
The standard PowerShell launchers disable Uvicorn's per-request access log so an unread terminal
pipe cannot stall the event loop; domain events and errors remain available through JSONL and the
server error log.

Genie capabilities are declarative trusted plugins under `server/plugins/`. `GET /genie/plugins`
returns their manifests and flattened capability list; `PUT /genie/plugins/{plugin_id}` enables or
disables a plugin without restarting the server, and `POST /genie/plugins/reload` reloads manifests.
The enabled registry simultaneously controls the model prompt and Monty runtime allow-list, so a
disabled capability is neither advertised nor executable. The same controls are available in the
`ПЛАГИНЫ` screen of Observer.

The `АРТЕФАКТЫ` screen reads `client/test-artifacts/` and pairs each real Godot `after.png` with
its `before.json`, `after.json`, and `result.json`. The 40-case client runner and the three-step
start-level playthrough are the authoritative visual regression set. The separate
`client/test-artifacts/ttfa/summary.json` contains stage-by-stage client timing for the latency SLO.

## Scope intentionally excluded

No campaign, progression, mana economy, procedural generation, multiplayer, production art/audio, voice input, accounts, or generative LLM game master. The prototype is focused on whether asking a persistent genie for free-form wishes under real-time pressure produces understandable, discoverable laws and entertaining unintended consequences.
