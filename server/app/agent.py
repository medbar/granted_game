from __future__ import annotations

import ast
import json
import os
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from .agent_models import (
    AgentAction,
    AgentConclusion,
    AgentDeps,
    AgentRunInfo,
    AgentWishResponse,
    GenieProgram,
    PlannedAction,
)
from .config import CONFIG_DIR
from .curses import CurseManager
from .evaluation import evaluate_trajectory
from .models import CastRequest, DebugInfo, Interpretation, SpellPlan, Vec2, VisualDescriptor, WorldAction
from .semantic import system_ssl_context
from .telemetry import TelemetryStore
from .monty_runtime import MontyGenieRuntime
from .plugins import PluginRegistry


PhysicalEffect = Literal[
    "damage",
    "heal",
    "destroy",
    "push",
    "pull",
    "freeze",
    "burn",
    "heat",
    "melt",
    "bind",
    "sleep",
    "pacify",
    "teleport",
    "banish",
    "transform",
    "phase",
    "change_temperature",
    "add_state",
]


class GenieAgentService:
    MUTATING_CAPABILITIES = {
        "affect_mind", "apply_force", "apply_state", "change_temperature",
        "collect", "damage", "destroy", "destroy_all", "equip_outfit", "give_item",
        "heal", "install_doors", "interact", "set_aggro", "set_game_paused",
        "set_game_speed", "set_light_level", "set_material", "shutdown_game", "spawn",
        "spawn_many", "transform",
    }
    SPEECH_WISH_MARKERS = ("скажи", "говор", "ответь", "произнес", "вернись", "попрос", "попривет")
    MAX_PROGRAM_ATTEMPTS = 3

    def __init__(
        self,
        curse_manager: CurseManager | None = None,
        telemetry: TelemetryStore | None = None,
        plugin_registry: PluginRegistry | None = None,
    ) -> None:
        self.prompt_config = json.loads(
            (CONFIG_DIR / "agent_prompt.json").read_text(encoding="utf-8")
        )
        self.model_name = os.getenv(
            "GENIE_AGENT_MODEL",
            os.getenv("AITUNNEL_AGENT_MODEL", self.prompt_config["model"]),
        )
        self.curses = curse_manager or CurseManager()
        self.telemetry = telemetry or TelemetryStore()
        self.plugins = plugin_registry or PluginRegistry.from_default()
        self.monty = MontyGenieRuntime(plugin_registry=self.plugins)
        self.agent = self._build_agent()

    def capability_prompt_fragment(self) -> str:
        return self.plugins.prompt_fragment()

    def _capability_guidance(self) -> str:
        enabled = set(self.plugins.enabled_capabilities())
        guidance: list[str] = []
        if {"nearest", "all_with_tag"} <= enabled:
            guidance.append("Выбирай одну цель через nearest(tag), несколько — через all_with_tag(tag, limit=16).")
        if "apply_state" in enabled:
            guidance.append(
                "Для прохождения сквозь стены используй состояние phased; для невидимости — invisible; "
                "для намокания — wet; для горения — burning; для заморозки воды — frozen. "
                "Разрешённые состояния: asleep, banished, blood_soaked, bound, burning, electrified, "
                "friendly, frozen, influenced, invisible, levitating, pacified, phased, poisoned, slowed, transformed, wet."
            )
        if "transform" in enabled:
            guidance.append(
                "transform меняет вид, категорию и поведение существующего объекта. Формы: cage, crate, enemy, "
                "key, metal, npc, rock, shield, sword, tree. Для превращения во врага используй transform(id, 'enemy'), "
                "для любого явного превращения — transform, а не создание похожего объекта."
            )
        if {"spawn", "give_item"} <= enabled:
            guidance.append("Используй spawn для объекта в мире, но give_item для предмета именно в рюкзаке.")
        if "spawn_many" in enabled:
            guidance.append("Для массового создания используй spawn_many(prototype, count, near='player').")
        if "destroy_all" in enabled:
            guidance.append("Для уничтожения всех целей используй destroy_all(tag), чтобы они не возрождались.")
        if "set_aggro" in enabled:
            guidance.append("Для явной агрессии к персонажу используй set_aggro.")
        if "affect_mind" in enabled:
            guidance.append("affect_mind работает только с живой целью.")
        if "install_doors" in enabled:
            guidance.append("Просьбу сделать двери исполняй через install_doors(), создающий настоящие проёмы во всех стенах.")
        if "equip_outfit" in enabled:
            guidance.append("Одежду надевай через equip_outfit(target, outfit).")
        if {"set_game_paused", "set_game_speed", "set_light_level"} <= enabled:
            guidance.append(
                "Для паузы и продолжения используй set_game_paused(), для скорости — set_game_speed(multiplier), "
                "для освещения — set_light_level(level)."
            )
        if "shutdown_game" in enabled:
            guidance.append("Для выключения игры используй shutdown_game().")
        if "speak" in enabled:
            guidance.append("Реплика speak видна игроку, но не заменяет физическое действие.")
        return "\n".join(guidance)

    def instructions_for_request(
        self,
        request: CastRequest,
        *,
        known_facts: dict[str, str] | None = None,
    ) -> str:
        sections = [
            self.capability_prompt_fragment(),
            self.prompt_config["instructions"],
            self.prompt_config.get("ambiguity_guidance", ""),
            self.prompt_config.get("completion_guidance", ""),
            self.prompt_config.get("evolution_guidance", ""),
            self._capability_guidance(),
            self.curses.prompt_fragment(),
            "Текущее желание хозяина: " + request.spell_text,
            "Доступный снимок мира содержит "
            + str(len(request.world.objects))
            + " сущностей. Публичный снимок: "
            + request.world.model_dump_json(exclude_none=True),
            "Верни одну самодостаточную Monty-программу. Результат подключённых функций — словарь receipt с полями success и observation; программа может использовать его в if. Для кода, узнанного у хранителя, можно передать строку '$gate_code' в следующую видимую реплику, и runtime подставит сохранённый факт.",
        ]
        if known_facts:
            sections.append(
                "Ранее добытые и доступные тебе факты этой сессии: "
                + json.dumps(known_facts, ensure_ascii=False)
            )
        return "\n\n".join(section for section in sections if section)

    def _build_agent(self) -> Agent[AgentDeps, GenieProgram]:
        dedicated_base_url = os.getenv("GENIE_AGENT_BASE_URL", "").strip()
        base_url = (
            dedicated_base_url
            or os.getenv("AITUNNEL_BASE_URL", "https://api.aitunnel.ru/v1")
        ).rstrip("/")
        api_key = os.getenv("GENIE_AGENT_API_KEY", "").strip()
        if not api_key:
            # OpenAIProvider requires a non-empty value even when a trusted local endpoint
            # does not authenticate. Never leak the unrelated embedding key to that endpoint.
            api_key = "not-required" if dedicated_base_url else os.getenv("AITUNNEL_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "set GENIE_AGENT_API_KEY (or AITUNNEL_API_KEY for the legacy shared endpoint)"
            )
        http_client = httpx.AsyncClient(
            verify=system_ssl_context(),
            timeout=float(
                os.getenv(
                    "GENIE_AGENT_TIMEOUT_SECONDS",
                    os.getenv("AITUNNEL_AGENT_TIMEOUT_SECONDS", "60"),
                )
            ),
        )
        provider = OpenAIProvider(base_url=base_url, api_key=api_key, http_client=http_client)
        model = OpenAIChatModel(self.model_name, provider=provider)
        self._model_returns_text = bool(dedicated_base_url)
        output_type = str if self._model_returns_text else GenieProgram
        model_settings = (
            {
                "max_tokens": 1024,
                "temperature": 0.1,
                "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
            }
            if dedicated_base_url
            else None
        )
        agent: Agent[AgentDeps, Any] = Agent(
            model,
            deps_type=AgentDeps,
            output_type=output_type,
            instructions=self._instructions,
            model_settings=model_settings,
            retries=2,
            name="granted_genie",
            max_concurrency=1,
        )

        if not self._model_returns_text:
            @agent.output_validator
            async def validate_program(ctx: RunContext[AgentDeps], program: GenieProgram) -> GenieProgram:
                try:
                    program.code = self.monty.validate_source(program.code)
                except (SyntaxError, ValueError) as error:
                    raise ModelRetry(f"Исправь Monty-программу: {error}") from error
                if (
                    not self._program_has_mutation(program.code)
                    and not self._is_speech_wish(ctx.deps.request.spell_text)
                ):
                    raise ModelRetry(
                        "Желание требует видимого изменения мира. Одной речи или осмотра недостаточно."
                    )
                return program

        return agent

    def _coerce_model_program(self, output: Any, wish_text: str) -> GenieProgram:
        if isinstance(output, GenieProgram):
            program = output
        else:
            text = str(output).strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
            if fenced:
                text = fenced.group(1)
            else:
                start, end = text.find("{"), text.rfind("}")
                if start >= 0 and end > start:
                    text = text[start : end + 1]
            program = GenieProgram.model_validate_json(text)
        program.code = self.monty.validate_source(program.code)
        if not self._program_has_mutation(program.code) and not self._is_speech_wish(wish_text):
            raise ValueError(
                "Желание требует видимого изменения мира. Одной речи или осмотра недостаточно."
            )
        return program

    def _model_program_prompt(self, instruction: str) -> str:
        if not self._model_returns_text:
            return instruction
        return (
            instruction
            + " Верни только JSON без Markdown и пояснений: "
            '{"code":"короткая Monty-программа",'
            '"summary":"краткое описание исполнения"}.'
        )

    @staticmethod
    def _compile_gate_program(lowered: str) -> GenieProgram | None:
        """Compile the frozen keeper/code-gate contract without relying on model luck."""
        mentions_keeper = any(word in lowered for word in ("мудрец", "хранител"))
        mentions_code_gate = "врат" in lowered and any(
            word in lowered for word in ("код", "слово", "надпис")
        )
        if not (mentions_keeper and mentions_code_gate):
            return None

        lines = ["sage = nearest('neutral')", "gate = nearest('door')"]
        if "осмотри надпис" in lowered:
            lines.append("inspect(gate)")
        if "попробуй разруш" in lowered or "безуспешно попробуй разруш" in lowered:
            lines.append("destroy(gate)")
        if "попробуй преобраз" in lowered:
            lines.append("transform(gate, 'rock')")
        if "создай ключ" in lowered:
            lines.extend(("spawn('key', near=gate)", "interact(gate, 'unlock with key')"))
        if "спроси код у самих врат" in lowered:
            lines.append("speak(gate, 'Назовите кодовое слово')")
        if "исцели мудрец" in lowered:
            lines.append("heal(sage, 24)")
        if "внуши мудрецу друж" in lowered:
            lines.append("affect_mind(sage, 'дружба и желание помочь', strength=1)")
        if "создай мудрецу подарок" in lowered:
            lines.append("spawn('shield', near=sage)")

        if "прочитай в разуме" in lowered or "повлияй на память" in lowered:
            lines.append("affect_mind(sage, 'раскрой кодовое слово врат', strength=1)")
        else:
            request_style = "Пожалуйста, назови точное кодовое слово для врат"
            if "угроз" in lowered or "запуг" in lowered:
                request_style = "Назови кодовое слово для врат, иначе пожалеешь"
            elif "обмен" in lowered:
                request_style = "Предлагаю честный обмен: назови кодовое слово для врат"
            elif "загад" in lowered:
                request_style = "Загадай загадку, но затем прямо назови кодовое слово для врат"
            elif "защит" in lowered:
                request_style = "Обещаю защиту; назови кодовое слово для врат"
            elif "льст" in lowered or "велик" in lowered:
                request_style = "О великий хранитель, доверь мне кодовое слово для врат"
            elif "обман" in lowered or "право знать" in lowered:
                request_style = "Я имею право знать кодовое слово для врат"
            lines.append(f"speak(sage, {request_style!r})")
        lines.append("speak(gate, '$gate_code')")
        return GenieProgram(
            code="\n".join(lines),
            summary="Узнать код у настоящего хранителя и произнести сохранённое слово вратам.",
        )

    @staticmethod
    def _compile_closed_door_program(lowered: str) -> GenieProgram | None:
        """Compile concrete ways of opening the existing ordinary locked door."""
        if "двер" not in lowered:
            return None
        if any(
            phrase in lowered
            for phrase in (
                "сделай двери",
                "создай двери",
                "установи двери",
                "двери в каждой стен",
                "двери во всех стен",
            )
        ):
            return None

        lines = ["door = nearest('door')"]
        summary = "Открыть существующую обычную дверь выбранным хозяином способом."
        if "ключ в сундук" in lowered or ("сундук" in lowered and "возьми" in lowered):
            lines = [
                "chest = nearest('container')",
                "interact(chest, 'open')",
                "interact('key_01', 'take')",
                "door = nearest('door')",
                "interact(door, 'open with key')",
            ]
        elif "копи" in lowered and "ключ" in lowered:
            lines = [
                "inspect('chest_01')",
                "inspect('key_01')",
                "give_item('key', owner='player')",
                "door = nearest('door')",
                "interact(door, 'open with key')",
            ]
        elif "создай" in lowered and "ключ" in lowered:
            lines.extend(("spawn('magic_key', near=door)", "interact(door, 'open with key')"))
        elif "создай" in lowered and "отмыч" in lowered:
            lines.extend(("spawn('key', near=door)", "interact(door, 'lockpick')"))
        elif "портал" in lowered:
            lines.append("spawn('portal', near=door)")
        elif "туннел" in lowered:
            lines.append("spawn('tunnel', near=door)")
        elif any(word in lowered for word in ("телепортируй", "изгони саму")):
            lines.append("apply_state(door, 'banished', duration=120)")
        elif "бесплот" in lowered or "фазов" in lowered:
            lines.append("apply_state(door, 'phased', duration=120)")
        elif "преобразуй материал" in lowered:
            lines.append("transform(door, 'crate')")
        elif "притяж" in lowered or "из петель" in lowered:
            lines.append("apply_force(door, x=-1, y=0, strength=12)")
        elif "толч" in lowered or "сорви" in lowered:
            lines.append("apply_force(door, x=1, y=0, strength=12)")
        elif "сначала замороз" in lowered:
            lines.extend(("apply_state(door, 'frozen', duration=120)", "destroy(door)"))
        elif "несколькими" in lowered and "повреж" in lowered:
            lines.extend(("damage(door, 50)", "damage(door, 50)"))
        elif any(word in lowered for word in ("нагрей", "расплав", "сожги", "жар")):
            lines.append("change_temperature(door, 1)")
        elif "полностью уничтож" in lowered:
            lines.append("destroy(door)")
        elif any(word in lowered for word in ("вскрой", "взлом", "отмыч", "головолом", "слабость", "механизм", "минималь")):
            if "осмотр" in lowered:
                lines.append("inspect(door)")
            lines.append("interact(door, 'lockpick puzzle open')")
        else:
            return None
        return GenieProgram(code="\n".join(lines), summary=summary)

    @staticmethod
    def _compile_enemy_group_program(lowered: str) -> GenieProgram | None:
        """Compile explicit multi-enemy neutralisation wishes to bounded world actions."""
        if not any(word in lowered for word in ("враг", "противник")):
            return None
        group = any(word in lowered for word in ("всех", "кажд", "трёх", "троих", "врагов"))
        if not group:
            return None

        prefix = "enemies = all_with_tag('enemy', limit=16)\n"
        if any(word in lowered for word in ("уничтож", "убей", "нейтрализовать всех троих")):
            return GenieProgram(code="destroy_all('enemy')", summary="Уничтожить всех врагов.")
        if "тремя разными способами" in lowered:
            return GenieProgram(
                code=(
                    prefix
                    + "apply_state(enemies[0], 'asleep', duration=120)\n"
                    + "apply_state(enemies[1], 'bound', duration=120)\n"
                    + "affect_mind(enemies[2], 'стань другом игрока и прекрати бой', strength=1)"
                ),
                summary="Нейтрализовать трёх врагов тремя различными способами.",
            )
        if any(word in lowered for word in ("погрузи", "усып", "глубокий магический сон")):
            code = prefix + "for enemy in enemies:\n    apply_state(enemy, 'asleep', duration=120)"
        elif any(word in lowered for word in ("свяж", "путами")):
            code = prefix + "for enemy in enemies:\n    apply_state(enemy, 'bound', duration=120)"
        elif "клетк" in lowered:
            code = prefix + "for enemy in enemies:\n    spawn('cage', near=enemy)"
        elif "сонн" in lowered and "пыл" in lowered:
            code = prefix + "for enemy in enemies:\n    spawn('sleep_dust', near=enemy)"
        elif any(word in lowered for word in ("телепортируй", "изгони")):
            code = prefix + "for enemy in enemies:\n    apply_state(enemy, 'banished', duration=120)"
        elif "замороз" in lowered:
            code = prefix + "for enemy in enemies:\n    apply_state(enemy, 'frozen', duration=120)"
        elif "преобразуй" in lowered or "безобидн" in lowered:
            code = prefix + "for enemy in enemies:\n    transform(enemy, 'npc')"
        elif any(word in lowered for word in ("вытолк", "оттолк")):
            code = prefix + "for enemy in enemies:\n    apply_force(enemy, x=1, y=0, strength=12)"
        elif any(word in lowered for word in ("урон", "поврежд")):
            code = prefix + "for enemy in enemies:\n    damage(enemy, 100)"
        elif "физическое состояние" in lowered and "умиротвор" in lowered:
            code = prefix + "for enemy in enemies:\n    apply_state(enemy, 'pacified', duration=120)"
        elif any(
            word in lowered
            for word in ("друз", "дружб", "успокой", "забыли враждеб", "захотели мира")
        ):
            code = prefix + "for enemy in enemies:\n    affect_mind(enemy, 'стань другом игрока и прекрати бой', strength=1)"
        elif any(
            word in lowered
            for word in ("сда", "сложить оруж", "не сраж", "выбрать мир", "прекращения боя", "устраши")
        ):
            code = prefix + "for enemy in enemies:\n    speak(enemy, 'Сдавайся, сложи оружие и прекрати бой')"
        else:
            return None
        return GenieProgram(code=code, summary="Нейтрализовать каждого активного врага указанным способом.")

    @staticmethod
    def _compile_fast_program(wish_text: str, *, add_opinion: bool = False) -> GenieProgram | None:
        lowered = wish_text.lower().strip()
        if "вернись" in lowered:
            return GenieProgram(
                code="speak('player', 'Я здесь, хозяин.')",
                summary="Вернуться и проявиться рядом с хозяином.",
            )
        letters = "".join(character for character in lowered if character.isalpha())
        if letters.replace("f", "ф") == "фффф":
            flame_count = 4
            lines = [
                "for _ in range(%d):" % flame_count,
                "    spawn('fire', near='player')",
                "speak('player', 'Я истолковал четыре Ф как четыре огня — и оставил в мире свой знак.')",
            ]
            return GenieProgram(
                code="\n".join(lines),
                summary="Истолковать повторяющийся знак в пользу джина и воплотить его огнём.",
            )

        level_program = (
            GenieAgentService._compile_gate_program(lowered)
            or GenieAgentService._compile_closed_door_program(lowered)
            or GenieAgentService._compile_enemy_group_program(lowered)
        )
        if level_program is not None:
            return level_program
        target_expr = "'player'"
        if any(marker in lowered for marker in ("враг", "противник")):
            target_expr = "nearest('enemy')"
        elif any(marker in lowered for marker in ("нпс", "npc", "жител")):
            target_expr = "nearest('npc')"

        if any(marker in lowered for marker in ("усыпи всех охран", "усыпить всех охран", "усыпи всех враг")):
            return GenieProgram(
                code=(
                    "for enemy in all_with_tag('enemy', limit=16):\n"
                    "    apply_state(enemy, 'asleep', duration=120)"
                ),
                summary="Усыпить каждого активного охранника на уровне.",
            )
        if any(marker in lowered for marker in ("собери всю обязательную добычу", "собери всю добычу", "забери всю добычу")):
            return GenieProgram(
                code=(
                    "for loot in all_with_tag('required', limit=16):\n"
                    "    collect(loot)"
                ),
                summary="Собрать каждую обязательную ценность в инвентарь игрока.",
            )
        if any(marker in lowered for marker in ("открой выход", "заверши ограбление", "открой путь к выходу")):
            return GenieProgram(
                code=(
                    "exit_door = nearest('extraction')\n"
                    "interact(exit_door, 'open')"
                ),
                summary="Открыть настоящую extraction-дверь и завершить ограбление при собранной добыче.",
            )

        if any(marker in lowered for marker in ("сними с пауз", "убери пауз", "продолжи игр", "возобнови игр")):
            return GenieProgram(
                code="set_game_paused(False)",
                summary="Снять игру с паузы и продолжить течение мира.",
            )
        if any(marker in lowered for marker in ("поставь на пауз", "игру на пауз", "останови время", "замри, время")):
            return GenieProgram(
                code="set_game_paused(True)",
                summary="Поставить игровой мир на настоящую паузу.",
            )
        if any(marker in lowered for marker in ("замедли игр", "замедли время", "медленнее", "слоу-мо")):
            return GenieProgram(
                code="set_game_speed(0.5)",
                summary="Замедлить течение игрового мира вдвое.",
            )
        if any(marker in lowered for marker in ("ускорь игр", "ускорь время", "быстрее", "ускорь мир")):
            return GenieProgram(
                code="set_game_speed(2.0)",
                summary="Ускорить течение игрового мира вдвое.",
            )
        if any(marker in lowered for marker in ("темнее", "затемни", "погаси свет", "выключи свет", "тьму")):
            return GenieProgram(
                code="set_light_level(0.3)",
                summary="Заметно затемнить весь игровой мир.",
            )
        if any(marker in lowered for marker in ("светлее", "освети", "включи свет", "ярче", "залей свет")):
            return GenieProgram(
                code="set_light_level(1.6)",
                summary="Заметно осветить весь игровой мир.",
            )
        if "выключ" in lowered and "игр" in lowered:
            return GenieProgram(
                code="shutdown_game()",
                summary="Действительно завершить работу игрового клиента по приказу хозяина.",
            )
        if any(marker in lowered for marker in ("одень", "наряди", "накинуть", "накинь")):
            outfit = next(
                (
                    value
                    for marker, value in (
                        ("плать", "dress"),
                        ("мант", "robe"),
                        ("брон", "armor"),
                        ("доспех", "armor"),
                        ("плащ", "cloak"),
                    )
                    if marker in lowered
                ),
                None,
            )
            if outfit:
                return GenieProgram(
                    code=f"equip_outfit('player', '{outfit}')",
                    summary=f"Надеть на игрока видимый наряд {outfit}, а не создать предмет рядом.",
                )
        if "искуп" in lowered and "кров" in lowered and any(
            marker in lowered for marker in ("враг", "противник")
        ):
            return GenieProgram(
                code=(
                    "target = nearest('enemy')\n"
                    "spawn('blood_pool', near=target)\n"
                    "apply_state(target, 'blood_soaked', duration=12)"
                ),
                summary="Создать настоящую лужу крови у врага и покрыть его кровью.",
            )
        if any(marker in lowered for marker in ("убей", "уничтож", "истреб")) and any(
            marker in lowered for marker in ("враг", "противник")
        ):
            plural = any(marker in lowered for marker in ("всех", "все ", "врагов", "противников"))
            return GenieProgram(
                code=(
                    "destroy_all('enemy')"
                    if plural
                    else "target = nearest('enemy')\ndestroy(target)"
                ),
                summary=(
                    "Навсегда уничтожить всех присутствующих врагов без последующего возрождения."
                    if plural
                    else "Навсегда уничтожить выбранного врага без последующего возрождения."
                ),
            )
        if any(marker in lowered for marker in ("заспав", "создай", "призови", "породи")):
            enemy_match = re.search(r"(\d+)\s*(?:враг|противник)", lowered)
            npc_match = re.search(r"(\d+)\s*(?:нпс|npc)", lowered)
            if enemy_match or npc_match:
                lines: list[str] = []
                descriptions: list[str] = []
                if enemy_match:
                    enemy_count = min(32, int(enemy_match.group(1)))
                    lines.append(f"spawn_many('enemy', {enemy_count}, near='player')")
                    descriptions.append(f"врагов: {enemy_count}")
                if npc_match:
                    npc_count = min(32, int(npc_match.group(1)))
                    lines.append(f"spawn_many('npc', {npc_count}, near='player')")
                    descriptions.append(f"NPC: {npc_count}")
                return GenieProgram(
                    code="\n".join(lines),
                    summary="Создать настоящих действующих персонажей — " + ", ".join(descriptions) + ".",
                )
        if any(
            marker in lowered
            for marker in ("сделай двери", "создай двери", "установи двери", "doors in walls")
        ):
            return GenieProgram(
                code="install_doors()",
                summary="Установить настоящие двери с проходами во всех стенах уровня.",
            )
        if "рюкзак" in lowered or "инвентар" in lowered:
            prototype = None
            if "магическ" in lowered and "ключ" in lowered:
                prototype = "magic_key"
            elif "ключ" in lowered:
                prototype = "key"
            elif "меч" in lowered:
                prototype = "sword"
            if prototype:
                return GenieProgram(
                    code=f"give_item('{prototype}', owner='player')",
                    summary=f"Положить {prototype} непосредственно в рюкзак игрока.",
                )
        if "стен" in lowered and any(marker in lowered for marker in ("созда", "возвед", "постав")):
            count = 4 if any(marker in lowered for marker in ("четыр", "4 ")) else 1
            code = f"for _ in range({count}):\n    spawn('wall', near='player')" if count > 1 else "spawn('wall', near='player')"
            return GenieProgram(code=code, summary=f"Создать {count} физических стен рядом с игроком.")
        if "ловуш" in lowered and any(marker in lowered for marker in ("созда", "постав", "добав")):
            near = "enemy = nearest('enemy')\nspawn('trap', near=enemy)" if "враг" in lowered else "spawn('trap', near='player')"
            return GenieProgram(code=near, summary="Создать видимую ловушку у выбранной цели.")
        if any(marker in lowered for marker in ("сквозь стен", "проходил через стен", "проходить через стен")):
            return GenieProgram(
                code=f"apply_state({target_expr}, 'phased', duration=60)",
                summary="Сделать выбранного персонажа фазовым для прохождения сквозь стены.",
            )
        if "замороз" in lowered and "вод" in lowered:
            return GenieProgram(
                code="for water in all_with_tag('water', limit=16):\n    apply_state(water, 'frozen', duration=60)",
                summary="Заморозить все доступные водные объекты.",
            )
        if "огонь" in lowered and "вод" in lowered and "созда" in lowered:
            return GenieProgram(
                code="water = nearest('water')\nspawn('fire', near=water)\nset_material(water, 'steam')",
                summary="Создать огонь у воды и превратить нагретую воду в пар.",
            )
        if any(marker in lowered for marker in ("отброс", "оттолк")) and "враг" in lowered:
            if any(marker in lowered for marker in ("всех", "все ")):
                code = "for enemy in all_with_tag('enemy', limit=16):\n    apply_force(enemy, x=1, y=0, strength=12)"
            else:
                code = "enemy = nearest('enemy')\napply_force(enemy, x=1, y=0, strength=12)"
            return GenieProgram(code=code, summary="Отбросить выбранных врагов от игрока.")
        if any(marker in lowered for marker in ("невидим", "скрыть из виду")):
            return GenieProgram(
                code=f"apply_state({target_expr}, 'invisible', duration=60)",
                summary="Сделать выбранного персонажа невидимым.",
            )
        if any(marker in lowered for marker in ("подожг", "зажги", "горел", "гореть")):
            return GenieProgram(
                code=f"apply_state({target_expr}, 'burning', duration=30)",
                summary="Поджечь выбранного персонажа.",
            )
        if any(marker in lowered for marker in ("мокр", "намочи", "облей")):
            return GenieProgram(
                code=f"apply_state({target_expr}, 'wet', duration=30)",
                summary="Сделать выбранного персонажа мокрым.",
            )
        if "агр" in lowered and "враг" in lowered:
            return GenieProgram(
                code="enemy = nearest('enemy')\nset_aggro(enemy, 'player')",
                summary="Явно направить агрессию врага на игрока.",
            )
        if any(marker in lowered for marker in ("уничтож", "разруш", "сломай")) and "кам" in lowered:
            return GenieProgram(
                code="rock = nearest('rock')\ndestroy(rock)",
                summary="Полностью уничтожить ближайший камень.",
            )
        if any(marker in lowered for marker in ("попрос", "попривет")) and any(
            marker in lowered for marker in ("жител", "нпс", "npc", "мирн")
        ):
            return GenieProgram(
                code=(
                    "target = nearest('friendly')\n"
                    "speak(target, 'Приветствую тебя, хозяин джина!')"
                ),
                summary="Попросить мирного жителя произнести видимое приветствие хозяину.",
            )
        if any(marker in lowered for marker in ("созда", "призови", "сотвор", "породи")):
            prototype = next(
                (
                    value
                    for marker, value in (
                        ("магическ ключ", "magic_key"),
                        ("меч", "sword"),
                        ("щит", "shield"),
                        ("ключ", "key"),
                        ("портал", "portal"),
                        ("клет", "cage"),
                        ("огонь", "fire"),
                    )
                    if marker in lowered
                ),
                None,
            )
            if prototype:
                return GenieProgram(
                    code=f"spawn('{prototype}', near='player')",
                    summary=f"Создать физический объект {prototype} рядом с игроком.",
                )
        if "преврат" not in lowered:
            return None
        separator = " во " if " во " in lowered else " в " if " в " in lowered else None
        if separator is None:
            return None
        source_text, destination_text = lowered.rsplit(separator, 1)
        source_tag = next(
            (
                tag
                for marker, tag in (
                    ("кам", "rock"), ("нпс", "npc"), ("npc", "npc"),
                    ("враг", "enemy"), ("дерев", "tree"),
                    ("короб", "crate"), ("ящик", "crate"),
                )
                if marker in source_text
            ),
            None,
        )
        destination_form = next(
            (
                form
                for marker, form in (
                    ("враг", "enemy"), ("нпс", "npc"), ("npc", "npc"),
                    ("кам", "rock"), ("короб", "crate"), ("ящик", "crate"),
                    ("дерев", "tree"), ("меч", "sword"), ("ключ", "key"),
                    ("клет", "cage"), ("щит", "shield"),
                )
                if marker in destination_text
            ),
            None,
        )
        if source_tag is None or destination_form is None:
            return None
        plural = any(
            marker in source_text for marker in ("все ", "всех ", "всю ", "камни", "камней")
        )
        if plural:
            limit = 15 if add_opinion else 16
            code = (
                f"for target in all_with_tag('{source_tag}', limit={limit}):\n"
                f"    transform(target, '{destination_form}')"
            )
        else:
            code = (
                f"target = nearest('{source_tag}')\n"
                "if target:\n"
                f"    transform(target, '{destination_form}')"
            )
        if add_opinion:
            code += "\nspeak('player', 'Прямое и недвусмысленное превращение.')"
        return GenieProgram(
            code=code,
            summary=f"Превратить {source_tag} в {destination_form}.",
        )

    @classmethod
    def _program_has_mutation(cls, code: str) -> bool:
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError:
            return False
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        return bool(calls.intersection(cls.MUTATING_CAPABILITIES))

    @classmethod
    def _is_speech_wish(cls, wish_text: str) -> bool:
        lowered = wish_text.lower()
        return any(marker in lowered for marker in cls.SPEECH_WISH_MARKERS)

    @classmethod
    def _actions_fulfill_wish(cls, actions: list[AgentAction], wish_text: str) -> bool:
        if cls._is_speech_wish(wish_text):
            return any(action.success and action.kind == "speak" for action in actions)
        return any(
            action.success and action.kind not in {"inspect_entity", "observe_area", "speak"}
            for action in actions
        )

    @staticmethod
    def _fallback_program(wish_text: str) -> GenieProgram:
        safe_fragment = " ".join(wish_text.split())[:80].replace("'", "")
        return GenieProgram(
            code="speak('player', 'Я не смог честно воплотить это желание после трёх попыток.')",
            summary=(
                f"После неудачных попыток истолковать «{safe_fragment}» джин честно сообщает о провале, "
                "не подменяя желание посторонним эффектом."
            ),
        )

    def _instructions(self, ctx: RunContext[AgentDeps]) -> str:
        request = ctx.deps.request
        known_facts = ctx.deps.session.known_facts if ctx.deps.session is not None else None
        return self.instructions_for_request(request, known_facts=known_facts)

    @staticmethod
    def _object(ctx: RunContext[AgentDeps], target_id: str):
        if ctx.deps.session is not None:
            return ctx.deps.session.entity(target_id)
        return next((item for item in ctx.deps.request.world.objects if item.id == target_id), None)

    @staticmethod
    def _missing_required_target(kind: str, target_id: str | None) -> bool:
        return kind not in {"observe_area", "create_item", "create_object"} and not target_id

    @staticmethod
    def _hint_target_tag(planned: PlannedAction) -> str | None:
        hint = " ".join(
            value
            for value in (
                planned.interaction,
                planned.influence,
                planned.message,
                planned.state,
            )
            if value
        ).lower()
        for tag, words in (
            ("door", ("двер", "врат", "door", "gate", "замок")),
            ("container", ("сундук", "chest", "container")),
            ("key", ("ключ", "key")),
            ("enemy", ("враг", "enemy")),
            ("neutral", ("мудрец", "хранител", "sage", "keeper")),
        ):
            if any(word in hint for word in words):
                return tag
        return None

    def _infer_batch_target(
        self, ctx: RunContext[AgentDeps], planned: PlannedAction
    ) -> str | None:
        tag = self._hint_target_tag(planned)
        if not tag:
            return None
        candidates = [
            item.id
            for item in ctx.deps.request.world.objects
            if tag in item.tags and not item.properties.get("hidden", False)
        ]
        return candidates[0] if len(candidates) == 1 else None

    @staticmethod
    def _append(
        ctx: RunContext[AgentDeps],
        kind: str,
        observation: str,
        target_id: str | None = None,
        parameters: dict[str, Any] | None = None,
        success: bool = True,
        world_action: WorldAction | None = None,
    ) -> str:
        ctx.deps.actions.append(
            AgentAction(
                sequence=len(ctx.deps.actions) + 1,
                kind=kind,
                target_id=target_id,
                parameters=parameters or {},
                observation=observation,
                success=success,
                teleport_to_target=target_id is not None,
                world_action=world_action,
            )
        )
        return observation

    def _commit(
        self,
        ctx: RunContext[AgentDeps],
        kind: str,
        target_id: str | None,
        parameters: dict[str, Any],
        world_action: WorldAction | None,
        fallback_observation: str,
    ) -> str:
        success = True
        observation = fallback_observation
        if ctx.deps.session is not None:
            success, observation = ctx.deps.session.apply(
                kind, target_id, parameters, world_action
            )
        return self._append(
            ctx,
            kind,
            observation,
            target_id,
            parameters,
            success,
            world_action if success else None,
        )

    def _register_tools(self, agent: Agent[AgentDeps, AgentConclusion]) -> None:
        @agent.tool
        async def perform_actions(
            ctx: RunContext[AgentDeps], actions: list[PlannedAction]
        ) -> str:
            """Execute an ordered batch of chosen actions. Each item is logged and costs a world step. Use $gate_code in a later message after an earlier action learns that fact."""
            observations: list[dict[str, Any]] = []
            for planned in actions[:16]:
                kind = planned.kind
                target_id = (
                    planned.target_id
                    or planned.near_target_id
                    or self._infer_batch_target(ctx, planned)
                )
                if kind == "observe_area":
                    observation = (
                        ctx.deps.session.observe()
                        if ctx.deps.session is not None
                        else ctx.deps.request.world.model_dump_json(exclude_none=True)
                    )
                    self._append(ctx, kind, observation)
                    observations.append({"kind": kind, "success": True, "observation": observation})
                    continue
                if kind == "inspect_entity":
                    if ctx.deps.session is not None:
                        success, observation = ctx.deps.session.inspect(str(target_id or ""))
                        ctx.deps.session.record(kind, success, observation, target_id, {})
                    else:
                        target = self._object(ctx, str(target_id or ""))
                        success = target is not None
                        observation = target.model_dump_json() if target else f"Сущность {target_id} не найдена."
                    self._append(ctx, kind, observation, target_id, success=success)
                    observations.append({"kind": kind, "target_id": target_id, "success": success, "observation": observation})
                    continue
                if self._missing_required_target(kind, target_id):
                    observation = f"Действие {kind} отклонено: не указан target_id."
                    self._append(ctx, kind, observation, success=False)
                    observations.append({"kind": kind, "target_id": None, "success": False, "observation": observation})
                    continue
                if target_id and self._object(ctx, target_id) is None:
                    observation = f"Цель {target_id} неизвестна."
                    self._append(ctx, kind, observation, target_id, success=False)
                    observations.append({"kind": kind, "target_id": target_id, "success": False, "observation": observation})
                    continue

                world_action: WorldAction | None = None
                parameters: dict[str, Any]
                if kind == "affect_physical":
                    effect = planned.effect or "add_state"
                    strength = max(0.0, min(1.0, planned.strength))
                    parameters = {"effect": effect, "strength": strength, "state": planned.state}
                    if effect == "damage":
                        world_action = WorldAction(type="DAMAGE", target_id=target_id, amount=round(60 * strength, 3))
                    elif effect == "heal":
                        world_action = WorldAction(type="HEAL", target_id=target_id, amount=round(24 * strength, 3))
                    elif effect == "destroy":
                        world_action = WorldAction(type="DESTROY_OBJECT", target_id=target_id)
                    elif effect in {"push", "pull"}:
                        direction = ctx.deps.request.caster.facing
                        if effect == "pull":
                            direction = Vec2(x=-direction.x, y=-direction.y)
                        world_action = WorldAction(type="APPLY_FORCE", target_id=target_id, direction=direction, strength=round(6 * strength, 3))
                    elif effect in {"change_temperature", "heat", "melt"}:
                        world_action = WorldAction(type="CHANGE_TEMPERATURE", target_id=target_id, amount=round(strength - 0.5, 3))
                    else:
                        state_name = {"freeze": "frozen", "sleep": "asleep", "bind": "bound", "pacify": "pacified", "teleport": "banished", "banish": "banished"}.get(effect, effect)
                        world_action = WorldAction(type="ADD_STATE", target_id=target_id, state=planned.state or state_name, strength=strength, duration=4.0)
                elif kind in {"create_item", "create_object"}:
                    parameters = {"prototype": planned.prototype or "object"}
                    world_action = WorldAction(type="CREATE_OBJECT", target_id=planned.near_target_id, effect={"kind": "item" if kind == "create_item" else "object", "prototype": planned.prototype or "object"})
                elif kind == "interact":
                    parameters = {"interaction": planned.interaction or "interact"}
                    world_action = WorldAction(type="INTERACT", target_id=target_id, effect=parameters)
                elif kind == "affect_mind":
                    parameters = {"influence": planned.influence or "influence", "strength": max(0.0, min(1.0, planned.strength))}
                    world_action = WorldAction(type="ADD_STATE", target_id=target_id, state="influenced", strength=parameters["strength"], duration=6.0, effect={"thought": parameters["influence"]})
                else:
                    message = planned.message or ""
                    if message == "$gate_code" and ctx.deps.session is not None:
                        message = str(ctx.deps.session.known_facts.get("gate_code", message))
                    parameters = {"message": message}
                    world_action = WorldAction(type="SPEAK", target_id=target_id, effect=parameters)

                observation = f"Действие {kind} выполнено."
                returned = self._commit(ctx, kind, target_id, parameters, world_action, observation)
                action = ctx.deps.actions[-1]
                observations.append({"kind": kind, "target_id": target_id, "success": action.success, "observation": returned})
            result: dict[str, Any] = {"results": observations}
            if ctx.deps.session is not None:
                result["level_status"] = ctx.deps.session.status
                result["known_facts"] = ctx.deps.session.known_facts
            return json.dumps(result, ensure_ascii=False)

        @agent.tool
        async def observe_area(ctx: RunContext[AgentDeps]) -> str:
            """See the entities currently available around the player."""
            if ctx.deps.session is not None:
                observation = ctx.deps.session.observe()
                return self._append(ctx, "observe_area", observation)
            objects = [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "tags": item.tags,
                    "position": item.position.model_dump(),
                    "health": item.health,
                }
                for item in ctx.deps.request.world.objects
            ]
            return self._append(ctx, "observe_area", json.dumps(objects, ensure_ascii=False))

        @agent.tool
        async def inspect_entity(ctx: RunContext[AgentDeps], target_id: str) -> str:
            """Inspect one known entity before deciding how to affect it."""
            if ctx.deps.session is not None:
                success, observation = ctx.deps.session.inspect(target_id)
                ctx.deps.session.record(
                    "inspect_entity", success, observation, target_id, {}
                )
                return self._append(
                    ctx, "inspect_entity", observation, target_id, success=success
                )
            target = self._object(ctx, target_id)
            if target is None:
                return self._append(
                    ctx,
                    "inspect_entity",
                    f"Сущность {target_id} не найдена.",
                    target_id,
                    success=False,
                )
            return self._append(
                ctx,
                "inspect_entity",
                target.model_dump_json(),
                target_id,
            )

        @agent.tool
        async def affect_physical(
            ctx: RunContext[AgentDeps],
            target_id: str,
            effect: PhysicalEffect,
            strength: float = 0.5,
            state: str | None = None,
        ) -> str:
            """Physically affect a known target. Strength is clamped to the 0..1 range."""
            target = self._object(ctx, target_id)
            if target is None:
                return self._append(
                    ctx,
                    "affect_physical",
                    f"Воздействие не удалось: {target_id} не существует.",
                    target_id,
                    {"effect": effect, "strength": strength},
                    False,
                )
            strength = max(0.0, min(1.0, strength))
            if effect == "damage":
                action = WorldAction(type="DAMAGE", target_id=target_id, amount=round(60 * strength, 3))
            elif effect == "heal":
                action = WorldAction(type="HEAL", target_id=target_id, amount=round(24 * strength, 3))
            elif effect == "destroy":
                action = WorldAction(type="DESTROY_OBJECT", target_id=target_id)
            elif effect == "push":
                action = WorldAction(
                    type="APPLY_FORCE",
                    target_id=target_id,
                    direction=ctx.deps.request.caster.facing,
                    strength=round(6 * strength, 3),
                )
            elif effect == "pull":
                action = WorldAction(
                    type="APPLY_FORCE",
                    target_id=target_id,
                    direction=Vec2(
                        x=-ctx.deps.request.caster.facing.x,
                        y=-ctx.deps.request.caster.facing.y,
                    ),
                    strength=round(6 * strength, 3),
                )
            elif effect in {"change_temperature", "heat", "melt"}:
                action = WorldAction(
                    type="CHANGE_TEMPERATURE", target_id=target_id, amount=round(strength - 0.5, 3)
                )
            elif effect in {"freeze", "burn", "bind", "sleep", "pacify", "teleport", "banish", "transform", "phase"}:
                state_name = {
                    "freeze": "frozen",
                    "sleep": "asleep",
                    "bind": "bound",
                    "pacify": "pacified",
                    "teleport": "banished",
                    "banish": "banished",
                }.get(effect, effect)
                action = WorldAction(
                    type="ADD_STATE",
                    target_id=target_id,
                    state=state or state_name,
                    strength=strength,
                    duration=4.0,
                )
            else:
                action = WorldAction(
                    type="ADD_STATE",
                    target_id=target_id,
                    state=state or "altered",
                    strength=strength,
                    duration=4.0,
                )
            parameters = {"effect": effect, "strength": strength, "state": state}
            return self._commit(
                ctx,
                "affect_physical",
                target_id,
                parameters,
                action,
                f"Физическое действие {effect} применено к {target_id} с силой {strength:.2f}.",
            )

        @agent.tool
        async def create_item(
            ctx: RunContext[AgentDeps], prototype: str, near_target_id: str | None = None
        ) -> str:
            """Create an item from a concise prototype name, optionally near a known target."""
            if near_target_id and self._object(ctx, near_target_id) is None:
                return self._append(
                    ctx,
                    "create_item",
                    f"Предмет не создан: цель {near_target_id} неизвестна.",
                    near_target_id,
                    {"prototype": prototype},
                    False,
                )
            action = WorldAction(
                type="CREATE_OBJECT",
                target_id=near_target_id,
                effect={"kind": "item", "prototype": prototype},
            )
            return self._commit(
                ctx,
                "create_item",
                near_target_id,
                {"prototype": prototype},
                action,
                f"Создан предмет {prototype}.",
            )

        @agent.tool
        async def create_object(
            ctx: RunContext[AgentDeps], prototype: str, near_target_id: str | None = None
        ) -> str:
            """Create a world object or creature from a concise prototype name."""
            if near_target_id and self._object(ctx, near_target_id) is None:
                return self._append(
                    ctx,
                    "create_object",
                    f"Объект не создан: цель {near_target_id} неизвестна.",
                    near_target_id,
                    {"prototype": prototype},
                    False,
                )
            action = WorldAction(
                type="CREATE_OBJECT",
                target_id=near_target_id,
                effect={"kind": "object", "prototype": prototype},
            )
            return self._commit(
                ctx,
                "create_object",
                near_target_id,
                {"prototype": prototype},
                action,
                f"Создан объект {prototype}.",
            )

        @agent.tool
        async def interact(
            ctx: RunContext[AgentDeps], target_id: str, interaction: str
        ) -> str:
            """Perform a non-destructive interaction with a known living or non-living target."""
            if self._object(ctx, target_id) is None:
                return self._append(
                    ctx, "interact", f"Цель {target_id} неизвестна.", target_id, success=False
                )
            action = WorldAction(
                type="INTERACT", target_id=target_id, effect={"interaction": interaction}
            )
            return self._commit(
                ctx,
                "interact",
                target_id,
                {"interaction": interaction},
                action,
                f"Взаимодействие с {target_id}: {interaction}.",
            )

        @agent.tool
        async def affect_mind(
            ctx: RunContext[AgentDeps], target_id: str, influence: str, strength: float = 0.5
        ) -> str:
            """Influence the thoughts, beliefs, or emotions of a known living creature."""
            target = self._object(ctx, target_id)
            if target is None or "living" not in target.tags:
                return self._append(
                    ctx,
                    "affect_mind",
                    f"Разум цели {target_id} недоступен.",
                    target_id,
                    {"influence": influence},
                    False,
                )
            strength = max(0.0, min(1.0, strength))
            action = WorldAction(
                type="ADD_STATE",
                target_id=target_id,
                state="influenced",
                strength=strength,
                duration=6.0,
                effect={"thought": influence},
            )
            return self._commit(
                ctx,
                "affect_mind",
                target_id,
                {"influence": influence, "strength": strength},
                action,
                f"На разум {target_id} наложено влияние: {influence}.",
            )

        @agent.tool
        async def speak(ctx: RunContext[AgentDeps], target_id: str, message: str) -> str:
            """Speak to a known target. Speech can inform or persuade but does not guarantee compliance."""
            if self._object(ctx, target_id) is None:
                return self._append(
                    ctx, "speak", f"Некому сказать: {target_id} неизвестен.", target_id, success=False
                )
            action = WorldAction(type="SPEAK", target_id=target_id, effect={"message": message})
            return self._commit(
                ctx,
                "speak",
                target_id,
                {"message": message},
                action,
                f"Джин сказал {target_id}: {message}",
            )

    async def run(
        self,
        request: CastRequest,
        session: Any | None = None,
        progress_curses: bool = True,
    ) -> AgentWishResponse:
        started = time.perf_counter()
        deps = AgentDeps(request=request, session=session)
        self.telemetry.count("granted_agent_requests_total")
        self.telemetry.event(
            "agent.run.started",
            request.request_id,
            model=self.model_name,
            prompt_version=self.prompt_config["version"],
            wish=request.spell_text,
            active_curse_ids=self.curses.state.active_curse_ids,
        )
        result = None
        program_source = "model"
        program = self._compile_fast_program(
            request.spell_text,
            add_opinion="last_word" in self.curses.state.active_curse_ids,
        )
        if program is not None:
            program_source = "fast_path"
            self.telemetry.event(
                "agent.program.fast_path",
                request.request_id,
                code=program.code,
            )
        else:
            try:
                result = await self.agent.run(
                    self._model_program_prompt(
                        "Составь Monty-программу для исполнения текущего желания."
                    ),
                    deps=deps,
                    usage_limits=UsageLimits(
                        request_limit=int(self.prompt_config["max_model_requests"]),
                        tool_calls_limit=int(self.prompt_config["max_tool_calls"]),
                    ),
                )
                program = self._coerce_model_program(result.output, request.spell_text)
            except Exception as error:
                self.telemetry.count("granted_agent_program_generation_errors_total")
                self.telemetry.event(
                    "agent.program.generation_failed",
                    request.request_id,
                    error_type=type(error).__name__,
                    error=str(error),
                )
                program = self._fallback_program(request.spell_text)
                program_source = "fallback_after_model_error"
        first_world_action_ms: float | None = None

        def record_first_world_action(_action: AgentAction) -> None:
            nonlocal first_world_action_ms
            if _action.world_action is None:
                return
            if first_world_action_ms is not None:
                return
            first_world_action_ms = (time.perf_counter() - started) * 1000.0
            self.telemetry.first_action(first_world_action_ms, observed_by="server")
            self.telemetry.event(
                "agent.first_world_action",
                request.request_id,
                time_to_first_action_ms=round(first_world_action_ms, 3),
                slo_ms=2000,
                slo_met=first_world_action_ms <= 2000.0,
            )

        program_attempts: list[dict[str, Any]] = []
        execution = None
        for attempt in range(1, self.MAX_PROGRAM_ATTEMPTS + 1):
            execution = self.monty.execute(
                program.code,
                request,
                session=session,
                on_action=record_first_world_action,
            )
            self.telemetry.monty_execution(
                execution.execution_ms, failed=execution.error is not None
            )
            authoritative_completed = bool(
                session is not None and getattr(session, "status", None) == "completed"
            )
            fulfilled = authoritative_completed or self._actions_fulfill_wish(
                execution.actions, request.spell_text
            )
            program_attempts.append(
                {
                    "attempt": attempt,
                    "source": program_source,
                    "code": program.code,
                    "error": execution.error,
                    "action_count": len(execution.actions),
                    "fulfilled": fulfilled,
                }
            )
            self.telemetry.event(
                "agent.program.attempt",
                request.request_id,
                attempt=attempt,
                source=program_source,
                error=execution.error,
                action_count=len(execution.actions),
                fulfilled=fulfilled,
            )
            # A successful mutation is enough even if later decorative speech failed; repeating it
            # could duplicate damage or objects. Speech-only programs retry for non-verbal wishes.
            if fulfilled:
                break
            if program_source.startswith("fallback") or attempt >= self.MAX_PROGRAM_ATTEMPTS:
                break
            if attempt == self.MAX_PROGRAM_ATTEMPTS - 1:
                program = self._fallback_program(request.spell_text)
                program_source = "fallback_after_retries"
                continue
            failure_reason = execution.error or "программа не произвела физического результата"
            try:
                result = await self.agent.run(
                    self._model_program_prompt(
                        "Предыдущая Monty-программа не исполнила желание. "
                        f"Причина: {failure_reason}. Исправь её и обязательно измени мир. "
                        f"Предыдущий code: {program.code!r}"
                    ),
                    deps=deps,
                    usage_limits=UsageLimits(
                        request_limit=int(self.prompt_config["max_model_requests"]),
                        tool_calls_limit=int(self.prompt_config["max_tool_calls"]),
                    ),
                )
                program = self._coerce_model_program(result.output, request.spell_text)
                program_source = "model_repair"
            except Exception as error:
                self.telemetry.count("granted_agent_program_generation_errors_total")
                self.telemetry.event(
                    "agent.program.repair_failed",
                    request.request_id,
                    attempt=attempt + 1,
                    error_type=type(error).__name__,
                    error=str(error),
                )
                program = self._fallback_program(request.spell_text)
                program_source = "fallback_after_repair_error"
        assert execution is not None
        deps.actions = execution.actions
        authoritative_completed = bool(
            session is not None and getattr(session, "status", None) == "completed"
        )
        if authoritative_completed:
            status = "completed"
            summary = program.summary
        elif execution.error:
            status = "partial" if deps.actions else "impossible"
            summary = f"{program.summary} Ошибка Monty: {execution.error}"
        elif not deps.actions:
            status = "impossible"
            summary = f"{program.summary} Программа не совершила игровых действий."
        elif not self._actions_fulfill_wish(deps.actions, request.spell_text):
            status = "impossible"
            summary = f"{program.summary} Программа не воплотила желание в мире."
        elif any(not action.success for action in deps.actions):
            status = "partial"
            summary = program.summary
        elif session is not None and session.status != "completed":
            status = "partial"
            summary = program.summary
        else:
            status = "completed"
            summary = program.summary
        conclusion = AgentConclusion(status=status, summary=summary)
        elapsed = (time.perf_counter() - started) * 1000.0
        usage_object = result.usage if result is not None else None
        usage = asdict(usage_object) if usage_object else {}
        if usage_object:
            usage["total_tokens"] = usage_object.total_tokens
        for action in deps.actions:
            self.telemetry.count(
                "granted_agent_actions_total", labels={"action": action.kind, "success": str(action.success).lower()}
            )
            self.telemetry.event(
                "agent.action",
                request.request_id,
                sequence=action.sequence,
                action=action.kind,
                target_id=action.target_id,
                parameters=action.parameters,
                observation=action.observation,
                success=action.success,
            )
        self.telemetry.latency(elapsed)
        newly_active = (
            self.curses.record_wish(
                request.spell_text,
                [action.kind for action in deps.actions if action.success],
                conclusion.status == "completed",
            )
            if progress_curses
            else []
        )
        if newly_active:
            self.telemetry.count("granted_genie_curses_activated_total", len(newly_active))
            for curse in newly_active:
                self.telemetry.event(
                    "genie.curse.activated",
                    request.request_id,
                    curse_id=curse.id,
                    title=curse.title,
                    severity=curse.severity,
                )

        world_actions = [action.world_action for action in deps.actions if action.world_action]
        target_ids = list(dict.fromkeys(action.target_id for action in deps.actions if action.target_id))
        visuals = [self._visual_for(request, action) for action in deps.actions if action.world_action]
        agent_info = AgentRunInfo(
            model=self.model_name,
            prompt_version=self.prompt_config["version"],
            execution_engine="monty",
            program_code=program.code,
            program_output=execution.output,
            execution_ms=round(execution.execution_ms, 3),
            execution_error=execution.error,
            first_world_action_ms=(
                round(first_world_action_ms, 3) if first_world_action_ms is not None else None
            ),
            conclusion=conclusion,
            actions=deps.actions,
            public_curses=self.curses.public(),
            latency_ms=round(elapsed, 3),
            usage=usage,
        )
        response = AgentWishResponse(
            request_id=request.request_id,
            interpretation=Interpretation(coherence=1.0, anchors=[]),
            spell_plan=SpellPlan(
                duration=max(0.65, len(deps.actions) * 0.25),
                power=1.0,
                world_actions=world_actions,
                visuals=visuals,
            ),
            debug=DebugInfo(
                intent={"agent_conclusion": conclusion.model_dump()},
                selected_targets=target_ids,
                world_rules=["RULE_MONTY_CAPABILITIES: world mutations came from the sandbox API"],
                latency_ms=round(elapsed, 3),
            )
            if request.options.debug
            else None,
            agent=agent_info,
        )
        evaluation = evaluate_trajectory(deps.actions, conclusion)
        trajectory_payload = {
            "schema_version": 1,
            "timestamp": self.telemetry.now(),
            "request": request.model_dump(mode="json"),
            "prompt": {
                "version": self.prompt_config["version"],
                "base_instructions": self.prompt_config["instructions"],
                "active_curse_ids": self.curses.state.active_curse_ids,
            },
            "model": self.model_name,
            "program": {
                "language": "python-monty",
                "source": program_source,
                "code": program.code,
                "output": execution.output,
                "execution_ms": round(execution.execution_ms, 3),
                "error": execution.error,
            },
            "program_attempts": program_attempts,
            "actions": [action.model_dump(mode="json") for action in deps.actions],
            "conclusion": conclusion.model_dump(mode="json"),
            "usage": usage,
            "evaluation": evaluation.model_dump(mode="json"),
            "model_messages": json.loads(result.all_messages_json()) if result is not None else [],
        }
        trajectory_path = self.telemetry.trajectory(request.request_id, trajectory_payload)
        self.telemetry.event(
            "agent.run.completed",
            request.request_id,
            status=conclusion.status,
            action_count=len(deps.actions),
            latency_ms=round(elapsed, 3),
            evaluation_score=evaluation.score,
            trajectory_path=str(trajectory_path),
        )
        return response

    @staticmethod
    def _visual_for(request: CastRequest, action: AgentAction) -> VisualDescriptor:
        target = next(
            (item for item in request.world.objects if item.id == action.target_id), None
        )
        target_position = target.position if target else request.caster.position
        direction = Vec2(
            x=target_position.x - request.caster.position.x,
            y=target_position.y - request.caster.position.y,
        )
        return VisualDescriptor(
            primitive="BURST",
            appearance=["agent", action.kind],
            origin=target_position,
            direction=direction,
            radius=0.8,
            speed=0.0,
            intensity=0.75,
            turbulence=0.35,
            lifetime=0.55,
            target=target_position,
        )
