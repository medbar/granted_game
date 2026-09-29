# Bureaucracy of Reality agent instructions

## Canonical setting knowledge base

The Obsidian vault at `docs/Bureaucracy_of_Reality_Obsidian_Vault/` is the source of truth for
the game's setting, fiction, characters, terminology, gameplay pillars, and accepted design
decisions. Start with `docs/Bureaucracy_of_Reality_Obsidian_Vault/Home.md`.

Before changing game code, agent prompts, content, tests, eval cases, or OpenSpec artifacts, read
the relevant vault notes and design-decision records. All implementation work MUST be consistent
with notes whose frontmatter says `status: canon` and with accepted ADRs. In particular, archived
concepts are historical context rather than current design, and proposal/open-question notes must
not be treated as settled requirements.

If a requested or planned implementation conflicts with the canonical vault, do not silently
encode the contradiction. Surface the conflict and either align the implementation with the
existing canon or update the vault as an explicit, user-approved design decision first. When a
change intentionally alters lore, terminology, a gameplay pillar, or a design decision, update
the affected vault notes in the same change and preserve Obsidian frontmatter and wikilinks.

OpenSpec remains the source of truth for planned and shipped observable behavior, while the vault
is authoritative for the setting and game-design context that behavior must implement. OpenSpec
proposals, tests, and eval oracles must cite or reflect the relevant vault constraints.

## Primary workflow: OpenSpec

OpenSpec is the source of truth for planned and shipped behavior. Before changing observable
server, lawyer-agent, legal reality, world, or client behavior, create or continue a change under
`openspec/changes/` using the default `granted-eval-first` schema. Read `openspec/config.yaml`,
the active change artifacts, and `openspec/quality-gates.json` before implementation.

Use the generated Codex skills when appropriate:

- `$openspec-propose` to create proposal, delta specs, eval plan, design, and tasks;
- `$openspec-apply-change` only after the artifacts are ready;
- `$openspec-sync-specs` and `$openspec-archive-change` only after all gates pass.

If the user explicitly invokes the propose skill, respect its planning boundary and wait for a
separate apply request. For an ordinary explicit implementation request, keep the artifacts
current while implementing; never skip them for an observable behavior change.

## Mandatory TDD and eval-first order

1. Reproduce the baseline and inspect the most relevant existing trajectory or eval report.
2. Write or update the OpenSpec requirements and `eval-plan.md` acceptance matrix.
3. Add the deterministic regression test. For agent behavior, add the eval case and its
   authoritative world state oracle before changing the prompt, tools, loop, or world code.
4. Run the narrow test/eval and observe the intended RED failure. Record the command and failure
   in the change's `eval-plan.md`.
5. Make the smallest production change that can pass the new case.
6. Run the narrow test/eval to GREEN, then refactor while keeping it green.
7. Select the union of gates for all applicable classes in `openspec/quality-gates.json` using
   the default `legal` profile and run every selected automated/live gate. Use `legacy_genie`
   explicitly only when changing the archived genie prototype; it is not evidence for current laws.
8. For player-visible behavior, inspect a real client trajectory and the final game world. Record
   report paths and complete the trajectory checklist.
9. Validate OpenSpec and the quality policy, then sync and archive the change.

Never treat generated Python, an action name, HTTP 200, hidden speech, or an unrelated fallback
action as fulfillment. The requested postcondition in the authoritative game world is the oracle.
If it does not occur after the allowed retries, the eval must fail and the player must see an
honest failure outcome.

Live-model evals supplement deterministic tests; they never replace them. Do not weaken or delete
a test merely to make a prompt or implementation green. Prompt evolution must compare against the
same frozen eval set and review regressions case by case, not only by aggregate score.

## Legal evaluation contract

The primary suite is `server/evals/legal_cases.json`, executed by `run_legal_evals.py`.
Check the legal basis, authoritative world effect, scope for player/NPCs, collateral changes,
precedent creation/reuse/persistence, and honest refusal without mutation. Do not derive expected
answers from production `LAWS`. A passed refusal test is not a fulfilled petition. Live runs must
use actual model answers, report excluded cases, and never substitute frozen decisions on failure.
Keep proposal-only vault ideas separate from the seven implemented prototype laws.
