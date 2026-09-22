extends SceneTree

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("run")


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error("LEVEL CONTRACT: " + message)


func ids(items: Array) -> Array[String]:
	var result: Array[String] = []
	for item in items:
		result.append(str(item.get("id", "")))
	result.sort()
	return result


func run() -> void:
	var packed: PackedScene = load("res://scenes/main.tscn")
	check(packed != null, "main scene loads")
	if packed == null:
		finish()
		return
	var game = packed.instantiate()
	root.add_child(game)
	for _frame in range(5):
		await process_frame

	var level: Dictionary = game.level_definition
	check(level.get("version") == "monaco-start-v1", "the frozen level version is loaded")
	check(level.get("rooms", []).size() >= 8, "the level has at least eight labelled rooms")
	check(level.get("walls", []).size() >= 24, "the level has substantial blueprint geometry")
	check(level.get("doors", []).size() >= 6, "the level has real stateful doors")
	check(game.ROOMS.size() == level.get("rooms", []).size(), "rendered rooms come from JSON")
	check(game.WALLS.size() == level.get("walls", []).size(), "collision walls come from JSON")
	var main_source_file := FileAccess.open("res://scripts/main.gd", FileAccess.READ)
	check(main_source_file != null, "main.gd is readable for identity contract audit")
	if main_source_file != null:
		var main_source := main_source_file.get_as_text()
		check(not main_source.contains('var wall_id := "wall_%02d"'), "wall ids are never derived from array order")
		check(main_source.contains('wall_data.get("id"'), "wall ids are read from canonical JSON")
	check(ids(level.get("doors", [])) == ids(game.collect_world_snapshot(true).filter(func(item): return item.get("kind") == "door")), "all JSON door ids exist in the runtime snapshot")
	check(ids(level.get("walls", [])) == ids(game.collect_world_snapshot(true).filter(func(item): return "wall" in item.get("tags", []))), "all exact JSON wall ids exist in the runtime snapshot")

	var document: Dictionary = game.serialize_world_document()
	var snapshot_ids := ids(document.get("world", {}).get("objects", []))
	for entity in level.get("entities", []):
		check(snapshot_ids.has(str(entity.get("id"))), "serialized world contains entity " + str(entity.get("id")))
	check(document.get("level", {}).get("version") == level.get("version"), "serialized level preserves its version")
	check(document.get("mission", {}).get("required_loot_ids", []).size() == 3, "mission requirements survive serialization")

	game.apply_world_action({"type": "INTERACT", "target_id": "loot_01", "effect": {"interaction": "collect"}})
	game.apply_world_action({"type": "INTERACT", "target_id": "exit_door_01", "effect": {"interaction": "open"}})
	var after: Dictionary = game.serialize_world_document()
	var loot = after.get("world", {}).get("objects", []).filter(func(item): return item.get("id") == "loot_01")
	var exits = after.get("world", {}).get("objects", []).filter(func(item): return item.get("id") == "exit_door_01")
	check(loot.size() == 1 and loot[0].get("properties", {}).get("collected") == true, "agent collection mutates authoritative JSON")
	check(exits.size() == 1 and exits[0].get("properties", {}).get("open") == true, "agent interaction opens a rendered door")
	finish()


func finish() -> void:
	Engine.time_scale = 1.0
	if failures.is_empty():
		print("LEVEL_CONTRACT_OK")
		quit(0)
	else:
		print("LEVEL_CONTRACT_FAILED: %d" % failures.size())
		for failure in failures:
			print(" - " + failure)
		quit(1)
