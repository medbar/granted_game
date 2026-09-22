# wish-visual-validation Specification

## Purpose
Связывает семантический успех желания с реальным изменением Godot-сцены и визуальным доказательством, исключая ложнозелёные server-only evals.

## Requirements

### Requirement: Wish success uses authoritative postconditions
Eval SHALL считать желание выполненным только если его конкретные postconditions присутствуют в after-world JSON и применены соответствующими Godot nodes. Посторонний fallback SHALL NOT влиять на успех.

#### Scenario: Requested transformation is missing
- **WHEN** server вернул completed или другое действие, но целевой объект не имеет требуемой формы в Godot snapshot
- **THEN** eval падает с перечнем отсутствующих postconditions

### Requirement: Every frozen environment wish runs client-in-loop
Все cases из frozen environment suite SHALL применяться к Godot scene с reset между cases и проверяться тем же типом postcondition oracle, что server simulation.

#### Scenario: Full visual eval runs
- **WHEN** запускается client visual eval suite
- **THEN** каждый case имеет before JSON, after JSON, applied actions, pass/fail и screenshot reference
- **THEN** общий pass возможен только при успехе каждого case

### Requirement: Screenshots are produced from the validated state
Screenshot SHALL сниматься после того же action feedback и after snapshot, которые были оценены, при фиксированных viewport, level version и camera state.

#### Scenario: Reviewer opens an eval result
- **WHEN** case завершён
- **THEN** связанный PNG показывает визуальное состояние, соответствующее сохранённому after JSON
- **THEN** renderer metadata содержит image dimensions, level id, level version и request id

### Requirement: Prompt evolution is regression-safe
Изменения prompt или fast route SHALL оцениваться на неизменном frozen наборе; выбранная версия SHALL проходить все обязательные cases, а не только улучшать aggregate score.

#### Scenario: Candidate prompt improves one wish but breaks another
- **WHEN** хотя бы один ранее проходивший frozen case перестаёт выполнять postcondition
- **THEN** candidate отклоняется независимо от среднего score
