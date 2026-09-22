from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from .agent_models import AgentAction
from .models import CastRequest, WorldAction, WorldSnapshot
from .telemetry import TelemetryStore


JobRunner = Callable[[], Awaitable[Any]]
AgenticPlanner = Callable[[CastRequest], Awaitable[Any]]


@dataclass
class WishJob:
    job_id: str
    request_id: str
    first_actions: list[AgentAction] = field(default_factory=list)
    server_ttfa_ms: float | None = None
    status: str = "running"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    client_ttfa_reported: bool = False
    task: asyncio.Task[None] | None = None


class WishJobManager:
    """In-memory asynchronous wish execution with honest world-action timing."""

    def __init__(self, telemetry: TelemetryStore, max_jobs: int = 256) -> None:
        self.telemetry = telemetry
        self.max_jobs = max_jobs
        self.jobs: dict[str, WishJob] = {}

    def start(
        self,
        request_id: str,
        runner: JobRunner,
        *,
        received_at: float | None = None,
        visible_object_count: int = 0,
    ) -> dict[str, Any]:
        job = WishJob(
            job_id=uuid.uuid4().hex,
            request_id=request_id,
        )
        self._discard_old_jobs()
        self.jobs[job.job_id] = job
        job.task = asyncio.create_task(self._execute(job, runner))
        return self.view(job, include_first_actions=True)

    async def _execute(self, job: WishJob, runner: JobRunner) -> None:
        try:
            response = await runner()
            if isinstance(response, BaseModel):
                job.result = response.model_dump(mode="json")
            else:
                job.result = dict(response)
            agent = job.result.get("agent", {}) if job.result else {}
            measured = agent.get("first_world_action_ms")
            if measured is not None:
                job.server_ttfa_ms = float(measured)
            job.status = "completed"
        except Exception as error:
            job.error = f"{type(error).__name__}: {error}"
            job.status = "failed"

    def get(self, job_id: str, client_ttfa_ms: float | None = None) -> dict[str, Any]:
        job = self.jobs[job_id]
        if client_ttfa_ms is not None and not job.client_ttfa_reported:
            bounded = max(0.0, min(float(client_ttfa_ms), 60_000.0))
            job.client_ttfa_reported = True
            self.telemetry.first_action(bounded, observed_by="client")
            self.telemetry.event(
                "agent.first_action.client_observed",
                job.request_id,
                job_id=job.job_id,
                time_to_first_action_ms=round(bounded, 3),
                slo_ms=2000,
                slo_met=bounded <= 2000.0,
            )
        return self.view(job)

    @staticmethod
    def view(job: WishJob, include_first_actions: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": job.job_id,
            "request_id": job.request_id,
            "status": job.status,
            "server_time_to_first_action_ms": (
                round(job.server_ttfa_ms, 3) if job.server_ttfa_ms is not None else None
            ),
            "created_at": job.created_at,
        }
        if include_first_actions:
            payload["first_actions"] = [
                action.model_dump(mode="json") for action in job.first_actions
            ]
        if job.status == "completed":
            payload["result"] = job.result
        elif job.status == "failed":
            payload["error"] = job.error
        return payload

    def _discard_old_jobs(self) -> None:
        overflow = len(self.jobs) - self.max_jobs + 1
        if overflow <= 0:
            return
        removable = [
            job_id for job_id, job in self.jobs.items() if job.status != "running"
        ]
        for job_id in removable[:overflow]:
            self.jobs.pop(job_id, None)


class ClientTimingBreakdown(BaseModel):
    submit_to_initial_response_ms: float = Field(ge=0.0, le=60_000.0)
    submit_to_action_ready_ms: float = Field(ge=0.0, le=60_000.0)
    action_ready_to_mutation_ms: float = Field(ge=0.0, le=60_000.0)
    client_ttfa_ms: float = Field(ge=0.0, le=60_000.0)


class WishFeedback(BaseModel):
    step_id: str
    applied: bool = True
    observation: str = ""
    world: WorldSnapshot
    client_ttfa_ms: float | None = None
    client_timing: ClientTimingBreakdown | None = None
    client_timing_profile: Literal[
        "runtime", "latency_eval", "software_renderer_visual"
    ] = "runtime"


@dataclass
class AgenticWishJob:
    job_id: str
    request_id: str
    request: CastRequest
    planner: AgenticPlanner
    status: str = "planning"
    attempt: int = 0
    result: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    action_index: int = 0
    step_id: str | None = None
    error: str | None = None
    verification: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_monotonic: float = field(default_factory=time.perf_counter)
    first_action_ready_ms: float | None = None
    task: asyncio.Task[None] | None = None
    client_ttfa_reported: bool = False


class AgenticWishJobManager:
    """One action at a time: plan, ask the client to apply, observe, verify, retry."""

    def __init__(self, telemetry: TelemetryStore, max_jobs: int = 256, max_attempts: int = 3) -> None:
        self.telemetry = telemetry
        self.max_jobs = max_jobs
        self.max_attempts = max_attempts
        self.jobs: dict[str, AgenticWishJob] = {}

    def start(self, request: CastRequest, planner: AgenticPlanner) -> dict[str, Any]:
        self._discard_old_jobs()
        job = AgenticWishJob(
            job_id=uuid.uuid4().hex,
            request_id=request.request_id,
            request=request,
            planner=planner,
        )
        self.jobs[job.job_id] = job
        job.task = asyncio.create_task(self._plan(job))
        return self.view(job)

    async def _plan(self, job: AgenticWishJob) -> None:
        job.attempt += 1
        job.status = "planning"
        self.telemetry.event(
            "agent.loop.planning",
            job.request_id,
            job_id=job.job_id,
            attempt=job.attempt,
            visible_object_count=len(job.request.world.objects),
        )
        try:
            response = await job.planner(job.request)
            result = response.model_dump(mode="json") if isinstance(response, BaseModel) else dict(response)
            job.result = result
            agent_actions = result.get("agent", {}).get("actions", [])
            visuals = list(result.get("spell_plan", {}).get("visuals", []))
            visual_index = 0
            prepared: list[dict[str, Any]] = []
            for raw_action in agent_actions:
                action = dict(raw_action)
                world_action = action.get("world_action")
                if not isinstance(world_action, dict) or not world_action:
                    continue
                if visual_index < len(visuals):
                    action["_visual_descriptor"] = visuals[visual_index]
                    visual_index += 1
                prepared.append(action)
            if not prepared:
                raise RuntimeError("planner produced no client-visible world actions")
            job.actions = prepared
            job.action_index = 0
            if job.attempt == 1:
                self.telemetry.event(
                    "agent.loop.started", job.request_id, job_id=job.job_id, max_attempts=self.max_attempts
                )
            self._ready_current_action(job)
        except Exception as error:
            job.error = f"{type(error).__name__}: {error}"
            if job.attempt < self.max_attempts:
                self.telemetry.event(
                    "agent.loop.replanning",
                    job.request_id,
                    job_id=job.job_id,
                    attempt=job.attempt,
                    reason=job.error,
                )
                job.task = asyncio.create_task(self._plan(job))
            else:
                job.status = "failed"
                self.telemetry.count("granted_agent_loop_failures_total")
                self.telemetry.event(
                    "agent.loop.failed", job.request_id, job_id=job.job_id, error=job.error
                )

    def _ready_current_action(self, job: AgenticWishJob) -> None:
        if job.first_action_ready_ms is None:
            job.first_action_ready_ms = (time.perf_counter() - job.started_monotonic) * 1000.0
        job.step_id = uuid.uuid4().hex
        job.status = "action_ready"
        action = job.actions[job.action_index]
        self.telemetry.event(
            "agent.loop.action_ready",
            job.request_id,
            job_id=job.job_id,
            step_id=job.step_id,
            attempt=job.attempt,
            action_index=job.action_index,
            action=action.get("kind"),
            target_id=action.get("target_id"),
        )

    def get(self, job_id: str, client_ttfa_ms: float | None = None) -> dict[str, Any]:
        job = self.jobs[job_id]
        self._report_client_ttfa(job, client_ttfa_ms)
        return self.view(job)

    def feedback(self, job_id: str, feedback: WishFeedback) -> dict[str, Any]:
        job = self.jobs[job_id]
        if job.status != "action_ready" or feedback.step_id != job.step_id:
            raise ValueError("feedback does not match the current agent step")
        self._report_client_ttfa(
            job,
            feedback.client_ttfa_ms,
            feedback.client_timing,
            feedback.client_timing_profile,
        )
        action = job.actions[job.action_index]
        world_action = WorldAction.model_validate(action["world_action"])
        verified, detail = self.verify_world_action(
            world_action, job.request.world, feedback.world, applied=feedback.applied
        )
        record = {
            "step_id": feedback.step_id,
            "attempt": job.attempt,
            "action_index": job.action_index,
            "action": action.get("kind"),
            "target_id": action.get("target_id"),
            "verified": verified,
            "detail": detail,
            "client_observation": feedback.observation,
        }
        job.verification.append(record)
        self.telemetry.event(
            "agent.loop.feedback", job.request_id, job_id=job.job_id, **record
        )
        job.request = job.request.model_copy(update={"world": feedback.world})
        if verified:
            job.action_index += 1
            if job.action_index < len(job.actions):
                self._ready_current_action(job)
            else:
                goal_verified, goal_detail = self.verify_wish_goal(
                    job.request.spell_text, feedback.world
                )
                if not goal_verified:
                    job.error = goal_detail
                    if job.attempt < self.max_attempts:
                        job.status = "planning"
                        job.step_id = None
                        job.actions = []
                        job.action_index = 0
                        self.telemetry.event(
                            "agent.loop.replanning",
                            job.request_id,
                            job_id=job.job_id,
                            attempt=job.attempt,
                            reason=goal_detail,
                        )
                        job.task = asyncio.create_task(self._plan(job))
                        return self.view(job)
                    job.status = "failed"
                    self.telemetry.count("granted_agent_loop_failures_total")
                    self.telemetry.event(
                        "agent.loop.failed", job.request_id, job_id=job.job_id, error=goal_detail
                    )
                    return self.view(job)
                job.status = "completed"
                if job.result is not None:
                    job.result["agentic_loop"] = {
                        "verified": True,
                        "attempts": job.attempt,
                        "steps": job.verification,
                    }
                self.telemetry.count("granted_agent_loop_completed_total")
                self.telemetry.event(
                    "agent.loop.completed",
                    job.request_id,
                    job_id=job.job_id,
                    attempts=job.attempt,
                    verified_steps=len(job.verification),
                )
        elif job.attempt < self.max_attempts:
            job.error = detail
            job.status = "planning"
            job.step_id = None
            job.actions = []
            job.action_index = 0
            self.telemetry.event(
                "agent.loop.replanning",
                job.request_id,
                job_id=job.job_id,
                attempt=job.attempt + 1,
                reason=detail,
            )
            job.task = asyncio.create_task(self._plan(job))
        else:
            job.status = "failed"
            job.error = detail
            self.telemetry.count("granted_agent_loop_failures_total")
            self.telemetry.event(
                "agent.loop.failed", job.request_id, job_id=job.job_id, error=detail
            )
        return self.view(job)

    def _report_client_ttfa(
        self,
        job: AgenticWishJob,
        client_ttfa_ms: float | None,
        client_timing: ClientTimingBreakdown | None = None,
        timing_profile: str = "runtime",
    ) -> None:
        if client_ttfa_ms is None or job.client_ttfa_reported:
            return
        bounded = max(0.0, min(float(client_ttfa_ms), 60_000.0))
        job.client_ttfa_reported = True
        slo_applicable = timing_profile != "software_renderer_visual"
        if slo_applicable:
            self.telemetry.first_action(bounded, observed_by="client")
        else:
            self.telemetry.count(
                "granted_agent_client_ttfa_non_authoritative_samples_total",
                labels={"profile": timing_profile},
            )
        self.telemetry.event(
            "agent.first_action.client_observed",
            job.request_id,
            job_id=job.job_id,
            time_to_first_action_ms=round(bounded, 3),
            slo_ms=2000,
            slo_met=bounded <= 2000.0 if slo_applicable else None,
            slo_applicable=slo_applicable,
            timing_profile=timing_profile,
            meaning="first world mutation applied by client",
            client_timing=client_timing.model_dump(mode="json") if client_timing else None,
            server_action_ready_ms=(
                round(job.first_action_ready_ms, 3)
                if job.first_action_ready_ms is not None
                else None
            ),
        )

    @staticmethod
    def verify_world_action(
        action: WorldAction,
        before: WorldSnapshot,
        after: WorldSnapshot,
        *,
        applied: bool,
    ) -> tuple[bool, str]:
        if not applied:
            return False, "клиент сообщил, что действие не применено"
        before_by_id = {item.id: item for item in before.objects}
        after_by_id = {item.id: item for item in after.objects}
        target_before = before_by_id.get(action.target_id or "")
        target_after = after_by_id.get(action.target_id or "")
        if action.type == "CREATE_OBJECT_BATCH":
            prototype = str((action.effect or {}).get("prototype", ""))
            expected_count = int((action.effect or {}).get("count", 0))
            before_count = sum(prototype in item.tags for item in before.objects)
            after_count = sum(prototype in item.tags for item in after.objects)
            created_count = after_count - before_count
            ok = expected_count > 0 and created_count >= expected_count
            return (
                ok,
                f"создано {created_count} объектов {prototype}"
                if ok
                else f"ожидалось {expected_count} объектов {prototype}, появилось {created_count}",
            )
        if action.type == "DESTROY_OBJECTS":
            target_ids = [str(item) for item in (action.effect or {}).get("target_ids", [])]
            remaining = [
                target_id
                for target_id in target_ids
                if target_id in after_by_id
                and not AgenticWishJobManager._is_removed(after_by_id[target_id])
            ]
            ok = bool(target_ids) and not remaining
            return (
                ok,
                f"навсегда уничтожены все цели: {len(target_ids)}"
                if ok
                else f"после уничтожения остались цели: {', '.join(remaining)}",
            )
        if action.type == "INSTALL_DOORS":
            wall_ids = [str(item) for item in (action.effect or {}).get("wall_ids", [])]
            installed = [
                wall_id
                for wall_id in wall_ids
                if after_by_id.get(wall_id) is not None
                and after_by_id[wall_id].properties.get("door_installed") is True
            ]
            ok = bool(wall_ids) and len(installed) == len(wall_ids)
            detail = (
                f"двери подтверждены во всех {len(installed)} стенах"
                if ok
                else f"двери подтверждены только в {len(installed)} из {len(wall_ids)} стен"
            )
            return ok, detail
        if action.type == "EQUIP_OUTFIT":
            outfit = str((action.effect or {}).get("outfit", ""))
            ok = target_after is not None and target_after.properties.get("outfit") == outfit
            return ok, f"наряд {outfit} надет" if ok else f"наряд {outfit} не появился на цели"
        if action.type == "SHUTDOWN_GAME":
            state_names = {
                item if isinstance(item, str) else item.name
                for item in (target_after.states if target_after is not None else [])
            }
            ok = "game_shutdown" in state_names
            return ok, "клиент подтвердил выключение игры" if ok else "клиент не начал выключение"
        if action.type == "SET_GAME_PAUSED":
            expected = bool((action.effect or {}).get("paused", True))
            actual = target_after.properties.get("world_paused") if target_after is not None else None
            ok = actual is expected
            return ok, f"состояние паузы подтверждено: {actual}" if ok else f"пауза={actual}, ожидалось {expected}"
        if action.type == "SET_GAME_SPEED":
            expected = float((action.effect or {}).get("multiplier", 1.0))
            actual = target_after.properties.get("game_time_scale") if target_after is not None else None
            ok = actual is not None and abs(float(actual) - expected) < 0.001
            return ok, f"скорость мира подтверждена: {actual}" if ok else f"скорость={actual}, ожидалось {expected}"
        if action.type == "SET_LIGHT_LEVEL":
            expected = float((action.effect or {}).get("level", 1.0))
            actual = target_after.properties.get("light_level") if target_after is not None else None
            ok = actual is not None and abs(float(actual) - expected) < 0.001
            return ok, f"освещённость подтверждена: {actual}" if ok else f"освещённость={actual}, ожидалось {expected}"
        if action.type == "CREATE_OBJECT":
            prototype = str((action.effect or {}).get("prototype", ""))
            new_objects = [item for item in after.objects if item.id not in before_by_id]
            ok = any(prototype in item.tags or item.material.name == prototype for item in new_objects)
            return ok, f"новый объект {prototype} найден" if ok else f"новый объект {prototype} не появился"
        if action.type == "ADD_INVENTORY_ITEM":
            prototype = str((action.effect or {}).get("prototype", ""))
            before_inventory = set((target_before.properties if target_before else {}).get("inventory", []))
            after_inventory = set((target_after.properties if target_after else {}).get("inventory", []))
            ok = prototype in after_inventory or len(after_inventory - before_inventory) > 0
            return ok, f"{prototype} найден в рюкзаке" if ok else f"{prototype} не появился в рюкзаке"
        if action.type == "SPEAK":
            return True, "реплика показана клиентом"
        if action.type == "DESTROY_OBJECT":
            ok = target_before is not None and (
                target_after is None or AgenticWishJobManager._is_removed(target_after)
            )
            return ok, "цель уничтожена" if ok else "цель всё ещё активна"
        if target_before is None or target_after is None:
            return False, "цель отсутствует в снимке до или после действия"
        if action.type == "DAMAGE":
            ok = target_after.health is None or (
                target_before.health is not None and target_after.health < target_before.health
            )
            return ok, "здоровье уменьшилось" if ok else "здоровье не изменилось"
        if action.type == "HEAL":
            ok = (
                target_before.health is not None
                and target_after.health is not None
                and target_after.health > target_before.health
            )
            return ok, "здоровье увеличилось" if ok else "здоровье не увеличилось"
        if action.type == "TRANSFORM_OBJECT":
            prototype = str((action.effect or {}).get("prototype", ""))
            ok = prototype in target_after.tags
            return ok, f"форма {prototype} подтверждена" if ok else f"форма {prototype} не подтверждена"
        if action.type == "CHANGE_MATERIAL_STATE":
            expected = action.material or str((action.effect or {}).get("material", ""))
            ok = target_after.material.name == expected
            return ok, f"материал {expected} подтверждён" if ok else f"материал остался {target_after.material.name}"
        if action.type == "CHANGE_TEMPERATURE":
            ok = target_after.material.temperature != target_before.material.temperature
            return ok, "температура изменилась" if ok else "температура не изменилась"
        if action.type == "ADD_STATE":
            names = {item if isinstance(item, str) else item.name for item in target_after.states}
            ok = bool(action.state and action.state in names)
            return ok, f"состояние {action.state} подтверждено" if ok else f"состояние {action.state} не найдено"
        if action.type == "SET_AGGRO_TARGET":
            expected = str((action.effect or {}).get("aggro_target", "player"))
            ok = target_after.properties.get("aggro_target") == expected or any(
                (item if isinstance(item, str) else item.name) == "aggressive"
                for item in target_after.states
            )
            return ok, f"агро на {expected} подтверждено" if ok else f"агро на {expected} не установлено"
        if action.type in {"APPLY_FORCE", "CHANGE_VELOCITY"}:
            moved = target_after.position != target_before.position or target_after.velocity != target_before.velocity
            return moved, "движение подтверждено" if moved else "цель не сдвинулась"
        return True, "клиент подтвердил применение действия"

    @staticmethod
    def _is_removed(item: WorldObject) -> bool:
        return (
            item.properties.get("removed") is True
            or item.properties.get("destroyed") is True
            or (item.health is not None and item.health <= 0.0)
        )

    @staticmethod
    def verify_wish_goal(wish: str, world: WorldSnapshot) -> tuple[bool, str]:
        lowered = wish.lower()
        if any(marker in lowered for marker in ("убей", "уничтож", "истреб")) and any(
            marker in lowered for marker in ("враг", "противник")
        ):
            enemies = [
                item.id
                for item in world.objects
                if "enemy" in item.tags and not AgenticWishJobManager._is_removed(item)
            ]
            if enemies:
                return False, f"исходное желание не выполнено: живы враги — {', '.join(enemies)}"
            return True, "исходное желание выполнено: врагов в мире не осталось"
        if any(marker in lowered for marker in ("одень", "наряди", "накинуть", "накинь")):
            player = next((item for item in world.objects if item.id == "player"), None)
            expected_outfit = next(
                (
                    value
                    for marker, value in (
                        ("плать", "dress"), ("мант", "robe"),
                        ("брон", "armor"), ("доспех", "armor"), ("плащ", "cloak"),
                    )
                    if marker in lowered
                ),
                None,
            )
            if expected_outfit:
                ok = player is not None and player.properties.get("outfit") == expected_outfit
                return ok, f"наряд {expected_outfit} надет" if ok else f"на игроке нет наряда {expected_outfit}"
        if "выключ" in lowered and "игр" in lowered:
            player = next((item for item in world.objects if item.id == "player"), None)
            states = {
                item if isinstance(item, str) else item.name
                for item in (player.states if player is not None else [])
            }
            ok = "game_shutdown" in states
            return ok, "клиент начал выключение" if ok else "клиент не подтвердил выключение"
        player = next((item for item in world.objects if item.id == "player"), None)
        if any(marker in lowered for marker in ("сними с пауз", "убери пауз", "продолжи игр", "возобнови игр")):
            ok = player is not None and player.properties.get("world_paused") is False
            return ok, "игра снята с паузы" if ok else "игра осталась на паузе"
        if any(marker in lowered for marker in ("поставь на пауз", "игру на пауз", "останови время", "замри, время")):
            ok = player is not None and player.properties.get("world_paused") is True
            return ok, "игра поставлена на паузу" if ok else "игра не остановлена"
        if any(marker in lowered for marker in ("замедли игр", "замедли время", "медленнее", "слоу-мо")):
            actual = player.properties.get("game_time_scale") if player is not None else None
            ok = actual is not None and float(actual) < 1.0
            return ok, "мир действительно замедлен" if ok else "скорость мира не уменьшилась"
        if any(marker in lowered for marker in ("ускорь игр", "ускорь время", "быстрее", "ускорь мир")):
            actual = player.properties.get("game_time_scale") if player is not None else None
            ok = actual is not None and float(actual) > 1.0
            return ok, "мир действительно ускорен" if ok else "скорость мира не увеличилась"
        if any(marker in lowered for marker in ("темнее", "затемни", "погаси свет", "выключи свет", "тьму")):
            actual = player.properties.get("light_level") if player is not None else None
            ok = actual is not None and float(actual) < 1.0
            return ok, "мир действительно затемнён" if ok else "освещённость не уменьшилась"
        if any(marker in lowered for marker in ("светлее", "освети", "включи свет", "ярче", "залей свет")):
            actual = player.properties.get("light_level") if player is not None else None
            ok = actual is not None and float(actual) > 1.0
            return ok, "мир действительно освещён" if ok else "освещённость не увеличилась"
        if any(marker in lowered for marker in ("заспав", "создай", "призови", "породи")):
            for match, tag in (
                (re.search(r"(\d+)\s*(?:враг|противник)", lowered), "enemy"),
                (re.search(r"(\d+)\s*(?:нпс|npc)", lowered), "npc"),
            ):
                if match:
                    expected = min(32, int(match.group(1)))
                    actual = sum(tag in item.tags for item in world.objects)
                    if actual < expected:
                        return False, f"исходное желание не выполнено: {tag} только {actual} из {expected}"
        if any(marker in lowered for marker in ("двер", "ворот", "door", "gate")):
            walls = [item for item in world.objects if "wall" in item.tags]
            if not walls:
                return False, "итоговая проверка не видит стен в снимке мира"
            missing = [item.id for item in walls if item.properties.get("door_installed") is not True]
            if missing:
                return False, f"исходное желание не выполнено: без дверей осталось стен — {len(missing)}"
            return True, f"исходное желание выполнено: двери есть во всех {len(walls)} стенах"
        return True, "для этого желания используется проверка отдельных действий"

    @staticmethod
    def view(job: AgenticWishJob) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "agentic_loop": True,
            "job_id": job.job_id,
            "request_id": job.request_id,
            "status": job.status,
            "attempt": job.attempt,
            "created_at": job.created_at,
            "server_action_ready_ms": (
                round(job.first_action_ready_ms, 3)
                if job.first_action_ready_ms is not None
                else None
            ),
        }
        if job.status == "action_ready":
            payload["step_id"] = job.step_id
            payload["agent_action"] = job.actions[job.action_index]
        elif job.status == "completed":
            payload["result"] = job.result
            payload["verification"] = job.verification
        elif job.status == "failed":
            payload["error"] = job.error
            payload["verification"] = job.verification
        return payload

    def _discard_old_jobs(self) -> None:
        overflow = len(self.jobs) - self.max_jobs + 1
        if overflow <= 0:
            return
        removable = [job_id for job_id, job in self.jobs.items() if job.status not in {"planning", "action_ready"}]
        for job_id in removable[:overflow]:
            self.jobs.pop(job_id, None)
