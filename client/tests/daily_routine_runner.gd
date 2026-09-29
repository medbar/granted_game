extends SceneTree

var failures: Array[String] = []
var commands: Array[String] = []
var game
var evidence: Array = []
const OUT := "res://test-artifacts/daily-routine"

func _initialize() -> void:
	Engine.max_fps = 60
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok:
		failures.append(message)
		push_error("DAILY ROUTINE: " + message)

func wait_idle() -> void:
	for _i in range(900):
		await create_timer(.05).timeout
		if not game.command_pending and not game.is_routine_busy():
			return
	check(false, "bounded wait for routine command")

func key(code: int, pressed: bool) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = code
	event.pressed = pressed
	Input.parse_input_event(event)

func approach(target: Vector2) -> void:
	for _i in range(200):
		var point := Vector2(game.state.player.x, game.state.player.y)
		if point.distance_to(target) < 21:
			break
		key(KEY_D, point.x < target.x - 9)
		key(KEY_A, point.x > target.x + 9)
		key(KEY_S, point.y < target.y - 9)
		key(KEY_W, point.y > target.y + 9)
		await create_timer(.08).timeout
	for code in [KEY_D, KEY_A, KEY_S, KEY_W]:
		key(code, false)
	await create_timer(.2).timeout
	check(Vector2(game.state.player.x, game.state.player.y).distance_to(target) < 38,
		"actual player reaches interaction point")

func capture(name: String) -> void:
	DirAccess.make_dir_recursive_absolute(OUT)
	var snapshot: Dictionary = game.routine.describe()
	evidence.append({"frame": name, "view": snapshot, "phase": game.state.phase})
	var file := FileAccess.open(OUT + "/" + name + ".json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"view": snapshot, "state": game.state}, "\t"))
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png(OUT + "/" + name + ".png")

func finish() -> void:
	DirAccess.make_dir_recursive_absolute(OUT)
	var file := FileAccess.open(OUT + "/result.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed": failures.is_empty(), "issues": failures,
		"commands": commands, "evidence": evidence}, "\t"))
	if failures.is_empty():
		print("DAILY_ROUTINE_OK")
	quit(0 if failures.is_empty() else 1)

func run() -> void:
	game = load("res://scenes/bureaucracy.tscn").instantiate()
	game.fresh_session = true
	root.add_child(game)
	if game.get("routine") == null:
		check(false, "separate routine presentation must exist")
		finish()
		return
	game.command_dispatched.connect(func(action): commands.append(action))
	for _i in range(600):
		await create_timer(.05).timeout
		if not game.state.is_empty():
			break
	if game.state.is_empty():
		check(false, "real backend creates a session")
		finish()
		return
	check(game.state.phase == "apartment", "starts in apartment")
	check(game.routine.describe().location == "apartment", "isolated apartment")
	check(not game.routine.describe().entities.has("police_1"), "no city police in apartment")
	check(game.actions.get_child_count() == 0, "no global routine command bar")
	await capture("01-apartment")
	game.request_routine_action("commute")
	check(commands.is_empty(), "cannot use exit from across the room")
	var exit_point: Vector2 = game.routine.exit_point()
	await approach(exit_point)
	key(KEY_E, true)
	await process_frame
	key(KEY_E, false)
	check(game.routine.describe().location == "metro", "exit opens metro presentation")
	var departure := Time.get_ticks_msec()
	game.request_routine_action("commute")
	await create_timer(.75).timeout
	await capture("02-metro")
	await wait_idle()
	check(Time.get_ticks_msec() - departure >= 2700, "metro is visible for minimum duration")
	check(commands.count("commute") == 1, "duplicate input does not send another trip")
	check(game.state.phase == "office", "server confirms work location")
	check(game.routine.describe().location == "office", "separate work interior")
	check(game.routine.describe().buttons == ["ОБРАБОТАТЬ"], "exactly one office button")
	check(game.actions.get_child_count() == 0, "no home/journal/new-game buttons on work screen")
	await capture("03-office")
	var processed: int = game.state.processed
	game.routine.action_button.pressed.emit()
	await wait_idle()
	check(game.state.processed == processed + 1, "first click really processes one application")
	game.routine.action_button.pressed.emit()
	await wait_idle()
	check(game.state.phase == "apartment" and game.state.processed == processed + 2,
		"two work clicks return home automatically")
	check(game.state.contract_ready and not game.state.contract_signed, "contract remains voluntary")
	await capture("04-home")
	# Force a connection error on the actual command path, then recover.
	await approach(game.routine.exit_point())
	var original_api: String = game.api
	game.api = "http://127.0.0.1:1"
	game.request_routine_action("commute")
	await wait_idle()
	check(game.state.phase == "apartment" and game.routine.describe().location == "apartment",
		"failed travel never displays an unconfirmed destination")
	await create_timer(.6).timeout
	check(game.last_message.contains("не подтверждена") or game.last_message.contains("Не удалось"),
		"connection failure remains visibly actionable after subsequent ticks")
	await capture("05-failed-trip")
	game.api = original_api
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	# parse_input_event uses window pixels; the game uses a stretched 1280x720 canvas.
	click.position = root.get_final_transform() * game.routine.project(game.routine.exit_point())
	click.global_position = click.position
	click.pressed = true
	Input.parse_input_event(click)
	await process_frame
	click.pressed = false
	Input.parse_input_event(click)
	await wait_idle()
	check(game.state.phase == "office", "trip can be retried after failure")
	await capture("06-recovered")
	finish()
