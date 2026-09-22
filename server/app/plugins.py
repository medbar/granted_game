from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


SERVER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFESTS_ROOT = SERVER_ROOT / "plugins"
DEFAULT_STATE_PATH = SERVER_ROOT / "runtime" / "plugins-state.json"


class CapabilityDefinition(BaseModel):
    name: str
    signature: str
    description: str
    mutates_world: bool = False


class PluginManifest(BaseModel):
    schema_version: int = 1
    id: str
    version: str
    description: str
    enabled_by_default: bool = True
    capabilities: list[CapabilityDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_capabilities(self) -> "PluginManifest":
        names = [item.name for item in self.capabilities]
        if len(names) != len(set(names)):
            raise ValueError(f"plugin {self.id} declares duplicate capabilities")
        return self


class PluginToggleRequest(BaseModel):
    enabled: bool


class PluginRegistry:
    """Hot-reloadable ownership registry for trusted built-in Monty handlers."""

    def __init__(self, manifests_root: Path, state_path: Path) -> None:
        self.manifests_root = manifests_root
        self.state_path = state_path
        self._lock = threading.RLock()
        self._manifests: dict[str, PluginManifest] = {}
        self._owners: dict[str, str] = {}
        self._enabled: dict[str, bool] = {}
        self.revision = 0
        self.reload()

    @classmethod
    def from_default(cls, state_path: Path | None = None) -> "PluginRegistry":
        return cls(DEFAULT_MANIFESTS_ROOT, state_path or DEFAULT_STATE_PATH)

    def _stored_enabled(self) -> dict[str, bool]:
        if not self.state_path.is_file():
            return {}
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        return {str(key): bool(value) for key, value in payload.get("enabled", {}).items()}

    def _persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"schema_version": 1, "revision": self.revision, "enabled": self._enabled},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def reload(self) -> None:
        with self._lock:
            stored = self._stored_enabled()
            manifests: dict[str, PluginManifest] = {}
            owners: dict[str, str] = {}
            for path in sorted(self.manifests_root.glob("*/plugin.json")):
                manifest = PluginManifest.model_validate_json(path.read_text(encoding="utf-8"))
                if manifest.id in manifests:
                    raise ValueError(f"duplicate plugin id: {manifest.id}")
                manifests[manifest.id] = manifest
                for capability in manifest.capabilities:
                    previous = owners.get(capability.name)
                    if previous is not None:
                        raise ValueError(
                            f"capability {capability.name} is owned by both {previous} and {manifest.id}"
                        )
                    owners[capability.name] = manifest.id
            if not manifests:
                raise ValueError(f"no plugin manifests found under {self.manifests_root}")
            self._manifests = manifests
            self._owners = owners
            self._enabled = {
                plugin_id: stored.get(plugin_id, manifest.enabled_by_default)
                for plugin_id, manifest in manifests.items()
            }
            self.revision += 1

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        with self._lock:
            if plugin_id not in self._manifests:
                raise KeyError(plugin_id)
            if self._enabled[plugin_id] == enabled:
                return
            self._enabled[plugin_id] = enabled
            self.revision += 1
            self._persist()

    def capability_owner(self, capability: str) -> str | None:
        return self._owners.get(capability)

    def enabled_capabilities(self) -> list[str]:
        with self._lock:
            return sorted(
                capability
                for capability, owner in self._owners.items()
                if self._enabled.get(owner, False)
            )

    def is_enabled(self, capability: str) -> bool:
        owner = self._owners.get(capability)
        return bool(owner and self._enabled.get(owner, False))

    def prompt_fragment(self) -> str:
        with self._lock:
            lines = [f"ENABLED GENIE PLUGINS (revision {self.revision}):"]
            for plugin_id, manifest in sorted(self._manifests.items()):
                if not self._enabled.get(plugin_id, False):
                    continue
                lines.append(f"[{plugin_id} {manifest.version}] {manifest.description}")
                for capability in manifest.capabilities:
                    lines.append(
                        f"- {capability.signature}: {capability.description}"
                    )
            return "\n".join(lines)

    def public_state(self) -> dict[str, object]:
        with self._lock:
            plugins = []
            for plugin_id, manifest in sorted(self._manifests.items()):
                plugins.append(
                    {
                        "id": plugin_id,
                        "version": manifest.version,
                        "description": manifest.description,
                        "enabled": self._enabled.get(plugin_id, False),
                        "capabilities": [item.name for item in manifest.capabilities],
                    }
                )
            digest = hashlib.sha256(
                json.dumps(plugins, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            return {
                "schema_version": 1,
                "revision": self.revision,
                "digest": digest,
                "capabilities": self.enabled_capabilities(),
                "plugins": plugins,
            }
