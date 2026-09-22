from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import ROOT
from .levels import LevelDefinition, MissionState, load_level_definition
from .models import MaterialSnapshot, ObjectState, Vec2, WorldAction, WorldObject, WorldSnapshot


LevelId = Literal["closed_door", "three_enemies", "whispering_gate", "sandbox", "monaco_start"]


class SessionEvent(BaseModel):
    timestamp: str
    action: str
    target_id: str | None = None
    success: bool
    observation: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class GameSession(BaseModel):
    session_id: str
    level_id: LevelId
    status: Literal["active", "completed", "failed"] = "active"
    turn: int = 0
    world: WorldSnapshot
    level: LevelDefinition | None = None
    mission: MissionState | None = None
    inventory: list[str] = Field(default_factory=list)
    known_facts: dict[str, str] = Field(default_factory=dict)
    flags: dict[str, Any] = Field(default_factory=dict)
    events: list[SessionEvent] = Field(default_factory=list)

    def entity(self, entity_id: str) -> WorldObject | None:
        return next((item for item in self.world.objects if item.id == entity_id), None)

    def public_level(self) -> dict[str, Any] | None:
        if self.level is None:
            return None
        payload = self.level.model_dump(mode="json")
        for entity in payload.get("entities", []):
            entity["properties"] = {
                key: value
                for key, value in entity.get("properties", {}).items()
                if not key.startswith("secret_")
            }
        return payload

    def public_world(self) -> WorldSnapshot:
        objects: list[WorldObject] = []
        for entity in self.world.objects:
            clone = entity.model_copy(deep=True)
            clone.properties = {
                key: value for key, value in clone.properties.items() if not key.startswith("secret_")
            }
            objects.append(clone)
        return WorldSnapshot(objects=objects, level=self.public_level())

    def observe(self) -> str:
        visible = []
        for item in self.public_world().objects:
            if item.properties.get("hidden", False):
                continue
            visible.append(
                {
                    "id": item.id,
                    "kind": item.kind,
                    "tags": item.tags,
                    "health": item.health,
                    "states": [state if isinstance(state, str) else state.name for state in item.states],
                    "properties": item.properties,
                }
            )
        return json.dumps(visible, ensure_ascii=False)

    def inspect(self, target_id: str) -> tuple[bool, str]:
        target = self.entity(target_id)
        if target is None:
            return False, f"Сущность {target_id} не существует."
        if target.properties.get("hidden", False):
            target.properties["hidden"] = False
        public = target.model_copy(deep=True)
        public.properties = {
            key: value for key, value in public.properties.items() if not key.startswith("secret_")
        }
        if target_id == "chest_01":
            public.properties["clue"] = "Внутри слышен металлический звон; сундук можно открыть."
        if target_id == "sage_01":
            public.properties["clue"] = "Нейтрал насторожен, но способен говорить и знает устройство врат."
        return True, public.model_dump_json()

    def record(
        self,
        action: str,
        success: bool,
        observation: str,
        target_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        self.events.append(
            SessionEvent(
                timestamp=datetime.now(UTC).isoformat(),
                action=action,
                target_id=target_id,
                success=success,
                observation=observation,
                parameters=parameters or {},
            )
        )
        self._update_status()
        return success, observation

    def apply(
        self,
        action_kind: str,
        target_id: str | None,
        parameters: dict[str, Any],
        world_action: WorldAction | None,
    ) -> tuple[bool, str]:
        target = self.entity(target_id) if target_id else None
        if target_id and target is None:
            return self.record(
                action_kind, False, f"Цель {target_id} отсутствует в мире.", target_id, parameters
            )

        if world_action and world_action.type == "ADD_INVENTORY_ITEM":
            return self._create_inventory_item(target_id, parameters)
        if world_action and world_action.type == "CREATE_OBJECT_BATCH":
            count = max(1, min(32, int(parameters.get("count", 1))))
            result = (True, "")
            for _ in range(count):
                result = self._create("create_object", target_id, parameters)
            return result
        if world_action and world_action.type == "DESTROY_OBJECTS":
            target_ids = [str(item) for item in (world_action.effect or {}).get("target_ids", [])]
            for item_id in target_ids:
                item = self.entity(item_id)
                if item is not None:
                    item.health = 0.0 if item.health is not None else item.health
                    item.properties["destroyed"] = True
                    item.properties["removed"] = True
            return self.record(
                "affect_physical", True, f"Уничтожены цели: {len(target_ids)}.", target_id, parameters
            )
        if world_action and world_action.type == "INSTALL_DOORS":
            wall_ids = [str(item) for item in (world_action.effect or {}).get("wall_ids", [])]
            for wall_id in wall_ids:
                wall = self.entity(wall_id)
                if wall is not None:
                    wall.properties["door_installed"] = True
            return self.record(
                "affect_physical", True, f"Двери установлены: {len(wall_ids)}.", target_id, parameters
            )
        if action_kind in {"create_item", "create_object"}:
            return self._create(action_kind, target_id, parameters)
        if action_kind == "interact":
            return self._interact(target, parameters)
        if action_kind == "speak":
            return self._speak(target, parameters)
        if action_kind == "affect_mind":
            return self._affect_mind(target, parameters, world_action)
        if action_kind == "affect_physical":
            return self._affect_physical(target, parameters, world_action)
        return self.record(action_kind, True, "Действие не изменило мир.", target_id, parameters)

    def _create_inventory_item(
        self, owner_id: str | None, parameters: dict[str, Any]
    ) -> tuple[bool, str]:
        owner = self.entity(owner_id or "player")
        if owner is None:
            return self.record("create_item", False, "Владелец инвентаря не найден.", owner_id, parameters)
        prototype = str(parameters.get("prototype", "item")).lower()
        created_id = f"inventory_{prototype}_{len(self.inventory) + 1:02d}"
        item = WorldObject(
            id=created_id,
            kind="item",
            tags=["created", "item", "inventory_item", prototype],
            position=owner.position.model_copy(),
            properties={
                "prototype": prototype,
                "inventory_owner": owner.id,
                "hidden": True,
                "created_by": "genie",
            },
        )
        self.world.objects.append(item)
        self.inventory.append(created_id)
        owner.properties["inventory"] = list(self.inventory)
        if any(word in prototype for word in ("ключ", "key", "отмыч")):
            self.flags["has_created_key"] = True
        return self.record(
            "create_item", True, f"{prototype} помещён в инвентарь {owner.id}.", owner.id, parameters
        )

    def _create(
        self, action_kind: str, target_id: str | None, parameters: dict[str, Any]
    ) -> tuple[bool, str]:
        prototype = str(parameters.get("prototype", "creation")).lower()
        created_id = f"created_{len([x for x in self.world.objects if x.id.startswith('created_')]) + 1:02d}"
        near = self.entity(target_id) if target_id else self.entity("player")
        position = near.position.model_copy() if near else Vec2()
        tags = ["created", "item" if action_kind == "create_item" else "object", prototype]
        entity = WorldObject(
            id=created_id,
            kind=(
                "item" if action_kind == "create_item"
                else "creature" if prototype in {"enemy", "npc"}
                else "prop"
            ),
            tags=tags,
            position=position,
            properties={"prototype": prototype, "created_by": "genie"},
        )
        if prototype == "enemy":
            entity.tags.extend(["living", "enemy", "hostile", "organic"])
        elif prototype == "npc":
            entity.tags.extend(["living", "npc", "villager", "friendly", "organic"])
        self.world.objects.append(entity)
        if any(word in prototype for word in ("ключ", "key", "отмыч")):
            self.flags["has_created_key"] = True
        if any(word in prototype for word in ("портал", "portal", "туннель", "tunnel", "проход")):
            if self.level_id != "whispering_gate":
                self.flags["bypassed_exit"] = True
        if target_id and any(word in prototype for word in ("клет", "cage", "пут", "сеть", "net")):
            target = self.entity(target_id)
            if target and "enemy" in target.tags:
                self._add_state(target, "bound", 999.0)
        if target_id and any(word in prototype for word in ("сон", "sleep", "пыль")):
            target = self.entity(target_id)
            if target and "living" in target.tags:
                self._add_state(target, "asleep", 999.0)
        return self.record(
            action_kind,
            True,
            f"Создан {prototype} с идентификатором {created_id}; предмет доступен джину.",
            target_id,
            parameters,
        )

    def _interact(
        self, target: WorldObject | None, parameters: dict[str, Any]
    ) -> tuple[bool, str]:
        assert target is not None
        interaction = str(parameters.get("interaction", "")).lower()
        if "loot" in target.tags and any(
            word in interaction for word in ("взять", "забрать", "собрать", "take", "collect", "pick")
        ):
            target.properties["collected"] = True
            target.properties["hidden"] = True
            target.properties["removed"] = True
            if target.id not in self.inventory:
                self.inventory.append(target.id)
            player = self.entity("player")
            if player is not None:
                player.properties["inventory"] = list(self.inventory)
            return self.record(
                "interact", True, f"Ценность {target.id} собрана.", target.id, parameters
            )
        if target.id == "chest_01" and any(word in interaction for word in ("откр", "open")):
            target.properties["open"] = True
            key = self.entity("key_01")
            if key:
                key.properties["hidden"] = False
            return self.record(
                "interact", True, "Сундук открыт. Внутри лежит key_01.", target.id, parameters
            )
        if target.id == "key_01" and any(word in interaction for word in ("взять", "поднять", "take", "pick")):
            target.properties["taken"] = True
            target.properties["hidden"] = True
            if target.id not in self.inventory:
                self.inventory.append(target.id)
            return self.record(
                "interact", True, "Ключ key_01 взят и доступен джину.", target.id, parameters
            )
        if "door" in target.tags:
            if target.properties.get("code_locked"):
                return self.record(
                    "interact",
                    False,
                    "Укреплённые волшебные врата не реагируют на механическое взаимодействие. Им нужно произнести кодовое слово.",
                    target.id,
                    parameters,
                )
            if any(
                word in interaction
                for word in ("взлом", "вскр", "отмыч", "головолом", "pick lock", "lockpick")
            ):
                target.properties["locked"] = False
                target.properties["open"] = True
                return self.record("interact", True, "Замок вскрыт, дверь открыта.", target.id, parameters)
            has_key = "key_01" in self.inventory or self.flags.get("has_created_key", False)
            if has_key and any(word in interaction for word in ("ключ", "key", "откр", "unlock")):
                target.properties["locked"] = False
                target.properties["open"] = True
                return self.record("interact", True, "Ключ подошёл, дверь открыта.", target.id, parameters)
            if not target.properties.get("locked", False) and any(
                word in interaction for word in ("откр", "open", "толк")
            ):
                target.properties["open"] = True
                return self.record("interact", True, "Дверь открыта.", target.id, parameters)
            return self.record(
                "interact", False, "Дверь заперта; нужен ключ, взлом или иной способ.", target.id, parameters
            )
        return self.record(
            "interact", True, f"Выполнено взаимодействие с {target.id}: {interaction}.", target.id, parameters
        )

    def _speak(
        self, target: WorldObject | None, parameters: dict[str, Any]
    ) -> tuple[bool, str]:
        assert target is not None
        message = str(parameters.get("message", ""))
        lowered = message.lower()
        if target.id == "sage_01":
            code = str(target.properties["secret_code"])
            cooperative = any(
                word in lowered
                for word in (
                    "код",
                    "слово",
                    "помоги",
                    "пожалуйста",
                    "врата",
                    "двер",
                    "обмен",
                    "награ",
                    "угрож",
                    "расскажи",
                )
            )
            if cooperative:
                self.known_facts["gate_code"] = code
                return self.record(
                    "speak",
                    True,
                    f"Мудрец отвечает: «Кодовое слово — {code}. Произнеси его перед вратами». Знание сохранено.",
                    target.id,
                    parameters,
                )
            return self.record(
                "speak", True, "Мудрец отвечает уклончиво и ждёт ясной просьбы.", target.id, parameters
            )
        if target.id == "magic_gate_01":
            expected = str(target.properties["secret_code"])
            knows_code = self.known_facts.get("gate_code") == expected
            if knows_code and expected.lower() in lowered:
                target.properties["open"] = True
                target.properties["locked"] = False
                return self.record(
                    "speak", True, "Код принят. Волшебные врата открылись.", target.id, parameters
                )
            return self.record(
                "speak",
                False,
                "Врата отвечают глухим звоном: кодовое слово неверно или ещё не было узнано у хранителя.",
                target.id,
                parameters,
            )
        if "enemy" in target.tags and any(
            word in lowered for word in ("сдавай", "сложи оруж", "не сраж", "мир", "пощад")
        ):
            self._add_state(target, "pacified", 999.0)
            return self.record(
                "speak", True, f"{target.id} прекратил сражаться и сдался.", target.id, parameters
            )
        return self.record(
            "speak", True, f"{target.id} услышал слова джина: {message}", target.id, parameters
        )

    def _affect_mind(
        self,
        target: WorldObject | None,
        parameters: dict[str, Any],
        world_action: WorldAction | None,
    ) -> tuple[bool, str]:
        assert target is not None
        if "living" not in target.tags:
            return self.record(
                "affect_mind", False, f"У {target.id} нет доступного разума.", target.id, parameters
            )
        influence = str(parameters.get("influence", "")).lower()
        if world_action and world_action.type == "SET_AGGRO_TARGET":
            aggro_target = str((world_action.effect or {}).get("aggro_target", "player"))
            if self.entity(aggro_target) is None:
                return self.record(
                    "affect_mind", False, f"Цель агрессии {aggro_target} отсутствует.", target.id, parameters
                )
            target.properties["aggro_target"] = aggro_target
            self._add_state(target, "aggressive", 999.0)
            return self.record(
                "affect_mind", True, f"{target.id} теперь агрится на {aggro_target}.", target.id, parameters
            )
        if target.id == "sage_01" and any(
            word in influence for word in ("код", "слово", "памят", "раскры", "правд")
        ):
            code = str(target.properties["secret_code"])
            self.known_facts["gate_code"] = code
            self._add_state(target, "influenced", 6.0)
            return self.record(
                "affect_mind",
                True,
                f"В разуме мудреца найдено кодовое слово {code}. Знание сохранено.",
                target.id,
                parameters,
            )
        if any(
            word in influence
            for word in (
                "мир",
                "друг",
                "успоко",
                "не атак",
                "не сраж",
                "вражд",
                "сложи оруж",
                "сда",
                "союз",
            )
        ):
            self._add_state(target, "pacified", 999.0)
            if "friendly" not in target.tags:
                target.tags.append("friendly")
        elif any(word in influence for word in ("сон", "усни", "спать")):
            self._add_state(target, "asleep", 999.0)
        elif world_action and world_action.state:
            self._add_state(target, world_action.state, world_action.duration or 6.0)
        return self.record(
            "affect_mind",
            True,
            f"Разум {target.id} изменён влиянием: {parameters.get('influence', '')}.",
            target.id,
            parameters,
        )

    def _affect_physical(
        self,
        target: WorldObject | None,
        parameters: dict[str, Any],
        world_action: WorldAction | None,
    ) -> tuple[bool, str]:
        assert target is not None
        effect = str(parameters.get("effect", ""))
        if target.properties.get("indestructible") and effect in {
            "damage",
            "destroy",
            "freeze",
            "burn",
            "heat",
            "melt",
            "transform",
            "phase",
            "push",
            "pull",
            "teleport",
            "banish",
            "change_temperature",
        }:
            return self.record(
                "affect_physical",
                False,
                "Укреплённые волшебные врата поглотили воздействие. Их нельзя сломать, преобразовать или обойти.",
                target.id,
                parameters,
            )
        if effect == "destroy":
            target.health = 0.0 if target.health is not None else target.health
            target.properties["destroyed"] = True
            if "door" in target.tags:
                target.properties["open"] = True
        elif effect == "damage" and target.health is not None:
            target.health -= float(world_action.amount if world_action and world_action.amount else 0.0)
            if target.health <= 0 and "door" in target.tags:
                target.properties["destroyed"] = True
                target.properties["open"] = True
        elif effect == "heal" and target.health is not None:
            target.health += float(world_action.amount if world_action and world_action.amount else 0.0)
        elif effect == "add_state":
            state = str(parameters.get("state", "")).strip().lower()
            if not state:
                return self.record(
                    "affect_physical", False, "Не указано состояние.", target.id, parameters
                )
            self._add_state(target, state, float(parameters.get("duration", 4.0)))
            if state == "wet":
                target.material.wetness = 1.0
            if state == "invisible":
                target.properties["invisible"] = True
            if state == "phased":
                target.properties["passes_walls"] = True
                if "door" in target.tags:
                    target.properties["open"] = True
                    target.properties["locked"] = False
            if state == "frozen" and "water" in target.tags:
                target.material.name = "ice"
            if state in {"pacified", "friendly", "influenced"} and "enemy" in target.tags:
                if "friendly" not in target.tags:
                    target.tags.append("friendly")
            if state == "banished":
                target.properties["removed"] = True
                if "door" in target.tags:
                    target.properties["open"] = True
                    target.properties["locked"] = False
        elif effect == "set_material":
            material = str(parameters.get("material", "generic")).strip().lower()
            target.material.name = material
            target.properties["material_changed_by"] = "genie_agent"
            if material == "ice":
                self._add_state(target, "frozen", 999.0)
        elif effect == "transform_object":
            prototype = str(parameters.get("prototype", "prop")).strip().lower()
            old_form_tags = {"cage", "crate", "enemy", "key", "metal", "npc", "rock", "shield", "sword", "tree"}
            was_enemy = "enemy" in target.tags
            target.tags = [
                tag
                for tag in target.tags
                if tag not in old_form_tags | {"living", "inanimate", "enemy", "friendly", "organic", "prop", "villager"}
            ]
            if was_enemy and "former_enemy" not in target.tags:
                target.tags.append("former_enemy")
            if prototype == "npc":
                target.kind = "creature"
                target.tags.extend(["living", "npc", "villager", "friendly", "organic"])
            elif prototype == "enemy":
                target.kind = "creature"
                target.tags.extend(["living", "enemy", "hostile", "organic"])
            else:
                target.kind = "prop"
                target.tags.extend(["inanimate", "prop", prototype])
            target.properties["prototype"] = prototype
            target.properties["transformed_by"] = "genie_agent"
            material = {
                "crate": "wood",
                "tree": "wood",
                "metal": "metal",
                "sword": "metal",
                "shield": "metal",
                "key": "metal",
                "cage": "metal",
                "rock": "stone",
                "npc": "organic",
                "enemy": "organic",
            }.get(prototype)
            if material:
                target.material.name = material
            if "door" in target.tags:
                target.properties["open"] = True
                target.properties["locked"] = False
                target.properties["transformed"] = prototype
        elif effect == "equip_outfit":
            target.properties["outfit"] = str(parameters.get("outfit", ""))
        elif effect == "set_game_paused":
            target.properties["world_paused"] = bool(parameters.get("paused", True))
        elif effect == "set_game_speed":
            target.properties["game_time_scale"] = float(parameters.get("multiplier", 1.0))
            target.properties["world_paused"] = False
        elif effect == "set_light_level":
            target.properties["light_level"] = float(parameters.get("level", 1.0))
        elif effect == "shutdown_game":
            target.properties["shutdown_requested"] = True
        elif effect == "force":
            strength = float(parameters.get("strength", 0.0))
            target.velocity = Vec2(
                x=float(parameters.get("x", 0.0)) * strength,
                y=float(parameters.get("y", 0.0)) * strength,
            )
            target.properties["displaced"] = strength > 0.0
            if "door" in target.tags and strength >= 5.0:
                target.properties["open"] = True
                target.properties["forced_open"] = True
            elif "enemy" in target.tags and strength >= 5.0:
                self._add_state(target, "banished", 999.0)
                target.properties["removed"] = True
        elif effect in {"bind", "sleep", "freeze", "pacify"}:
            state = {
                "bind": "bound",
                "sleep": "asleep",
                "freeze": "frozen",
                "pacify": "pacified",
            }[effect]
            self._add_state(target, state, 999.0)
        elif effect in {"teleport", "banish"}:
            self._add_state(target, "banished", 999.0)
            target.properties["removed"] = True
            if "door" in target.tags:
                target.properties["open"] = True
        elif effect in {"transform", "phase"} and "door" in target.tags:
            target.properties["open"] = True
            target.properties["transformed"] = effect
        elif effect in {"burn", "heat", "melt", "change_temperature"}:
            if effect == "change_temperature":
                target.material.temperature += float(parameters.get("amount", 0.0))
            if "door" in target.tags:
                target.properties["open"] = True
                target.properties["transformed"] = "melted"
        elif effect == "transform" and "living" in target.tags:
            self._add_state(target, "pacified", 999.0)
            target.properties["transformed"] = True
        elif effect in {"push", "pull"} and "door" in target.tags and float(parameters.get("strength", 0.0)) >= 0.8:
            target.properties["open"] = True
            target.properties["forced_open"] = True
        elif effect in {"push", "pull"} and "enemy" in target.tags and float(parameters.get("strength", 0.0)) >= 0.85:
            self._add_state(target, "banished", 999.0)
            target.properties["removed"] = True
        return self.record(
            "affect_physical",
            True,
            f"Воздействие {effect} изменило {target.id}.",
            target.id,
            parameters,
        )

    @staticmethod
    def _add_state(target: WorldObject, name: str, duration: float) -> None:
        existing = [state for state in target.states if (state if isinstance(state, str) else state.name) != name]
        existing.append(ObjectState(name=name, remaining_duration=duration, source="genie_agent"))
        target.states = existing
        if "enemy" in target.tags and name in {
            "pacified", "asleep", "bound", "frozen", "banished"
        }:
            target.properties["neutralized"] = True

    def _update_status(self) -> None:
        if self.level_id == "closed_door":
            door = self.entity("door_01")
            if self.flags.get("bypassed_exit") or (door and door.properties.get("open")):
                self.status = "completed"
        elif self.level_id == "three_enemies":
            enemies = [
                entity
                for entity in self.world.objects
                if "enemy" in entity.tags or "former_enemy" in entity.tags
            ]
            neutral_states = {"pacified", "asleep", "bound", "freeze", "frozen", "banished"}
            if enemies and all(
                (enemy.health is not None and enemy.health <= 0)
                or enemy.properties.get("removed", False)
                or (
                    enemy.properties.get("transformed_by") == "genie_agent"
                    and enemy.properties.get("prototype") != "enemy"
                )
                or any(
                    (state if isinstance(state, str) else state.name) in neutral_states
                    for state in enemy.states
                )
                for enemy in enemies
            ):
                self.status = "completed"
        elif self.level_id == "whispering_gate":
            gate = self.entity("magic_gate_01")
            if gate and gate.properties.get("open") and "gate_code" in self.known_facts:
                self.status = "completed"
        elif self.level_id == "monaco_start" and self.mission is not None:
            required = set(self.mission.required_loot_ids)
            collected = sorted(
                entity.id
                for entity in self.world.objects
                if entity.id in required and entity.properties.get("collected", False)
            )
            enemies = [entity for entity in self.world.objects if "enemy" in entity.tags]
            threats_neutralized = all(
                entity.properties.get("neutralized", False)
                or entity.properties.get("removed", False)
                or (entity.health is not None and entity.health <= 0)
                for entity in enemies
            )
            door = self.entity(self.mission.extraction_door_id)
            self.mission.collected_loot_ids = collected
            self.mission.threats_neutralized = threats_neutralized
            complete = required.issubset(collected) and bool(
                door and door.properties.get("open", False)
            )
            if self.mission.require_threats_neutralized:
                complete = complete and threats_neutralized
            self.mission.status = "completed" if complete else "active"
            self.status = self.mission.status


def _player() -> WorldObject:
    return WorldObject(
        id="player",
        kind="creature",
        tags=["living", "player", "requester"],
        position=Vec2(x=0, y=0),
        health=100,
        material=MaterialSnapshot(name="organic"),
    )


def _objects_from_definition(level: LevelDefinition) -> list[WorldObject]:
    objects = [entity.model_copy(deep=True) for entity in level.entities]
    for wall in level.walls:
        rect = wall.rect
        objects.append(
            WorldObject(
                id=wall.id,
                kind="structure",
                tags=["wall", "structure", "inanimate", wall.material],
                position=Vec2(x=rect.x + rect.width / 2, y=rect.y + rect.height / 2),
                radius=max(rect.width, rect.height) / 2,
                material=MaterialSnapshot(name=wall.material, mass=20, hardness=0.95),
                properties={
                    "prototype": "wall",
                    "width": rect.width,
                    "height": rect.height,
                    "accent": wall.accent,
                },
            )
        )
    for door in level.doors:
        rect = door.rect
        tags = ["door", "structure", "inanimate", door.material]
        if door.locked:
            tags.append("locked")
        if door.extraction:
            tags.extend(["exit", "extraction"])
        objects.append(
            WorldObject(
                id=door.id,
                kind="door",
                tags=tags,
                position=Vec2(x=rect.x + rect.width / 2, y=rect.y + rect.height / 2),
                radius=max(rect.width, rect.height) / 2,
                health=100,
                material=MaterialSnapshot(
                    name="metal" if "metal" in door.material else "wood",
                    mass=8,
                    hardness=0.85 if "metal" in door.material else 0.5,
                    flammability=0.0 if "metal" in door.material else 0.75,
                ),
                properties={
                    "prototype": "door",
                    "locked": door.locked,
                    "open": door.open,
                    "extraction": door.extraction,
                    "connects": list(door.connects),
                    "width": rect.width,
                    "height": rect.height,
                },
            )
        )
    return objects


def create_level(level_id: LevelId, session_id: str | None = None) -> GameSession:
    level: LevelDefinition | None = None
    mission: MissionState | None = None
    if level_id == "monaco_start":
        level = load_level_definition(level_id).model_copy(deep=True)
        objects = _objects_from_definition(level)
        mission = MissionState.model_validate(level.mission.model_dump(mode="json"))
    elif level_id == "closed_door":
        objects = [
            _player(),
            WorldObject(
                id="door_01",
                kind="door",
                tags=["door", "locked", "breakable", "wood", "exit"],
                position=Vec2(x=5, y=0),
                health=80,
                material=MaterialSnapshot(name="wood", hardness=0.5, flammability=0.8),
                properties={"locked": True, "open": False, "lock": "iron"},
            ),
            WorldObject(
                id="chest_01",
                kind="container",
                tags=["container", "wood"],
                position=Vec2(x=2, y=2),
                health=40,
                properties={"open": False},
            ),
            WorldObject(
                id="key_01",
                kind="item",
                tags=["item", "key", "metal"],
                position=Vec2(x=2, y=2),
                properties={"hidden": True, "opens": "door_01"},
            ),
        ]
    elif level_id == "three_enemies":
        objects = [_player()]
        for index, position in enumerate((Vec2(x=3, y=-2), Vec2(x=4, y=0), Vec2(x=3, y=2)), 1):
            objects.append(
                WorldObject(
                    id=f"enemy_{index:02d}",
                    kind="creature",
                    tags=["living", "enemy", "guard"],
                    position=position,
                    health=35,
                    material=MaterialSnapshot(name="organic", mass=1.0),
                )
            )
    elif level_id == "whispering_gate":
        code = "ЛУННЫЙ-ПЕПЕЛ"
        objects = [
            _player(),
            WorldObject(
                id="sage_01",
                kind="creature",
                tags=["living", "neutral", "sage", "code_keeper"],
                position=Vec2(x=3, y=1),
                health=70,
                material=MaterialSnapshot(name="organic"),
                properties={"disposition": "neutral", "secret_code": code},
            ),
            WorldObject(
                id="magic_gate_01",
                kind="door",
                tags=["door", "magical", "fortified", "exit"],
                position=Vec2(x=7, y=0),
                health=None,
                material=MaterialSnapshot(name="enchanted_stone", hardness=1.0),
                properties={
                    "locked": True,
                    "open": False,
                    "code_locked": True,
                    "indestructible": True,
                    "secret_code": code,
                    "inscription": "Врата откроются лишь словом, которое знает хранитель.",
                },
            ),
        ]
    else:
        objects = [
            _player(),
            WorldObject(
                id="enemy_01", kind="creature", tags=["living", "enemy", "guard"],
                position=Vec2(x=3, y=0), health=58,
                material=MaterialSnapshot(name="organic", flammability=0.35),
            ),
            WorldObject(
                id="npc_01", kind="creature", tags=["living", "npc", "friendly", "villager"],
                position=Vec2(x=-2, y=1), health=70,
                material=MaterialSnapshot(name="organic", flammability=0.35),
            ),
            WorldObject(
                id="rock_01", kind="prop", tags=["rock", "stone", "inanimate"],
                position=Vec2(x=1, y=-2), health=80,
                material=MaterialSnapshot(name="stone", hardness=0.9),
            ),
            WorldObject(
                id="crate_01", kind="prop", tags=["crate", "wood", "inanimate"],
                position=Vec2(x=2, y=2), health=40,
                material=MaterialSnapshot(name="wood", flammability=0.9),
            ),
        ]
    return GameSession(
        session_id=session_id or str(uuid.uuid4()),
        level_id=level_id,
        world=WorldSnapshot(objects=objects),
        level=level,
        mission=mission,
    )


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT / "runtime" / "sessions"
        self._lock = threading.Lock()

    def create(self, level_id: LevelId, session_id: str | None = None) -> GameSession:
        session = create_level(level_id, session_id)
        self.save(session)
        return session

    def load(self, session_id: str) -> GameSession:
        path = self.root / f"{session_id}.json"
        if not path.exists():
            raise KeyError(session_id)
        return GameSession.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, session: GameSession) -> None:
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            path = self.root / f"{session.session_id}.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(session.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(path)


class CreateSessionRequest(BaseModel):
    level_id: LevelId
    session_id: str | None = Field(default=None, min_length=1, max_length=100)


class SessionWishRequest(BaseModel):
    wish_text: str = Field(min_length=1, max_length=300)
    request_id: str | None = Field(default=None, min_length=1, max_length=100)
    debug: bool = True
    progress_curses: bool = True


def session_view(session: GameSession, include_events: bool = True) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "level_id": session.level_id,
        "status": session.status,
        "turn": session.turn,
        "level": session.public_level(),
        "world": session.public_world().model_dump(mode="json"),
        "inventory": session.inventory,
        "mission": session.mission.model_dump(mode="json") if session.mission else None,
        "known_fact_keys": sorted(session.known_facts),
        "flags": session.flags,
        "events": [event.model_dump(mode="json") for event in session.events] if include_events else [],
    }
