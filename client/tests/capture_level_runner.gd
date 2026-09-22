extends SceneTree


func _initialize() -> void:
	call_deferred("run")


func argument(name: String, fallback: String) -> String:
	var prefix := "--" + name + "="
	for item in OS.get_cmdline_user_args():
		if item.begins_with(prefix):
			return item.substr(prefix.length())
	return fallback


func run() -> void:
	var packed: PackedScene = load("res://scenes/main.tscn")
	if packed == null:
		push_error("CAPTURE: main scene did not load")
		quit(1)
		return
	var game = packed.instantiate()
	root.add_child(game)
	for _frame in range(8):
		await process_frame
	for child in game.player.get_children():
		if child is Camera2D:
			child.position_smoothing_enabled = false
			child.global_position = Vector2.ZERO
			child.zoom = Vector2(1.0, 1.0)
	game.debug_panel.visible = false
	game.spell_input.visible = false
	game.cast_label.visible = false
	for _frame in range(4):
		await process_frame

	var artifact_dir := argument("artifact-dir", "res://test-artifacts/monaco_start")
	var absolute_dir := ProjectSettings.globalize_path(artifact_dir)
	DirAccess.make_dir_recursive_absolute(absolute_dir)
	var json_path := absolute_dir.path_join("world.json")
	var png_path := absolute_dir.path_join("level.png")
	var json_file := FileAccess.open(json_path, FileAccess.WRITE)
	if json_file == null:
		push_error("CAPTURE: cannot write " + json_path)
		quit(1)
		return
	json_file.store_string(JSON.stringify(game.serialize_world_document(), "  "))
	json_file.close()
	var image := get_root().get_texture().get_image()
	var save_error := image.save_png(png_path)
	if save_error != OK:
		push_error("CAPTURE: cannot save PNG (%d)" % save_error)
		quit(1)
		return
	print("LEVEL_CAPTURE_OK json=%s png=%s" % [json_path, png_path])
	quit(0)
