extends Node2D
## Server-authoritative first district. Wish and movement requests use independent channels.
signal command_dispatched(action: String)

const RoutinePresentation = preload("res://scripts/routine_presentation.gd")
const METRO_SECONDS := 2.8
var routine
var travel_to := ""
var travel_elapsed := 0.0
var arrival_state: Dictionary = {}
var work_feedback := 0.0
var ui_work_requested := false
var return_after_work := false
var notice_remaining := 0.0

var state: Dictionary = {}
var last_message := "Подключение к бюрократии реальности…"
var last_wish_result: Dictionary = {}
var command_pending := false
var wish_pending := false
var tick_pending := false
var fresh_session := false
var api := "http://127.0.0.1:8000"
var sid := ""
var tick_elapsed := 0.0
var visual_time := 0.0
var command_http: HTTPRequest
var tick_http: HTTPRequest
var wish_http: HTTPRequest
var speech: Label
var headline: Label
var status_label: Label
var actions: HBoxContainer
var wish_input: LineEdit
var submit_button: Button
var journal: PanelContainer
var journal_text: RichTextLabel
var ui_signature := ""
var font: Font
var positions: Dictionary = {}
var wish_started_ms := 0
var last_wish_ms := 0
const PAPER := Color("#e1d7b8")
const GOLD := Color("#ddb56c")
const MINT := Color("#81c8ab")


func _ready() -> void:
	font = ThemeDB.fallback_font
	routine = RoutinePresentation.new()
	routine.action_selected.connect(request_routine_action)
	add_child(routine)
	var endpoint := OS.get_environment("BUREAU_API_URL")
	if not endpoint.is_empty():
		api = endpoint.trim_suffix("/")
	command_http = make_http(10.0)
	tick_http = make_http(5.0)
	wish_http = make_http(85.0)
	command_http.request_completed.connect(on_command)
	tick_http.request_completed.connect(on_tick)
	wish_http.request_completed.connect(on_wish)
	build_ui()
	if not fresh_session and FileAccess.file_exists("user://bureau_session.txt"):
		sid = FileAccess.get_file_as_string("user://bureau_session.txt").strip_edges()
	if sid.is_empty():
		new_session()
	else:
		command_pending = true
		var result := command_http.request(api + "/bureau/sessions/" + sid)
		if result != OK:
			command_pending = false
			new_session()


func make_http(timeout_seconds: float) -> HTTPRequest:
	var http := HTTPRequest.new()
	# HTTPRequest polls asynchronously without worker threads. On Windows with
	# llvmpipe, threaded requests can starve and leave the visible world stale.
	http.use_threads = false
	http.timeout = timeout_seconds
	add_child(http)
	return http


func build_ui() -> void:
	var canvas := CanvasLayer.new()
	add_child(canvas)
	headline = Label.new()
	headline.position = Vector2(26, 10)
	headline.add_theme_font_size_override("font_size", 25)
	headline.add_theme_color_override("font_color", PAPER)
	headline.text = "БЮРОКРАТИЯ РЕАЛЬНОСТИ"
	canvas.add_child(headline)
	status_label = Label.new()
	status_label.position = Vector2(660, 12)
	status_label.size = Vector2(595, 40)
	status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	status_label.add_theme_font_size_override("font_size", 14)
	status_label.add_theme_color_override("font_color", GOLD)
	canvas.add_child(status_label)
	var footer := PanelContainer.new()
	footer.position = Vector2(20, 610)
	footer.size = Vector2(1240, 98)
	var style := StyleBoxFlat.new()
	style.bg_color = Color("#172222")
	style.border_color = Color("#88714c")
	style.set_border_width_all(1)
	style.set_content_margin_all(12)
	footer.add_theme_stylebox_override("panel", style)
	canvas.add_child(footer)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	footer.add_child(box)
	speech = Label.new()
	speech.custom_minimum_size = Vector2(1180, 34)
	speech.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	speech.add_theme_font_size_override("font_size", 14)
	speech.add_theme_color_override("font_color", PAPER)
	box.add_child(speech)
	actions = HBoxContainer.new()
	actions.add_theme_constant_override("separation", 9)
	box.add_child(actions)
	journal = PanelContainer.new()
	journal.position = Vector2(780, 65)
	journal.size = Vector2(465, 490)
	journal.add_theme_stylebox_override("panel", style)
	journal.visible = false
	canvas.add_child(journal)
	journal_text = RichTextLabel.new()
	journal_text.custom_minimum_size = Vector2(435, 450)
	journal_text.add_theme_font_size_override("normal_font_size", 15)
	journal_text.add_theme_color_override("default_color", PAPER)
	journal.add_child(journal_text)


func button(title: String, callback: Callable) -> Button:
	var control := Button.new()
	control.text = title
	control.add_theme_font_size_override("font_size", 14)
	control.pressed.connect(func(): control.release_focus(); callback.call())
	actions.add_child(control)
	return control


func refresh_ui() -> void:
	speech.text = last_message
	routine.update_view(state, positions, travel_to, travel_elapsed, visual_time,
		command_pending or is_routine_busy())
	if state.is_empty():
		return
	var p: Dictionary = state.player
	status_label.text = "ДЕНЬ %d   ·   ЖИЗНЬ %d   ·   ВНИМАНИЕ %d   ·   ДЕЛА %d" % [
		state.day, int(p.health), state.attention, state.case_count]
	if wish_pending:
		status_label.text += "\nАДВОКАТ ВЕДЁТ ДЕЛО  %.1f c" % ((Time.get_ticks_msec() - wish_started_ms) / 1000.0)
	if not travel_to.is_empty():
		headline.text = "МЕТРО"
		status_label.text = "ДЕНЬ %d  ·  ПРЕДПИСАННЫЙ МАРШРУТ" % state.day
	elif state.phase != "city":
		headline.text = "КВАРТИРА № 17" if state.phase == "apartment" else "РАБОТА"
		status_label.text = "ДЕНЬ %d" % state.day
	else:
		headline.text = "БЮРОКРАТИЯ РЕАЛЬНОСТИ"
	if state.phase != "city" or not travel_to.is_empty():
		journal.visible = false
	var signature := str([state.phase, state.contract_ready, state.contract_signed, state.status, travel_to])
	if signature == ui_signature:
		return
	ui_signature = signature
	for child in actions.get_children():
		actions.remove_child(child)
		child.queue_free()
	wish_input = null
	submit_button = null
	if state.phase == "city" and travel_to.is_empty():
		wish_input = LineEdit.new()
		wish_input.custom_minimum_size = Vector2(730, 31)
		wish_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		wish_input.placeholder_text = "Ваше желание адвокату…  [Пробел — ввод, Esc — движение]"
		wish_input.max_length = 300
		wish_input.text_submitted.connect(func(_text): submit_wish())
		actions.add_child(wish_input)
		submit_button = button("Заявить", submit_wish)
		button("Реестр [J]", toggle_journal)
		button("Новая сессия", new_session)


func toggle_journal() -> void:
	if state.is_empty() or state.phase != "city":
		return
	journal.visible = not journal.visible
	update_journal()


func update_journal() -> void:
	if state.is_empty():
		return
	var text := "РЕЕСТР ПРЕЦЕДЕНТОВ\n\n"
	text += "Контракт подписан.\nЖизнь после смерти — плата за представительство.\n\n" if state.contract_signed else "Контракт ещё не подписан.\n\n"
	for precedent in state.precedents:
		text += "%s  ·  %s\n%s\nПрименений: %d\n\n" % [precedent.id, precedent.title, precedent.rule, precedent.uses]
	if state.precedents.is_empty():
		text += "Дел пока нет. Решения изменяют правила квартала и сохраняются вместе с миром."
	journal_text.text = text


func accept_state(value: Dictionary) -> void:
	if value.is_empty() or not value.has("id"):
		return
	if not state.is_empty() and state.id == value.id and value.revision < state.revision:
		return
	if state.is_empty() or state.get("phase") != value.get("phase"):
		positions.clear()
	state = value
	sid = state.id
	if notice_remaining <= 0:
		last_message = str(state.message)
	update_journal()
	refresh_ui()
	queue_redraw()


func post(http: HTTPRequest, route: String, data: Dictionary) -> Error:
	return http.request(api + route, ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(data))


func new_session() -> void:
	if command_pending or wish_pending or is_routine_busy():
		return
	tick_http.cancel_request()
	tick_pending = false
	state = {}
	positions.clear()
	ui_signature = ""
	command_pending = true
	var error := post(command_http, "/bureau/sessions", {})
	if error != OK:
		command_pending = false
		last_message = "Не удалось подключиться к серверу."
		refresh_ui()


func is_routine_busy() -> bool:
	return not travel_to.is_empty() or work_feedback > 0


func request_routine_action(action: String) -> void:
	if state.is_empty() or command_pending or is_routine_busy():
		return
	if state.phase == "apartment":
		if routine.nearby_action() != action:
			last_message = "Сначала подойдите к предмету или выходу."
			notice_remaining = 2.0
			refresh_ui()
			return
	elif state.phase != "office" or action != "work":
		return
	ui_work_requested = action == "work"
	notice_remaining = 0.0
	send_command(action)


func send_command(action: String) -> void:
	if command_pending or sid.is_empty() or is_routine_busy():
		return
	if action in ["commute", "home"]:
		travel_to = "office" if action == "commute" else "apartment"
		travel_elapsed = 0.0
		arrival_state = {}
		last_message = "Поезд следует по предписанному маршруту."
		tick_http.cancel_request()
		tick_pending = false
		tick_elapsed = 0.0
	command_pending = true
	command_dispatched.emit(action)
	if post(command_http, "/bureau/sessions/" + sid + "/command", {"action": action}) != OK:
		command_pending = false
		travel_to = ""
		ui_work_requested = false
		last_message = "Не удалось передать действие."
		notice_remaining = 3.0
	refresh_ui()


func decode_response(body: PackedByteArray) -> Variant:
	var document := JSON.new()
	if body.is_empty() or document.parse(body.get_string_from_utf8()) != OK:
		return null
	return document.data


func on_command(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	command_pending = false
	var value = decode_response(body)
	if result == HTTPRequest.RESULT_SUCCESS and code >= 200 and code < 300 and value is Dictionary and value.has("id"):
		if not travel_to.is_empty():
			arrival_state = value
		else:
			accept_state(value)
		if ui_work_requested:
			work_feedback = .65
			return_after_work = int(value.get("processed", 0)) % 2 == 0
			ui_work_requested = false
		if not fresh_session:
			var file := FileAccess.open("user://bureau_session.txt", FileAccess.WRITE)
			if file:
				file.store_string(sid)
	elif code == 404 or (state.is_empty() and code == 409):
		travel_to = ""
		arrival_state = {}
		ui_work_requested = false
		sid = ""
		new_session()
	else:
		travel_to = ""
		arrival_state = {}
		ui_work_requested = false
		last_message = str(value.get("detail", "Не удалось подтвердить действие. Попробуйте ещё раз.")) if value is Dictionary else "Связь прервалась. Поездка не подтверждена — попробуйте ещё раз."
		notice_remaining = 3.0
		refresh_ui()


func on_tick(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	tick_pending = false
	if is_routine_busy():
		return
	if result == HTTPRequest.RESULT_SUCCESS and code == 200:
		var value = decode_response(body)
		if value is Dictionary:
			accept_state(value)
	else:
		if notice_remaining <= 0:
			last_message = "Связь с сервером потеряна. Повторяю подключение…"
		refresh_ui()


func submit_wish() -> void:
	if wish_input == null or wish_pending or state.is_empty():
		return
	var text := wish_input.text.strip_edges()
	if text.is_empty():
		return
	wish_input.release_focus()
	wish_input.text = ""
	begin_wish_request(text)


func begin_wish_request(text: String) -> void:
	wish_pending = true
	wish_started_ms = Time.get_ticks_msec()
	last_wish_result = {}
	last_message = "Адвокат: «Займитесь своим спасением. Основания найду я»."
	var request_id := "wish_" + str(Time.get_ticks_usec())
	var error := post(wish_http, "/bureau/sessions/" + sid + "/wish", {"text": text, "request_id": request_id})
	if error != OK:
		wish_pending = false
		last_message = "Не удалось подать заявление. Попробуйте ещё раз."
	refresh_ui()


func on_wish(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	wish_pending = false
	last_wish_ms = Time.get_ticks_msec() - wish_started_ms
	var value = JSON.parse_string(body.get_string_from_utf8())
	if result == HTTPRequest.RESULT_SUCCESS and code == 200 and value is Dictionary:
		last_wish_result = value
		last_message = str(value.get("message", "Нет решения."))
	else:
		last_wish_result = {"status": "failed"}
		last_message = str(value.get("detail", "Адвокат не получил решения. Попробуйте ещё раз.")) if value is Dictionary else "Время ожидания истекло. Решение не подтверждено."
	refresh_ui()


func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	if event.physical_keycode == KEY_ESCAPE:
		if wish_input != null:
			wish_input.release_focus()
		journal.visible = false
	elif event.physical_keycode == KEY_SPACE and wish_input != null:
		wish_input.grab_focus()
	elif event.physical_keycode == KEY_J:
		toggle_journal()
	elif event.physical_keycode == KEY_E and not state.is_empty():
		if state.phase == "office":
			request_routine_action("work")
		elif state.phase == "apartment":
			var nearby: String = routine.nearby_action()
			if not nearby.is_empty():
				request_routine_action(nearby)
		elif state.phase == "city":
			send_command("vehicle")


func _process(delta: float) -> void:
	visual_time += delta
	notice_remaining = maxf(0, notice_remaining - delta)
	if not travel_to.is_empty():
		travel_elapsed += delta
		if travel_elapsed >= METRO_SECONDS and not arrival_state.is_empty():
			var arrived := arrival_state
			arrival_state = {}
			travel_to = ""
			tick_elapsed = 0.0
			accept_state(arrived)
	if work_feedback > 0:
		work_feedback = maxf(0.0, work_feedback - delta)
		if work_feedback == 0 and return_after_work:
			return_after_work = false
			send_command("home")
	tick_elapsed += delta
	if not state.is_empty():
		var targets: Dictionary = state.objects.duplicate()
		targets["player"] = state.player
		for key in targets:
			var obj: Dictionary = targets[key]
			var target := Vector2(float(obj.x), float(obj.y))
			positions[key] = Vector2(positions.get(key, target)).lerp(target, minf(1.0, delta * 18))
		if tick_elapsed >= .1 and not tick_pending and not command_pending and not is_routine_busy():
			var dx := 0.0
			var dy := 0.0
			if state.phase != "office" and (wish_input == null or not wish_input.has_focus()):
				dx = float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A))
				dy = float(Input.is_physical_key_pressed(KEY_S)) - float(Input.is_physical_key_pressed(KEY_W))
			tick_pending = true
			var error := post(tick_http, "/bureau/sessions/" + sid + "/tick",
				{"dx": dx, "dy": dy, "dt": minf(.2, tick_elapsed), "crouch": Input.is_physical_key_pressed(KEY_SHIFT)})
			tick_elapsed = 0.0
			if error != OK:
				tick_pending = false
		refresh_ui()
	queue_redraw()


func label_at(point: Vector2, text: String, size: int = 13, color: Color = PAPER) -> void:
	draw_string(font, point, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, color)


func actor_at(point: Vector2, color: Color, role: String) -> void:
	draw_ellipse_shadow(point)
	draw_rect(Rect2(point + Vector2(-6, -3), Vector2(12, 17)), color)
	draw_circle(point + Vector2(0, -7), 6, Color("#cfbda1"))
	draw_line(point + Vector2(-3, 13), point + Vector2(-4, 20), color.darkened(.2), 4)
	draw_line(point + Vector2(3, 13), point + Vector2(4, 20), color.darkened(.2), 4)
	draw_line(point + Vector2(0, 0), point + Vector2(0, 8), GOLD, 2)
	if role == "police":
		draw_rect(Rect2(point + Vector2(-7, -14), Vector2(14, 6)), Color("#617d98"))
	elif role == "lawyer":
		draw_line(point + Vector2(-4, -10), point + Vector2(-7, -17), Color("#bc6d58"), 3)
		draw_line(point + Vector2(4, -10), point + Vector2(7, -17), Color("#bc6d58"), 3)
		draw_rect(Rect2(point + Vector2(8, 4), Vector2(8, 10)), Color("#876f50"))


func draw_ellipse_shadow(point: Vector2) -> void:
	draw_circle(point + Vector2(2, 15), 13, Color(0, 0, 0, .27))


func _draw() -> void:
	draw_rect(Rect2(0, 0, 1280, 720), Color("#10191b"))
	draw_line(Vector2(24, 48), Vector2(1256, 48), Color("#7c6948"), 1)
	if state.is_empty():
		label_at(Vector2(380, 330), "УСТАНАВЛИВАЕМ СВЯЗЬ С РЕАЛЬНОСТЬЮ", 20)
		return
	if state.phase != "city" or not travel_to.is_empty():
		return
	var world: Dictionary = state.level
	draw_rect(Rect2(20, 55, 1240, 543), Color("#222c2c"))
	for x in range(40, 1250, 40):
		draw_line(Vector2(x, 55), Vector2(x, 598), Color(1, 1, 1, .025))
	for y in range(70, 590, 40):
		draw_line(Vector2(20, y), Vector2(1260, y), Color(1, 1, 1, .025))
	for room in world.rooms:
		var r: Array = room.rect
		var rect := Rect2(r[0], r[1], r[2], r[3])
		var color := Color(room.color)
		if state.phase != "city" and state.phase != room.id:
			color = color.darkened(.55)
		draw_rect(rect, Color("#080f10"))
		draw_rect(rect.grow(-7), color)
		draw_rect(rect.grow(-3), color.lightened(.25), false, 1)
		for stripe in range(int(rect.position.y + 44), int(rect.end.y - 12), 24):
			draw_line(Vector2(rect.position.x + 10, stripe), Vector2(rect.end.x - 10, stripe), Color(1,1,1,.035))
		label_at(rect.position + Vector2(17, 30), str(room.name), 13, GOLD)
	draw_line(Vector2(60, 374), Vector2(1010, 374), Color("#8a7a55"), 2)
	for x in range(55, 1030, 42):
		draw_line(Vector2(x, 382), Vector2(x + 19, 382), Color("#4b503e"), 2)
	label_at(Vector2(80, 410), "УЛИЦА ПРЕДПИСАННЫХ МАРШРУТОВ", 12, Color("#83928b"))
	for barrier in world.barriers:
		draw_rect(Rect2(barrier.x, barrier.y, barrier.w, barrier.h), Color("#11181b"))
		draw_line(Vector2(barrier.x, barrier.y), Vector2(barrier.x, barrier.y + barrier.h), Color("#967856"), 2)
	for key in state.objects:
		var obj: Dictionary = state.objects[key]
		var point := Vector2(positions.get(key, Vector2(obj.x, obj.y)))
		var kind: String = obj.kind
		if kind == "police":
			if state.phase == "city" and state.player.recognizable:
				var radius := 200.0 * float(state.lighting)
				var fill := Color(.9, .34, .23, .10 if not obj.get("chasing", false) else .22)
				draw_circle(point, radius, fill)
				draw_arc(point, radius, 0, TAU, 40, Color(.9,.5,.3,.3), 1)
			actor_at(point, Color("#536b80"), "police")
		elif kind == "npc":
			actor_at(point, Color("#8c8776"), "npc")
		elif kind == "door":
			var is_open: bool = obj.get("open", false)
			var color := MINT if is_open else Color("#be7855")
			if not is_open:
				draw_rect(Rect2(point - Vector2(obj.w / 2, obj.h / 2), Vector2(obj.w, obj.h)), color)
				for y in range(int(point.y - obj.h / 2), int(point.y + obj.h / 2), 16):
					draw_line(Vector2(point.x - 8, y), Vector2(point.x + 8, y + 9), Color("#302624"), 3)
			else:
				draw_line(point + Vector2(-8, -obj.h / 2), point + Vector2(28, -obj.h / 2), color, 4)
				draw_line(point + Vector2(-8, obj.h / 2), point + Vector2(28, obj.h / 2), color, 4)
			label_at(point + Vector2(-45, -obj.h / 2 - 9), "ПРОХОД" if is_open else str(obj.name), 11, color)
		elif kind == "tree":
			draw_circle(point + Vector2(3, 9), 24, Color(0,0,0,.25))
			draw_rect(Rect2(point + Vector2(-4, 0), Vector2(8, 24)), Color("#8a6b47"))
			draw_circle(point + Vector2(0, -10), 24, Color("#638267"))
			draw_circle(point + Vector2(-8, -17), 12, Color("#809b6e"))
		elif kind == "rock":
			draw_colored_polygon(PackedVector2Array([point + Vector2(-17, 6),point + Vector2(-10, -12),point + Vector2(10,-15),point + Vector2(19,2),point + Vector2(8,14)]),Color("#a29e88"))
		elif kind == "crate":
			draw_rect(Rect2(point - Vector2(15,15), Vector2(30,30)), Color("#aa8250"))
			draw_line(point - Vector2(12,12), point + Vector2(12,12), Color("#634a33"), 3)
			draw_line(point + Vector2(12,-12), point + Vector2(-12,12), Color("#634a33"), 3)
		elif kind == "car" or kind == "bus":
			var color := Color("#c3bb93") if kind == "car" else Color("#75837a")
			draw_rect(Rect2(point - Vector2(31, 15), Vector2(62, 30)), Color("#11181b"))
			draw_rect(Rect2(point - Vector2(27, 12), Vector2(54, 24)), color)
			draw_rect(Rect2(point - Vector2(12, 10), Vector2(24, 20)), Color("#324c54"))
			if obj.get("legal_status", "") == "emergency_vehicle":
				draw_line(point + Vector2(-2,-8),point + Vector2(-2,8),Color("#de6b58"),4)
				draw_line(point + Vector2(-10,0),point + Vector2(6,0),Color("#de6b58"),4)
				draw_circle(point + Vector2(0,-17), 4, Color("#79c2db"))
		else:
			var size := Vector2(42, 24) if kind != "bed" else Vector2(38, 65)
			draw_rect(Rect2(point - size / 2, size), Color("#a18e68"))
			draw_rect(Rect2(point - size / 2 + Vector2(3,3), size - Vector2(6,6)), Color("#596765"))
			if key == "desk" and state.contract_ready and not state.contract_signed:
				draw_rect(Rect2(point - Vector2(8,12), Vector2(16,24)), PAPER)
				draw_circle(point + Vector2(0,5),3,Color("#b44d40"))
			if key == "workdesk":
				draw_circle(point,8,Color("#b96849"))
			label_at(point + Vector2(-30,-24), str(obj.name), 11)
	var player_point := Vector2(positions.get("player",Vector2(state.player.x,state.player.y)))
	if not state.player.driving:
		actor_at(player_point, Color("#d1bc81"), "clerk")
	if state.player.protected:
		draw_arc(player_point, 25, 0, TAU, 36, MINT, 2)
	if not state.player.recognizable:
		draw_circle(player_point + Vector2(0,-27), 3, MINT)
	if state.contract_signed:
		var lawyer_point := player_point + Vector2(-32,-27)
		actor_at(lawyer_point,Color("#623b3c"),"lawyer")
		if wish_pending:
			draw_arc(lawyer_point, 25, visual_time * 2, visual_time * 2 + 4, 20, GOLD, 2)
	draw_rect(Rect2(20,55,1240,543),Color(0,0,0,clampf((.8-float(state.lighting))*.6,0,.5)))
	var hint := "МЫШЬ — действия рутины  ·  WASD — движение"
	if state.phase == "city":
		hint = "WASD — движение   SHIFT — красться   E — автомобиль   ПРОБЕЛ — желание   J — реестр"
	label_at(Vector2(32,593), hint, 13, PAPER)
	if state.status != "active":
		draw_rect(Rect2(295,235,690,130),Color("#172222"))
		draw_rect(Rect2(295,235,690,130),GOLD,false,2)
		label_at(Vector2(330,285), "ВЫ ЗА ПРЕДЕЛАМИ МАРШРУТА" if state.status == "escaped" else "ДОГОВОР ВСТУПИЛ В СИЛУ", 25, GOLD)
		label_at(Vector2(330,327), "Первое дело завершено. Мир сохранил ваши решения.",16)


func test_wish(text: String) -> bool:
	begin_wish_request(text)
	for _i in range(1800):
		await get_tree().create_timer(.05).timeout
		if not wish_pending:
			await get_tree().create_timer(.4).timeout
			return last_wish_result.get("status") == "completed"
	return false


func save_artifact(filename: String) -> void:
	DirAccess.make_dir_recursive_absolute("res://test-artifacts/bureaucracy")
	var file := FileAccess.open("res://test-artifacts/bureaucracy/" + filename, FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify(state, "\t"))
