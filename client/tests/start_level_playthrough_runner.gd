extends SceneTree

const ARTIFACT_DIR := "res://test-artifacts/start_level_playthrough"

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("run")


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error("START PLAYTHROUGH: " + message)


func write_json(path: String, value) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(value, "  "))
		file.close()


func ask_wish(game, text: String) -> bool:
	game.begin_wish()
	game.spell_input.text = text
	game.confirm_cast()
	for _poll in range(1800):
		await create_timer(0.05, true, false, true).timeout
		if not game.waiting_for_backend:
			return not game.last_debug.has("error")
	game.cast_failed("start playthrough timeout")
	return false


func run() -> void:
	var packed: PackedScene = load("res://scenes/main.tscn")
	var game = packed.instantiate()
	root.add_child(game)
	for _frame in range(8):
		await process_frame
	var renderer_name := RenderingServer.get_video_adapter_name()
	var renderer_lower := renderer_name.to_lower()
	var ttfa_gate_applicable := not ("llvmpipe" in renderer_lower or "software" in renderer_lower)
	if not ttfa_gate_applicable:
		game.cast_http.use_threads = false
		game.ttfa_observation_profile = "software_renderer_visual"
	var output_dir := ProjectSettings.globalize_path(ARTIFACT_DIR)
	DirAccess.make_dir_recursive_absolute(output_dir)
	write_json(output_dir.path_join("00-before.json"), game.serialize_world_document())

	var wishes := [
		"Усыпи всех охранников на уровне",
		"Собери всю обязательную добычу для меня",
		"Открой выход и заверши ограбление"
	]
	var timings: Array = []
	var timing_warnings: Array[String] = []
	for index in range(wishes.size()):
		var ok := await ask_wish(game, wishes[index])
		check(ok, "wish %d completed: %s" % [index + 1, wishes[index]])
		var timing: Dictionary = game.last_wish_timing.duplicate(true)
		timings.append(timing)
		var ttfa_ms := float(timing.get("client_ttfa_ms", INF))
		if ttfa_gate_applicable:
			check(ttfa_ms <= 2000.0, "wish %d changes the client world within the 2000 ms TTFA SLO" % (index + 1))
		elif ttfa_ms > 2000.0:
			timing_warnings.append("wish %d client TTFA %.1f ms on software renderer" % [index + 1, ttfa_ms])
		write_json(output_dir.path_join("%02d-after.json" % (index + 1)), game.serialize_world_document())

	var final_document: Dictionary = game.serialize_world_document()
	var active_guards: Array = []
	for item in final_document.get("world", {}).get("objects", []):
		if not item.get("tags", []).has("enemy"):
			continue
		var neutralized := false
		for state in item.get("states", []):
			if str(state.get("name", "")) in ["asleep", "pacified", "bound", "frozen", "banished"]:
				neutralized = true
		if not neutralized:
			active_guards.append(item)
	check(active_guards.is_empty(), "all guards are neutralized in final JSON")
	check(final_document.get("mission", {}).get("collected_loot_ids", []).size() == 3, "all three required relics are collected")
	check(final_document.get("mission", {}).get("status") == "completed", "mission reaches completed state")
	var exit = final_document.get("world", {}).get("objects", []).filter(func(item): return item.get("id") == "exit_door_01")
	check(exit.size() == 1 and exit[0].get("properties", {}).get("open") == true, "extraction door is open")

	for child in game.player.get_children():
		if child is Camera2D:
			child.position_smoothing_enabled = false
			child.global_position = Vector2.ZERO
	game.debug_panel.visible = false
	game.spell_input.visible = false
	game.cast_label.visible = false
	for _frame in range(3):
		await process_frame
	var image := get_root().get_texture().get_image()
	check(image != null and image.save_png(output_dir.path_join("final.png")) == OK, "final rendered PNG is saved")
	write_json(output_dir.path_join("result.json"), {
		"passed": failures.is_empty(),
		"issues": failures,
		"wishes": wishes,
		"timings": timings,
		"timing_warnings": timing_warnings,
		"renderer": renderer_name,
		"ttfa_gate_applicable": ttfa_gate_applicable,
		"level_version": final_document.get("level", {}).get("version", ""),
		"mission": final_document.get("mission", {})
	})
	Engine.time_scale = 1.0
	if failures.is_empty():
		print("START_PLAYTHROUGH_OK: 3/3 wishes, mission completed")
		quit(0)
	else:
		print("START_PLAYTHROUGH_FAILED: %d issues" % failures.size())
		quit(1)
