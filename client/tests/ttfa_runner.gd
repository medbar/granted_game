extends SceneTree

const ARTIFACT_DIR := "res://test-artifacts/ttfa"
const TTFA_SLO_MS := 2000.0

var failures: Array[String] = []
var results: Array = []


func _initialize() -> void:
	call_deferred("run")


func write_json(path: String, value) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(value, "  "))
		file.close()


func object_property(object: Object, property_name: String):
	for descriptor in object.get_property_list():
		if str(descriptor.get("name", "")) == property_name:
			return object.get(property_name)
	return null


func ask_wish(game, text: String) -> bool:
	game.begin_wish()
	game.spell_input.text = text
	game.confirm_cast()
	for _poll in range(800):
		await create_timer(0.025, true, false, true).timeout
		if not game.waiting_for_backend:
			return not game.last_debug.has("error")
	game.cast_failed("TTFA eval timeout")
	return false


func check_timing(case_id: String, game, world_changed: bool) -> void:
	var raw_timing = object_property(game, "last_wish_timing")
	var timing: Dictionary = raw_timing if typeof(raw_timing) == TYPE_DICTIONARY else {}
	var issues: Array[String] = []
	if not world_changed:
		issues.append("authoritative world did not change as requested")
	for field in ["submit_to_initial_response_ms", "submit_to_action_ready_ms", "action_ready_to_mutation_ms", "client_ttfa_ms"]:
		if not timing.has(field):
			issues.append("missing timing field: " + field)
	if timing.has("client_ttfa_ms") and float(timing.get("client_ttfa_ms", INF)) > TTFA_SLO_MS:
		issues.append("client TTFA %.1f ms exceeds %.1f ms" % [float(timing.get("client_ttfa_ms")), TTFA_SLO_MS])
	results.append({
		"case_id": case_id,
		"passed": issues.is_empty(),
		"world_changed": world_changed,
		"timing": timing,
		"issues": issues,
	})
	for issue in issues:
		failures.append(case_id + ": " + issue)
		push_error("TTFA EVAL: " + failures[-1])


func run() -> void:
	var packed: PackedScene = load("res://scenes/main.tscn")
	var game = packed.instantiate()
	root.add_child(game)
	game.ttfa_observation_profile = "latency_eval"
	for _frame in range(12):
		await process_frame

	var props_before: int = game.props.size()
	var create_ok: bool = await ask_wish(game, "Создай стену перед игроком")
	check_timing("create_wall", game, create_ok and game.props.size() == props_before + 1 and game.props[-1].prop_kind == "wall")

	var equip_ok: bool = await ask_wish(game, "Одень меня в платье")
	check_timing("equip_dress", game, equip_ok and game.player.outfit == "dress")

	var light_before: float = game.world_light_level
	var light_ok: bool = await ask_wish(game, "Сделай мир темнее")
	check_timing("darken_world", game, light_ok and game.world_light_level < light_before)

	var output_dir := ProjectSettings.globalize_path(ARTIFACT_DIR)
	DirAccess.make_dir_recursive_absolute(output_dir)
	write_json(output_dir.path_join("summary.json"), {
		"slo_ms": TTFA_SLO_MS,
		"total": results.size(),
		"passed": results.filter(func(item): return item.get("passed", false)).size(),
		"failed": failures.size(),
		"cases": results,
	})
	Engine.time_scale = 1.0
	if failures.is_empty():
		print("TTFA_EVAL_OK: %d/%d client mutations <= %.0f ms" % [results.size(), results.size(), TTFA_SLO_MS])
		quit(0)
	else:
		print("TTFA_EVAL_FAILED: %d issues" % failures.size())
		quit(1)
