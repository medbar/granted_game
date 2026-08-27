extends SceneTree

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("run")


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error("LIVE WISH: " + message)


func circle_points(center: Vector2, radius: float) -> Array:
	var points: Array = []
	for index in range(17):
		var point := center + Vector2.from_angle(float(index) / 16.0 * TAU) * radius
		points.append({"t_ms": index * 45, "screen_x": 0.5, "screen_y": 0.5, "world_x": point.x, "world_y": point.y})
	return points


func line_points(origin: Vector2, direction: Vector2) -> Array:
	return [
		{"t_ms": 0, "screen_x": 0.45, "screen_y": 0.5, "world_x": origin.x, "world_y": origin.y},
		{"t_ms": 100, "screen_x": 0.55, "screen_y": 0.5, "world_x": origin.x + direction.x * 2.0, "world_y": origin.y + direction.y * 2.0},
		{"t_ms": 200, "screen_x": 0.7, "screen_y": 0.5, "world_x": origin.x + direction.x * 4.0, "world_y": origin.y + direction.y * 4.0}
	]


func ask_wish(game, text: String, points: Array) -> bool:
	game.begin_wish()
	game.spell_input.text = text
	game.gesture_strokes = [points]
	game.confirm_cast()
	for _frame in range(360):
		await process_frame
		if not game.casting:
			return not game.last_debug.has("error")
	game.cancel_cast()
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
	var pool_center: Vector2 = game.water_position / game.UNIT
	var freeze_ok: bool = await ask_wish(game, "заморозь воду", circle_points(pool_center, 1.2))
	check(freeze_ok, "Godot receives a successful /wish response")
	check(game.water_state == "ice", "live backend response freezes the pool")
	check(game.last_debug.get("debug", {}).get("selected_targets", []).has("water_pool_01"), "live target resolution selects the pool")

	game.water_state = "water"
	game.water_temperature = 0.5
	var steam_ok: bool = await ask_wish(game, "создай огонь в воде", circle_points(pool_center, 0.8))
	check(steam_ok, "a second live wish completes")
	check(game.water_state == "steam", "fire in water resolves through heat and phase rules into steam")

	game.reset_sandbox()
	game.player.global_position = Vector2(-250, 0)
	game.dwarfs[0].global_position = Vector2(-50, 0)
	game.dwarfs[1].global_position = Vector2(10, 35)
	var origin: Vector2 = game.genie.global_position / game.UNIT
	var push_ok: bool = await ask_wish(game, "сильно отбрось всех врагов передо мной", line_points(origin, Vector2.RIGHT))
	check(push_ok, "enemy push wish completes")
	var targets: Array = game.last_debug.get("debug", {}).get("selected_targets", [])
	check(not targets.has("player"), "'from me' treats self as the force origin, not a target")
	check(targets.has("dwarf_01") and targets.has("dwarf_02"), "precise all-enemies wording selects multiple enemies")

	Engine.time_scale = 1.0
	if failures.is_empty():
		print("LIVE_WISH_OK: the genie and FastAPI completed all integration scenarios")
		quit(0)
	else:
		print("LIVE_WISH_FAILED: %d checks failed" % failures.size())
		for failure in failures:
			print(" - " + failure)
		quit(1)
