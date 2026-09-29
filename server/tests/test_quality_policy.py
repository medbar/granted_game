from pathlib import Path
import copy
import json

from scripts.quality_policy import validate_change, validate_repository


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_default_gates_evaluate_laws_not_legacy_genie():
    from scripts.quality_policy import select_gates, validate_manifest
    manifest = json.loads((PROJECT_ROOT / "openspec/quality-gates.json").read_text(encoding="utf-8"))
    assert manifest["default_profile"] == "legal"
    selected = select_gates(manifest, ["agent_behavior", "player_visible"])
    assert {"legal_frozen", "legal_live", "legal_client"} <= set(selected)
    assert not {"monty_live_model", "environment_evolution", "agent_level_live_model"} & set(selected)
    legacy = select_gates(manifest, ["agent_behavior"], profile="legacy_genie")
    assert {"monty_live_model", "environment_evolution", "agent_level_live_model"} <= set(legacy)
    weakened = copy.deepcopy(manifest)
    weakened["change_classes"]["agent_behavior"]["required_gates"].remove("legal_live")
    assert validate_manifest(weakened)


def test_verify_defaults_to_the_legal_profile():
    verify = (PROJECT_ROOT / "verify.ps1").read_text(encoding="utf-8")
    assert '[string]$Profile = "legal"' in verify
    assert "run_legal_evals.py" in verify
    assert "bureaucracy_runner.gd" in verify


def test_repository_quality_policy_is_valid() -> None:
    assert validate_repository(PROJECT_ROOT) == []


def test_verify_runs_quality_policy_before_pytest() -> None:
    verify = (PROJECT_ROOT / "verify.ps1").read_text(encoding="utf-8")

    policy_offset = verify.index("scripts\\quality_policy.py")
    pytest_offset = verify.index("-m pytest")

    assert policy_offset < pytest_offset


def test_completed_change_requires_evidence(tmp_path: Path) -> None:
    change = tmp_path / "missing-evidence"
    (change / "specs" / "demo").mkdir(parents=True)
    (change / ".openspec.yaml").write_text("schema: granted-eval-first\n", encoding="utf-8")
    (change / "proposal.md").write_text("## Why\n\nRegression.\n", encoding="utf-8")
    (change / "design.md").write_text("## Decisions\n\nMinimal.\n", encoding="utf-8")
    (change / "specs" / "demo" / "spec.md").write_text(
        "## ADDED Requirements\n\n"
        "### Requirement: Demo\nThe system SHALL work.\n\n"
        "#### Scenario: Demo\n- **WHEN** invoked\n- **THEN** it works\n",
        encoding="utf-8",
    )
    (change / "eval-plan.md").write_text(
        "## Change classification\n\n- `tooling`\n\n"
        "## Acceptance matrix\n\n| Requirement / scenario | Authoritative oracle | "
        "Test or eval added first | Expected RED | Required GREEN gates |\n"
        "|---|---|---|---|---|\n| demo | state | test | failure | quality_policy |\n\n"
        "## Baseline\n\nMissing.\n\n## RED evidence\n\n"
        "Заполняется после реализации.\n\n## GREEN evidence\n\nTBD\n",
        encoding="utf-8",
    )
    (change / "tasks.md").write_text(
        "## 0. Baseline\n- [x] 0.1 done\n\n"
        "## 1. RED — tests and evals first\n- [x] 1.1 done\n\n"
        "## 2. GREEN — minimal implementation\n- [x] 2.1 done\n\n"
        "## 3. Refactor\n- [x] 3.1 done\n\n"
        "## 4. Full evaluation and review\n- [x] 4.1 done\n",
        encoding="utf-8",
    )

    errors = validate_change(change)

    assert any("RED evidence" in error for error in errors)
    assert any("GREEN evidence" in error for error in errors)
