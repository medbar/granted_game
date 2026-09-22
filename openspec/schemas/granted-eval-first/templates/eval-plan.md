## Change classification

<!-- Select all that apply: deterministic_server, agent_behavior, player_visible, observability, tooling. -->

## Acceptance matrix

| Requirement / scenario | Authoritative oracle | Test or eval added first | Expected RED | Required GREEN gates |
|---|---|---|---|---|
| <!-- scenario --> | <!-- observable postcondition --> | <!-- path / case id --> | <!-- exact failure --> | <!-- gate ids --> |

## Baseline

<!-- Existing trajectory/report and current measured result. For a bug, include reproduction evidence. -->

## RED evidence

<!-- Filled during apply: command, date, and the expected failure observed before production code changed. -->

## GREEN evidence

<!-- Filled during apply: commands, pass counts, report paths, and relevant metrics. -->

## Trajectory review

- [ ] The requested effect is visible in the authoritative game world.
- [ ] The oracle checks postconditions, not generated code, action names, HTTP status, or speech.
- [ ] Retry and terminal failure are honest and visible to the player.
- [ ] No unrelated fallback action can make this case pass.
- [ ] The final real trajectory/report path is recorded above.
