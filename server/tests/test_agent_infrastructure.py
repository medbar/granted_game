from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from app.agent import GenieAgentService
from app.agent_jobs import AgenticWishJobManager, ClientTimingBreakdown, WishFeedback, WishJobManager
from app.agent_models import AgentAction, AgentConclusion, PlannedAction
from app.curses import CurseManager
from app.evaluation import evaluate_trajectory
from app.models import MaterialSnapshot, Vec2, WorldAction, WorldObject
from app.sim_world import create_level
from app.telemetry import TelemetryStore
from conftest import cast_request


def test_curses_expose_public_symptoms_without_prompt_text(tmp_path) -> None:
    manager = CurseManager(tmp_path / "genie_state.json")
    for _ in range(3):
        manager.record_wish("убей врага", ["affect_physical"], completed=True)

    public = manager.public()
    ids = {curse.id for curse in public}
    assert "violent_shortcut" in ids
    dumped = json.dumps([curse.model_dump() for curse in public], ensure_ascii=False)
    assert "instruction" not in dumped
    assert "предпочитай прямое физическое" not in dumped.lower()


def test_telemetry_writes_loki_jsonl_prometheus_and_trajectory(tmp_path) -> None:
    telemetry = TelemetryStore(tmp_path)
    telemetry.event("agent.run.started", "wish-1", model="glm-5.3-flash")
    telemetry.count("granted_agent_requests_total")
    telemetry.count("granted_agent_actions_total", labels={"action": "observe_area"})
    telemetry.latency(123.4)
    telemetry.monty_execution(8.25)
    trajectory = telemetry.trajectory("wish-1", {"schema_version": 1, "actions": []})

    event = json.loads(telemetry.log_path.read_text(encoding="utf-8").splitlines()[0])
    assert event["event"] == "agent.run.started"
    assert event["request_id"] == "wish-1"
    metrics = telemetry.metrics_path.read_text(encoding="utf-8")
    assert "granted_agent_requests_total 1" in metrics
    assert 'granted_agent_actions_total{action="observe_area"} 1' in metrics
    assert "granted_agent_last_run_latency_milliseconds 123.400" in metrics
    assert "granted_agent_last_monty_execution_milliseconds 8.250" in metrics
    assert "granted_agent_monty_executions_total 1" in metrics
    assert json.loads(trajectory.read_text(encoding="utf-8"))["schema_version"] == 1


def test_ttfa_metrics_include_server_client_and_two_second_slo(tmp_path) -> None:
    telemetry = TelemetryStore(tmp_path)
    telemetry.first_action(12.5, observed_by="server")
    telemetry.first_action(140.0, observed_by="client")
    metrics = telemetry.metrics_path.read_text(encoding="utf-8")
    assert "granted_agent_server_time_to_first_action_milliseconds 12.500" in metrics
    assert "granted_agent_client_time_to_first_action_milliseconds 140.000" in metrics
    assert "granted_agent_time_to_first_action_milliseconds 140.000" in metrics
    assert "granted_agent_ttfa_slo_milliseconds 2000.000" in metrics
    assert "granted_agent_ttfa_slo_met 1" in metrics


def test_wish_job_does_not_report_fake_action_before_background_result(tmp_path) -> None:
    async def scenario() -> None:
        telemetry = TelemetryStore(tmp_path)
        manager = WishJobManager(telemetry)
        release = asyncio.Event()

        async def runner() -> dict[str, object]:
            await release.wait()
            return {
                "request_id": "wish-job-test",
                "done": True,
                "agent": {"first_world_action_ms": 725.0},
            }

        started = manager.start("wish-job-test", runner, visible_object_count=4)
        assert started["status"] == "running"
        assert started["server_time_to_first_action_ms"] is None
        assert started["first_actions"] == []
        release.set()
        await manager.jobs[started["job_id"]].task
        completed = manager.get(started["job_id"], client_ttfa_ms=125.0)
        assert completed["status"] == "completed"
        assert completed["result"]["done"] is True
        assert completed["server_time_to_first_action_ms"] == 725.0

    asyncio.run(scenario())


def test_agentic_job_applies_one_action_then_verifies_world_before_advancing(tmp_path, world) -> None:
    async def scenario() -> None:
        manager = AgenticWishJobManager(TelemetryStore(tmp_path))

        async def planner(_request) -> dict[str, object]:
            return {
                "agent": {
                    "actions": [
                        {
                            "sequence": 1,
                            "kind": "affect_physical",
                            "target_id": "dwarf_01",
                            "teleport_to_target": True,
                            "world_action": {"type": "DAMAGE", "target_id": "dwarf_01", "amount": 10},
                        },
                        {
                            "sequence": 2,
                            "kind": "speak",
                            "target_id": "player",
                            "world_action": {
                                "type": "SPEAK",
                                "target_id": "player",
                                "effect": {"message": "Готово"},
                            },
                        },
                    ]
                },
                "spell_plan": {"visuals": []},
            }

        request = cast_request("рани врага", world)
        started = manager.start(request, planner)
        job = manager.jobs[started["job_id"]]
        await job.task
        first = manager.get(job.job_id)
        assert first["status"] == "action_ready"
        assert first["agent_action"]["world_action"]["type"] == "DAMAGE"

        after_damage = world.model_copy(deep=True)
        after_damage.objects[0].health = 62
        second = manager.feedback(
            job.job_id,
            WishFeedback(step_id=first["step_id"], world=after_damage),
        )
        assert second["status"] == "action_ready"
        assert second["agent_action"]["world_action"]["type"] == "SPEAK"

        completed = manager.feedback(
            job.job_id,
            WishFeedback(step_id=second["step_id"], world=after_damage),
        )
        assert completed["status"] == "completed"
        assert completed["result"]["agentic_loop"]["verified"] is True
        assert len(completed["verification"]) == 2

    asyncio.run(scenario())


def test_agentic_job_exposes_action_ready_and_client_stage_timings(tmp_path, world) -> None:
    async def scenario() -> None:
        telemetry = TelemetryStore(tmp_path)
        manager = AgenticWishJobManager(telemetry)

        async def planner(_request) -> dict[str, object]:
            return {
                "agent": {
                    "actions": [{
                        "sequence": 1,
                        "kind": "affect_physical",
                        "target_id": "dwarf_01",
                        "world_action": {
                            "type": "DAMAGE",
                            "target_id": "dwarf_01",
                            "amount": 10,
                        },
                    }]
                },
                "spell_plan": {"visuals": []},
            }

        started = manager.start(cast_request("рани врага", world), planner)
        job = manager.jobs[started["job_id"]]
        await job.task
        ready = manager.get(job.job_id)
        assert isinstance(ready["server_action_ready_ms"], float)
        assert ready["server_action_ready_ms"] >= 0.0

        after = world.model_copy(deep=True)
        after.objects[0].health = 62
        manager.feedback(
            job.job_id,
            WishFeedback(
                step_id=ready["step_id"],
                world=after,
                client_ttfa_ms=640.0,
                client_timing={
                    "submit_to_initial_response_ms": 25.0,
                    "submit_to_action_ready_ms": 110.0,
                    "action_ready_to_mutation_ms": 530.0,
                    "client_ttfa_ms": 640.0,
                },
            ),
        )
        events = [
            json.loads(line)
            for line in telemetry.log_path.read_text(encoding="utf-8").splitlines()
        ]
        observed = next(item for item in events if item["event"] == "agent.first_action.client_observed")
        assert observed["client_timing"]["submit_to_action_ready_ms"] == 110.0
        assert observed["server_action_ready_ms"] == ready["server_action_ready_ms"]

    asyncio.run(scenario())


def test_server_launchers_cannot_block_on_per_request_access_log() -> None:
    root = Path(__file__).resolve().parents[2]
    for script_name in ("run_backend.ps1", "run_all.ps1", "verify.ps1"):
        source = (root / script_name).read_text(encoding="utf-8")
        assert "--no-access-log" in source, f"{script_name} must disable uvicorn access log"


def test_server_lifespan_prewarms_agent_before_accepting_first_wish(monkeypatch) -> None:
    import app.main as main

    calls: list[str] = []
    monkeypatch.setattr(main, "agent_mode_enabled", lambda: True)
    monkeypatch.setattr(main, "agent_service", lambda: calls.append("warmed"))

    async def scenario() -> None:
        async with main.lifespan(main.app):
            assert calls == ["warmed"]

    asyncio.run(scenario())


def test_client_timing_breakdown_rejects_negative_or_unbounded_offsets() -> None:
    with pytest.raises(ValueError):
        ClientTimingBreakdown(
            submit_to_initial_response_ms=-1.0,
            submit_to_action_ready_ms=10.0,
            action_ready_to_mutation_ms=10.0,
            client_ttfa_ms=20.0,
        )
    with pytest.raises(ValueError):
        ClientTimingBreakdown(
            submit_to_initial_response_ms=10.0,
            submit_to_action_ready_ms=20.0,
            action_ready_to_mutation_ms=70_000.0,
            client_ttfa_ms=70_020.0,
        )


def test_software_renderer_ttfa_is_logged_but_does_not_replace_runtime_slo(tmp_path, world) -> None:
    async def scenario() -> None:
        telemetry = TelemetryStore(tmp_path)
        manager = AgenticWishJobManager(telemetry)

        async def planner(_request) -> dict[str, object]:
            return {
                "agent": {"actions": [{
                    "sequence": 1,
                    "kind": "affect_physical",
                    "target_id": "dwarf_01",
                    "world_action": {"type": "DAMAGE", "target_id": "dwarf_01", "amount": 10},
                }]},
                "spell_plan": {"visuals": []},
            }

        started = manager.start(cast_request("рани врага", world), planner)
        job = manager.jobs[started["job_id"]]
        await job.task
        ready = manager.get(job.job_id)
        after = world.model_copy(deep=True)
        after.objects[0].health = 62
        manager.feedback(
            job.job_id,
            WishFeedback(
                step_id=ready["step_id"],
                world=after,
                client_ttfa_ms=8_500.0,
                client_timing_profile="software_renderer_visual",
            ),
        )
        metrics = telemetry.metrics_path.read_text(encoding="utf-8")
        assert "granted_agent_client_ttfa_samples_total" not in metrics
        assert 'granted_agent_ttfa_slo_violations_total{observed_by="client"}' not in metrics
        events = [json.loads(line) for line in telemetry.log_path.read_text(encoding="utf-8").splitlines()]
        observed = next(item for item in events if item["event"] == "agent.first_action.client_observed")
        assert observed["timing_profile"] == "software_renderer_visual"
        assert observed["slo_applicable"] is False

    asyncio.run(scenario())


def test_agentic_job_replans_when_client_snapshot_does_not_confirm_action(tmp_path, world) -> None:
    async def scenario() -> None:
        manager = AgenticWishJobManager(TelemetryStore(tmp_path), max_attempts=3)
        planner_calls = 0

        async def planner(_request) -> dict[str, object]:
            nonlocal planner_calls
            planner_calls += 1
            return {
                "agent": {
                    "actions": [{
                        "sequence": 1,
                        "kind": "create_object",
                        "target_id": "player",
                        "world_action": {
                            "type": "CREATE_OBJECT",
                            "target_id": "player",
                            "effect": {"prototype": "fire"},
                        },
                    }]
                },
                "spell_plan": {"visuals": []},
            }

        started = manager.start(cast_request("создай огонь", world), planner)
        job = manager.jobs[started["job_id"]]
        await job.task
        first = manager.get(job.job_id)
        replanning = manager.feedback(
            job.job_id,
            WishFeedback(step_id=first["step_id"], world=world),
        )
        assert replanning["status"] == "planning"
        await job.task
        assert manager.get(job.job_id)["status"] == "action_ready"
        assert job.attempt == 2
        assert planner_calls == 2

    asyncio.run(scenario())


def test_door_wish_uses_dedicated_capability_instead_of_boxes() -> None:
    program = GenieAgentService._compile_fast_program("сделай двери в каждой стене")
    assert program is not None
    assert program.code == "install_doors()"
    assert "crate" not in program.code
    assert "cage" not in program.code


def test_recent_real_wishes_compile_to_truthful_game_capabilities() -> None:
    expected = {
        "убей всех врагов": "destroy_all('enemy')",
        "заспавнь 20 врагов и 10 нпс": "spawn_many('enemy', 20, near='player')\nspawn_many('npc', 10, near='player')",
        "выключи игру": "shutdown_game()",
        "одень меня в платье": "equip_outfit('player', 'dress')",
    }
    for wish, code in expected.items():
        program = GenieAgentService._compile_fast_program(wish)
        assert program is not None
        assert program.code == code
        assert "spawn('crate'" not in program.code


def test_door_action_and_final_goal_require_every_wall_to_have_a_door(world) -> None:
    before = world.model_copy(deep=True)
    for wall_id in ("wall_01", "wall_02"):
        before.objects.append(
            WorldObject(
                id=wall_id,
                kind="structure",
                tags=["wall", "stone"],
                position=Vec2(),
                material=MaterialSnapshot(name="stone"),
                properties={"door_installed": False},
            )
        )
    action = WorldAction(
        type="INSTALL_DOORS",
        target_id="wall_01",
        effect={"wall_ids": ["wall_01", "wall_02"]},
    )
    incomplete = before.model_copy(deep=True)
    incomplete.objects[-2].properties["door_installed"] = True
    verified, _ = AgenticWishJobManager.verify_world_action(action, before, incomplete, applied=True)
    assert verified is False
    goal_verified, _ = AgenticWishJobManager.verify_wish_goal(
        "сделай двери в каждой стене", incomplete
    )
    assert goal_verified is False

    complete = incomplete.model_copy(deep=True)
    complete.objects[-1].properties["door_installed"] = True
    verified, _ = AgenticWishJobManager.verify_world_action(action, before, complete, applied=True)
    assert verified is True
    goal_verified, _ = AgenticWishJobManager.verify_wish_goal(
        "сделай двери в каждой стене", complete
    )
    assert goal_verified is True


def test_destroy_verification_accepts_tombstones_in_full_world_snapshot(world) -> None:
    before = world.model_copy(deep=True)
    enemy = next(item for item in before.objects if "enemy" in item.tags)
    action = WorldAction(
        type="DESTROY_OBJECTS",
        target_id=enemy.id,
        effect={"target_ids": [enemy.id], "tag": "enemy"},
    )
    after = before.model_copy(deep=True)
    destroyed = next(item for item in after.objects if item.id == enemy.id)
    destroyed.health = 0.0
    destroyed.properties.update({"removed": True, "visible": False})

    verified, _ = AgenticWishJobManager.verify_world_action(
        action, before, after, applied=True
    )
    goal_verified, _ = AgenticWishJobManager.verify_wish_goal(
        "убей всех врагов", after
    )

    assert verified is True
    assert goal_verified is True

    single_verified, _ = AgenticWishJobManager.verify_world_action(
        WorldAction(type="DESTROY_OBJECT", target_id=enemy.id),
        before,
        after,
        applied=True,
    )
    assert single_verified is True


def test_baseline_trajectory_eval_is_versioned_and_bounded() -> None:
    actions = [
        AgentAction(
            sequence=1,
            kind="observe_area",
            observation="ok",
        ),
        AgentAction(
            sequence=2,
            kind="affect_physical",
            target_id="dwarf_01",
            observation="ok",
        ),
    ]
    result = evaluate_trajectory(
        actions,
        AgentConclusion(status="completed", summary="done"),
    )
    assert result.evaluator_version == "heuristic-v1"
    assert result.score == 1.0


def test_eval_penalizes_inspection_after_world_mutation() -> None:
    actions = [
        AgentAction(sequence=1, kind="observe_area", observation="seen"),
        AgentAction(sequence=2, kind="affect_physical", target_id="dwarf_01", observation="pushed"),
        AgentAction(sequence=3, kind="inspect_entity", target_id="dwarf_01", observation="late"),
    ]
    result = evaluate_trajectory(actions, AgentConclusion(status="completed", summary="done"))
    assert result.observation_order == 0.5
    assert result.score < 0.9


def test_batched_actions_reject_missing_targets_without_calling_world() -> None:
    assert GenieAgentService._missing_required_target("interact", None) is True
    assert GenieAgentService._missing_required_target("speak", "") is True
    assert GenieAgentService._missing_required_target("create_item", None) is False
    assert GenieAgentService._missing_required_target("observe_area", None) is False


def test_batched_actions_can_infer_obvious_target_tag_from_intent() -> None:
    door_action = PlannedAction(kind="interact", interaction="Открыть дверь созданным ключом")
    keeper_action = PlannedAction(kind="speak", message="Хранитель, назови код")
    assert GenieAgentService._hint_target_tag(door_action) == "door"
    assert GenieAgentService._hint_target_tag(keeper_action) == "neutral"


def test_fast_program_compiles_unambiguous_role_transformations() -> None:
    program = GenieAgentService._compile_fast_program("преврати нпс во врага")
    assert program is not None
    assert "nearest('npc')" in program.code
    assert "transform(target, 'enemy')" in program.code

    plural = GenieAgentService._compile_fast_program(
        "преврати все камни во врагов", add_opinion=True
    )
    assert plural is not None
    assert "all_with_tag('rock'" in plural.code
    assert "transform(target, 'enemy')" in plural.code
    assert "speak('player'" in plural.code


def test_fast_program_returns_genie_to_player() -> None:
    program = GenieAgentService._compile_fast_program("вернись ко мне")
    assert program is not None
    assert program.code.startswith("speak('player'")


def test_fast_program_turns_repeated_letters_into_visible_magic() -> None:
    program = GenieAgentService._compile_fast_program("фффф")
    assert program is not None
    assert "range(4)" in program.code
    assert "spawn('fire'" in program.code
    assert GenieAgentService._program_has_mutation(program.code)


def test_fallback_program_reports_failure_without_unrelated_world_mutation() -> None:
    program = GenieAgentService._fallback_program("непонятное желание")
    assert "speak('player'" in program.code
    assert "spawn(" not in program.code
    assert not GenieAgentService._program_has_mutation(program.code)


def test_fast_program_routes_inventory_walls_statuses_aggro_and_traps() -> None:
    cases = {
        "Создай четыре стены вокруг игрока": "spawn('wall'",
        "Сделай так, чтобы НПС проходил сквозь стены": "'phased'",
        "Сделай врага невидимым": "'invisible'",
        "Облей врага водой, чтобы он стал мокрым": "'wet'",
        "Заставь врага агриться на игрока": "set_aggro",
        "Положи магический ключ в рюкзак игрока": "give_item('magic_key'",
        "Создай ловушку рядом с врагом": "spawn('trap'",
    }
    for wish, expected_code in cases.items():
        program = GenieAgentService._compile_fast_program(wish)
        assert program is not None
        assert expected_code in program.code


def test_fast_program_preserves_singular_kill_blood_bath_and_visible_greeting() -> None:
    kill = GenieAgentService._compile_fast_program("Убей врага")
    blood = GenieAgentService._compile_fast_program("Искупай врага в крови")
    greeting = GenieAgentService._compile_fast_program(
        "Попроси мирного жителя поприветствовать меня"
    )

    assert kill is not None
    assert "destroy(target)" in kill.code
    assert "destroy_all" not in kill.code
    assert blood is not None
    assert "spawn('blood_pool', near=target)" in blood.code
    assert "apply_state(target, 'blood_soaked'" in blood.code
    assert greeting is not None
    assert "nearest('friendly')" in greeting.code
    assert "speak(target" in greeting.code
    assert GenieAgentService._is_speech_wish(
        "Попроси мирного жителя поприветствовать меня"
    )


def test_authoritative_level_completion_stops_retries_and_controls_visible_conclusion(
    tmp_path, world
) -> None:
    async def scenario() -> None:
        session = create_level("whispering_gate", "completed-oracle-regression")
        request = cast_request(
            "Сначала безуспешно попробуй разрушить укреплённые врата, "
            "затем спроси код у мудреца и открой врата кодом.",
            session.public_world(),
        )
        service = GenieAgentService(
            curse_manager=CurseManager(tmp_path / "curses.json"),
            telemetry=TelemetryStore(tmp_path / "telemetry"),
        )

        response = await service.run(request, session=session, progress_curses=False)

        assert session.status == "completed"
        assert response.agent.conclusion.status == "completed"
        assert response.agent.program_code != service._fallback_program(request.spell_text).code
        assert [action.kind for action in response.agent.actions] == [
            "affect_physical",
            "speak",
            "speak",
        ]

    asyncio.run(scenario())
