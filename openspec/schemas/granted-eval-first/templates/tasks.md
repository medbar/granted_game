## 0. Baseline

- [ ] 0.1 Reproduce the current behavior and record the baseline evidence in eval-plan.md

## 1. RED — tests and evals first

- [ ] 1.1 Add the smallest deterministic regression test and run it to record the intended failure
- [ ] 1.2 Add the change-specific eval case before agent behavior changes and record its intended failure

## 2. GREEN — minimal implementation

- [ ] 2.1 Implement only enough production behavior to pass the new narrow test and eval

## 3. Refactor

- [ ] 3.1 Improve the implementation without changing behavior and keep the narrow gates green

## 4. Full evaluation and review

- [ ] 4.1 Run all mandatory gates selected from openspec/quality-gates.json and record their reports
- [ ] 4.2 Review a real player-visible trajectory when applicable and complete the eval-plan checklist
- [ ] 4.3 Run OpenSpec and quality-policy validation before archive
