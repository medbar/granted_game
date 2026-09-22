## Why

Последний полный Godot eval показал ложное ощущение быстрого джина: сервер сообщил первое действие за 56 мс (median), но реальная client-observed мутация мира заняла до 6757 мс, а 43 из 62 накопленных client samples нарушили SLO. Игрок оценивает задержку по изменению мира, поэтому серверная цифра не может считаться успехом.

## What Changes

- Ввести отдельный контракт `wish-responsiveness`: для поддерживаемых fast-path желаний первая относящаяся к желанию мутация Godot-мира MUST произойти не позднее 2000 мс после отправки.
- Измерять и сохранять этапы submit → initial response → action ready → world mutation, чтобы задержку нельзя было спрятать за одним агрегатом.
- Добавить отдельный Godot TTFA eval и сохранять client TTFA breakdown в полном 40-case environment eval; hard timing gate применяется в latency-профиле и на аппаратном renderer, а программный llvmpipe-профиль помечается как неавторитетный для latency.
- Убрать задержку между получением готового действия и применением мутации, сохранив секундную визуальную телепортацию джина.

## Capabilities

### New Capabilities

- `wish-responsiveness`: наблюдаемое игроком время до первого релевантного изменения мира и диагностические этапы этого пути.

### Modified Capabilities

- Нет.

## Change classification

- `player_visible`
- `observability`
- `agent_behavior`

## Measurable outcome

Каждый frozen fast-path кейс в изолированном Godot TTFA eval имеет `client_ttfa_ms <= 2000`. Полный environment report содержит client/server breakdown, renderer profile и не скрывает ни одного нарушения; аппаратный профиль не проходит при нарушении SLO.

## Non-goals

- Не сокращать секундную анимацию растворения/проявления джина.
- Не считать реплику, анимацию ожидания, HTTP 202 или серверный action label первым действием.
- Не обещать двухсекундный planning для пока не поддерживаемого модельного long-tail без fast-path интерпретации.

## Impact

Godot wish polling/action sequencing и eval runners, payload/telemetry agentic job manager, Observer metrics, README и quality gates. Wire compatibility сохраняется: новые timing fields добавочные.
