from __future__ import annotations

from app.agent import GenieAgentService
from app.monty_runtime import MontyGenieRuntime
from app.plugins import PluginRegistry
from conftest import cast_request


def test_plugin_api_hot_toggles_and_restores_runtime_surface(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient
    import app.main as main_module

    registry = PluginRegistry.from_default(state_path=tmp_path / "api-plugins.json")
    service = GenieAgentService(plugin_registry=registry)
    monkeypatch.setattr(main_module, "_agent_service", service)
    client = TestClient(main_module.app)

    before = client.get("/genie/plugins")
    assert before.status_code == 200
    before_revision = before.json()["revision"]

    disabled = client.put("/genie/plugins/creation", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["revision"] > before_revision
    assert "spawn" not in disabled.json()["capabilities"]
    assert "spawn" not in service.capability_prompt_fragment()

    restored = client.put("/genie/plugins/creation", json={"enabled": True})
    assert restored.status_code == 200
    assert "spawn" in restored.json()["capabilities"]


def test_plugin_reload_endpoint_increments_revision(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient
    import app.main as main_module

    registry = PluginRegistry.from_default(state_path=tmp_path / "reload-plugins.json")
    monkeypatch.setattr(main_module, "_agent_service", GenieAgentService(plugin_registry=registry))
    client = TestClient(main_module.app)
    revision = client.get("/genie/plugins").json()["revision"]

    response = client.post("/genie/plugins/reload")

    assert response.status_code == 200
    assert response.json()["revision"] > revision


def test_default_plugins_own_every_exposed_capability(tmp_path) -> None:
    registry = PluginRegistry.from_default(state_path=tmp_path / "plugins.json")

    assert registry.capability_owner("spawn") == "creation"
    assert registry.capability_owner("destroy") == "physical"
    assert registry.capability_owner("observe_area") == "perception"
    assert registry.capability_owner("set_game_speed") == "world-control"
    assert registry.capability_owner("collect") == "heist"
    assert len(registry.enabled_capabilities()) == len(set(registry.enabled_capabilities()))


def test_plugin_can_be_disabled_and_enabled_without_recreating_registry(tmp_path) -> None:
    registry = PluginRegistry.from_default(state_path=tmp_path / "plugins.json")
    initial_revision = registry.revision

    registry.set_enabled("creation", False)

    assert registry.revision > initial_revision
    assert "spawn" not in registry.enabled_capabilities()
    assert "spawn" not in registry.prompt_fragment()

    disabled_revision = registry.revision
    registry.set_enabled("creation", True)
    assert registry.revision > disabled_revision
    assert "spawn" in registry.enabled_capabilities()


def test_disabled_plugin_blocks_monty_call_without_world_mutation(tmp_path, world) -> None:
    registry = PluginRegistry.from_default(state_path=tmp_path / "plugins.json")
    registry.set_enabled("creation", False)
    request = cast_request("создай огонь", world)

    result = MontyGenieRuntime(plugin_registry=registry).execute(
        "spawn('fire', near='player')", request
    )

    assert result.error is not None
    assert "plugin" in result.error.lower() or "capability" in result.error.lower()
    assert result.actions == []


def test_agent_capability_prompt_reflects_hot_plugin_state(tmp_path) -> None:
    registry = PluginRegistry.from_default(state_path=tmp_path / "plugins.json")
    service = GenieAgentService(plugin_registry=registry)
    assert "spawn" in service.capability_prompt_fragment()

    registry.set_enabled("creation", False)

    fragment = service.capability_prompt_fragment()
    assert "spawn" not in fragment
    assert "destroy" in fragment


def test_full_system_prompt_never_advertises_disabled_creation_tools(tmp_path, world) -> None:
    registry = PluginRegistry.from_default(state_path=tmp_path / "prompt-plugins.json")
    service = GenieAgentService(plugin_registry=registry)
    request = cast_request("создай меч", world)
    assert "spawn(" in service.instructions_for_request(request)

    registry.set_enabled("creation", False)
    prompt = service.instructions_for_request(request)

    assert "spawn(" not in prompt
    assert "spawn_many(" not in prompt
    assert "give_item(" not in prompt
    assert "destroy(" in prompt
