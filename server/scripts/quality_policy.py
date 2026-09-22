from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEFAULT_SCHEMA = "granted-eval-first"
REQUIRED_CLASSES = {
    "deterministic_server",
    "agent_behavior",
    "player_visible",
    "observability",
    "tooling",
}
REQUIRED_SKILLS = {
    "openspec-propose",
    "openspec-explore",
    "openspec-apply-change",
    "openspec-update-change",
    "openspec-sync-specs",
    "openspec-archive-change",
}
TASK_PHASES = (
    "## 0. Baseline",
    "## 1. RED",
    "## 2. GREEN",
    "## 3. Refactor",
    "## 4. Full evaluation and review",
)
PLACEHOLDERS = ("tbd", "todo", "заполняется", "<!--")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(markdown: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^## |\Z)",
        markdown,
    )
    return match.group("body").strip() if match else ""


def _has_real_evidence(markdown: str, heading: str) -> bool:
    body = _section(markdown, heading)
    lowered = body.lower()
    return len(body) >= 40 and not any(marker in lowered for marker in PLACEHOLDERS)


def validate_change(change: Path) -> list[str]:
    errors: list[str] = []
    required = (".openspec.yaml", "proposal.md", "eval-plan.md", "design.md", "tasks.md")
    for name in required:
        if not (change / name).is_file():
            errors.append(f"{change.name}: missing {name}")

    specs = sorted((change / "specs").glob("**/*.md")) if (change / "specs").is_dir() else []
    metadata = _read(change / ".openspec.yaml") if (change / ".openspec.yaml").is_file() else ""
    if not specs and "skip_specs: true" not in metadata:
        errors.append(f"{change.name}: missing delta spec without skip_specs: true")
    for spec in specs:
        content = _read(spec)
        for token in ("### Requirement:", "#### Scenario:", "- **WHEN**", "- **THEN**"):
            if token not in content:
                errors.append(f"{change.name}: {spec.name} missing {token}")

    eval_path = change / "eval-plan.md"
    if eval_path.is_file():
        eval_plan = _read(eval_path)
        for token in (
            "## Change classification",
            "## Acceptance matrix",
            "Authoritative oracle",
            "Expected RED",
            "Required GREEN gates",
            "## RED evidence",
            "## GREEN evidence",
        ):
            if token not in eval_plan:
                errors.append(f"{change.name}: eval-plan.md missing {token}")

    tasks_path = change / "tasks.md"
    if tasks_path.is_file():
        tasks = _read(tasks_path)
        offsets = [tasks.find(phase) for phase in TASK_PHASES]
        if any(offset < 0 for offset in offsets) or offsets != sorted(offsets):
            errors.append(f"{change.name}: tasks must follow Baseline → RED → GREEN → Refactor → Review")
        completed = "- [x]" in tasks.lower() and "- [ ]" not in tasks
        if completed and eval_path.is_file():
            eval_plan = _read(eval_path)
            if not _has_real_evidence(eval_plan, "RED evidence"):
                errors.append(f"{change.name}: completed change has no real RED evidence")
            if not _has_real_evidence(eval_plan, "GREEN evidence"):
                errors.append(f"{change.name}: completed change has no real GREEN evidence")
            classification = _section(eval_plan, "Change classification")
            if "player_visible" in classification and "- [ ]" in _section(
                eval_plan, "Trajectory review"
            ):
                errors.append(f"{change.name}: player-visible trajectory review is incomplete")
    return errors


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    openspec = root / "openspec"
    config_path = openspec / "config.yaml"
    schema_path = openspec / "schemas" / DEFAULT_SCHEMA / "schema.yaml"
    manifest_path = openspec / "quality-gates.json"

    if not config_path.is_file():
        errors.append("missing openspec/config.yaml")
    elif not re.search(rf"(?m)^schema:\s*{re.escape(DEFAULT_SCHEMA)}\s*$", _read(config_path)):
        errors.append(f"openspec/config.yaml must select {DEFAULT_SCHEMA}")

    if not schema_path.is_file():
        errors.append(f"missing custom schema {DEFAULT_SCHEMA}")
    else:
        schema = _read(schema_path)
        artifact_ids = re.findall(r"(?m)^\s+- id:\s*([a-z-]+)\s*$", schema)
        expected_order = ["proposal", "specs", "eval-plan", "design", "tasks"]
        if artifact_ids[:5] != expected_order:
            errors.append(f"custom schema artifact order must be {expected_order}")
        tasks_block = schema[schema.find("  - id: tasks") : schema.find("\napply:")]
        if "      - eval-plan" not in tasks_block:
            errors.append("tasks artifact must depend on eval-plan")
        if "world-state" not in schema.lower() and "world state" not in schema.lower():
            errors.append("custom schema must require a world-state oracle")

    if not manifest_path.is_file():
        errors.append("missing openspec/quality-gates.json")
    else:
        try:
            manifest = json.loads(_read(manifest_path))
        except json.JSONDecodeError as error:
            errors.append(f"invalid quality-gates.json: {error}")
        else:
            classes = manifest.get("change_classes", {})
            gates = manifest.get("gates", {})
            missing_classes = REQUIRED_CLASSES - set(classes)
            if missing_classes:
                errors.append(f"quality manifest missing classes: {sorted(missing_classes)}")
            for class_name, definition in classes.items():
                for gate_id in definition.get("required_gates", []):
                    if gate_id not in gates:
                        errors.append(f"{class_name} references unknown gate {gate_id}")
            for gate_id, definition in gates.items():
                if not definition.get("command") or not definition.get("evidence"):
                    errors.append(f"gate {gate_id} must define command and evidence")

    skills_root = root / ".agents" / "skills"
    installed_skills = {path.name for path in skills_root.iterdir()} if skills_root.is_dir() else set()
    if missing_skills := REQUIRED_SKILLS - installed_skills:
        errors.append(f"missing generated OpenSpec skills: {sorted(missing_skills)}")

    for relative, tokens in {
        "AGENTS.md": ("OpenSpec", "RED", "world state"),
        "CONTRIBUTING.md": ("OpenSpec", "eval-first", "quality-gates.json"),
    }.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing {relative}")
        else:
            content = _read(path).lower()
            for token in tokens:
                if token.lower() not in content:
                    errors.append(f"{relative} missing policy marker {token}")

    changes_root = openspec / "changes"
    if changes_root.is_dir():
        for change in sorted(path for path in changes_root.iterdir() if path.is_dir() and path.name != "archive"):
            errors.extend(validate_change(change))
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Granted's OpenSpec/TDD/eval-first policy")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    errors = validate_repository(args.root.resolve())
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("Granted quality policy: PASS")


if __name__ == "__main__":
    main()
