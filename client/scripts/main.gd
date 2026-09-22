extends Node2D

const UNIT := 60.0
const GAMEPLAY_CONFIG_PATH := "res://config/gameplay.json"
const LEVEL_DEFINITION_PATH := "res://levels/monaco_start.json"
const PlayerScript = preload("res://scripts/player.gd")
const GenieScript = preload("res://scripts/genie.gd")
const DwarfScript = preload("res://scripts/dwarf.gd")
const NpcScript = preload("res://scripts/npc.gd")
const WorldPropScript = preload("res://scripts/world_prop.gd")
const MagicEffectScript = preload("res://scripts/magic_effect.gd")
const RuntimeEffectScript = preload("res://scripts/runtime_effect.gd")
const WEAPON_RANGE := 82.0
const WEAPON_ARC_DOT := 0.34
const WEAPON_DAMAGE := 24.0
const WEAPON_KNOCKBACK := 0.72

var ARENA := Rect2(-570.0, -300.0, 1140.0, 600.0)
var EXTRACTION_ZONE := Rect2(-627.0, -60.0, 57.0, 120.0)
var ROOMS: Array[Rect2] = []
var ROOM_NAMES: Array[String] = []
var ROOM_COLORS: Array[Color] = []
var ROOM_PATTERNS: Array[String] = []
var WALLS: Array[Rect2] = []
var WALL_IDS: Array[String] = []

var player: CharacterBody2D
var genie: Node2D
var dwarfs: Array[CharacterBody2D] = []
var npcs: Array[CharacterBody2D] = []
var props: Array[CharacterBody2D] = []
var object_index: Dictionary = {}
var arena_walls: Dictionary = {}
var level_doors: Dictionary = {}
var level_definition: Dictionary = {}
var player_start_position := Vector2(-492.0, 0.0)
var water_state := "water"
var water_temperature := 0.5
var water_position := Vector2(190, 232)
var water_radius := 54.0
var initial_water_state := "water"
var initial_water_temperature := 0.5
var created_object_counter := 0
var loot_total := 0
var loot_collected := 0
var alarm_level := 0.0
var mission_complete := false
var shutdown_requested := false
var world_paused := false
var world_time_scale := 1.0
var world_light_level := 1.0

var casting := false
var waiting_for_backend := false
var cast_counter := 0
var debug_enabled := false
var last_debug: Dictionary = {}
var last_spell_text := ""
var gameplay_config: Dictionary = {}
var runtime_world_config: Dictionary = {}
var backend_url := "http://127.0.0.1:8000"
var cast_time_scale := 0.35
var snapshot_radius := 12.0
var request_timeout_seconds := 90.0
var runtime_contact_interval := 0.4
var wish_poll_interval_seconds := 0.25
var active_wish_job_id := ""
var wish_first_action_received := false
var wish_client_ttfa_reported := false
var wish_submitted_at_ms := 0
var wish_initial_response_at_ms := 0
var wish_action_ready_at_ms := 0
var last_client_ttfa_ms := 0.0
var last_wish_timing: Dictionary = {}
var wish_server_action_ready_ms = null
var ttfa_observation_profile := "runtime"
var pending_agent_actions: Array = []
var agent_action_playing := false
var active_agent_step_id := ""
var agent_step_feedback_pending := false

var cast_http: HTTPRequest
var health_http: HTTPRequest
var config_http: HTTPRequest
var wish_poll_timer: Timer
var ui_layer: CanvasLayer
var world_light_overlay: ColorRect
var cast_tint: ColorRect
var health_label: Label
var curse_label: Label
var connection_label: Label
var hint_label: Label
var cast_label: Label
var objective_label: Label
var alarm_label: Label
var spell_input: LineEdit
var debug_panel: Panel
var debug_text: RichTextLabel


func _ready() -> void:
	load_gameplay_config()
	load_level_definition()
	create_arena()
	create_actors()
	create_ui()
	create_http_clients()
	request_health()
	queue_redraw()


func load_gameplay_config() -> void:
	if not FileAccess.file_exists(GAMEPLAY_CONFIG_PATH):
		return
	var file := FileAccess.open(GAMEPLAY_CONFIG_PATH, FileAccess.READ)
	if file == null:
		return
	var parsed = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	gameplay_config = parsed
	backend_url = str(gameplay_config.get("backend_url", backend_url))
	cast_time_scale = float(gameplay_config.get("cast_time_scale", cast_time_scale))
	snapshot_radius = float(gameplay_config.get("snapshot_radius", snapshot_radius))
	request_timeout_seconds = float(gameplay_config.get("request_timeout_seconds", request_timeout_seconds))
	runtime_contact_interval = float(gameplay_config.get("runtime_contact_interval", runtime_contact_interval))
	wish_poll_interval_seconds = float(gameplay_config.get("wish_poll_interval_seconds", wish_poll_interval_seconds))


func rect_from_level(data: Dictionary) -> Rect2:
	return Rect2(
		float(data.get("x", 0.0)) * UNIT,
		float(data.get("y", 0.0)) * UNIT,
		float(data.get("width", 1.0)) * UNIT,
		float(data.get("height", 1.0)) * UNIT
	)


func position_from_level(data: Dictionary) -> Vector2:
	return Vector2(float(data.get("x", 0.0)) * UNIT, float(data.get("y", 0.0)) * UNIT)


func load_level_definition() -> void:
	if not FileAccess.file_exists(LEVEL_DEFINITION_PATH):
		push_error("LEVEL CONTRACT: missing " + LEVEL_DEFINITION_PATH)
		return
	var file := FileAccess.open(LEVEL_DEFINITION_PATH, FileAccess.READ)
	if file == null:
		push_error("LEVEL CONTRACT: cannot open " + LEVEL_DEFINITION_PATH)
		return
	var parsed = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("LEVEL CONTRACT: invalid JSON")
		return
	level_definition = parsed
	ARENA = rect_from_level(level_definition.get("bounds", {}))
	EXTRACTION_ZONE = rect_from_level(level_definition.get("extraction_zone", {}))
	ROOMS.clear()
	ROOM_NAMES.clear()
	ROOM_COLORS.clear()
	ROOM_PATTERNS.clear()
	for room_data in level_definition.get("rooms", []):
		ROOMS.append(rect_from_level(room_data.get("rect", {})))
		ROOM_NAMES.append(str(room_data.get("name", room_data.get("id", "ROOM"))))
		ROOM_COLORS.append(Color(str(room_data.get("color", "183d62"))))
		ROOM_PATTERNS.append(str(room_data.get("floor_pattern", "grid")))
	WALLS.clear()
	WALL_IDS.clear()
	for wall_data in level_definition.get("walls", []):
		WALL_IDS.append(str(wall_data.get("id", "")))
		WALLS.append(rect_from_level(wall_data.get("rect", {})))


func create_arena() -> void:
	for wall_index in range(WALLS.size()):
		var wall: Rect2 = WALLS[wall_index]
		var wall_id := WALL_IDS[wall_index]
		var body := StaticBody2D.new()
		body.position = wall.get_center()
		add_child(body)
		add_wall_collision_piece(body, wall.size, Vector2.ZERO)
		arena_walls[wall_id] = {"rect": wall, "body": body, "door_installed": false}
		object_index[wall_id] = body
	for door_data in level_definition.get("doors", []):
		create_level_door(door_data)


func create_level_door(door_data: Dictionary) -> void:
	var door_id := str(door_data.get("id", "door"))
	var rect := rect_from_level(door_data.get("rect", {}))
	var body := StaticBody2D.new()
	body.position = rect.get_center()
	body.collision_layer = 1
	body.collision_mask = 1
	add_child(body)
	add_wall_collision_piece(body, rect.size, Vector2.ZERO)
	level_doors[door_id] = {
		"definition": door_data.duplicate(true),
		"rect": rect,
		"body": body,
		"locked": bool(door_data.get("locked", false)),
		"open": bool(door_data.get("open", false)),
		"initial_locked": bool(door_data.get("locked", false)),
		"initial_open": bool(door_data.get("open", false))
	}
	object_index[door_id] = body
	set_level_door_open(door_id, bool(door_data.get("open", false)))


func set_level_door_open(door_id: String, opened: bool) -> bool:
	if not level_doors.has(door_id):
		return false
	var entry: Dictionary = level_doors[door_id]
	entry["open"] = opened
	if opened:
		entry["locked"] = false
	var body: StaticBody2D = entry["body"]
	body.collision_layer = 0 if opened else 1
	for child in body.get_children():
		if child is CollisionShape2D:
			child.disabled = opened
	level_doors[door_id] = entry
	queue_redraw()
	return true


func reset_level_doors() -> void:
	for door_id in level_doors:
		var entry: Dictionary = level_doors[door_id]
		entry["locked"] = bool(entry.get("initial_locked", false))
		level_doors[door_id] = entry
		set_level_door_open(str(door_id), bool(entry.get("initial_open", false)))


func add_wall_collision_piece(body: StaticBody2D, size: Vector2, offset: Vector2) -> void:
	if size.x <= 1.0 or size.y <= 1.0:
		return
	var collision := CollisionShape2D.new()
	var shape := RectangleShape2D.new()
	shape.size = size
	collision.position = offset
	collision.shape = shape
	body.add_child(collision)


func wall_door_rect(wall: Rect2) -> Rect2:
	var horizontal := wall.size.x >= wall.size.y
	var opening_length := minf(54.0, (wall.size.x if horizontal else wall.size.y) * 0.72)
	if horizontal:
		return Rect2(wall.get_center() - Vector2(opening_length * 0.5, wall.size.y * 0.5), Vector2(opening_length, wall.size.y))
	return Rect2(wall.get_center() - Vector2(wall.size.x * 0.5, opening_length * 0.5), Vector2(wall.size.x, opening_length))


func install_door_in_wall(wall_id: String) -> bool:
	if not arena_walls.has(wall_id):
		if object_index.has(wall_id) and is_instance_valid(object_index[wall_id]):
			var prop = object_index[wall_id]
			if "prop_kind" in prop and prop.prop_kind == "wall":
				prop.apply_world_action({"type": "INSTALL_DOOR"}, UNIT)
				return true
		return false
	var entry: Dictionary = arena_walls[wall_id]
	if bool(entry.get("door_installed", false)):
		return true
	var wall: Rect2 = entry["rect"]
	var body: StaticBody2D = entry["body"]
	for child in body.get_children():
		if child is CollisionShape2D:
			child.disabled = true
			child.queue_free()
	var doorway := wall_door_rect(wall)
	var horizontal := wall.size.x >= wall.size.y
	if horizontal:
		var left_width := doorway.position.x - wall.position.x
		var right_width := wall.end.x - doorway.end.x
		add_wall_collision_piece(body, Vector2(left_width, wall.size.y), Vector2(-wall.size.x * 0.5 + left_width * 0.5, 0.0))
		add_wall_collision_piece(body, Vector2(right_width, wall.size.y), Vector2(wall.size.x * 0.5 - right_width * 0.5, 0.0))
	else:
		var top_height := doorway.position.y - wall.position.y
		var bottom_height := wall.end.y - doorway.end.y
		add_wall_collision_piece(body, Vector2(wall.size.x, top_height), Vector2(0.0, -wall.size.y * 0.5 + top_height * 0.5))
		add_wall_collision_piece(body, Vector2(wall.size.x, bottom_height), Vector2(0.0, wall.size.y * 0.5 - bottom_height * 0.5))
	entry["door_installed"] = true
	arena_walls[wall_id] = entry
	queue_redraw()
	return true


func reset_arena_doors() -> void:
	for wall_id in arena_walls:
		var entry: Dictionary = arena_walls[wall_id]
		var body: StaticBody2D = entry["body"]
		for child in body.get_children():
			if child is CollisionShape2D:
				child.disabled = true
				child.queue_free()
		add_wall_collision_piece(body, entry["rect"].size, Vector2.ZERO)
		entry["door_installed"] = false
		arena_walls[wall_id] = entry
	queue_redraw()


func create_actors() -> void:
	var entity_definitions: Array = level_definition.get("entities", [])
	var player_definition: Dictionary = {}
	for entity_data in entity_definitions:
		if str(entity_data.get("id", "")) == "player":
			player_definition = entity_data
			break
	player = PlayerScript.new()
	player_start_position = position_from_level(player_definition.get("position", {"x": -8.2, "y": 0.0}))
	player.global_position = player_start_position
	player.arena_bounds = ARENA
	player.health = float(player_definition.get("health", 100.0))
	player.outfit = str(player_definition.get("properties", {}).get("outfit", ""))
	add_child(player)
	object_index["player"] = player
	genie = GenieScript.new()
	genie.setup(player)
	add_child(genie)
	var camera := Camera2D.new()
	camera.position_smoothing_enabled = true
	camera.position_smoothing_speed = 5.0
	camera.enabled = true
	player.add_child(camera)

	for entity_data in entity_definitions:
		var entity_id := str(entity_data.get("id", ""))
		if entity_id == "player":
			continue
		var tags: Array = entity_data.get("tags", [])
		var spawn_position := position_from_level(entity_data.get("position", {}))
		if tags.has("enemy"):
			var dwarf := DwarfScript.new()
			dwarf.setup(entity_id, spawn_position, player)
			var facing_degrees := float(entity_data.get("properties", {}).get("facing_degrees", 180.0))
			dwarf.look_direction = Vector2.from_angle(deg_to_rad(facing_degrees))
			add_child(dwarf)
			dwarfs.append(dwarf)
			object_index[entity_id] = dwarf
			continue
		if tags.has("npc"):
			var npc := NpcScript.new()
			npc.setup(entity_id, spawn_position)
			npc.target = player
			add_child(npc)
			npcs.append(npc)
			object_index[entity_id] = npc
			continue
		if tags.has("water"):
			water_position = spawn_position
			water_radius = float(entity_data.get("radius", 0.85)) * UNIT
			water_state = str(entity_data.get("material", {}).get("name", "water"))
			water_temperature = float(entity_data.get("material", {}).get("temperature", 0.5))
			initial_water_state = water_state
			initial_water_temperature = water_temperature
			continue
		var prototype := str(entity_data.get("properties", {}).get("prototype", "prop"))
		if tags.has("loot"):
			prototype = "loot"
		var prop := WorldPropScript.new()
		prop.setup(entity_id, prototype, spawn_position, player, entity_data)
		add_child(prop)
		props.append(prop)
		object_index[entity_id] = prop
		if prop.is_heist_loot():
			loot_total += 1


func create_ui() -> void:
	ui_layer = CanvasLayer.new()
	add_child(ui_layer)
	world_light_overlay = ColorRect.new()
	world_light_overlay.position = Vector2.ZERO
	world_light_overlay.size = Vector2(1280, 720)
	world_light_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui_layer.add_child(world_light_overlay)
	update_world_light_overlay()
	cast_tint = ColorRect.new()
	cast_tint.color = Color(0.18, 0.3, 0.5, 0.0)
	cast_tint.position = Vector2.ZERO
	cast_tint.size = Vector2(1280, 720)
	cast_tint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui_layer.add_child(cast_tint)

	health_label = make_label(Vector2(24, 20), Vector2(260, 34), 22)
	curse_label = make_label(Vector2(24, 48), Vector2(760, 28), 14)
	curse_label.text = "ПРОКЛЯТИЯ ДЖИНА: нет видимых признаков"
	curse_label.modulate = Color("cbb8ff")
	connection_label = make_label(Vector2(1010, 22), Vector2(245, 30), 16)
	connection_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	objective_label = make_label(Vector2(24, 76), Vector2(500, 30), 16)
	objective_label.modulate = Color("ffd85a")
	alarm_label = make_label(Vector2(1010, 52), Vector2(245, 30), 16)
	alarm_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	hint_label = make_label(Vector2(360, 670), Vector2(560, 32), 17)
	hint_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint_label.text = "WASD — движение    ЛКМ — удар оружием    SPACE — желание джину"

	cast_label = make_label(Vector2(160, 582), Vector2(960, 40), 18)
	cast_label.text = "ЖЕЛАНИЕ ДЖИНУ  •  только текст, затем ENTER"
	cast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	cast_label.modulate = Color("a8edff")
	cast_label.visible = false

	spell_input = LineEdit.new()
	spell_input.position = Vector2(160, 622)
	spell_input.size = Vector2(960, 52)
	spell_input.placeholder_text = "Джин, я желаю…"
	spell_input.max_length = 300
	spell_input.add_theme_font_size_override("font_size", 22)
	spell_input.add_theme_color_override("font_color", Color("eef6ff"))
	spell_input.add_theme_color_override("caret_color", Color("a8edff"))
	spell_input.add_theme_stylebox_override("normal", panel_style(Color(0.035, 0.05, 0.09, 0.94), Color("6786b7"), 2, 12))
	spell_input.add_theme_stylebox_override("focus", panel_style(Color(0.04, 0.06, 0.11, 0.97), Color("a8edff"), 3, 12))
	spell_input.text_submitted.connect(_on_spell_submitted)
	spell_input.visible = false
	ui_layer.add_child(spell_input)

	debug_panel = Panel.new()
	debug_panel.position = Vector2(18, 70)
	debug_panel.size = Vector2(440, 500)
	debug_panel.add_theme_stylebox_override("panel", panel_style(Color(0.02, 0.028, 0.05, 0.94), Color("5f77a3"), 1, 8))
	debug_panel.visible = false
	ui_layer.add_child(debug_panel)
	debug_text = RichTextLabel.new()
	debug_text.position = Vector2(14, 12)
	debug_text.size = Vector2(412, 474)
	debug_text.bbcode_enabled = true
	debug_text.scroll_active = true
	debug_text.add_theme_font_size_override("normal_font_size", 14)
	debug_text.add_theme_color_override("default_color", Color("d8e7f4"))
	debug_panel.add_child(debug_text)
	update_hud()
	update_debug_panel()


func create_http_clients() -> void:
	cast_http = HTTPRequest.new()
	cast_http.timeout = request_timeout_seconds
	cast_http.use_threads = true
	cast_http.request_completed.connect(_on_cast_request_completed)
	add_child(cast_http)
	health_http = HTTPRequest.new()
	health_http.timeout = 1.5
	health_http.use_threads = true
	health_http.request_completed.connect(_on_health_request_completed)
	add_child(health_http)
	config_http = HTTPRequest.new()
	config_http.timeout = request_timeout_seconds
	config_http.use_threads = true
	config_http.request_completed.connect(_on_config_request_completed)
	add_child(config_http)
	wish_poll_timer = Timer.new()
	wish_poll_timer.one_shot = true
	wish_poll_timer.ignore_time_scale = true
	wish_poll_timer.wait_time = wish_poll_interval_seconds
	wish_poll_timer.timeout.connect(_poll_wish_job)
	add_child(wish_poll_timer)


func make_label(position_value: Vector2, size_value: Vector2, font_size: int) -> Label:
	var label := Label.new()
	label.position = position_value
	label.size = size_value
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", Color("e7f0fa"))
	label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	label.add_theme_constant_override("shadow_offset_x", 2)
	label.add_theme_constant_override("shadow_offset_y", 2)
	ui_layer.add_child(label)
	return label


func panel_style(background: Color, border: Color, width: int, radius: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(width)
	style.set_corner_radius_all(radius)
	style.content_margin_left = 16.0
	style.content_margin_right = 16.0
	return style


func request_health() -> void:
	connection_label.text = "Backend: соединение…"
	var error := health_http.request(backend_url + "/health")
	if error != OK:
		connection_label.text = "Backend: недоступен"
		connection_label.modulate = Color("ff8f8f")


func _on_health_request_completed(result: int, response_code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
	if result == HTTPRequest.RESULT_SUCCESS and response_code == 200:
		connection_label.text = "Backend: готов • 100 якорей"
		connection_label.modulate = Color("78e08f")
		config_http.request(backend_url + "/world/config")
	else:
		connection_label.text = "Backend: запустите server"
		connection_label.modulate = Color("ffb36b")


func _on_config_request_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		return
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	runtime_world_config = parsed
	var server_spell: Dictionary = runtime_world_config.get("spell", {})
	cast_time_scale = float(server_spell.get("cast_time_scale", cast_time_scale))
	snapshot_radius = float(server_spell.get("snapshot_radius", snapshot_radius))


func _process(_delta: float) -> void:
	update_heist_state()
	update_hud()
	queue_redraw()


func update_hud() -> void:
	if is_instance_valid(player):
		health_label.text = "ЗДОРОВЬЕ  %d / 100" % int(player.health)
		health_label.modulate = Color("ff8f8f") if player.health < 35.0 else Color.WHITE
	if mission_complete:
		objective_label.text = "ДЕЛО СДЕЛАНО  •  добыча вывезена"
		objective_label.modulate = Color("89ffc2")
	elif loot_collected >= loot_total and loot_total > 0:
		objective_label.text = "ДОБЫЧА %d/%d  •  вернитесь к выходу" % [loot_collected, loot_total]
		objective_label.modulate = Color("89ffc2")
	else:
		objective_label.text = "ДОБЫЧА %d/%d  •  соберите ценности" % [loot_collected, loot_total]
		objective_label.modulate = Color("ffd85a")
	if alarm_level >= 0.52:
		alarm_label.text = "ТРЕВОГА  %d%%" % int(alarm_level * 100.0)
		alarm_label.modulate = Color("ff5757")
	elif alarm_level > 0.04:
		alarm_label.text = "ПОДОЗРЕНИЕ  %d%%" % int(alarm_level * 100.0)
		alarm_label.modulate = Color("ffd45a")
	else:
		alarm_label.text = "СКРЫТНО"
		alarm_label.modulate = Color("70e8d0")


func update_heist_state() -> void:
	alarm_level = 0.0
	for dwarf in dwarfs:
		if dwarf.visible and dwarf.transformed_form.is_empty():
			alarm_level = maxf(alarm_level, dwarf.alertness)
	for prop in props:
		if prop.visible and prop.prop_kind == "enemy":
			alarm_level = maxf(alarm_level, prop.alertness)
	if mission_complete:
		return
	for prop in props:
		if prop.is_heist_loot() and not prop.collected and player.global_position.distance_to(prop.global_position) <= 34.0:
			if prop.collect_loot():
				loot_collected = collected_loot_ids().size()
				connection_label.text = "Ценность похищена  •  %d/%d" % [loot_collected, loot_total]
				connection_label.modulate = Color("ffd85a")
	loot_collected = collected_loot_ids().size()
	var extraction_door_id := str(level_definition.get("mission", {}).get("extraction_door_id", "exit_door_01"))
	var exit_is_open := level_doors.has(extraction_door_id) and bool(level_doors[extraction_door_id].get("open", false))
	if loot_total > 0 and loot_collected >= loot_total and (EXTRACTION_ZONE.has_point(player.global_position) or exit_is_open):
		mission_complete = true
		connection_label.text = "Ограбление завершено — добыча у вас"
		connection_label.modulate = Color("89ffc2")


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F3:
			debug_enabled = not debug_enabled
			debug_panel.visible = debug_enabled
			update_debug_panel()
			get_viewport().set_input_as_handled()
			return
		if event.keycode == KEY_R and not casting and not waiting_for_backend and not agent_action_playing:
			reset_sandbox()
			get_viewport().set_input_as_handled()
			return
		if event.keycode == KEY_SPACE and not casting:
			if waiting_for_backend or agent_action_playing:
				connection_label.text = "Джин ещё исполняет предыдущее желание"
				connection_label.modulate = Color("f5d76e")
			else:
				begin_wish()
			get_viewport().set_input_as_handled()
			return
		if event.keycode == KEY_ESCAPE and casting:
			cancel_cast()
			get_viewport().set_input_as_handled()
			return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed and not casting:
		try_weapon_attack()
		get_viewport().set_input_as_handled()


func begin_cast() -> void:
	casting = true
	waiting_for_backend = false
	Engine.time_scale = cast_time_scale
	player.movement_enabled = false
	player.cancel_weapon_swing()
	genie.set_wish_state(true, false)
	cast_tint.color = Color(0.06, 0.42, 0.43, 0.16)
	cast_label.visible = true
	spell_input.visible = true
	spell_input.editable = true
	spell_input.text = ""
	spell_input.grab_focus()
	hint_label.text = "ENTER — попросить    ESC — передумать"


func begin_wish() -> void:
	begin_cast()


func cancel_cast() -> void:
	finish_cast_mode()
	connection_label.text = "Вы передумали просить джина"
	connection_label.modulate = Color("d9e5e8")


func _on_spell_submitted(_value: String) -> void:
	confirm_cast()


func confirm_cast() -> void:
	if not casting or waiting_for_backend:
		return
	var text := spell_input.text.strip_edges()
	if text.is_empty():
		spell_input.placeholder_text = "Скажите джину, чего вы желаете"
		return
	waiting_for_backend = true
	active_wish_job_id = ""
	wish_first_action_received = false
	wish_client_ttfa_reported = false
	active_agent_step_id = ""
	agent_step_feedback_pending = false
	wish_submitted_at_ms = Time.get_ticks_msec()
	wish_initial_response_at_ms = 0
	wish_action_ready_at_ms = 0
	last_client_ttfa_ms = 0.0
	last_wish_timing = {}
	wish_server_action_ready_ms = null
	spell_input.editable = false
	cast_label.text = "ДЖИН ПРИНИМАЕТ ЖЕЛАНИЕ…"
	genie.set_wish_state(true, true)
	last_spell_text = text
	cast_counter += 1
	var payload := build_cast_payload(text)
	var headers := PackedStringArray(["Content-Type: application/json"])
	var error := cast_http.request(backend_url + "/wish/jobs", headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		cast_failed("backend request could not start")
		return
	release_player_after_submission()
	genie.accept_wish()


func release_player_after_submission() -> void:
	restore_world_time_scale()
	casting = false
	player.movement_enabled = not world_paused
	cast_tint.color = Color(0.06, 0.42, 0.43, 0.0)
	cast_label.visible = false
	spell_input.visible = false
	spell_input.editable = true
	spell_input.release_focus()
	hint_label.text = "WASD — движение    ЛКМ — удар    Джин исполняет желание…"
	connection_label.text = "Джин принял желание"
	connection_label.modulate = Color("f5d76e")


func build_cast_payload(text: String) -> Dictionary:
	return {
		"request_id": "wish-%06d" % cast_counter,
		"wish_text": text,
		"seed": cast_counter,
		"caster": {
			"id": "player",
			"position": {"x": genie.global_position.x / UNIT, "y": genie.global_position.y / UNIT},
			"velocity": {"x": 0.0, "y": 0.0},
			"facing": {"x": genie.facing.x, "y": genie.facing.y}
		},
		"world": {
			"objects": collect_world_snapshot(true),
			"level": current_level_document()
		},
		"options": {"debug": true}
	}


func collect_world_snapshot(full_world: bool = true) -> Array:
	var player_snapshot: Dictionary = player.get_snapshot(UNIT)
	var player_properties: Dictionary = player_snapshot.get("properties", {})
	player_properties["world_paused"] = world_paused
	player_properties["game_time_scale"] = world_time_scale
	player_properties["light_level"] = world_light_level
	player_properties["mission_status"] = "completed" if mission_complete else "active"
	player_properties["collected_loot_ids"] = collected_loot_ids()
	player_snapshot["properties"] = player_properties
	var objects: Array = [player_snapshot]
	for wall_id in arena_walls:
		objects.append(wall_snapshot(str(wall_id)))
	for door_id in level_doors:
		objects.append(door_snapshot(str(door_id)))
	if full_world or player.global_position.distance_to(water_position) <= snapshot_radius * UNIT + water_radius:
		objects.append(water_snapshot())
	for dwarf in dwarfs:
		if full_world or (dwarf.visible and player.global_position.distance_to(dwarf.global_position) <= snapshot_radius * UNIT):
			objects.append(dwarf.get_snapshot(UNIT))
	for npc in npcs:
		if full_world or (npc.visible and player.global_position.distance_to(npc.global_position) <= snapshot_radius * UNIT):
			objects.append(npc.get_snapshot(UNIT))
	for prop in props:
		if full_world or (prop.visible and player.global_position.distance_to(prop.global_position) <= snapshot_radius * UNIT):
			objects.append(prop.get_snapshot(UNIT))
	return objects


func current_level_document() -> Dictionary:
	var document: Dictionary = level_definition.duplicate(true)
	document["runtime"] = {
		"mission": mission_snapshot(),
		"world_paused": world_paused,
		"game_time_scale": world_time_scale,
		"light_level": world_light_level
	}
	return document


func serialize_world_document() -> Dictionary:
	return {
		"schema_version": 1,
		"level": current_level_document(),
		"world": {"objects": collect_world_snapshot(true)},
		"mission": mission_snapshot()
	}


func collected_loot_ids() -> Array[String]:
	var ids: Array[String] = []
	for prop in props:
		if prop.is_heist_loot() and prop.collected:
			ids.append(str(prop.object_id))
	ids.sort()
	return ids


func mission_snapshot() -> Dictionary:
	var mission: Dictionary = level_definition.get("mission", {}).duplicate(true)
	mission["collected_loot_ids"] = collected_loot_ids()
	mission["status"] = "completed" if mission_complete else "active"
	mission["loot_total"] = loot_total
	mission["loot_collected"] = loot_collected
	return mission


func wall_snapshot(wall_id: String) -> Dictionary:
	var entry: Dictionary = arena_walls[wall_id]
	var wall: Rect2 = entry["rect"]
	return {
		"id": wall_id,
		"kind": "structure",
		"tags": ["wall", "structure", "inanimate", "stone"],
		"position": {"x": wall.get_center().x / UNIT, "y": wall.get_center().y / UNIT},
		"velocity": {"x": 0.0, "y": 0.0},
		"radius": maxf(wall.size.x, wall.size.y) * 0.5 / UNIT,
		"material": {
			"name": "stone", "mass": 20.0, "temperature": 0.5,
			"wetness": 0.0, "flammability": 0.0, "conductivity": 0.1,
			"hardness": 0.95, "brittleness": 0.25
		},
		"states": [],
		"properties": {
			"door_installed": bool(entry.get("door_installed", false)),
			"width": wall.size.x / UNIT,
			"height": wall.size.y / UNIT
		}
	}


func door_snapshot(door_id: String) -> Dictionary:
	var entry: Dictionary = level_doors[door_id]
	var definition: Dictionary = entry.get("definition", {})
	var rect: Rect2 = entry["rect"]
	var tags: Array = ["door", "structure", "inanimate", str(definition.get("material", "metal"))]
	if bool(entry.get("locked", false)):
		tags.append("locked")
	if bool(definition.get("extraction", false)):
		tags.append_array(["exit", "extraction"])
	return {
		"id": door_id,
		"kind": "door",
		"tags": tags,
		"position": {"x": rect.get_center().x / UNIT, "y": rect.get_center().y / UNIT},
		"velocity": {"x": 0.0, "y": 0.0},
		"radius": maxf(rect.size.x, rect.size.y) * 0.5 / UNIT,
		"health": 100.0,
		"material": {"name": "metal", "mass": 8.0, "temperature": 0.5, "wetness": 0.0, "flammability": 0.0, "conductivity": 0.8, "hardness": 0.85, "brittleness": 0.2},
		"states": [],
		"properties": {
			"prototype": "door",
			"locked": bool(entry.get("locked", false)),
			"open": bool(entry.get("open", false)),
			"extraction": bool(definition.get("extraction", false)),
			"connects": definition.get("connects", []),
			"width": rect.size.x / UNIT,
			"height": rect.size.y / UNIT
		}
	}


func water_snapshot() -> Dictionary:
	var tags := [water_state, "terrain", "surface"]
	if water_state in ["water", "steam"]:
		tags.append("wet")
	if water_state == "ice":
		tags.append("frozen")
	return {
		"id": "water_pool_01",
		"kind": "terrain",
		"tags": tags,
		"position": {"x": water_position.x / UNIT, "y": water_position.y / UNIT},
		"velocity": {"x": 0.0, "y": 0.0},
		"radius": water_radius / UNIT,
		"material": {
			"name": water_state, "mass": 1.0, "temperature": water_temperature,
			"wetness": 1.0 if water_state == "water" else 0.2,
			"flammability": 0.0, "conductivity": 0.65 if water_state == "water" else 0.25,
			"hardness": 0.75 if water_state == "ice" else 0.0,
			"brittleness": 0.8 if water_state == "ice" else 0.0
		},
		"states": []
	}


func _on_cast_request_completed(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or response_code not in [200, 202]:
		cast_failed("HTTP %d / result %d" % [response_code, result])
		return
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if typeof(parsed) != TYPE_DICTIONARY:
		cast_failed("invalid JSON response")
		return
	if wish_initial_response_at_ms == 0:
		wish_initial_response_at_ms = Time.get_ticks_msec()
	if parsed.has("job_id") and parsed.has("status"):
		handle_wish_job_response(parsed)
		return
	apply_spell_response(parsed)
	finish_cast_mode()
	connection_label.text = "Джин: желание исполнено"
	connection_label.modulate = Color("78e08f")


func handle_wish_job_response(payload: Dictionary) -> void:
	active_wish_job_id = str(payload.get("job_id", active_wish_job_id))
	var is_agentic_loop := bool(payload.get("agentic_loop", false))
	var status := str(payload.get("status", "failed"))
	if is_agentic_loop and status == "action_ready":
		var step_id := str(payload.get("step_id", ""))
		var action = payload.get("agent_action", {})
		if step_id.is_empty() or typeof(action) != TYPE_DICTIONARY:
			cast_failed("invalid agent step")
			return
		if step_id != active_agent_step_id:
			if wish_action_ready_at_ms == 0:
				wish_action_ready_at_ms = Time.get_ticks_msec()
			wish_server_action_ready_ms = payload.get("server_action_ready_ms")
			active_agent_step_id = step_id
			agent_step_feedback_pending = true
			connection_label.text = "Джин действует • шаг %d, попытка %d" % [int(action.get("sequence", 1)), int(payload.get("attempt", 1))]
			connection_label.modulate = Color("f5d76e")
			enqueue_agent_actions([action])
		return
	if is_agentic_loop and status == "completed":
		var completed_response = payload.get("result", {})
		if typeof(completed_response) != TYPE_DICTIONARY:
			cast_failed("invalid completed agent result")
			return
		last_debug = completed_response
		update_debug_panel()
		update_curse_display(completed_response.get("agent", {}).get("public_curses", []))
		finish_cast_mode()
		connection_label.text = "Джин: желание исполнено и проверено"
		connection_label.modulate = Color("78e08f")
		return
	var first_actions: Array = payload.get("first_actions", [])
	if not wish_first_action_received and not first_actions.is_empty():
		if wish_action_ready_at_ms == 0:
			wish_action_ready_at_ms = Time.get_ticks_msec()
		for action in first_actions:
			apply_agent_action(action)
			record_first_world_mutation()
	if status in ["running", "planning"]:
		wish_poll_timer.start(wish_poll_interval_seconds)
		return
	if status == "failed":
		cast_failed(str(payload.get("error", "agent job failed")))
		return
	var response = payload.get("result", {})
	if typeof(response) != TYPE_DICTIONARY:
		cast_failed("invalid completed job result")
		return
	var result_actions: Array = response.get("spell_plan", {}).get("world_actions", [])
	if not wish_first_action_received and not result_actions.is_empty() and wish_action_ready_at_ms == 0:
		wish_action_ready_at_ms = Time.get_ticks_msec()
	apply_spell_response(response)
	if not wish_first_action_received and not result_actions.is_empty() and response.get("agent", {}).get("actions", []).is_empty():
		record_first_world_mutation()
	waiting_for_backend = false
	wish_poll_timer.stop()
	active_wish_job_id = ""
	if agent_action_playing or not pending_agent_actions.is_empty():
		connection_label.text = "Джин воплощает задуманное…"
		connection_label.modulate = Color("f5d76e")
	else:
		genie.set_wish_state(false, false)
		var agent_actions: Array = response.get("agent", {}).get("actions", [])
		var conclusion_status := str(response.get("agent", {}).get("conclusion", {}).get("status", "completed"))
		if agent_actions.is_empty() and result_actions.is_empty():
			genie.ensure_visible_near_companion(1.0)
			connection_label.text = "Джин вернулся • желание не исполнено"
			connection_label.modulate = Color("ffb86b")
		elif conclusion_status == "impossible":
			genie.ensure_visible_near_companion(1.0)
			connection_label.text = "Джин: желание не удалось исполнить"
			connection_label.modulate = Color("ffb86b")
		else:
			connection_label.text = "Джин: желание исполнено"
			connection_label.modulate = Color("78e08f")
	hint_label.text = "WASD — движение    ЛКМ — удар оружием    SPACE — желание джину"


func _poll_wish_job() -> void:
	if not waiting_for_backend or active_wish_job_id.is_empty():
		return
	var url := backend_url + "/wish/jobs/" + active_wish_job_id
	if wish_first_action_received and not wish_client_ttfa_reported:
		url += "?client_ttfa_ms=%.3f" % last_client_ttfa_ms
		wish_client_ttfa_reported = true
	var error := cast_http.request(url, PackedStringArray(), HTTPClient.METHOD_GET)
	if error != OK:
		wish_client_ttfa_reported = false
		wish_poll_timer.start(wish_poll_interval_seconds)


func apply_spell_response(response: Dictionary) -> void:
	var plan: Dictionary = response.get("spell_plan", {})
	var agent_data: Dictionary = response.get("agent", {})
	var agent_actions: Array = agent_data.get("actions", [])
	if not agent_actions.is_empty():
		var queued_actions: Array = []
		var visuals: Array = plan.get("visuals", [])
		var visual_index := 0
		for raw_action in agent_actions:
			var queued_action: Dictionary = raw_action.duplicate(true)
			var world_action = queued_action.get("world_action")
			if typeof(world_action) == TYPE_DICTIONARY and not world_action.is_empty() and visual_index < visuals.size():
				queued_action["_visual_descriptor"] = visuals[visual_index].duplicate(true)
				visual_index += 1
			queued_actions.append(queued_action)
		enqueue_agent_actions(queued_actions)
		update_curse_display(agent_data.get("public_curses", []))
	else:
		for action in plan.get("world_actions", []):
			apply_world_action(action)
		for descriptor in plan.get("visuals", []):
			spawn_visual(descriptor)
	last_debug = response
	update_debug_panel()


func apply_agent_action(agent_action: Dictionary) -> void:
	if str(agent_action.get("kind", "")) == "observe_area":
		genie.acknowledge_wish()
	var target_id := str(agent_action.get("target_id", ""))
	if bool(agent_action.get("teleport_to_target", false)) and object_index.has(target_id) and is_instance_valid(object_index[target_id]):
		genie.appear_at_interaction(object_index[target_id].global_position)
	elif bool(agent_action.get("teleport_to_target", false)) and target_id == "water_pool_01":
		genie.appear_at_interaction(water_position)
	var world_action = agent_action.get("world_action")
	if typeof(world_action) == TYPE_DICTIONARY and not world_action.is_empty():
		apply_world_action(world_action)


func enqueue_agent_actions(actions: Array) -> void:
	for action in actions:
		pending_agent_actions.append(action)
	if not agent_action_playing:
		play_agent_action_sequence()


func record_first_world_mutation() -> void:
	if wish_first_action_received or wish_submitted_at_ms <= 0:
		return
	var mutation_at_ms := Time.get_ticks_msec()
	if wish_initial_response_at_ms == 0:
		wish_initial_response_at_ms = mutation_at_ms
	if wish_action_ready_at_ms == 0:
		wish_action_ready_at_ms = mutation_at_ms
	wish_first_action_received = true
	last_client_ttfa_ms = float(mutation_at_ms - wish_submitted_at_ms)
	last_wish_timing = {
		"submit_to_initial_response_ms": float(wish_initial_response_at_ms - wish_submitted_at_ms),
		"submit_to_action_ready_ms": float(wish_action_ready_at_ms - wish_submitted_at_ms),
		"action_ready_to_mutation_ms": float(mutation_at_ms - wish_action_ready_at_ms),
		"client_ttfa_ms": last_client_ttfa_ms,
	}
	if wish_server_action_ready_ms != null:
		last_wish_timing["server_action_ready_ms"] = float(wish_server_action_ready_ms)
	connection_label.text = "Мир изменён • %.0f мс" % last_client_ttfa_ms
	connection_label.modulate = Color("78e08f") if last_client_ttfa_ms <= 2000.0 else Color("ff8f8f")


func play_agent_action_sequence() -> void:
	agent_action_playing = true
	genie.set_wish_state(true, true)
	while not pending_agent_actions.is_empty():
		var agent_action: Dictionary = pending_agent_actions.pop_front()
		var target_position := agent_action_target_position(agent_action)
		var has_target := target_position != Vector2.INF
		var action_delay := 0.0
		if has_target and bool(agent_action.get("teleport_to_target", false)):
			action_delay = genie.appear_at_interaction(target_position, 1.0)
			await get_tree().create_timer(action_delay, true, false, true).timeout
		var visual: Dictionary = prepare_agent_action_visual(agent_action, target_position, has_target)
		if not visual.is_empty():
			spawn_visual(visual)
		apply_agent_action_without_teleport(agent_action)
		record_first_world_mutation()
		if has_target and bool(agent_action.get("teleport_to_target", false)):
			await get_tree().create_timer(maxf(0.0, 1.0 - action_delay), true, false, true).timeout
		else:
			await get_tree().create_timer(0.18, true, false, true).timeout
	if agent_step_feedback_pending:
		agent_action_playing = false
		submit_agent_step_feedback()
		return
	if genie.is_dissolved():
		genie.reappear_near_companion(1.0)
		await get_tree().create_timer(1.0, true, false, true).timeout
	agent_action_playing = false
	genie.set_wish_state(false, false)
	connection_label.text = "Джин: желание исполнено"
	connection_label.modulate = Color("78e08f")


func submit_agent_step_feedback() -> void:
	if active_wish_job_id.is_empty() or active_agent_step_id.is_empty():
		cast_failed("agent step lost before verification")
		return
	agent_step_feedback_pending = false
	connection_label.text = "Джин проверяет, сработала ли магия…"
	connection_label.modulate = Color("a8edff")
	var payload := {
		"step_id": active_agent_step_id,
		"applied": true,
		"observation": "Клиент применил действие и сделал новый снимок мира",
		"world": {
			"objects": collect_world_snapshot(true),
			"level": current_level_document()
		},
		"client_ttfa_ms": last_client_ttfa_ms if wish_first_action_received else null,
		"client_timing": last_wish_timing if wish_first_action_received else null,
		"client_timing_profile": ttfa_observation_profile
	}
	var headers := PackedStringArray(["Content-Type: application/json"])
	var url := backend_url + "/wish/jobs/" + active_wish_job_id + "/feedback"
	var error := cast_http.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		agent_step_feedback_pending = true
		cast_failed("agent feedback could not start")


func agent_action_target_position(agent_action: Dictionary) -> Vector2:
	var target_id := str(agent_action.get("target_id", ""))
	if object_index.has(target_id) and is_instance_valid(object_index[target_id]):
		return object_index[target_id].global_position
	if target_id == "water_pool_01":
		return water_position
	return Vector2.INF


func prepare_agent_action_visual(agent_action: Dictionary, target_position: Vector2, has_target: bool) -> Dictionary:
	var raw_visual = agent_action.get("_visual_descriptor")
	if typeof(raw_visual) != TYPE_DICTIONARY or raw_visual.is_empty():
		return {}
	var visual: Dictionary = raw_visual.duplicate(true)
	visual["origin"] = {
		"x": genie.global_position.x / UNIT,
		"y": genie.global_position.y / UNIT,
	}
	if has_target:
		visual["target"] = {
			"x": target_position.x / UNIT,
			"y": target_position.y / UNIT,
		}
	return visual


func apply_agent_action_without_teleport(agent_action: Dictionary) -> void:
	if str(agent_action.get("kind", "")) == "observe_area":
		genie.acknowledge_wish()
	var world_action = agent_action.get("world_action")
	if typeof(world_action) == TYPE_DICTIONARY and not world_action.is_empty():
		apply_world_action(world_action)


func update_curse_display(curses: Array) -> void:
	if curses.is_empty():
		curse_label.text = "ПРОКЛЯТИЯ ДЖИНА: нет видимых признаков"
		return
	var names: Array[String] = []
	for curse in curses:
		names.append("%s  —  %s" % [str(curse.get("title", "Неизвестный знак")), str(curse.get("public_hint", ""))])
	curse_label.text = "ПРОКЛЯТИЯ ДЖИНА: " + "  •  ".join(names)


func apply_world_action(action: Dictionary) -> void:
	var action_type := str(action.get("type", ""))
	if action_type == "SET_GAME_PAUSED":
		world_paused = bool(action.get("effect", {}).get("paused", true))
		restore_world_time_scale()
		connection_label.text = "Время остановлено" if world_paused else "Время снова идёт"
		connection_label.modulate = Color("a8edff")
		return
	if action_type == "SET_GAME_SPEED":
		world_time_scale = clampf(float(action.get("effect", {}).get("multiplier", 1.0)), 0.1, 3.0)
		world_paused = false
		restore_world_time_scale()
		connection_label.text = "Скорость мира: %.1fx" % world_time_scale
		connection_label.modulate = Color("a8edff")
		return
	if action_type == "SET_LIGHT_LEVEL":
		world_light_level = clampf(float(action.get("effect", {}).get("level", 1.0)), 0.1, 2.0)
		update_world_light_overlay()
		connection_label.text = "Освещённость мира: %.1f" % world_light_level
		connection_label.modulate = Color("ffe59a")
		return
	if action_type == "CREATE_OBJECT_BATCH":
		var batch_effect: Dictionary = action.get("effect", {})
		var count := clampi(int(batch_effect.get("count", 1)), 1, 32)
		for _index in range(count):
			spawn_created_object({
				"type": "CREATE_OBJECT",
				"target_id": action.get("target_id", "player"),
				"effect": {"prototype": batch_effect.get("prototype", "object")}
			})
		return
	if action_type == "DESTROY_OBJECTS":
		var destroy_effect: Dictionary = action.get("effect", {})
		for destroy_id in destroy_effect.get("target_ids", []):
			var object_id := str(destroy_id)
			if level_doors.has(object_id):
				set_level_door_open(object_id, true)
			elif object_index.has(object_id) and is_instance_valid(object_index[object_id]) and object_index[object_id].has_method("apply_world_action"):
				object_index[object_id].apply_world_action({"type": "DESTROY_OBJECT"}, UNIT)
		return
	if action_type == "SHUTDOWN_GAME":
		shutdown_requested = true
		player.apply_world_action({"type": "ADD_STATE", "state": "game_shutdown", "duration": 120.0}, UNIT)
		player.movement_enabled = false
		connection_label.text = "Джин выключает игру…"
		connection_label.modulate = Color("ff9b8f")
		var shutdown_timer := get_tree().create_timer(2.5, true, false, true)
		shutdown_timer.timeout.connect(func(): get_tree().quit())
		return
	if action_type == "INSTALL_DOORS":
		var effect: Dictionary = action.get("effect", {})
		var wall_ids: Array = effect.get("wall_ids", [])
		if wall_ids.is_empty():
			wall_ids = arena_walls.keys()
		var installed_count := 0
		for wall_id in wall_ids:
			if install_door_in_wall(str(wall_id)):
				installed_count += 1
		connection_label.text = "Джин прорезал двери в стенах: %d" % installed_count
		connection_label.modulate = Color("78e08f")
		return
	if action_type == "SPAWN_EFFECT_ENTITY":
		spawn_runtime_effect(action.get("effect", {}))
		return
	if action_type == "CREATE_OBJECT":
		spawn_created_object(action)
		return
	if action_type == "ADD_INVENTORY_ITEM":
		player.apply_world_action(action, UNIT)
		connection_label.text = "В рюкзаке появился предмет: %s" % str(action.get("effect", {}).get("prototype", "item"))
		connection_label.modulate = Color("78e08f")
		return
	var target_id := str(action.get("target_id", ""))
	if action_type == "INTERACT" and level_doors.has(target_id):
		set_level_door_open(target_id, true)
		connection_label.text = "Джин открыл дверь: %s" % target_id
		connection_label.modulate = Color("78e08f")
		update_heist_state()
		return
	if action_type == "INTERACT" and object_index.has(target_id) and is_instance_valid(object_index[target_id]):
		var interaction_target = object_index[target_id]
		if interaction_target.has_method("collect_loot") and interaction_target.collect_loot():
			loot_collected = collected_loot_ids().size()
			connection_label.text = "Джин забрал ценность: %s" % target_id
			connection_label.modulate = Color("78e08f")
			update_heist_state()
			return
	if target_id == "water_pool_01":
		match action_type:
			"CHANGE_TEMPERATURE":
				water_temperature += float(action.get("amount", 0.0))
			"CHANGE_MATERIAL_STATE":
				water_state = str(action.get("material", water_state))
			"ADD_STATE":
				if str(action.get("state", "")) == "frozen":
					water_state = "ice"
			"SPEAK":
				show_spoken_action(action)
		return
	if action_type == "SPEAK":
		show_spoken_action(action)
	if action_type == "SET_AGGRO_TARGET":
		var actor_id := str(action.get("target_id", ""))
		var aggro_id := str(action.get("effect", {}).get("aggro_target", "player"))
		if object_index.has(actor_id) and object_index.has(aggro_id):
			var actor = object_index[actor_id]
			if "target" in actor:
				actor.target = object_index[aggro_id]
	if object_index.has(target_id) and is_instance_valid(object_index[target_id]) and object_index[target_id].has_method("apply_world_action"):
		object_index[target_id].apply_world_action(action, UNIT)


func spawn_created_object(action: Dictionary) -> void:
	var effect: Dictionary = action.get("effect", {})
	var prototype := str(effect.get("prototype", "object")).to_lower().replace(" ", "_")
	var target_id := str(action.get("target_id", "player"))
	var target_position := player.global_position
	if target_id == "water_pool_01":
		target_position = water_position
	elif object_index.has(target_id) and is_instance_valid(object_index[target_id]):
		target_position = object_index[target_id].global_position
	created_object_counter += 1
	var created := WorldPropScript.new()
	var created_id := "created_%03d" % created_object_counter
	var angle := float(created_object_counter % 10) / 10.0 * TAU
	var ring := float((created_object_counter - 1) / 10)
	created.setup(created_id, prototype, target_position + Vector2.from_angle(angle) * (46.0 + ring * 42.0), player)
	add_child(created)
	props.append(created)
	object_index[created_id] = created


func show_spoken_action(action: Dictionary) -> void:
	var effect: Dictionary = action.get("effect", {})
	var message := str(effect.get("message", "…"))
	genie.show_speech(message)
	connection_label.text = "Джин говорит: %s" % message
	connection_label.modulate = Color("b9f4ff")


func spawn_visual(descriptor: Dictionary) -> void:
	var effect := MagicEffectScript.new()
	effect.setup(descriptor, UNIT)
	add_child(effect)


func spawn_runtime_effect(effect_data: Dictionary) -> void:
	if effect_data.is_empty():
		return
	var runtime_effect := RuntimeEffectScript.new()
	runtime_effect.setup(effect_data, UNIT, self, runtime_contact_interval)
	add_child(runtime_effect)


func get_runtime_candidates() -> Array:
	var candidates: Array = [
		{"id": "player", "position": player.global_position, "radius": 18.0}
	]
	for dwarf in dwarfs:
		if dwarf.visible:
			candidates.append({"id": dwarf.object_id, "position": dwarf.global_position, "radius": 16.0})
	for npc in npcs:
		if npc.visible:
			candidates.append({"id": npc.object_id, "position": npc.global_position, "radius": 16.0})
	for prop in props:
		if prop.visible:
			candidates.append({"id": prop.object_id, "position": prop.global_position, "radius": 20.0})
	if water_state != "steam":
		candidates.append({"id": "water_pool_01", "position": water_position, "radius": water_radius})
	return candidates


func apply_runtime_payload(target_id: String, payload: Dictionary, direction: Vector2) -> void:
	var snapshot: Dictionary
	if target_id == "water_pool_01":
		snapshot = water_snapshot()
	elif object_index.has(target_id) and is_instance_valid(object_index[target_id]):
		snapshot = object_index[target_id].get_snapshot(UNIT)
	else:
		return
	var material: Dictionary = snapshot.get("material", {})
	var tags: Array = snapshot.get("tags", [])
	var reactions: Dictionary = runtime_world_config.get("reactions", {})
	var heat_config: Dictionary = reactions.get("heat", {"temperature_delta": 0.52})
	var cold_config: Dictionary = reactions.get("cold", {"temperature_delta": 0.52, "living_freeze_strength": 0.85})
	var phases: Dictionary = reactions.get("phase_changes", {"water_freezes_at": 0.25, "water_boils_at": 0.8})
	var burning: Dictionary = reactions.get("burning", {"flammability_threshold": 0.3, "ignition_strength": 0.35, "duration": 5.0})
	var electricity_config: Dictionary = reactions.get("electricity", {"wetness_threshold": 0.5, "wet_conductivity_multiplier": 2.0, "base_damage": 5.0, "conductivity_damage": 14.0, "state_duration": 1.6})
	var force_config: Dictionary = reactions.get("force", {"base_strength": 4.5})
	var harm_config: Dictionary = reactions.get("harm", {"base_damage": 18.0})
	var poison_config: Dictionary = reactions.get("poison", {"duration": 5.0})
	var power := float(payload.get("power", 1.0))
	var heat := float(payload.get("heat", 0.0))
	var cold := float(payload.get("cold", 0.0))
	var electricity := float(payload.get("electricity", 0.0))
	var force := float(payload.get("force", 0.0))
	var harm := float(payload.get("harm", 0.0))
	var poison := float(payload.get("poison", 0.0))
	if heat > 0.08:
		apply_world_action({"type": "CHANGE_TEMPERATURE", "target_id": target_id, "amount": heat * power * float(heat_config.get("temperature_delta", 0.52))})
		if float(material.get("flammability", 0.0)) >= float(burning.get("flammability_threshold", 0.3)) and heat * power >= float(burning.get("ignition_strength", 0.35)):
			apply_world_action({"type": "ADD_STATE", "target_id": target_id, "state": "burning", "duration": float(burning.get("duration", 5.0))})
		if tags.has("living"):
			apply_world_action({"type": "DAMAGE", "target_id": target_id, "amount": float(heat_config.get("living_damage", 12.0)) * heat * power})
	if cold > 0.08:
		apply_world_action({"type": "CHANGE_TEMPERATURE", "target_id": target_id, "amount": -cold * power * float(cold_config.get("temperature_delta", 0.52))})
		if tags.has("living"):
			apply_world_action({"type": "ADD_STATE", "target_id": target_id, "state": "slowed", "duration": float(cold_config.get("slowed_duration", 3.0))})
			if cold * power >= float(cold_config.get("living_freeze_strength", 0.85)):
				apply_world_action({"type": "ADD_STATE", "target_id": target_id, "state": "frozen", "duration": float(cold_config.get("frozen_duration", 1.6))})
	if electricity > 0.08:
		var conductivity := float(material.get("conductivity", 0.0))
		if float(material.get("wetness", 0.0)) >= float(electricity_config.get("wetness_threshold", 0.5)) or tags.has("water"):
			conductivity *= float(electricity_config.get("wet_conductivity_multiplier", 2.0))
		apply_world_action({"type": "DAMAGE", "target_id": target_id, "amount": (float(electricity_config.get("base_damage", 5.0)) + float(electricity_config.get("conductivity_damage", 14.0)) * clampf(conductivity, 0.0, 1.0)) * electricity * power})
		apply_world_action({"type": "ADD_STATE", "target_id": target_id, "state": "electrified", "duration": float(electricity_config.get("state_duration", 1.6))})
	if force > 0.08:
		var strength := force * power * float(force_config.get("base_strength", 4.5)) / maxf(0.15, float(material.get("mass", 1.0)))
		apply_world_action({"type": "APPLY_FORCE", "target_id": target_id, "direction": {"x": direction.x, "y": direction.y}, "strength": strength})
	if harm > 0.08:
		apply_world_action({"type": "DAMAGE", "target_id": target_id, "amount": float(harm_config.get("base_damage", 18.0)) * harm * power})
	if poison > 0.08 and tags.has("living"):
		apply_world_action({"type": "ADD_STATE", "target_id": target_id, "state": "poisoned", "duration": float(poison_config.get("duration", 5.0))})
	if target_id == "water_pool_01":
		if water_state == "water" and water_temperature <= float(phases.get("water_freezes_at", 0.25)):
			water_state = "ice"
		elif water_state == "water" and water_temperature >= float(phases.get("water_boils_at", 0.8)):
			water_state = "steam"


func cast_failed(reason: String) -> void:
	spawn_visual({
		"primitive": "BURST", "appearance": ["force", "darkness"],
		"origin": {"x": genie.global_position.x / UNIT, "y": genie.global_position.y / UNIT},
		"direction": {"x": genie.facing.x, "y": genie.facing.y},
		"radius": 0.65, "speed": 0.0, "intensity": 0.35, "turbulence": 0.9, "lifetime": 0.65
	})
	last_debug = {"error": reason, "wish_text": last_spell_text}
	update_debug_panel()
	finish_cast_mode()
	connection_label.text = "Джин не смог исполнить желание"
	connection_label.modulate = Color("ff8f8f")


func finish_cast_mode() -> void:
	if is_instance_valid(wish_poll_timer):
		wish_poll_timer.stop()
	active_wish_job_id = ""
	active_agent_step_id = ""
	agent_step_feedback_pending = false
	pending_agent_actions.clear()
	agent_action_playing = false
	restore_world_time_scale()
	casting = false
	waiting_for_backend = false
	player.movement_enabled = not world_paused
	genie.set_wish_state(false, false)
	genie.ensure_visible_near_companion(1.0)
	cast_tint.color = Color(0.06, 0.42, 0.43, 0.0)
	cast_label.visible = false
	cast_label.text = "ЖЕЛАНИЕ ДЖИНУ  •  только текст, затем ENTER"
	spell_input.visible = false
	spell_input.editable = true
	spell_input.release_focus()
	hint_label.text = "WASD — движение    ЛКМ — удар оружием    SPACE — желание джину"
	queue_redraw()


func update_debug_panel() -> void:
	if not is_instance_valid(debug_text):
		return
	if last_debug.is_empty():
		debug_text.text = "[b]GENIE WISH VIEW[/b]\n\nПопросите джина исполнить первое желание.\n\nЗдесь появятся смысловые якоря, цели, правила мира и задержка REST."
		return
	if last_debug.has("error"):
		debug_text.text = "[b][color=#ff8f8f]ДЖИН НЕ СПРАВИЛСЯ[/color][/b]\n\n%s\n\nПоследнее желание: %s" % [last_debug["error"], last_debug.get("wish_text", "")]
		return
	var interpretation: Dictionary = last_debug.get("interpretation", {})
	var lines: Array[String] = []
	lines.append("[b]GENIE WISH VIEW[/b]")
	lines.append("\n[b]Желание[/b]\n\"%s\"" % last_spell_text)
	lines.append("\n[b]Coherence[/b]  %.3f" % float(interpretation.get("coherence", 0.0)))
	lines.append("\n[b]Top anchors[/b]")
	for anchor in interpretation.get("anchors", []).slice(0, 10):
		lines.append("%-16s %.3f" % [str(anchor.get("id", "")), float(anchor.get("score", 0.0))])
	var debug: Dictionary = last_debug.get("debug", {})
	var intent: Dictionary = debug.get("intent", {})
	lines.append("\n[b]WishIntent[/b]")
	lines.append("matter    %s" % JSON.stringify(intent.get("matter", {})))
	lines.append("actions   %s" % JSON.stringify(intent.get("actions", {})))
	lines.append("movement  %s" % JSON.stringify(intent.get("movement", {})))
	lines.append("geometry  %s" % JSON.stringify(intent.get("geometry", {})))
	lines.append("\n[b]Targets[/b]  %s" % ", ".join(debug.get("selected_targets", [])))
	lines.append("\n[b]World rules[/b]")
	for rule in debug.get("world_rules", []):
		lines.append("• %s" % str(rule))
	lines.append("\n[b]Real time to first world action[/b]  %.2f ms" % last_client_ttfa_ms)
	lines.append("[b]REST latency[/b]  %.2f ms" % float(debug.get("latency_ms", 0.0)))
	debug_text.text = "\n".join(lines)


func restore_world_time_scale() -> void:
	Engine.time_scale = 0.0 if world_paused else world_time_scale


func update_world_light_overlay() -> void:
	if not is_instance_valid(world_light_overlay):
		return
	if world_light_level < 1.0:
		world_light_overlay.color = Color(0.0, 0.015, 0.035, clampf((1.0 - world_light_level) * 0.82, 0.0, 0.76))
	elif world_light_level > 1.0:
		world_light_overlay.color = Color(1.0, 0.93, 0.68, clampf((world_light_level - 1.0) * 0.24, 0.0, 0.3))
	else:
		world_light_overlay.color = Color(0.0, 0.0, 0.0, 0.0)


func reset_sandbox() -> void:
	water_state = initial_water_state
	water_temperature = initial_water_temperature
	reset_arena_doors()
	reset_level_doors()
	player.health = 100.0
	player.temperature = 0.5
	player.wetness = 0.0
	player.inventory.clear()
	player.outfit = ""
	player.global_position = player_start_position
	genie.snap_to_companion()
	player.states.clear()
	for dwarf in dwarfs:
		dwarf.reset_actor()
	for npc in npcs:
		npc.reset_actor()
	for prop in props.duplicate():
		if str(prop.object_id).begins_with("created_"):
			object_index.erase(prop.object_id)
			props.erase(prop)
			prop.queue_free()
			continue
		prop.reset_prop()
	created_object_counter = 0
	loot_collected = 0
	alarm_level = 0.0
	mission_complete = false
	shutdown_requested = false
	world_paused = false
	world_time_scale = 1.0
	world_light_level = 1.0
	restore_world_time_scale()
	update_world_light_overlay()
	player.movement_enabled = true
	connection_label.text = "Мир и джин готовы"
	connection_label.modulate = Color("d9e5e8")


func _draw() -> void:
	draw_rect(ARENA, Color("071722"))
	var fallback_font := ThemeDB.fallback_font
	for room_index in range(ROOMS.size()):
		var room: Rect2 = ROOMS[room_index]
		var room_color: Color = ROOM_COLORS[room_index]
		draw_rect(room, room_color)
		draw_rect(room, room_color.lightened(0.38), false, 3.0)
		draw_room_pattern(room, ROOM_PATTERNS[room_index] if room_index < ROOM_PATTERNS.size() else "grid", room_color.lightened(0.28))
		draw_string(fallback_font, room.position + Vector2(12, 21), ROOM_NAMES[room_index], HORIZONTAL_ALIGNMENT_LEFT, room.size.x - 24.0, 12, Color(0.88, 0.96, 0.94, 0.58))
	for x in range(int(ARENA.position.x), int(ARENA.end.x), int(UNIT)):
		draw_line(Vector2(x, ARENA.position.y), Vector2(x, ARENA.end.y), Color(0.2, 0.75, 0.72, 0.07), 1.0)
	for y in range(int(ARENA.position.y), int(ARENA.end.y), int(UNIT)):
		draw_line(Vector2(ARENA.position.x, y), Vector2(ARENA.end.x, y), Color(0.2, 0.75, 0.72, 0.07), 1.0)
	draw_rect(EXTRACTION_ZONE, Color(0.15, 0.9, 0.62, 0.16))
	draw_rect(EXTRACTION_ZONE, Color("65f0b0"), false, 3.0)
	for wall_index in range(WALLS.size()):
		var wall: Rect2 = WALLS[wall_index]
		draw_rect(wall, Color("061017"))
		draw_rect(wall.grow(-3.0), Color("327985"), false, 2.0)
		var wall_id := WALL_IDS[wall_index]
		if arena_walls.has(wall_id) and bool(arena_walls[wall_id].get("door_installed", false)):
			var doorway := wall_door_rect(wall)
			draw_rect(doorway, Color("102a33"))
			draw_rect(doorway.grow(-2.0), Color("e1b45d"), false, 3.0)
			if wall.size.x >= wall.size.y:
				draw_line(Vector2(doorway.position.x + 4.0, doorway.get_center().y), Vector2(doorway.end.x - 4.0, doorway.get_center().y), Color("73e6df"), 2.0)
			else:
				draw_line(Vector2(doorway.get_center().x, doorway.position.y + 4.0), Vector2(doorway.get_center().x, doorway.end.y - 4.0), Color("73e6df"), 2.0)
	for door_id in level_doors:
		draw_level_door(str(door_id))
	match water_state:
		"ice":
			draw_circle(water_position, water_radius, Color(0.48, 0.85, 0.94, 0.74))
			for index in range(7):
				var angle := float(index) / 7.0 * TAU
				draw_line(water_position + Vector2.from_angle(angle) * 12.0, water_position + Vector2.from_angle(angle + 0.32) * (water_radius - 8.0), Color(0.86, 0.98, 1.0, 0.55), 2.0)
		"steam":
			draw_circle(water_position, water_radius, Color(0.55, 0.66, 0.69, 0.18))
			for index in range(9):
				var angle := float(index) / 9.0 * TAU
				draw_circle(water_position + Vector2.from_angle(angle) * water_radius * 0.55, 28.0, Color(0.85, 0.9, 0.92, 0.2))
		_:
			draw_circle(water_position, water_radius, Color(0.12, 0.5, 0.72, 0.68))
			draw_arc(water_position, water_radius - 6.0, 0.0, TAU, 48, Color(0.45, 0.82, 1.0, 0.42), 3.0)
	draw_string(fallback_font, EXTRACTION_ZONE.position + Vector2(7, -8), "ВЫХОД", HORIZONTAL_ALIGNMENT_LEFT, 80, 14, Color("8affc5"))
	draw_string(fallback_font, water_position + Vector2(-42, 5), water_state.to_upper(), HORIZONTAL_ALIGNMENT_CENTER, 84, 14, Color(0.88, 0.96, 1.0, 0.62))


func draw_room_pattern(room: Rect2, pattern: String, accent: Color) -> void:
	var ink := Color(accent, 0.13)
	match pattern:
		"wood":
			for y in range(int(room.position.y + 30.0), int(room.end.y), 24):
				draw_line(Vector2(room.position.x, y), Vector2(room.end.x, y), ink, 1.0)
		"marble":
			for x in range(int(room.position.x - room.size.y), int(room.end.x), 48):
				draw_line(Vector2(x, room.end.y), Vector2(x + room.size.y, room.position.y), ink, 1.0)
		"carpet":
			draw_rect(room.grow(-14.0), Color(accent, 0.08))
			draw_rect(room.grow(-18.0), Color(accent, 0.25), false, 2.0)
		"files":
			for x in range(int(room.position.x + 22.0), int(room.end.x - 12.0), 34):
				draw_line(Vector2(x, room.position.y + 34.0), Vector2(x, room.end.y - 12.0), ink, 3.0)
		"tech":
			for y in range(int(room.position.y + 38.0), int(room.end.y), 38):
				draw_line(Vector2(room.position.x + 14.0, y), Vector2(room.end.x - 14.0, y), ink, 1.0)
		"vault":
			for y in range(int(room.position.y + 34.0), int(room.end.y), 32):
				for x in range(int(room.position.x + 20.0), int(room.end.x), 40):
					draw_circle(Vector2(x, y), 2.0, ink)
		"garden":
			for x in range(int(room.position.x + 28.0), int(room.end.x), 46):
				draw_arc(Vector2(x, room.end.y - 14.0), 16.0, PI, TAU, 8, ink, 2.0)
		_:
			pass


func draw_level_door(door_id: String) -> void:
	var entry: Dictionary = level_doors[door_id]
	var rect: Rect2 = entry["rect"]
	var opened := bool(entry.get("open", false))
	var locked := bool(entry.get("locked", false))
	if opened:
		draw_rect(rect, Color("071722"))
		draw_line(rect.position, rect.end, Color("65f0b0"), 2.0)
		return
	draw_rect(rect, Color("d9a93d") if not locked else Color("d45d68"))
	draw_rect(rect.grow(-3.0), Color("3a2c25") if not locked else Color("401d2b"))
	var center := rect.get_center()
	draw_circle(center, 2.5, Color("fff1a8"))


func try_weapon_attack() -> void:
	if casting or not player.start_weapon_swing():
		return
	var direction: Vector2 = player.facing.normalized()
	var hit_count := 0
	for dwarf in dwarfs:
		if not dwarf.visible:
			continue
		var offset: Vector2 = dwarf.global_position - player.global_position
		var distance := offset.length()
		if distance > WEAPON_RANGE + 16.0 or distance <= 0.001:
			continue
		if offset.normalized().dot(direction) < WEAPON_ARC_DOT:
			continue
		dwarf.apply_world_action({
			"type": "APPLY_FORCE",
			"direction": {"x": direction.x, "y": direction.y},
			"strength": WEAPON_KNOCKBACK
		}, UNIT)
		dwarf.apply_world_action({"type": "DAMAGE", "amount": WEAPON_DAMAGE}, UNIT)
		hit_count += 1
	if hit_count > 0:
		connection_label.text = "Оружие: попадание"
		connection_label.modulate = Color("ffd27a")


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		Engine.time_scale = 1.0
		get_tree().quit()
