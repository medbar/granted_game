from __future__ import annotations

import ast
import atexit
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic_monty import Monty, MontyError

from .agent_models import AgentAction
from .models import CastRequest, Vec2, WorldAction, WorldObject
from .plugins import PluginRegistry


MAX_PROGRAM_CHARS = 6_000
MAX_AST_NODES = 320
MAX_ACTIONS = 16
ACTION_CAPABILITIES = {
    "affect_mind",
    "apply_force",
    "apply_state",
    "change_temperature",
    "collect",
    "damage",
    "destroy",
    "destroy_all",
    "equip_outfit",
    "heal",
    "give_item",
    "inspect",
    "install_doors",
    "interact",
    "set_material",
    "shutdown_game",
    "spawn",
    "spawn_many",
    "speak",
    "set_aggro",
    "set_game_paused",
    "set_game_speed",
    "set_light_level",
    "transform",
}
KNOWN_CAPABILITIES = ACTION_CAPABILITIES | {"observe_area", "nearest", "all_with_tag", "inspect"}
ALLOWED_STATES = {
    "asleep",
    "banished",
    "blood_soaked",
    "bound",
    "burning",
    "electrified",
    "friendly",
    "frozen",
    "influenced",
    "invisible",
    "levitating",
    "pacified",
    "phased",
    "poisoned",
    "slowed",
    "transformed",
    "wet",
}
STATE_ALIASES = {
    "burn": "burning",
    "on_fire": "burning",
    "freeze": "frozen",
    "sleep": "asleep",
    "bind": "bound",
    "pacify": "pacified",
    "blood": "blood_soaked",
    "soaked_in_blood": "blood_soaked",
    "soaked and drenched in blood from head to toe": "blood_soaked",
    "phase": "phased",
    "invisibility": "invisible",
    "invisible": "invisible",
    "soaked": "wet",
    "transform": "transformed",
}
ALLOWED_MATERIALS = {"ash", "blood", "gold", "ice", "metal", "stone", "steam", "water", "wood"}
ALLOWED_PROTOTYPES = {
    "blood",
    "blood_pool",
    "cage",
    "crate",
    "enemy",
    "fire",
    "key",
    "magic_key",
    "npc",
    "portal",
    "rope",
    "shield",
    "sleep_dust",
    "sword",
    "trap",
    "tunnel",
    "wall",
}
ALLOWED_OUTFITS = {"dress", "robe", "armor", "cloak"}
ALLOWED_TRANSFORM_FORMS = {"cage", "crate", "enemy", "key", "metal", "npc", "rock", "shield", "sword", "tree"}
FORM_ALIASES = {"box": "crate", "wooden_box": "crate"}


@dataclass
class MontyExecutionResult:
    output: Any = None
    actions: list[AgentAction] = field(default_factory=list)
    execution_ms: float = 0.0
    error: str | None = None

    @property
    def successful(self) -> bool:
        return self.error is None and bool(self.actions) and all(action.success for action in self.actions)


class MontyGenieRuntime:
    """Execute model-written Python in Monty with a tiny capability-only game API."""

    _pool: Monty | None = None
    _pool_lock = threading.Lock()
    _execution_lock = threading.Lock()

    def __init__(self, plugin_registry: PluginRegistry | None = None) -> None:
        self.plugin_registry = plugin_registry or PluginRegistry.from_default()

    @classmethod
    def _get_pool(cls) -> Monty:
        with cls._pool_lock:
            if cls._pool is None:
                cls._pool = Monty(
                    min_processes=1,
                    max_processes=2,
                    checkout_timeout=2.0,
                    request_timeout=2.0,
                    max_checkouts_per_worker=250,
                )
                cls._pool.__enter__()
            return cls._pool

    @classmethod
    def close_pool(cls) -> None:
        with cls._pool_lock:
            if cls._pool is not None:
                cls._pool.__exit__(None, None, None)
                cls._pool = None

    def validate_source(self, code: str) -> str:
        source = code.strip()
        if source.startswith("```python") and source.endswith("```"):
            source = source[len("```python") : -3].strip()
        elif source.startswith("```") and source.endswith("```"):
            source = source[3:-3].strip()
        if not source:
            raise ValueError("Monty program is empty")
        if len(source) > MAX_PROGRAM_CHARS:
            raise ValueError(f"Monty program exceeds {MAX_PROGRAM_CHARS} characters")
        tree = ast.parse(source, filename="genie_wish.py", mode="exec")
        nodes = list(ast.walk(tree))
        if len(nodes) > MAX_AST_NODES:
            raise ValueError(f"Monty program exceeds {MAX_AST_NODES} syntax nodes")
        forbidden = (
            ast.Import,
            ast.ImportFrom,
            ast.ClassDef,
            ast.Global,
            ast.Nonlocal,
            ast.With,
            ast.AsyncWith,
            ast.While,
        )
        for node in nodes:
            if isinstance(node, forbidden):
                raise ValueError(f"{type(node).__name__} is not allowed in genie programs")
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise ValueError("dunder names are not allowed in genie programs")
            if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                raise ValueError("dunder attributes are not allowed in genie programs")
        capability_calls = {
            node.func.id
            for node in nodes
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        disabled = sorted(
            capability
            for capability in capability_calls.intersection(KNOWN_CAPABILITIES)
            if not self.plugin_registry.is_enabled(capability)
        )
        if disabled:
            raise ValueError(
                "capability disabled by plugin registry: " + ", ".join(disabled)
            )
        if not capability_calls.intersection(ACTION_CAPABILITIES):
            raise ValueError("genie program must call at least one game capability")
        if len(source.splitlines()) == 1 and "#" in source:
            raise ValueError(
                "single-line programs cannot contain comments; put every statement on its own line"
            )
        if capability_calls and capability_calls <= {"inspect"}:
            raise ValueError("inspect alone does not fulfill a wish; add a world action")
        return source

    def execute(
        self,
        code: str,
        request: CastRequest,
        *,
        session: Any | None = None,
        on_action: Callable[[AgentAction], None] | None = None,
    ) -> MontyExecutionResult:
        started = time.perf_counter()
        actions: list[AgentAction] = []
        transformed_forms: dict[str, str] = {}
        try:
            source = self.validate_source(code)
        except (SyntaxError, ValueError) as error:
            return MontyExecutionResult(
                actions=actions,
                execution_ms=(time.perf_counter() - started) * 1000.0,
                error=f"validation: {error}",
            )

        def objects() -> list[WorldObject]:
            return session.world.objects if session is not None else request.world.objects

        def entity(target_id: str | None) -> WorldObject | None:
            if not target_id:
                return None
            if session is not None:
                return session.entity(str(target_id))
            return next((item for item in objects() if item.id == str(target_id)), None)

        def safe_target(target_id: Any) -> str:
            value = str(target_id or "")
            if not value or entity(value) is None:
                raise ValueError(f"unknown target: {value or '<empty>'}")
            return value

        def bounded(value: Any, minimum: float = 0.0, maximum: float = 1.0) -> float:
            return max(minimum, min(maximum, float(value)))

        def effective_tags(item: WorldObject) -> set[str]:
            tags = {part.lower() for part in item.tags}
            form = transformed_forms.get(item.id)
            if form is None:
                return tags
            tags -= {
                "cage", "crate", "enemy", "friendly", "inanimate", "key", "living",
                "metal", "npc", "organic", "prop", "rock", "shield", "sword", "tree",
                "villager",
            }
            if form == "npc":
                tags.update({"living", "npc", "villager", "friendly", "organic"})
            elif form == "enemy":
                tags.update({"living", "enemy", "hostile", "organic"})
            else:
                tags.update({"inanimate", "prop", form})
            return tags

        def record(
            kind: str,
            target_id: str | None,
            parameters: dict[str, Any],
            world_action: WorldAction | None,
            observation: str,
        ) -> dict[str, Any]:
            if len(actions) >= MAX_ACTIONS:
                raise RuntimeError(f"genie action limit ({MAX_ACTIONS}) exceeded")
            success = True
            actual_observation = observation
            if session is not None:
                success, actual_observation = session.apply(kind, target_id, parameters, world_action)
            action = AgentAction(
                sequence=len(actions) + 1,
                kind=kind,
                target_id=target_id,
                parameters=parameters,
                observation=actual_observation,
                success=success,
                teleport_to_target=target_id is not None,
                world_action=world_action if success else None,
            )
            actions.append(action)
            if on_action is not None:
                on_action(action)
            return {
                "success": success,
                "target_id": target_id,
                "observation": actual_observation,
                "sequence": action.sequence,
            }

        def nearest(tag: str, from_id: str = "player") -> str | None:
            wanted = str(tag).lower()
            origin_entity = entity(from_id)
            origin = origin_entity.position if origin_entity else request.caster.position
            candidates = [item for item in objects() if wanted in effective_tags(item)]
            if not candidates:
                return None
            return min(
                candidates,
                key=lambda item: (item.position.x - origin.x) ** 2 + (item.position.y - origin.y) ** 2,
            ).id

        def all_with_tag(tag: str, limit: int = MAX_ACTIONS) -> list[str]:
            bounded_limit = max(0, min(MAX_ACTIONS, int(limit)))
            wanted = str(tag).lower()
            return [
                item.id
                for item in objects()
                if wanted in effective_tags(item)
            ][:bounded_limit]

        def inspect(target_id: str) -> dict[str, Any]:
            target = entity(safe_target(target_id))
            assert target is not None
            result = record(
                "inspect_entity",
                target.id,
                {},
                None,
                target.model_dump_json(exclude_none=True),
            )
            result["entity"] = target.model_dump(mode="json", exclude_none=True)
            return result

        def damage(target_id: str, amount: float = 60.0) -> dict[str, Any]:
            target = safe_target(target_id)
            value = bounded(amount, 0.0, 10_000.0)
            return record(
                "affect_physical",
                target,
                {"effect": "damage", "amount": value},
                WorldAction(type="DAMAGE", target_id=target, amount=value),
                f"Нанесено {value:.1f} урона цели {target}.",
            )

        def heal(target_id: str, amount: float = 24.0) -> dict[str, Any]:
            target = safe_target(target_id)
            value = bounded(amount, 0.0, 10_000.0)
            return record(
                "affect_physical",
                target,
                {"effect": "heal", "amount": value},
                WorldAction(type="HEAL", target_id=target, amount=value),
                f"Восстановлено {value:.1f} здоровья цели {target}.",
            )

        def destroy(target_id: str) -> dict[str, Any]:
            target = safe_target(target_id)
            return record(
                "affect_physical",
                target,
                {"effect": "destroy", "strength": 1.0},
                WorldAction(type="DESTROY_OBJECT", target_id=target),
                f"Цель {target} уничтожена.",
            )

        def destroy_all(tag: str) -> dict[str, Any]:
            wanted = str(tag).strip().lower()
            target_ids = [item.id for item in objects() if wanted in effective_tags(item)]
            if not target_ids:
                raise ValueError(f"there are no entities tagged {wanted}")
            return record(
                "affect_physical",
                target_ids[0],
                {"effect": "destroy_all", "tag": wanted, "target_ids": target_ids},
                WorldAction(
                    type="DESTROY_OBJECTS",
                    target_id=target_ids[0],
                    effect={"tag": wanted, "target_ids": target_ids},
                ),
                f"Уничтожены все цели с тегом {wanted}: {len(target_ids)}.",
            )

        def apply_force(target_id: str, x: float = 1.0, y: float = 0.0, strength: float = 6.0) -> dict[str, Any]:
            target = safe_target(target_id)
            direction = Vec2(x=bounded(x, -1.0, 1.0), y=bounded(y, -1.0, 1.0))
            value = bounded(strength, 0.0, 12.0)
            return record(
                "affect_physical",
                target,
                {"effect": "force", "x": direction.x, "y": direction.y, "strength": value},
                WorldAction(type="APPLY_FORCE", target_id=target, direction=direction, strength=value),
                f"К цели {target} приложена магическая сила {value:.2f}.",
            )

        def apply_state(
            target_id: str,
            state: str,
            intensity: float = 1.0,
            duration: float = 4.0,
        ) -> dict[str, Any]:
            target = safe_target(target_id)
            normalized = STATE_ALIASES.get(str(state).strip().lower(), str(state).strip().lower())
            if normalized not in ALLOWED_STATES:
                raise ValueError(f"unsupported state: {state}")
            value = bounded(intensity)
            seconds = bounded(duration, 0.1, 120.0)
            target_entity = entity(target)
            if normalized == "frozen" and target_entity and "water" in target_entity.tags:
                world_action = WorldAction(type="CHANGE_MATERIAL_STATE", target_id=target, material="ice")
            else:
                world_action = WorldAction(
                    type="ADD_STATE",
                    target_id=target,
                    state=normalized,
                    strength=value,
                    duration=seconds,
                )
            return record(
                "affect_physical",
                target,
                {"effect": "add_state", "state": normalized, "strength": value, "duration": seconds},
                world_action,
                f"На {target} наложено состояние {normalized}.",
            )

        def set_material(target_id: str, material: str) -> dict[str, Any]:
            target = safe_target(target_id)
            normalized = str(material).strip().lower()
            if normalized not in ALLOWED_MATERIALS:
                raise ValueError(f"unsupported material: {material}")
            return record(
                "affect_physical",
                target,
                {"effect": "set_material", "material": normalized},
                WorldAction(type="CHANGE_MATERIAL_STATE", target_id=target, material=normalized),
                f"Материал {target} изменён на {normalized}.",
            )

        def transform(target_id: str, form: str) -> dict[str, Any]:
            target = safe_target(target_id)
            normalized = str(form).strip().lower().replace(" ", "_")
            normalized = FORM_ALIASES.get(normalized, normalized)
            if normalized not in ALLOWED_TRANSFORM_FORMS:
                raise ValueError(f"unsupported transform form: {form}")
            result = record(
                "affect_physical",
                target,
                {"effect": "transform_object", "prototype": normalized},
                WorldAction(
                    type="TRANSFORM_OBJECT",
                    target_id=target,
                    effect={"prototype": normalized},
                ),
                f"Форма {target} изменена на {normalized}.",
            )
            if result["success"]:
                transformed_forms[target] = normalized
            return result

        def change_temperature(target_id: str, amount: float) -> dict[str, Any]:
            target = safe_target(target_id)
            value = bounded(amount, -1.0, 1.0)
            return record(
                "affect_physical",
                target,
                {"effect": "change_temperature", "amount": value},
                WorldAction(type="CHANGE_TEMPERATURE", target_id=target, amount=value),
                f"Температура {target} изменена на {value:+.2f}.",
            )

        def install_doors() -> dict[str, Any]:
            wall_ids = [item.id for item in objects() if "wall" in effective_tags(item)]
            if not wall_ids:
                raise ValueError("there are no wall entities in the world snapshot")
            target = wall_ids[0]
            return record(
                "affect_physical",
                target,
                {"effect": "install_doors", "wall_ids": wall_ids},
                WorldAction(
                    type="INSTALL_DOORS",
                    target_id=target,
                    effect={"wall_ids": wall_ids},
                ),
                f"В {len(wall_ids)} стенах установлены двери.",
            )

        def equip_outfit(target_id: str, outfit: str) -> dict[str, Any]:
            target = safe_target(target_id)
            normalized = str(outfit).strip().lower().replace(" ", "_")
            if normalized not in ALLOWED_OUTFITS:
                raise ValueError(f"unsupported outfit: {outfit}")
            return record(
                "affect_physical",
                target,
                {"effect": "equip_outfit", "outfit": normalized},
                WorldAction(
                    type="EQUIP_OUTFIT",
                    target_id=target,
                    effect={"outfit": normalized},
                ),
                f"На {target} надет наряд {normalized}.",
            )

        def shutdown_game() -> dict[str, Any]:
            target = safe_target("player")
            return record(
                "affect_physical",
                target,
                {"effect": "shutdown_game"},
                WorldAction(type="SHUTDOWN_GAME", target_id=target),
                "Джин выключает игру.",
            )

        def set_game_paused(paused: bool = True) -> dict[str, Any]:
            target = safe_target("player")
            value = bool(paused)
            return record(
                "affect_physical",
                target,
                {"effect": "set_game_paused", "paused": value},
                WorldAction(
                    type="SET_GAME_PAUSED",
                    target_id=target,
                    effect={"paused": value},
                ),
                "Игра поставлена на паузу." if value else "Игра продолжена.",
            )

        def set_game_speed(multiplier: float) -> dict[str, Any]:
            target = safe_target("player")
            value = bounded(multiplier, 0.1, 3.0)
            return record(
                "affect_physical",
                target,
                {"effect": "set_game_speed", "multiplier": value},
                WorldAction(
                    type="SET_GAME_SPEED",
                    target_id=target,
                    effect={"multiplier": value},
                ),
                f"Скорость мира установлена: {value:.2f}.",
            )

        def set_light_level(level: float) -> dict[str, Any]:
            target = safe_target("player")
            value = bounded(level, 0.1, 2.0)
            return record(
                "affect_physical",
                target,
                {"effect": "set_light_level", "level": value},
                WorldAction(
                    type="SET_LIGHT_LEVEL",
                    target_id=target,
                    effect={"level": value},
                ),
                f"Освещённость мира установлена: {value:.2f}.",
            )

        def spawn(prototype: str, near: str = "player", kind: str = "object") -> dict[str, Any]:
            normalized = str(prototype).strip().lower().replace(" ", "_")
            if normalized not in ALLOWED_PROTOTYPES:
                raise ValueError(f"unsupported prototype: {prototype}")
            target = safe_target(near)
            action_kind = "create_item" if str(kind).lower() == "item" else "create_object"
            return record(
                action_kind,
                target,
                {"prototype": normalized},
                WorldAction(
                    type="CREATE_OBJECT",
                    target_id=target,
                    effect={"kind": "item" if action_kind == "create_item" else "object", "prototype": normalized},
                ),
                f"Рядом с {target} создан объект {normalized}.",
            )

        def spawn_many(prototype: str, count: int, near: str = "player") -> dict[str, Any]:
            normalized = str(prototype).strip().lower().replace(" ", "_")
            if normalized not in ALLOWED_PROTOTYPES:
                raise ValueError(f"unsupported prototype: {prototype}")
            bounded_count = max(1, min(32, int(count)))
            target = safe_target(near)
            return record(
                "create_object",
                target,
                {"prototype": normalized, "count": bounded_count},
                WorldAction(
                    type="CREATE_OBJECT_BATCH",
                    target_id=target,
                    effect={"kind": "object", "prototype": normalized, "count": bounded_count},
                ),
                f"Рядом с {target} создано объектов {normalized}: {bounded_count}.",
            )

        def give_item(prototype: str, owner: str = "player") -> dict[str, Any]:
            normalized = str(prototype).strip().lower().replace(" ", "_")
            if normalized not in ALLOWED_PROTOTYPES:
                raise ValueError(f"unsupported inventory prototype: {prototype}")
            target = safe_target(owner)
            return record(
                "create_item",
                target,
                {"prototype": normalized, "owner": target, "destination": "inventory"},
                WorldAction(
                    type="ADD_INVENTORY_ITEM",
                    target_id=target,
                    effect={"kind": "item", "prototype": normalized, "owner": target},
                ),
                f"Предмет {normalized} добавлен в инвентарь {target}.",
            )

        def set_aggro(actor_id: str, target_id: str = "player") -> dict[str, Any]:
            actor = safe_target(actor_id)
            target = safe_target(target_id)
            actor_entity = entity(actor)
            if actor_entity is None or "living" not in effective_tags(actor_entity):
                raise ValueError(f"target {actor} is not a living actor")
            return record(
                "affect_mind",
                actor,
                {"influence": f"attack and pursue {target}", "strength": 1.0, "aggro_target": target},
                WorldAction(
                    type="SET_AGGRO_TARGET",
                    target_id=actor,
                    effect={"aggro_target": target},
                ),
                f"{actor} теперь преследует {target}.",
            )

        def interact(target_id: str, interaction: str = "interact") -> dict[str, Any]:
            target = safe_target(target_id)
            text = str(interaction)[:240]
            return record(
                "interact",
                target,
                {"interaction": text},
                WorldAction(type="INTERACT", target_id=target, effect={"interaction": text}),
                f"Джин взаимодействовал с {target}: {text}",
            )

        def collect(target_id: str) -> dict[str, Any]:
            target = safe_target(target_id)
            target_entity = entity(target)
            if target_entity is None or "loot" not in effective_tags(target_entity):
                raise ValueError(f"target {target} is not collectible loot")
            return record(
                "interact",
                target,
                {"interaction": "collect"},
                WorldAction(
                    type="INTERACT",
                    target_id=target,
                    effect={"interaction": "collect"},
                ),
                f"Джин забрал ценность {target}.",
            )

        def affect_mind(target_id: str, influence: str, strength: float = 1.0) -> dict[str, Any]:
            target = safe_target(target_id)
            target_entity = entity(target)
            if target_entity is None or "living" not in effective_tags(target_entity):
                raise ValueError(f"target {target} has no mind; transform it to npc first")
            text = str(influence)[:300]
            value = bounded(strength)
            return record(
                "affect_mind",
                target,
                {"influence": text, "strength": value},
                WorldAction(
                    type="ADD_STATE",
                    target_id=target,
                    state="influenced",
                    strength=value,
                    duration=6.0,
                    effect={"thought": text},
                ),
                f"Мысли {target} изменены: {text}",
            )

        def speak(target_id: str, message: str) -> dict[str, Any]:
            target = safe_target(target_id)
            text = str(message)[:300]
            if session is not None and "$gate_code" in text:
                text = text.replace("$gate_code", session.known_facts.get("gate_code", "$gate_code"))
            return record(
                "speak",
                target,
                {"message": text},
                WorldAction(type="SPEAK", target_id=target, effect={"message": text}),
                f"Джин сказал {target}: {text}",
            )

        external_lookup = {
            "nearest": nearest,
            "all_with_tag": all_with_tag,
            "inspect": inspect,
            "damage": damage,
            "heal": heal,
            "give_item": give_item,
            "destroy": destroy,
            "destroy_all": destroy_all,
            "apply_force": apply_force,
            "apply_state": apply_state,
            "set_material": set_material,
            "transform": transform,
            "change_temperature": change_temperature,
            "install_doors": install_doors,
            "equip_outfit": equip_outfit,
            "shutdown_game": shutdown_game,
            "set_game_paused": set_game_paused,
            "set_game_speed": set_game_speed,
            "set_light_level": set_light_level,
            "spawn": spawn,
            "spawn_many": spawn_many,
            "interact": interact,
            "collect": collect,
            "affect_mind": affect_mind,
            "speak": speak,
            "set_aggro": set_aggro,
        }
        external_lookup = {
            name: handler
            for name, handler in external_lookup.items()
            if self.plugin_registry.is_enabled(name)
        }

        try:
            pool = self._get_pool()
            with self._execution_lock:
                with pool.checkout(
                    script_name="genie_wish.py",
                    limits={
                        "max_duration_secs": 0.08,
                        "max_memory": 4 * 1024 * 1024,
                        "max_recursion_depth": 48,
                    },
                ) as monty_session:
                    output = monty_session.feed_run(source, external_lookup=external_lookup)
            return MontyExecutionResult(
                output=output,
                actions=actions,
                execution_ms=(time.perf_counter() - started) * 1000.0,
            )
        except (MontyError, RuntimeError, TypeError, ValueError) as error:
            detail = error.display(format="type-msg") if isinstance(error, MontyError) else str(error)
            return MontyExecutionResult(
                actions=actions,
                execution_ms=(time.perf_counter() - started) * 1000.0,
                error=detail,
            )


atexit.register(MontyGenieRuntime.close_pool)
