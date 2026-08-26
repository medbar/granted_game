from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def _load_json_yaml(name: str) -> Any:
    """Load JSON-compatible YAML without adding a parser to the runtime hot path."""
    with (CONFIG_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache
def anchors_config() -> dict[str, Any]:
    value = _load_json_yaml("anchors.yaml")
    if len(value["anchors"]) != 100:
        raise RuntimeError("anchors.yaml must contain exactly 100 hidden anchors")
    return value


@lru_cache
def materials_config() -> dict[str, Any]:
    return _load_json_yaml("materials.yaml")


@lru_cache
def reactions_config() -> dict[str, Any]:
    return _load_json_yaml("reactions.yaml")


@lru_cache
def spell_settings() -> dict[str, Any]:
    return _load_json_yaml("spell_settings.yaml")


@lru_cache
def visual_mapping() -> dict[str, Any]:
    return _load_json_yaml("visual_mapping.yaml")

