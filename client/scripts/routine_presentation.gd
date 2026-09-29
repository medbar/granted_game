extends Node2D
## A presentation of the authoritative apartment/office, not a second world simulation.
signal action_selected(action: String)

const PAPER := Color("#e1d7b8")
const GOLD := Color("#ddb56c")
const MINT := Color("#81c8ab")
const ZOOM := 2.15
var snapshot: Dictionary = {}
var smoothed: Dictionary = {}
var travel_target := ""
var travel_age := 0.0
var clock_time := 0.0
var busy := false
var selected_action := ""
var action_button: Button
var font: Font

func _ready() -> void:
	font = ThemeDB.fallback_font
	action_button = Button.new()
	action_button.add_theme_font_size_override("font_size", 19)
	action_button.add_theme_color_override("font_color", PAPER)
	var style := StyleBoxFlat.new()
	style.bg_color = Color("#603e32")
	style.border_color = GOLD
	style.set_border_width_all(2)
	style.set_corner_radius_all(3)
	action_button.add_theme_stylebox_override("normal", style)
	var hover := style.duplicate()
	hover.bg_color = Color("#80523b")
	action_button.add_theme_stylebox_override("hover", hover)
	action_button.pressed.connect(func():
		action_button.release_focus()
		action_selected.emit(selected_action))
	add_child(action_button)

func update_view(value: Dictionary, points: Dictionary, destination: String,
		age: float, now: float, locked: bool) -> void:
	snapshot = value
	smoothed = points
	travel_target = destination
	travel_age = age
	clock_time = now
	busy = locked
	visible = not value.is_empty() and (not destination.is_empty() or value.phase != "city")
	selected_action = ""
	action_button.visible = false
	if visible and destination.is_empty():
		if value.phase == "office":
			selected_action = "work"
			action_button.text = "ОБРАБОТАТЬ"
			action_button.position = Vector2(535, 324)
			action_button.size = Vector2(210, 62)
			action_button.visible = true
		else:
			selected_action = nearby_action()
			if not selected_action.is_empty():
				action_button.text = action_title(selected_action) + "  [E]"
				action_button.position = Vector2(390, 549)
				action_button.size = Vector2(500, 42)
				action_button.visible = true
	action_button.disabled = busy
	queue_redraw()

func location() -> String:
	return "metro" if not travel_target.is_empty() else str(snapshot.get("phase", ""))

func describe() -> Dictionary:
	var entities: Array[String] = []
	match location():
		"apartment": entities.assign(["table", "bed", "desk", "exit", "player"])
		"office": entities.assign(["workdesk", "player"])
		"metro": entities.assign(["train", "player", "passengers"])
	var buttons: Array[String] = []
	if action_button.visible and visible:
		buttons.append(action_button.text)
	return {"location": location(), "entities": entities, "buttons": buttons}

func world_room() -> Rect2:
	for room in snapshot.level.rooms:
		if room.id == snapshot.phase:
			var r: Array = room.rect
			return Rect2(r[0], r[1], r[2], r[3])
	return Rect2(50, 80, 290, 220)

func floor_rect() -> Rect2:
	var size := world_room().size * ZOOM
	return Rect2(Vector2(640, 335) - size / 2, size)

func project(point: Vector2) -> Vector2:
	return floor_rect().position + (point - world_room().position) * ZOOM

func object_point(id: String) -> Vector2:
	var obj: Dictionary = snapshot.objects[id]
	return Vector2(obj.x, obj.y)

func exit_point() -> Vector2:
	var room := world_room()
	return Vector2(room.end.x - 12, room.position.y + room.size.y * .55)

func action_title(action: String) -> String:
	match action:
		"commute": return "Отправиться на работу"
		"eat": return "Поесть"
		"sleep": return "Поспать"
		"sign": return "Подписать: жизнь после смерти"
		"leave": return "Выйти за пределы маршрута"
	return "ОБРАБОТАТЬ"

func hotspots() -> Dictionary:
	if snapshot.is_empty() or snapshot.phase != "apartment":
		return {}
	var result := {"eat": object_point("table"), "sleep": object_point("bed")}
	result["leave" if snapshot.contract_signed else "commute"] = exit_point()
	if snapshot.contract_ready and not snapshot.contract_signed:
		result["sign"] = object_point("desk")
	return result

func nearby_action() -> String:
	if snapshot.is_empty() or snapshot.phase != "apartment":
		return ""
	var player := Vector2(snapshot.player.x, snapshot.player.y)
	var closest := 38.0
	var result := ""
	for action in hotspots():
		var distance := player.distance_to(hotspots()[action])
		if distance < closest:
			result = action
			closest = distance
	return result

func _unhandled_input(event: InputEvent) -> void:
	if not visible or busy or location() != "apartment":
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var clicked: Vector2 = get_global_transform_with_canvas().affine_inverse() * event.position
		for action in hotspots():
			if clicked.distance_to(project(hotspots()[action])) < 52:
				action_selected.emit(action)
				get_viewport().set_input_as_handled()
				return

func text_at(point: Vector2, text: String, size: int = 16, color: Color = PAPER) -> void:
	draw_string(font, point, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, color)

func centered(y: float, text: String, size: int = 18, color: Color = PAPER) -> void:
	text_at(Vector2((1280 - font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x) / 2, y), text, size, color)

func person(point: Vector2, coat: Color, seated: bool = false) -> void:
	draw_set_transform(point, 0, Vector2(1.7, 1.7))
	draw_circle(Vector2(0, 9), 12, Color(0, 0, 0, .18))
	draw_rect(Rect2(-8, -19, 16, 22), coat)
	draw_rect(Rect2(-3, -18, 6, 14), PAPER.darkened(.16))
	draw_line(Vector2(0, -15), Vector2(0, -3), Color("#77563c"), 3)
	draw_circle(Vector2(0, -26), 7, Color("#cdb79b"))
	draw_rect(Rect2(-7, -33, 14, 5), Color("#443b32"))
	for side in [-1, 1]:
		draw_line(Vector2(side * 5, 3), Vector2(side * 7, 13 if not seated else 6), Color("#3b403b"), 5)
		draw_line(Vector2(side * 10, -16), Vector2(side * 10, -2), coat, 4)
	draw_set_transform(Vector2.ZERO)

func draw_interior() -> void:
	var rect := floor_rect()
	draw_rect(Rect2(rect.position + Vector2(12, 18), rect.size), Color(0, 0, 0, .38))
	draw_rect(rect.grow(13), Color("#39443e") if snapshot.phase == "apartment" else Color("#424c50"))
	draw_rect(rect, Color("#585343") if snapshot.phase == "apartment" else Color("#414a4a"))
	for y in range(int(rect.position.y + 12), int(rect.end.y), 25):
		draw_line(Vector2(rect.position.x, y), Vector2(rect.end.x, y), Color(0, 0, 0, .14), 2)
		for x in range(int(rect.position.x + (25 if y % 2 else 0)), int(rect.end.x), 105):
			draw_line(Vector2(x, y), Vector2(x, y + 25), Color(0, 0, 0, .06))
	draw_rect(Rect2(rect.position, Vector2(rect.size.x, 30)), Color("#6d7364") if snapshot.phase == "apartment" else Color("#737974"))
	draw_rect(rect, Color("#969782"), false, 2)
	if snapshot.phase == "apartment":
		draw_apartment(rect)
	else:
		draw_office(rect)

func draw_apartment(rect: Rect2) -> void:
	# A cold window, a rug, a meal, a bed and a desk. No other district exists in this view.
	draw_rect(Rect2(rect.position + Vector2(42, -5), Vector2(115, 44)), Color("#202e31"))
	draw_rect(Rect2(rect.position + Vector2(49, 1), Vector2(101, 31)), Color("#89a3a1"))
	draw_line(rect.position + Vector2(100, 0), rect.position + Vector2(100, 35), Color("#34433f"), 5)
	draw_rect(Rect2(rect.get_center() - Vector2(112, 70), Vector2(224, 184)), Color("#464e45"))
	draw_rect(Rect2(rect.get_center() - Vector2(104, 62), Vector2(208, 168)), Color("#85836a"), false, 2)
	var meal := project(object_point("table"))
	draw_circle(meal + Vector2(5, 10), 48, Color(0, 0, 0, .23))
	draw_circle(meal, 43, Color("#947651"))
	draw_circle(meal, 40, Color("#ad9068"))
	draw_circle(meal - Vector2(7, 3), 15, PAPER)
	draw_circle(meal - Vector2(7, 3), 10, Color("#947046"))
	draw_rect(Rect2(meal + Vector2(18, -17), Vector2(10, 16)), Color("#bfc3ae"))
	text_at(meal + Vector2(-28, -55), "ПОЕСТЬ", 13)
	var bed := project(object_point("bed"))
	draw_rect(Rect2(bed - Vector2(42, 59) + Vector2(5, 8), Vector2(84, 125)), Color(0, 0, 0, .24))
	draw_rect(Rect2(bed - Vector2(42, 59), Vector2(84, 125)), Color("#887a59"))
	draw_rect(Rect2(bed - Vector2(35, 53), Vector2(70, 111)), Color("#adad91"))
	draw_rect(Rect2(bed - Vector2(30, 47), Vector2(60, 23)), PAPER.darkened(.04))
	draw_rect(Rect2(bed - Vector2(35, 13), Vector2(70, 71)), Color("#556d68"))
	for i in range(4):
		draw_line(bed + Vector2(-34, i * 18 - 10), bed + Vector2(34, i * 18 - 10), Color("#637d72"), 2)
	text_at(bed + Vector2(-27, -72), "СПАТЬ", 13)
	var desk := project(object_point("desk"))
	draw_rect(Rect2(desk - Vector2(58, 27), Vector2(116, 61)), Color("#5f4c38"))
	draw_rect(Rect2(desk - Vector2(58, 32), Vector2(116, 56)), Color("#a08b64"))
	if snapshot.contract_ready:
		draw_rect(Rect2(desk - Vector2(14, 21), Vector2(29, 36)), PAPER)
		for i in range(4):
			draw_line(desk + Vector2(-9, -13 + i * 5), desk + Vector2(9, -13 + i * 5), Color("#898571"))
		draw_circle(desk + Vector2(5, 8), 4, Color("#9a4940"))
		text_at(desk + Vector2(-65, -44), "ДОГОВОР" if not snapshot.contract_signed else "ПОДПИСАНО", 14, GOLD)
	var door := project(exit_point())
	draw_rect(Rect2(door - Vector2(9, 45), Vector2(37, 90)), Color("#172326"))
	draw_rect(Rect2(door - Vector2(7, 43), Vector2(32, 86)), Color("#96734c"), false, 3)
	draw_line(door + Vector2(-5, -42), door + Vector2(-23, -21), Color("#b39764"), 6)
	draw_line(door + Vector2(-23, -21), door + Vector2(-23, 42), Color("#b39764"), 6)
	text_at(door + Vector2(64, -12), "Отправиться" if not snapshot.contract_signed else "Выйти за пределы", 17, GOLD)
	text_at(door + Vector2(64, 11), "на работу" if not snapshot.contract_signed else "маршрута", 17, GOLD)
	draw_line(door + Vector2(30, 25), door + Vector2(53, 25), GOLD, 2)
	draw_line(door + Vector2(53, 25), door + Vector2(47, 19), GOLD, 2)
	var position: Vector2 = smoothed.get("player", Vector2(snapshot.player.x, snapshot.player.y))
	person(project(position), Color("#b1aa81"))
	if not selected_action.is_empty():
		draw_arc(project(hotspots()[selected_action]), 55, 0, TAU, 40, Color(.83,.71,.43,.55), 2)
	text_at(Vector2(33, 604), "WASD — подойти   ·   E или щелчок по предмету — действие", 14, Color("#a9b1a3"))

func draw_office(rect: Rect2) -> void:
	var monitor := Rect2(Vector2(552, rect.position.y + 56), Vector2(176, 73))
	draw_rect(monitor.grow(7), Color("#252f2c"))
	draw_rect(monitor, Color("#283d37"))
	centered(monitor.position.y + 24, "ОБРАБОТАНО ЗАЯВОК", 13, Color("#91a99a"))
	centered(monitor.position.y + 56, "%04d" % int(snapshot.processed), 29, MINT)
	draw_colored_polygon(PackedVector2Array([Vector2(566,155), Vector2(714,155), Vector2(870,495), Vector2(410,495)]), Color(.86,.83,.60,.045))
	draw_rect(Rect2(477, 272, 326, 154), Color(0,0,0,.3))
	draw_rect(Rect2(466, 254, 326, 146), Color("#514c3b"))
	draw_rect(Rect2(466, 249, 326, 137), Color("#a29571"))
	draw_rect(Rect2(480, 263, 45, 60), PAPER.darkened(.13))
	for i in range(4):
		draw_line(Vector2(485, 273+i*10), Vector2(517, 273+i*10), Color("#7a7c67"))
	draw_rect(Rect2(765, 273, 13, 65), Color("#49473c"))
	draw_rect(Rect2(610, 452, 60, 36), Color("#6d6550"))
	person(Vector2(640, 450), Color("#b1aa81"), true)
	centered(526, "Ваша функция — нажимать кнопку.", 17, Color("#a8afa0"))

func draw_metro() -> void:
	draw_rect(Rect2(0, 54, 1280, 552), Color("#0a1114"))
	var shake := sin(clock_time * 31) * .65
	draw_set_transform(Vector2(0, shake))
	draw_rect(Rect2(109, 145, 1062, 365), Color("#293b3e"))
	draw_rect(Rect2(122, 156, 1036, 323), Color("#89968c"))
	draw_rect(Rect2(122, 379, 1036, 120), Color("#435857"))
	for x in [159, 390, 621, 852]:
		draw_rect(Rect2(x, 185, 190, 159), Color("#283b3d"))
		draw_rect(Rect2(x+7, 192, 176, 145), Color("#14232a"))
		for stripe in range(3):
			var light_x := fposmod(clock_time * -390 + stripe * 63, 168)
			draw_rect(Rect2(x+11+light_x, 208, 4, 95), Color("#537770", .5))
		draw_line(Vector2(x+11, 263), Vector2(x+180, 263), Color("#2d464b"), 2)
		draw_rect(Rect2(x+12, 369, 177, 48), Color("#3b6670"))
		draw_rect(Rect2(x+12, 415, 177, 25), Color("#517780"))
		draw_line(Vector2(x-12, 176), Vector2(x-12, 439), Color("#bec1ad"), 4)
		draw_arc(Vector2(x+91, 185), 13, 0, PI, 18, Color("#d6d0b6"), 3)
	person(Vector2(242, 407), Color("#696f68"), true)
	person(Vector2(484, 407), Color("#b1aa81"), true)
	person(Vector2(713, 407), Color("#586773"), true)
	person(Vector2(944, 407), Color("#787164"), true)
	draw_line(Vector2(124, 473), Vector2(1157, 473), Color("#b2b39c"), 2)
	draw_set_transform(Vector2.ZERO)
	centered(116, "ПРЕДПИСАННЫЙ МАРШРУТ", 14, Color("#849a93"))
	centered(554, "Следующая станция: " + ("Работа" if travel_target == "office" else "Дом"), 24, GOLD)
	draw_line(Vector2(500, 580), Vector2(780, 580), Color("#334943"), 3)
	draw_line(Vector2(500, 580), Vector2(500 + 280 * minf(1, travel_age / 2.8), 580), MINT, 3)
	draw_circle(Vector2(500, 580), 5, MINT)
	draw_circle(Vector2(780, 580), 5, MINT if travel_age >= 2.8 else Color("#50695c"))

func _draw() -> void:
	if not visible or snapshot.is_empty():
		return
	if not travel_target.is_empty():
		draw_metro()
	else:
		draw_interior()
