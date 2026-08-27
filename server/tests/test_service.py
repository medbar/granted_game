import json

from app.service import SpellService
from conftest import cast_request


def test_debug_cast_is_logged_as_structured_jsonl(tmp_path, world) -> None:
    log_path = tmp_path / "casts.jsonl"
    response = SpellService(log_path=log_path).cast(
        cast_request("оттолкни врага", world, debug=True)
    )
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["request"]["request_id"] == response.request_id
    assert record["request"]["spell_text"] == "оттолкни врага"
    assert record["response"]["interpretation"]["anchors"]
    assert record["response"]["debug"]["world_rules"]
