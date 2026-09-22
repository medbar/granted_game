extends SceneTree

const CASES_PATH := "res://../server/evals/agent_evolution_cases.json"
const ARTIFACT_ROOT := "res://test-artifacts/environment"
const TTFA_SLO_MS := 2000.0

var failures: Array[String] = []
var results: Array = []
var renderer_name := ""
var ttfa_gate_applicable := true
var timing_violation_count := 0


func _initialize() -> void:
	call_deferred("run")


func read_json(path: String):
	var file := FileAccess.open(ProjectSettings.globalize_path(path), FileAccess.READ)
	if file == null:
		return null
	return JSON.parse_string(file.get_as_text())


func write_json(path: String, value) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify(value, "  "))
	file.close()
	return true


func object_property(object: Object, property_name: String):
	for descriptor in object.get_property_list():
		if str(descriptor.get("name", "")) == property_name:
			return object.get(property_name)
	return null


func ask_wish(game, text: String) -> bool:
	game.begin_wish()
	game.spell_input.text = text
	game.confirm_cast()
	for _poll in range(1600):
		await create_timer(0.05, true, false, true).timeout
		if not game.waiting_for_backend:
			return not game.last_debug.has("error")
	game.cast_failed("environment eval timeout")
	return false


func objects(document: Dictionary) -> Array:
	return document.get("world", {}).get("objects", [])


func resolve_target(document: Dictionary, requested: String) -> Dictionary:
	for item in objects(document):
		if str(item.get("id", "")) == requested:
			return item
	var wanted_tag := ""
	if requested.begins_with("enemy_"):
		wanted_tag = "enemy"
	elif requested.begins_with("npc_"):
		wanted_tag = "npc"
	elif requested.begins_with("rock_"):
		wanted_tag = "rock"
	elif requested.begins_with("crate_"):
		wanted_tag = "crate"
	if not wanted_tag.is_empty():
		for item in objects(document):
			if item.get("tags", []).has(wanted_tag) and not bool(item.get("properties", {}).get("created", false)):
				return item
	return {}


func resolve_same_target(before: Dictionary, after: Dictionary, requested: String) -> Dictionary:
	var before_item := resolve_target(before, requested)
	if not before_item.is_empty():
		var stable_id := str(before_item.get("id", ""))
		for item in objects(after):
			if str(item.get("id", "")) == stable_id:
				return item
	return resolve_target(after, requested)


func state_names(item: Dictionary) -> Array[String]:
	var names: Array[String] = []
	for state in item.get("states", []):
		if typeof(state) == TYPE_DICTIONARY:
			names.append(str(state.get("name", "")))
		else:
			names.append(str(state))
	return names


func prototype_count(document: Dictionary, prototype: String) -> int:
	var count := 0
	for item in objects(document):
		var properties: Dictionary = item.get("properties", {})
		if str(properties.get("prototype", "")) == prototype or item.get("tags", []).has(prototype):
			if not bool(properties.get("removed", false)):
				count += 1
	return count


func evaluate_case(before: Dictionary, after: Dictionary, expected: Dictionary) -> Array[String]:
	var issues: Array[String] = []
	for requirement in expected.get("objects", []):
		var prototype := str(requirement.get("prototype", ""))
		var delta := prototype_count(after, prototype) - prototype_count(before, prototype)
		var wanted := int(requirement.get("count", 1))
		if delta < wanted:
			issues.append("created %s: expected %d, observed %d" % [prototype, wanted, delta])
	for requirement in expected.get("states", []):
		var item := resolve_same_target(before, after, str(requirement.get("target", "")))
		var state := str(requirement.get("name", ""))
		if item.is_empty() or not state_names(item).has(state):
			issues.append("state %s missing on %s" % [state, requirement.get("target", "")])
	for requirement in expected.get("properties", []):
		var item := resolve_same_target(before, after, str(requirement.get("target", "")))
		var name := str(requirement.get("name", ""))
		var actual = item.get("properties", {}).get(name) if not item.is_empty() else null
		if actual != requirement.get("value"):
			issues.append("property %s.%s expected %s, observed %s" % [requirement.get("target", ""), name, str(requirement.get("value")), str(actual)])
	for requirement in expected.get("wetness", []):
		var item := resolve_same_target(before, after, str(requirement.get("target", "")))
		var actual := float(item.get("material", {}).get("wetness", 0.0)) if not item.is_empty() else 0.0
		if actual < float(requirement.get("minimum", 0.0)):
			issues.append("wetness on %s expected >= %.2f, observed %.2f" % [requirement.get("target", ""), float(requirement.get("minimum", 0.0)), actual])
	for requirement in expected.get("aggro", []):
		var item := resolve_same_target(before, after, str(requirement.get("actor", "")))
		var actual := str(item.get("properties", {}).get("aggro_target", "")) if not item.is_empty() else ""
		if actual != str(requirement.get("target", "")) and not state_names(item).has("aggressive"):
			issues.append("aggro target missing on %s" % requirement.get("actor", ""))
	for requirement in expected.get("inventory", []):
		var owner := resolve_same_target(before, after, str(requirement.get("owner", "")))
		if not owner.get("properties", {}).get("inventory", []).has(requirement.get("prototype")):
			issues.append("inventory item %s missing" % requirement.get("prototype", ""))
	for target_id in expected.get("destroyed", []):
		var item := resolve_same_target(before, after, str(target_id))
		if not item.is_empty() and not bool(item.get("properties", {}).get("removed", false)) and float(item.get("health", 1.0)) > 0.0:
			issues.append("target %s is still active" % target_id)
	return issues


func prepare_full_level_frame(game) -> void:
	for child in game.player.get_children():
		if child is Camera2D:
			child.position_smoothing_enabled = false
			child.global_position = Vector2.ZERO
	game.debug_panel.visible = false
	game.spell_input.visible = false
	game.cast_label.visible = false


func run() -> void:
	var suite = read_json(CASES_PATH)
	if typeof(suite) != TYPE_DICTIONARY:
		push_error("ENVIRONMENT EVAL: cannot read frozen cases")
		quit(1)
		return
	var packed: PackedScene = load("res://scenes/main.tscn")
	renderer_name = RenderingServer.get_video_adapter_name()
	var renderer_lower := renderer_name.to_lower()
	ttfa_gate_applicable = not ("llvmpipe" in renderer_lower or "software" in renderer_lower)
	var root_dir := ProjectSettings.globalize_path(ARTIFACT_ROOT)
	DirAccess.make_dir_recursive_absolute(root_dir)
	for case in suite.get("cases", []):
		Engine.time_scale = 1.0
		var game = packed.instantiate()
		root.add_child(game)
		for _frame in range(8):
			await process_frame
		if not ttfa_gate_applicable:
			# Thread scheduling competes with CPU rendering under llvmpipe. The
			# dedicated headless TTFA runner is the hard latency gate for this host.
			game.cast_http.use_threads = false
			game.ttfa_observation_profile = "software_renderer_visual"
		var before: Dictionary = game.serialize_world_document()
		var request_ok: bool = await ask_wish(game, str(case.get("wish", "")))
		for _frame in range(3):
			await process_frame
		var after: Dictionary = game.serialize_world_document()
		var issues := evaluate_case(before, after, case.get("expected", {}))
		if not request_ok:
			issues.append("wish request did not complete successfully")
		var raw_timing = object_property(game, "last_wish_timing")
		var timing: Dictionary = raw_timing if typeof(raw_timing) == TYPE_DICTIONARY else {}
		var timing_warnings: Array[String] = []
		for field in ["submit_to_initial_response_ms", "submit_to_action_ready_ms", "action_ready_to_mutation_ms", "client_ttfa_ms"]:
			if not timing.has(field):
				issues.append("missing timing field: " + field)
		if timing.has("client_ttfa_ms") and float(timing.get("client_ttfa_ms", INF)) > TTFA_SLO_MS:
			var violation := "client TTFA %.1f ms exceeds %.1f ms" % [float(timing.get("client_ttfa_ms")), TTFA_SLO_MS]
			timing_violation_count += 1
			if ttfa_gate_applicable:
				issues.append(violation)
			else:
				timing_warnings.append(violation + " (software renderer; raw value retained)")
		var case_id := str(case.get("id", "unknown"))
		var case_dir := root_dir.path_join(case_id)
		DirAccess.make_dir_recursive_absolute(case_dir)
		write_json(case_dir.path_join("before.json"), before)
		write_json(case_dir.path_join("after.json"), after)
		var result := {
			"case_id": case_id,
			"wish": case.get("wish", ""),
			"passed": issues.is_empty(),
			"issues": issues,
			"level_version": after.get("level", {}).get("version", ""),
			"timing": timing,
			"timing_warnings": timing_warnings,
			"debug": game.last_debug
		}
		write_json(case_dir.path_join("result.json"), result)
		prepare_full_level_frame(game)
		await process_frame
		var image := get_root().get_texture().get_image()
		if image == null or image.save_png(case_dir.path_join("after.png")) != OK:
			issues.append("PNG capture failed")
			result["passed"] = false
			result["issues"] = issues
			write_json(case_dir.path_join("result.json"), result)
		results.append(result)
		if not issues.is_empty():
			failures.append(case_id + ": " + "; ".join(issues))
			push_error("ENVIRONMENT EVAL: " + failures[-1])
		else:
			print("ENVIRONMENT_CASE_OK: " + case_id)
		game.queue_free()
		for _cleanup in range(3):
			await process_frame
	var summary := {
		"suite_version": suite.get("version", ""),
		"level_version": "monaco-start-v1",
		"total": results.size(),
		"passed": results.filter(func(item): return item.get("passed", false)).size(),
		"failed": failures.size(),
		"renderer": renderer_name,
		"ttfa_gate_applicable": ttfa_gate_applicable,
		"timing_violation_count": timing_violation_count,
		"cases": results
	}
	write_json(root_dir.path_join("summary.json"), summary)
	Engine.time_scale = 1.0
	if failures.is_empty():
		print("ENVIRONMENT_EVAL_OK: %d/%d" % [results.size(), results.size()])
		quit(0)
	else:
		print("ENVIRONMENT_EVAL_FAILED: %d/%d" % [results.size() - failures.size(), results.size()])
		quit(1)
