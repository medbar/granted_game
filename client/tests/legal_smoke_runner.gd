extends SceneTree

func _initialize() -> void:
	var issues: Array[String] = []
	for source in ["res://scripts/routine_presentation.gd", "res://scripts/bureaucracy.gd"]:
		var script: Script = load(source)
		if script == null or script.reload() != OK or not script.can_instantiate():
			issues.append("invalid script: " + source)
	var level = JSON.parse_string(FileAccess.get_file_as_string("res://levels/bureaucracy_start.json"))
	var scene = load("res://scenes/bureaucracy.tscn")
	if scene == null:
		issues.append("campaign scene missing")
	else:
		var instance = scene.instantiate()
		if not instance.has_method("is_routine_busy"):
			issues.append("campaign script or its dependencies failed to compile")
		instance.free()
	if str(ProjectSettings.get_setting("application/run/main_scene")) != "res://scenes/bureaucracy.tscn":
		issues.append("campaign is not the default")
	if not level is Dictionary:
		issues.append("legal district JSON invalid")
	else:
		for id in ["checkpoint", "side_gate"]:
			var door: Dictionary = level.objects.get(id, {})
			if door.get("kind") != "door" or door.get("open", true):
				issues.append(id + " must start as a closed door")
		for id in ["car", "police_1", "police_2", "rock", "npc_1"]:
			if not level.objects.has(id):
				issues.append("missing legal target: " + id)
	if issues.is_empty():
		print("LEGAL_SMOKE_OK")
	else:
		for issue in issues:
			push_error("LEGAL SMOKE: " + issue)
	quit(0 if issues.is_empty() else 1)
