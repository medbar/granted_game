extends SceneTree

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("run")


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error("LIVE WISH: " + message)


func ask_wish(game, text: String) -> bool:
	game.begin_wish()
	game.spell_input.text = text
	game.confirm_cast()
	for _poll in range(1200):
		await create_timer(0.05, true, false, true).timeout
		if not game.waiting_for_backend:
			return not game.last_debug.has("error")
	game.cast_failed("live test timeout")
	return false


func run() -> void:
	var packed: PackedScene = load("res://scenes/main.tscn")
	var game = packed.instantiate()
	root.add_child(game)
	for _frame in range(20):
		await process_frame

	game.player.global_position = game.water_position - Vector2(145, 0)
	game.genie.snap_to_companion()
	await process_frame
	var freeze_ok: bool = await ask_wish(game, "заморозь воду")
	check(freeze_ok, "Godot receives a successful /wish response")
	check(game.water_state == "ice", "live backend response freezes the pool")
	check(game.last_debug.get("debug", {}).get("selected_targets", []).has("water_pool_01"), "live target resolution selects the pool")

	game.water_state = "water"
	game.water_temperature = 0.5
	var steam_ok: bool = await ask_wish(game, "создай огонь в воде")
	check(steam_ok, "a second live wish completes")
	check(game.water_state == "steam", "fire in water resolves through heat and phase rules into steam")

	game.reset_sandbox()
	game.player.global_position = Vector2(-250, 0)
	game.dwarfs[0].global_position = Vector2(-50, 0)
	game.dwarfs[1].global_position = Vector2(10, 35)
	game.genie.facing = Vector2.RIGHT
	var push_ok: bool = await ask_wish(game, "сильно отбрось всех врагов передо мной")
	check(push_ok, "enemy push wish completes")
	var targets: Array = []
	for action in game.last_debug.get("agent", {}).get("actions", []):
		var target_id := str(action.get("target_id", ""))
		if not target_id.is_empty() and not targets.has(target_id):
			targets.append(target_id)
	check(not targets.has("player"), "'from me' treats self as the force origin, not a target")
	var expected_enemy_ids: Array = game.dwarfs.map(func(enemy): return enemy.object_id)
	check(expected_enemy_ids.all(func(enemy_id): return targets.has(enemy_id)), "precise all-enemies wording selects every level guard")

	game.reset_sandbox()
	var inventory_ok: bool = await ask_wish(game, "Положи магический ключ в рюкзак игрока")
	check(inventory_ok and game.player.inventory.has("magic_key"), "live agent puts an item in the real player inventory")
	var wall_ok: bool = await ask_wish(game, "Создай стену перед игроком")
	check(wall_ok and game.props[-1].prop_kind == "wall" and game.props[-1].collision_layer == 1, "live agent creates a physical wall")
	var doors_ok: bool = await ask_wish(game, "Сделай двери в каждой стене")
	var every_arena_wall_has_door: bool = game.arena_walls.values().all(func(item): return item.get("door_installed", false))
	check(doors_ok and every_arena_wall_has_door and game.props[-1].door_installed, "live agent creates real doorways in arena and conjured walls")
	var phase_ok: bool = await ask_wish(game, "Сделай так, чтобы игрок проходил сквозь стены")
	await physics_frame
	check(phase_ok and game.player.states.has("phased") and game.player.collision_mask == 0, "live agent makes the player phase through walls")

	game.reset_sandbox()
	var kill_ok: bool = await ask_wish(game, "убей всех врагов")
	await create_timer(4.2, true, false, true).timeout
	check(kill_ok and game.dwarfs.all(func(enemy): return not enemy.visible and enemy.permanently_destroyed), "live agent permanently kills every enemy without respawn")

	game.reset_sandbox()
	var spawn_ok: bool = await ask_wish(game, "заспавнь 20 врагов и 10 нпс")
	var spawned_enemies: Array = game.props.filter(func(item): return item.object_id.begins_with("created_") and item.prop_kind == "enemy")
	var spawned_npcs: Array = game.props.filter(func(item): return item.object_id.begins_with("created_") and item.prop_kind == "npc")
	check(spawn_ok and spawned_enemies.size() == 20 and spawned_npcs.size() == 10, "live agent spawns the exact requested actor counts without placeholder boxes")

	var dress_ok: bool = await ask_wish(game, "одень меня в платье")
	check(dress_ok and game.player.outfit == "dress", "live agent equips a visible dress on the player")
	var robe_ok: bool = await ask_wish(game, "Наряди игрока в мантию")
	check(robe_ok and game.player.outfit == "robe", "live agent replaces the dress with the requested robe")

	var props_before_shield: int = game.props.size()
	var shield_ok: bool = await ask_wish(game, "Сотвори щит рядом со мной")
	check(shield_ok and game.props.size() == props_before_shield + 1 and game.props[-1].prop_kind == "shield", "live agent creates the requested shield prototype")
	var transform_ok: bool = await ask_wish(game, "Преврати камень в коробку")
	var a_rock_became_a_crate: bool = game.object_index["rock_01"].prop_kind == "crate" or game.object_index["rock_02"].prop_kind == "crate"
	check(transform_ok and a_rock_became_a_crate, "live agent transforms a real rock into a visible crate")
	game.queue_free()
	for _cleanup_frame in range(4):
		await process_frame
	game = packed.instantiate()
	root.add_child(game)
	for _fresh_frame in range(20):
		await process_frame

	var pause_ok: bool = await ask_wish(game, "Поставь игру на паузу")
	check(pause_ok and game.world_paused and is_zero_approx(Engine.time_scale), "live agent pauses the world")
	var resume_ok: bool = await ask_wish(game, "Сними с паузы игру")
	check(resume_ok and not game.world_paused and is_equal_approx(Engine.time_scale, 1.0), "live agent resumes the world")
	var slow_ok: bool = await ask_wish(game, "Замедли игру")
	check(slow_ok and is_equal_approx(game.world_time_scale, 0.5) and is_equal_approx(Engine.time_scale, 0.5), "live agent slows the world")
	var fast_ok: bool = await ask_wish(game, "Ускорь игру")
	check(fast_ok and is_equal_approx(game.world_time_scale, 2.0) and is_equal_approx(Engine.time_scale, 2.0), "live agent accelerates the world")
	var dark_ok: bool = await ask_wish(game, "Сделай мир темнее")
	check(dark_ok and is_equal_approx(game.world_light_level, 0.3) and game.world_light_overlay.color.a > 0.5, "live agent darkens the rendered world")
	var bright_ok: bool = await ask_wish(game, "Сделай мир светлее")
	check(bright_ok and is_equal_approx(game.world_light_level, 1.6), "live agent brightens the rendered world")

	Engine.time_scale = 1.0
	if failures.is_empty():
		print("LIVE_WISH_OK: the genie and FastAPI completed all integration scenarios")
		quit(0)
	else:
		print("LIVE_WISH_FAILED: %d checks failed" % failures.size())
		for failure in failures:
			print(" - " + failure)
		quit(1)
