from __future__ import annotations

import argparse
import json
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = SERVER_ROOT / "config" / "agent_prompt.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-report", required=True)
    parser.add_argument("--next-generation", type=int, required=True)
    args = parser.parse_args()

    report = json.loads(Path(args.from_report).read_text(encoding="utf-8"))
    config = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    failed_ids = [result["id"] for result in report["results"] if not result["passed"]]
    slow_ids = [
        result["id"] for result in report["results"]
        if float(result.get("latency_ms", 0)) > 2000
    ]
    learned = [
        "Сначала выбери минимальную прямую capability, чьё постусловие буквально совпадает с желанием.",
        "Не заменяй запрошенный эффект декоративным огнём, речью или близким по смыслу объектом.",
        "Для мокрого состояния всегда apply_state(target, 'wet'); создание воды само по себе не делает цель мокрой.",
        "Для простого желания выдай одну capability без inspect и без поясняющего speak.",
    ]
    if not failed_ids:
        learned.append("Предыдущее поколение прошло все проверки среды: сохраняй точные отображения capability и не усложняй программы.")
    config["version"] = f"genie-agent-evolution-g{args.next_generation}"
    config["evolution_guidance"] = (
        "Эволюционные правила по предыдущему полному прогону: "
        + " ".join(learned)
        + f" Провалившиеся кейсы: {', '.join(failed_ids) or 'нет'}."
        + f" Медленные кейсы: {', '.join(slow_ids) or 'нет'}."
    )
    snapshot_dir = SERVER_ROOT / "runtime" / "evolution"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_dir / f"prompt-generation-{args.next_generation}.json"
    serialized = json.dumps(config, ensure_ascii=False, indent=2)
    PROMPT_PATH.write_text(serialized + "\n", encoding="utf-8")
    snapshot.write_text(serialized + "\n", encoding="utf-8")
    print(f"EVOLVED prompt={config['version']} failed={len(failed_ids)} slow={len(slow_ids)} snapshot={snapshot}")


if __name__ == "__main__":
    main()
