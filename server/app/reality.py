from __future__ import annotations

import asyncio
import copy
import json
import math
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from .config import ROOT
from .telemetry import TelemetryStore

LEVEL_PATH = ROOT.parent / "client/levels/bureaucracy_start.json"
Effect = Literal["open_exit", "erase_description", "validate_pass", "protect",
                 "emergency_vehicle", "transform", "create", "lighting", "pace"]
KINDS = {"rock", "crate", "tree", "npc", "police"}
LAWS = {
    "life_safety": {"title": "Приоритет сохранения жизни", "effects": ["open_exit", "emergency_vehicle"],
                    "rule": "Пути эвакуации и транспорт для спасения жизни получают приоритет доступа."},
    "identity_review": {"title": "Пересмотр идентификации", "effects": ["erase_description"],
                        "rule": "Неподтверждённое описание лица исключается из текущего розыска."},
    "document_correction": {"title": "Исправление регистрационной ошибки", "effects": ["validate_pass"],
                            "rule": "Исправленный пропуск предоставляет право прохода его владельцу."},
    "non_aggression": {"title": "Обеспечительный запрет причинения вреда", "effects": ["protect"],
                       "rule": "Участнику дела нельзя причинять физический вред до пересмотра решения."},
    "classification_amendment": {"title": "Изменение вещественной классификации", "effects": ["transform"],
                                 "rule": "Объект после регистрации новой категории приобретает её материальные свойства."},
    "property_registration": {"title": "Регистрация нового имущества", "effects": ["create"],
                              "rule": "Зарегистрированный вещественный объект допускается к существованию в квартале."},
    "environment_exception": {"title": "Особый порядок исполнения событий", "effects": ["lighting", "pace"],
                               "rule": "Свет и ход событий в квартале допускают временное исключение."},
}


class RealityError(ValueError):
    pass


class Petition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effect: Effect
    target: str = Field(min_length=1, max_length=80)
    basis: str = Field(min_length=1, max_length=80)
    argument: str = Field(min_length=1, max_length=400)
    value: str = Field(default="", max_length=80)

    @field_validator("value", mode="before")
    @classmethod
    def normalize_scalar(cls, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return value


Planner = Callable[[str, dict[str, Any], str], Awaitable[Petition]]


class Lawyer:
    """Drafts a petition; the deterministic court owns permission and execution."""

    def __init__(self):
        self._agent = None

    def prepare(self):
        if self._agent is None:
            from pydantic_ai import Agent
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider
            dedicated = os.getenv("GENIE_AGENT_BASE_URL", "").strip()
            provider = OpenAIProvider(
                base_url=dedicated or os.getenv("AITUNNEL_BASE_URL", "https://api.aitunnel.ru/v1"),
                api_key=os.getenv("GENIE_AGENT_API_KEY") or (
                    "not-required" if dedicated else os.getenv("AITUNNEL_API_KEY", "")
                ),
            )
            self._agent = Agent(
                OpenAIChatModel(os.getenv("GENIE_AGENT_MODEL", "qwen3-35-36"), provider=provider),
                output_type=str,
                instructions=(
                    "Ты дьявол-адвокат обычного клерка в Bureaucracy of Reality. "
                    "Представляй интересы клиента через нормы, исключения и прецеденты. "
                    "Не джин, не маг. Помоги клиенту выжить. "
                    "Верни ТОЛЬКО JSON одного ходатайства без markdown: "
                    '{"effect":"open_exit","target":"checkpoint","basis":"life_safety",'
                    '"argument":"Путь нужен для безопасной эвакуации.","value":""}. '
                    "Выбери эффект, который действительно выполняет желание, подходящую цель и "
                    "разрешённое основание из списка. Дверь без уточнения — checkpoint. "
                    "Машина — car. Камень — rock. Себя/меня/пропуск — player. "
                    "transform/create: value=rock/crate/tree/npc/police. "
                    "lighting: value от 0.2 до 1; pace: от 0 (пауза) до 2. "
                    "Для света/времени target=world. Для create target=player. "
                    "Автомобиль как скорая помощь — effect=emergency_vehicle, basis=life_safety, "
                    "target=car: это правовой статус транспорта, а не transform. "
                    "Если величина не указана, стандартные значения: темнее=0.35, "
                    "светлее=1, замедлить=0.4, ускорить=1.8, пауза=0, возобновить=1. "
                    "После ошибки исправь заявку. Не заявляй об исполнении до решения системы. "
                    "Если никакой эффект не выполняет желание, верни JSON с effect=unsupported "
                    "и объясни ограничение в argument: суд честно отклонит его."
                ),
                model_settings={"temperature": 0.1, "max_tokens": 420,
                                "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}},
                retries=1, name="bureaucracy_attorney",
            )
    async def __call__(self, wish, state, error):
        self.prepare()
        public = {k: state[k] for k in ("phase", "player", "objects", "precedents", "lighting", "pace")}
        result = await self._agent.run(json.dumps(
            {"wish": wish, "world": public, "laws": LAWS, "previous_error": error}, ensure_ascii=False))
        text = re.sub(r"<think>.*?</think>", "", result.output, flags=re.S).strip()
        if text.startswith(chr(96) * 3):
            text = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", text)
        return Petition.model_validate_json(text)


class Campaign:
    def __init__(self, root: Path | None = None, *, planner: Planner | None = None,
                 telemetry: TelemetryStore | None = None):
        self.root = root or ROOT / "runtime/bureaucracy"
        self.sessions = {}
        self.lock = threading.RLock()
        self.busy = set()
        self.planner = planner or Lawyer()
        self.telemetry = telemetry or TelemetryStore(self.root)
        self.last_save = {}

    def _path(self, sid):
        if not re.fullmatch(r"[a-f0-9]{32}", sid):
            raise RealityError("Некорректный номер сессии.")
        return self.root / "sessions" / f"{sid}.json"

    def _state(self, sid):
        if sid not in self.sessions:
            path = self._path(sid)
            if not path.is_file():
                raise RealityError("Сессия не найдена.")
            self.sessions[sid] = json.loads(path.read_text(encoding="utf-8"))
        return self.sessions[sid]

    def _save(self, state):
        path = self._path(state["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        self.last_save[state["id"]] = time.monotonic()

    def create(self):
        level = json.loads(LEVEL_PATH.read_text(encoding="utf-8"))
        state = {
            "id": uuid.uuid4().hex, "revision": 0, "level": level,
            "phase": "apartment", "day": 1, "processed": 0, "meals": 0,
            "contract_ready": False, "contract_signed": False,
            "contract_terms": "Исполнение желаний в обмен на твою жизнь после смерти.",
            "player": {"id": "player", "x": 180.0, "y": 200.0, "health": 100.0,
                       "recognizable": True, "valid_pass": False, "protected": False,
                       "driving": False, "crouching": False},
            "objects": copy.deepcopy(level["objects"]), "precedents": [], "receipts": {},
            "attention": 0, "lighting": 0.8, "pace": 1.0, "elapsed": 0.0,
            "status": "active", "message": "Поесть. Поспать. На работу. Всё по расписанию.",
            "case_status": "idle", "case_count": 0,
        }
        with self.lock:
            self.sessions[state["id"]] = state
            self._save(state)
        return copy.deepcopy(state)

    def get(self, sid):
        with self.lock:
            return copy.deepcopy(self._state(sid))

    def _changed(self, state, *, save=True):
        state["revision"] += 1
        if save:
            self._save(state)
        return copy.deepcopy(state)

    def command(self, sid, action):
        with self.lock:
            state = self._state(sid)
            phase = state["phase"]
            if state["status"] == "dead":
                raise RealityError("Клерк погиб. Начните новую жизнь кнопкой «Новая сессия».")
            if action in {"eat", "sleep", "commute", "sign", "leave"} and phase != "apartment":
                raise RealityError("Это действие доступно в квартире.")
            if action in {"work", "home"} and phase != "office":
                raise RealityError("Это действие доступно на работе.")
            if action == "eat":
                state["meals"] += 1
                state["message"] = "Ужин по установленной норме."
            elif action == "sleep":
                state["day"] += 1
                state["message"] = "Новый день. Маршрут остаётся прежним."
            elif action == "commute":
                state["phase"] = "office"
                state["player"].update(x=525.0, y=235.0)
                state["message"] = "Ваша задача: нажимать «ОБРАБОТАТЬ». Смысл задачи не сообщается."
            elif action == "work":
                state["processed"] += 1
                state["message"] = f"Заявка № {state['processed']:04d} обработана. Следующая."
            elif action == "home":
                state["phase"] = "apartment"
                state["player"].update(x=180.0, y=215.0)
                state["contract_ready"] = state["processed"] >= 2
                state["message"] = (
                    "На столе договор. Желания — в обмен на жизнь после смерти. Подпись добровольна."
                    if state["contract_ready"] and not state["contract_signed"] else "Вы вернулись домой."
                )
            elif action == "sign":
                if not state["contract_ready"] or state["contract_signed"]:
                    raise RealityError("На столе нет нового договора.")
                state["contract_signed"] = True
                state["message"] = "Адвокат: «Теперь ваши интересы представляю я. Давайте выйдем за рамки»."
            elif action == "leave":
                if not state["contract_signed"]:
                    raise RealityError("Выход за пределы маршрута пока не разрешён.")
                state["phase"] = "city"
                state["attention"] = max(1, state["attention"])
                state["player"].update(x=210.0, y=355.0)
                state["message"] = "Нарушение предписанного маршрута. Пройдите кордон на востоке."
            elif action == "vehicle":
                if phase != "city":
                    raise RealityError("Транспорт доступен в городе.")
                car, player = state["objects"]["car"], state["player"]
                if not player["driving"] and math.hypot(car["x"] - player["x"], car["y"] - player["y"]) > 85:
                    raise RealityError("Подойдите к автомобилю.")
                player["driving"] = not player["driving"]
                state["message"] = "Вы за рулём." if player["driving"] else "Вы вышли из автомобиля."
            else:
                raise RealityError("Неизвестное действие.")
            return self._changed(state)

    @staticmethod
    def _cross(state, door_id, actor):
        if state["objects"].get(door_id, {}).get("open", False):
            return True
        if actor != "player":
            return False
        p = state["player"]
        return bool(p["valid_pass"] or (p["driving"] and
                    state["objects"]["car"]["legal_status"] == "emergency_vehicle"))

    def can_cross(self, sid, door_id, actor):
        with self.lock:
            return self._cross(self._state(sid), door_id, actor)

    @staticmethod
    def _blocked(state, x, y, actor="player"):
        for r in state["level"]["barriers"]:
            if r["x"] - 9 < x < r["x"] + r["w"] + 9 and r["y"] - 9 < y < r["y"] + r["h"] + 9:
                return True
        for key, obj in state["objects"].items():
            if obj["kind"] == "door" and not Campaign._cross(state, key, actor):
                if abs(x - obj["x"]) < obj["w"] / 2 + 9 and abs(y - obj["y"]) < obj["h"] / 2 + 9:
                    return True
        return False

    @staticmethod
    def _detected(state, observer):
        p, o = state["player"], state["objects"].get(observer)
        if not o or o["kind"] != "police" or state["phase"] != "city" or not p["recognizable"]:
            return False
        radius = (90 if p["crouching"] else 200) * max(0.35, state["lighting"])
        return math.hypot(o["x"] - p["x"], o["y"] - p["y"]) < radius

    def detected(self, sid, observer):
        with self.lock:
            return self._detected(self._state(sid), observer)

    @staticmethod
    def _damage(state, amount):
        if not state["player"]["protected"]:
            state["player"]["health"] = max(0, state["player"]["health"] - max(0, amount))
        if state["player"]["health"] <= 0:
            state["status"] = "dead"
            state["message"] = "Жизнь окончена. Договор вступил в силу. Мир сохранил ваши решения."

    def damage(self, sid, amount):
        with self.lock:
            state = self._state(sid)
            self._damage(state, amount)
            return self._changed(state)

    def tick(self, sid, dx, dy, dt, crouch=False):
        with self.lock:
            if not all(math.isfinite(v) for v in (dx, dy, dt)):
                raise RealityError("Некорректный ввод движения.")
            state = self._state(sid)
            if state["status"] != "active":
                return copy.deepcopy(state)
            step = max(0, min(0.2, dt)) * state["pace"]
            state["elapsed"] += step
            p = state["player"]
            p["crouching"] = bool(crouch)
            length = max(1, math.hypot(dx, dy))
            speed = 255 if p["driving"] else (75 if crouch else 155)
            x, y = p["x"] + dx / length * speed * step, p["y"] + dy / length * speed * step
            bounds = state["level"]["bounds"]
            if state["phase"] in {"apartment", "office"}:
                bounds = next(r["rect"] for r in state["level"]["rooms"] if r["id"] == state["phase"])
            x = max(bounds[0] + 12, min(bounds[0] + bounds[2] - 12, x))
            y = max(bounds[1] + 28, min(bounds[1] + bounds[3] - 12, y))
            if not self._blocked(state, x, p["y"]):
                p["x"] = x
            if not self._blocked(state, p["x"], y):
                p["y"] = y
            if p["driving"]:
                state["objects"]["car"].update(x=p["x"], y=p["y"])
            if state["phase"] == "city":
                for key, obj in state["objects"].items():
                    if obj["kind"] != "police":
                        continue
                    chasing = self._detected(state, key)
                    obj["chasing"] = chasing
                    tx = p["x"] if chasing else obj.get("home_x", obj["x"]) + math.sin(state["elapsed"] * .45) * 40
                    ty = p["y"] if chasing else obj.get("home_y", obj["y"])
                    distance = math.hypot(tx - obj["x"], ty - obj["y"])
                    if distance > 2:
                        ratio = min(1, (100 if chasing else 38) * step / distance)
                        nx, ny = obj["x"] + (tx - obj["x"]) * ratio, obj["y"] + (ty - obj["y"]) * ratio
                        if not self._blocked(state, nx, obj["y"], key):
                            obj["x"] = nx
                        if not self._blocked(state, obj["x"], ny, key):
                            obj["y"] = ny
                    if chasing and distance < 30:
                        self._damage(state, 28 * step)
                if p["x"] > 1100 and state["status"] != "dead":
                    state["status"] = "escaped"
                    state["message"] = "Маршрут нарушен. Вы за кордоном. Это дело станет прецедентом."
            return self._changed(state, save=time.monotonic() - self.last_save.get(sid, 0) >= 1)

    def resolve(self, sid, decision: Petition, request_id):
        """Validate on the latest state, then publish effect and precedent together."""
        with self.lock:
            current = self._state(sid)
            if request_id in current["receipts"]:
                return copy.deepcopy(current["receipts"][request_id])
            if not current["contract_signed"]:
                raise RealityError("Сначала подпишите договор с адвокатом.")
            if current["status"] == "dead":
                raise RealityError("Клиент погиб до вынесения решения.")
            law = LAWS.get(decision.basis)
            if not law or decision.effect not in law["effects"]:
                raise RealityError("Основание не разрешает заявленный эффект.")
            state = copy.deepcopy(current)
            target = state["objects"].get(decision.target)
            effect, value, scope = decision.effect, decision.value, decision.effect
            if effect == "open_exit":
                if not target or target["kind"] != "door":
                    raise RealityError("Для изменения прохода нужна существующая дверь.")
                target.update(open=True, legal_status="emergency_exit")
                scope = "doors:emergency_exit"
                message = f"{target['name']}: аварийный выход признан. Проход открыт для всех — включая преследователей."
            elif effect in {"erase_description", "validate_pass", "protect"}:
                if decision.target != "player":
                    raise RealityError("В этом деле участником является player.")
                prop = {"erase_description": "recognizable", "validate_pass": "valid_pass", "protect": "protected"}[effect]
                state["player"][prop] = effect != "erase_description"
                message = {"erase_description": "Описание исключено из розыска. Полиция больше вас не узнаёт.",
                           "validate_pass": "Пропуск исправлен. Кордон обязан вас пропустить.",
                           "protect": "Запрет причинять вам вред вступил в силу."}[effect]
            elif effect == "emergency_vehicle":
                if not target or target["kind"] != "car":
                    raise RealityError("Для экстренного транспорта нужен автомобиль.")
                target["legal_status"] = "emergency_vehicle"
                message = "Автомобиль признан экстренным транспортом. Кордон пропустит его водителя."
            elif effect == "transform":
                if not target or target["kind"] not in KINDS or value not in KINDS:
                    raise RealityError("Допустимы существующие rock/crate/tree/npc/police и новая категория из этого списка.")
                target.update(kind=value, legal_status="reclassified", name=value)
                scope = f"reclassification:{value}"
                message = f"Классификация объекта изменена на {value}. Реальность привела форму в соответствие."
            elif effect == "create":
                if decision.target != "player" or value not in KINDS:
                    raise RealityError("Новый объект rock/crate/tree/npc/police регистрируется рядом с player.")
                if len(state["objects"]) >= 100:
                    raise RealityError("Реестр квартала заполнен.")
                key = f"registered_{state['case_count'] + 1}"
                state["objects"][key] = {"id": key, "kind": value, "name": value,
                                        "x": state["player"]["x"] + 45, "y": state["player"]["y"] + 25,
                                        "legal_status": "registered"}
                scope = f"registration:{value}"
                message = f"Новый объект {value} зарегистрирован и появился рядом с вами."
            else:
                if decision.target != "world":
                    raise RealityError("Свет и ход событий меняются для world.")
                try:
                    number = float(value)
                except ValueError as error:
                    raise RealityError("Требуется числовое значение.") from error
                low, high = (.2, 1) if effect == "lighting" else (0, 2)
                if not math.isfinite(number) or not low <= number <= high:
                    raise RealityError(f"Допустимый диапазон {low}..{high}.")
                state[effect] = number
                scope = f"{effect}:{number:g}"
                message = "Изменён режим освещения квартала." if effect == "lighting" else "Изменён ход событий. Адвокат продолжает принимать заявления."
            precedent = next((p for p in state["precedents"] if p["basis"] == decision.basis and p["scope"] == scope), None)
            if precedent is None:
                precedent = {"id": f"BOR-{len(state['precedents']) + 1:04d}", "basis": decision.basis,
                             "title": law["title"], "scope": scope, "rule": law["rule"], "uses": 0}
                state["precedents"].append(precedent)
                state["attention"] += 1
            precedent["uses"] += 1
            state["case_count"] += 1
            state["message"] = "Адвокат: " + message
            receipt = {"request_id": request_id, "status": "completed", "effect": effect,
                       "target": decision.target, "basis": decision.basis, "argument": decision.argument,
                       "precedent_id": precedent["id"], "message": state["message"]}
            state["receipts"][request_id] = receipt
            self.sessions[sid] = state
            self._changed(state)
            return copy.deepcopy(receipt)

    async def wish(self, sid, text, request_id):
        if not text.strip() or len(text) > 300:
            raise RealityError("Желание должно содержать от 1 до 300 символов.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id):
            raise RealityError("Некорректный идентификатор заявки.")
        with self.lock:
            state = self._state(sid)
            if request_id in state["receipts"]:
                return copy.deepcopy(state["receipts"][request_id])
            if not state["contract_signed"]:
                raise RealityError("Сначала подпишите договор с адвокатом.")
            if sid in self.busy:
                raise RealityError("Адвокат уже ведёт дело. Вы можете продолжать движение.")
            self.busy.add(sid)
            state["case_status"] = "considering"
            before = copy.deepcopy(state)
        trace_id = f"bor-{sid[:12]}-{request_id}"[:100]
        start = time.monotonic()
        attempts, error, result = [], "", None
        try:
            self.telemetry.event("agent.run.started", trace_id, wish=text, setting="bureaucracy")
            for attempt in range(1, 4):
                decision = None
                try:
                    decision = await asyncio.wait_for(self.planner(text, self.get(sid), error), timeout=25)
                    decision = Petition.model_validate(decision)
                    result = self.resolve(sid, decision, request_id)
                    attempts.append({"attempt": attempt, "petition": decision.model_dump(), "verified": True})
                    result["attempts"] = attempt
                    self.telemetry.event("agent.action", trace_id, effect=decision.effect,
                                         target_id=decision.target, basis=decision.basis, verified=True)
                    break
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"[:1000]
                    attempts.append({"attempt": attempt, "error": error, "verified": False,
                                     "petition": decision.model_dump() if isinstance(decision, Petition) else None})
                    self.telemetry.event("bureaucracy.petition.rejected", trace_id, attempt=attempt, error=error)
            if result is None:
                result = {"request_id": request_id, "status": "failed", "attempts": 3,
                          "message": "Адвокат: сейчас не удалось добиться решения. Мир не изменён. Попробуйте уточнить желание.",
                          "error": error}
            with self.lock:
                state = self._state(sid)
                state["message"] = result["message"]
                state["case_status"] = result["status"]
                state["receipts"][request_id] = copy.deepcopy(result)
                self._changed(state)
            latency = (time.monotonic() - start) * 1000
            path = self.telemetry.trajectory(trace_id, {
                "request": {"request_id": trace_id, "wish_text": text}, "response": result,
                "before": before, "after": self.get(sid), "attempts": attempts,
                "setting": "bureaucracy", "latency_ms": latency,
            })
            self.telemetry.event("agent.run.completed", trace_id, status=result["status"],
                                 latency_ms=latency, action_count=int(result["status"] == "completed"),
                                 trajectory_path=str(path))
            self.telemetry.count("bureaucracy_petitions_total", labels={"status": result["status"]})
            return result
        finally:
            with self.lock:
                self.busy.discard(sid)
                state = self._state(sid)
                if state["case_status"] == "considering":
                    state["case_status"] = "interrupted"
