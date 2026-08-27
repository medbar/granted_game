extends SceneTree

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("run")


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error("CLIENT SMOKE: " + message)


func run() -> void:
	var packed: PackedScene = load("res://scenes/main.tscn")
	check(packed != null, "main scene loads")
	if packed == null:
		finish()
		return
	var game = packed.instantiate()
	root.add_child(game)
	for _frame in range(4):
		await process_frame

	check(game.dwarfs.size() >= 5, "arena contains at least five gnomes")
	check(is_instance_valid(game.genie), "the player has a genie companion")
	check(game.genie.companion == game.player, "the genie follows the player rather than replacing them")
	check(game.props.size() >= 3, "arena contains several physical props")
	check(game.object_index.has("tree_01"), "arena contains a flammable object")
	check(game.water_snapshot()["material"]["name"] == "water", "arena exposes a water object")
	var has_camera := false
	for child in game.player.get_children():
		if child is Camera2D:
			has_camera = true
	check(has_camera, "top-down camera follows the player")

	var start_position: Vector2 = game.player.global_position
	var press := InputEventKey.new()
	press.physical_keycode = KEY_D
	press.pressed = true
	Input.parse_input_event(press)
	for _frame in range(8):
		await physics_frame
	var release := InputEventKey.new()
	release.physical_keycode = KEY_D
	release.pressed = false
	Input.parse_input_event(release)
	check(game.player.global_position.x > start_position.x, "WASD movement changes player position")

	var attacker = game.dwarfs[0]
	attacker.global_position = game.player.global_position + Vector2(24, 0)
	attacker.attack_cooldown = 0.0
	var health_before: float = game.player.health
	for _frame in range(4):
		await physics_frame
	check(game.player.health < health_before, "a nearby gnome attacks and damages the player")
	game.player.health = 100.0

	attacker.global_position = game.player.global_position + Vector2(180, 0)
	var enemy_before: Vector2 = attacker.global_position
	game.begin_wish()
	check(game.casting, "Space-equivalent input opens a request to the genie")
	check(game.genie.wish_active, "the genie visibly reacts while listening to a wish")
	check(is_equal_approx(Engine.time_scale, game.cast_time_scale), "wish entry uses configured slow motion")
	check(game.spell_input.visible and not game.player.movement_enabled, "wish mode shows text input and suspends WASD")
	for _frame in range(12):
		await physics_frame
	check(attacker.global_position.distance_to(enemy_before) > 0.1, "world simulation continues while the player asks the genie")

	game.spell_input.text = "заморозь воду"
	game.gesture_strokes = [[
		{"t_ms": 0, "screen_x": 0.4, "screen_y": 0.5, "world_x": 1.0, "world_y": 1.0},
		{"t_ms": 100, "screen_x": 0.5, "screen_y": 0.4, "world_x": 2.0, "world_y": 1.0},
		{"t_ms": 200, "screen_x": 0.4, "screen_y": 0.5, "world_x": 1.0, "world_y": 1.0}
	]]
	var payload: Dictionary = game.build_cast_payload(game.spell_input.text)
	check(payload["wish_text"] == "заморозь воду", "Cyrillic wish text survives the client request contract")
	check(is_equal_approx(float(payload["caster"]["position"]["x"]), game.genie.global_position.x / game.UNIT), "wish effects originate from the genie")
	check(payload["gesture"]["strokes"].size() == 1, "gesture strokes enter the client request contract")

	var response := {
		"interpretation": {"coherence": 0.9, "anchors": [], "gesture_features": {}},
		"debug": {"intent": {}, "selected_targets": ["water_pool_01"], "world_rules": ["test"], "latency_ms": 1.0},
		"spell_plan": {
			"world_actions": [
				{"type": "CHANGE_MATERIAL_STATE", "target_id": "water_pool_01", "material": "ice"},
				{"type": "SPAWN_EFFECT_ENTITY", "effect": {"form": "field", "payload": {"cold": 0.8, "power": 1.0}, "position": [3.0, 2.0], "velocity": [0.0, 0.0], "radius": 1.0, "lifetime": 0.5}}
			],
			"visuals": [{"primitive": "SURFACE_OVERLAY", "appearance": ["ice"], "origin": {"x": 3.0, "y": 2.0}, "direction": {"x": 1.0, "y": 0.0}, "radius": 1.0, "speed": 0.0, "intensity": 1.0, "turbulence": 0.0, "lifetime": 0.5}]
		}
	}
	game.apply_spell_response(response)
	check(game.water_state == "ice", "generic world action changes water into ice")
	check(game.last_debug == response, "response populates developer debug data")
	game.finish_cast_mode()
	check(is_equal_approx(Engine.time_scale, 1.0) and not game.casting and not game.genie.wish_active, "time returns to normal after the genie acts")

	var primitives := ["BURST", "PROJECTILE", "BEAM", "LINE", "RING", "FIELD", "CLOUD", "TRAIL", "TETHER", "SURFACE_OVERLAY"]
	for primitive in primitives:
		game.spawn_visual({"primitive": primitive, "appearance": ["force"], "origin": {"x": 0.0, "y": 0.0}, "direction": {"x": 1.0, "y": 0.0}, "radius": 0.5, "speed": 1.0, "intensity": 0.8, "turbulence": 0.1, "lifetime": 0.25})
	await process_frame
	check(primitives.size() == 10, "ten universal visual primitives instantiate")

	var debug_event := InputEventKey.new()
	debug_event.keycode = KEY_F3
	debug_event.pressed = true
	game._input(debug_event)
	check(game.debug_panel.visible, "F3 opens developer debug information")

	game.begin_wish()
	game.cast_failed("deliberate smoke-test failure")
	check(not game.casting and is_equal_approx(Engine.time_scale, 1.0), "backend failure safely exits wish mode")
	finish()


func finish() -> void:
	Engine.time_scale = 1.0
	if failures.is_empty():
		print("CLIENT_SMOKE_OK: all client v0 checks passed")
		quit(0)
	else:
		print("CLIENT_SMOKE_FAILED: %d checks failed" % failures.size())
		for failure in failures:
			print(" - " + failure)
		quit(1)
