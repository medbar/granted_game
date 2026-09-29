extends SceneTree

var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, message: String) -> void:
	if not value:
		failures.append(message)
		push_error("BUREAUCRACY: " + message)

func run() -> void:
	var scene = load("res://scenes/bureaucracy.tscn")
	check(scene != null, "new scene exists")
	if scene == null:
		quit(1)
		return
	var game = scene.instantiate()
	game.fresh_session = true
	root.add_child(game)
	for _i in range(600):
		await create_timer(0.05).timeout
		if not game.state.is_empty():
			break
	check(not game.state.is_empty(), "server creates actual campaign")
	if game.state.is_empty():
		quit(1)
		return
	check(not game.state.contract_signed, "contract is voluntary")
	for action in ["eat", "sleep", "commute", "work", "work", "home", "sign", "leave"]:
		game.send_command(action)
		for _i in range(200):
			await create_timer(0.05).timeout
			if not game.command_pending and not game.is_routine_busy():
				break
	check(game.state.contract_signed and game.state.phase == "city", "prologue reaches city")
	game.save_artifact("before.json")
	await capture("before.png")
	var wish_ok: bool = await game.test_wish("Пусть эта дверь считается аварийным выходом")
	check(wish_ok, "real lawyer completes a wish")
	check(game.state.objects.checkpoint.open, "door physically opens")
	check(game.state.precedents.size() > 0, "precedent is visible and stored")
	check(not game.last_message.is_empty(), "lawyer speech is visible")
	game.save_artifact("after.json")
	await capture("after.png")
	var before_move: float = game.state.player.x
	var press := InputEventKey.new()
	press.physical_keycode = KEY_D
	press.pressed = true
	Input.parse_input_event(press)
	check(await game.test_wish("Пусть полиция забудет моё описание"), "identity petition works in game")
	check(game.state.player.x > before_move, "movement continues during wish")
	for _i in range(500):
		await create_timer(.05).timeout
		if game.state.status == "escaped":
			break
	press.pressed = false
	Input.parse_input_event(press)
	check(game.state.status == "escaped", "player actually crosses the checkpoint")
	game.save_artifact("escaped.json")
	await capture("final.png")
	var before_refusal: Dictionary = game.state.objects.duplicate(true)
	var refused: bool = not await game.test_wish("Вернись на сто лет в прошлое и отмени само существование договора. Не меняй свет или скорость времени.")
	check(refused and game.last_wish_result.get("status") == "failed", "unsupported wish honestly fails")
	check(game.last_wish_result.get("attempts") == 3, "lawyer exhausts bounded retries")
	check(game.state.objects == before_refusal, "refusal does not substitute an unrelated effect")
	check(game.last_message.contains("не удалось"), "refusal is visible to the player")
	game.save_artifact("refused.json")
	await capture("refused.png")
	var file = FileAccess.open("res://test-artifacts/bureaucracy/result.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"case_id": "bureaucracy_playthrough", "wish": "Пусть эта дверь считается аварийным выходом", "passed": failures.is_empty(), "issues": failures}, "\t"))
	if failures.is_empty():
		print("BUREAUCRACY_OK")
	quit(0 if failures.is_empty() else 1)


func capture(filename: String) -> void:
	if DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		get_root().get_texture().get_image().save_png("res://test-artifacts/bureaucracy/" + filename)
