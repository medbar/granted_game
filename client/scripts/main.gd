extends Node2D

const UNIT := 64.0
const GAMEPLAY_CONFIG_PATH := "res://config/gameplay.json"
const PlayerScript = preload("res://scripts/player.gd")
const DwarfScript = preload("res://scripts/dwarf.gd")
const WorldPropScript = preload("res://scripts/world_prop.gd")
const MagicEffectScript = preload("res://scripts/magic_effect.gd")
const RuntimeEffectScript = preload("res://scripts/runtime_effect.gd")

const ARENA := Rect2(-600.0, -330.0, 1200.0, 660.0)
const WALLS := [
	Rect2(-600, -350, 1200, 20), Rect2(-600, 330, 1200, 20),
	Rect2(-620, -350, 20, 700), Rect2(600, -350, 20, 700),
	Rect2(-185, -145, 32, 210), Rect2(110, -265, 250, 30),
	Rect2(315, 55, 30, 190), Rect2(-430, 185, 205, 28)
]

var player: CharacterBody2D
var dwarfs: Array[CharacterBody2D] = []
var props: Array[CharacterBody2D] = []
var object_index: Dictionary = {}
var water_state := "water"
var water_temperature := 0.5
var water_position := Vector2(210, 120)
var water_radius := 92.0

var casting := false
var waiting_for_backend := false
var drawing_gesture := false
var cast_counter := 0
var cast_started_ms := 0
var gesture_strokes: Array = []
var current_stroke: Array = []
var debug_enabled := false
var last_debug: Dictionary = {}
var last_spell_text := ""
var gameplay_config: Dictionary = {}
var runtime_world_config: Dictionary = {}
var backend_url := "http://127.0.0.1:8000"
var cast_time_scale := 0.35
var snapshot_radius := 12.0
var max_gesture_points := 256
var request_timeout_seconds := 2.0
var runtime_contact_interval := 0.4

var cast_http: HTTPRequest
var health_http: HTTPRequest
var config_http: HTTPRequest
var ui_layer: CanvasLayer
var cast_tint: ColorRect
var health_label: Label
var connection_label: Label
var hint_label: Label
var cast_label: Label
var spell_input: LineEdit
var debug_panel: Panel
var debug_text: RichTextLabel


func _ready() -> void:
	load_gameplay_config()
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
	max_gesture_points = int(gameplay_config.get("max_gesture_points", max_gesture_points))
	request_timeout_seconds = float(gameplay_config.get("request_timeout_seconds", request_timeout_seconds))
	runtime_contact_interval = float(gameplay_config.get("runtime_contact_interval", runtime_contact_interval))


func create_arena() -> void:
	for wall in WALLS:
		var body := StaticBody2D.new()
		body.position = wall.get_center()
		var collision := CollisionShape2D.new()
		var shape := RectangleShape2D.new()
		shape.size = wall.size
		collision.shape = shape
		body.add_child(collision)
		add_child(body)


func create_actors() -> void:
	player = PlayerScript.new()
	player.global_position = Vector2(-260, 30)
	player.arena_bounds = ARENA
	add_child(player)
	object_index["player"] = player
	var camera := Camera2D.new()
	camera.position_smoothing_enabled = true
	camera.position_smoothing_speed = 5.0
	camera.enabled = true
	player.add_child(camera)

	var dwarf_spawns := [Vector2(315, -150), Vector2(430, -30), Vector2(430, 235), Vector2(-30, 245), Vector2(-370, -200), Vector2(60, -210)]
	for index in range(dwarf_spawns.size()):
		var dwarf := DwarfScript.new()
		var dwarf_id := "dwarf_%02d" % (index + 1)
		dwarf.setup(dwarf_id, dwarf_spawns[index], player)
		add_child(dwarf)
		dwarfs.append(dwarf)
		object_index[dwarf_id] = dwarf

	var prop_data := [
		["rock_01", "rock", Vector2(-40, 90)], ["rock_02", "rock", Vector2(85, 205)],
		["crate_01", "crate", Vector2(390, 10)], ["crate_02", "crate", Vector2(-300, -95)],
		["tree_01", "tree", Vector2(455, 175)], ["metal_01", "metal", Vector2(15, -90)]
	]
	for data in prop_data:
		var prop := WorldPropScript.new()
		prop.setup(data[0], data[1], data[2])
		add_child(prop)
		props.append(prop)
		object_index[data[0]] = prop


func create_ui() -> void:
	ui_layer = CanvasLayer.new()
	add_child(ui_layer)
	cast_tint = ColorRect.new()
	cast_tint.color = Color(0.18, 0.3, 0.5, 0.0)
	cast_tint.position = Vector2.ZERO
	cast_tint.size = Vector2(1280, 720)
	cast_tint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui_layer.add_child(cast_tint)

	health_label = make_label(Vector2(24, 20), Vector2(260, 34), 22)
	connection_label = make_label(Vector2(1010, 22), Vector2(245, 30), 16)
	connection_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	hint_label = make_label(Vector2(360, 670), Vector2(560, 32), 17)
	hint_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint_label.text = "WASD — движение    SPACE — начать заклинание    F3 — отладка"

	cast_label = make_label(Vector2(160, 582), Vector2(960, 40), 18)
	cast_label.text = "CASTING  •  удерживайте ЛКМ и ведите мышью, затем ENTER"
	cast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	cast_label.modulate = Color("a8edff")
	cast_label.visible = false

	spell_input = LineEdit.new()
	spell_input.position = Vector2(160, 622)
	spell_input.size = Vector2(960, 52)
	spell_input.placeholder_text = "Что должна сделать магия?"
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
	cast_http.request_completed.connect(_on_cast_request_completed)
	add_child(cast_http)
	health_http = HTTPRequest.new()
	health_http.timeout = 1.5
	health_http.request_completed.connect(_on_health_request_completed)
	add_child(health_http)
	config_http = HTTPRequest.new()
	config_http.timeout = request_timeout_seconds
	config_http.request_completed.connect(_on_config_request_completed)
	add_child(config_http)


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
	max_gesture_points = int(server_spell.get("max_gesture_points", max_gesture_points))


func _process(_delta: float) -> void:
	update_hud()
	queue_redraw()


func update_hud() -> void:
	if is_instance_valid(player):
		health_label.text = "ЗДОРОВЬЕ  %d / 100" % int(player.health)
		health_label.modulate = Color("ff8f8f") if player.health < 35.0 else Color.WHITE


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_F3:
			debug_enabled = not debug_enabled
			debug_panel.visible = debug_enabled
			update_debug_panel()
			get_viewport().set_input_as_handled()
			return
		if event.keycode == KEY_R and not casting:
			reset_sandbox()
			get_viewport().set_input_as_handled()
			return
		if event.keycode == KEY_SPACE and not casting:
			begin_cast()
			get_viewport().set_input_as_handled()
			return
		if event.keycode == KEY_ESCAPE and casting:
			cancel_cast()
			get_viewport().set_input_as_handled()
			return

	if not casting or waiting_for_backend:
		return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			drawing_gesture = true
			current_stroke = []
			append_gesture_point(event.position)
		else:
			if drawing_gesture:
				append_gesture_point(event.position)
				if current_stroke.size() > 1:
					gesture_strokes.append(current_stroke.duplicate(true))
			drawing_gesture = false
			current_stroke = []
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseMotion and drawing_gesture:
		var world_position := get_global_mouse_position()
		if current_stroke.is_empty() or Vector2(current_stroke[-1]["world_x"] * UNIT, current_stroke[-1]["world_y"] * UNIT).distance_to(world_position) >= 5.0:
			append_gesture_point(event.position)
		get_viewport().set_input_as_handled()


func begin_cast() -> void:
	casting = true
	waiting_for_backend = false
	drawing_gesture = false
	gesture_strokes.clear()
	current_stroke = []
	cast_started_ms = Time.get_ticks_msec()
	Engine.time_scale = cast_time_scale
	player.movement_enabled = false
	cast_tint.color = Color(0.16, 0.31, 0.58, 0.16)
	cast_label.visible = true
	spell_input.visible = true
	spell_input.editable = true
	spell_input.text = ""
	spell_input.grab_focus()
	hint_label.text = "ENTER — сотворить    ESC — отменить"


func cancel_cast() -> void:
	finish_cast_mode()
	connection_label.text = "Заклинание отменено"
	connection_label.modulate = Color("d9e5e8")


func _on_spell_submitted(_value: String) -> void:
	confirm_cast()


func confirm_cast() -> void:
	if not casting or waiting_for_backend:
		return
	var text := spell_input.text.strip_edges()
	if text.is_empty():
		spell_input.placeholder_text = "Введите хотя бы один символ"
		return
	if drawing_gesture and current_stroke.size() > 1:
		gesture_strokes.append(current_stroke.duplicate(true))
		drawing_gesture = false
		current_stroke = []
	waiting_for_backend = true
	spell_input.editable = false
	cast_label.text = "COMPILING MAGIC…  мир продолжает двигаться"
	last_spell_text = text
	cast_counter += 1
	var payload := build_cast_payload(text)
	var headers := PackedStringArray(["Content-Type: application/json"])
	var error := cast_http.request(backend_url + "/cast", headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		cast_failed("backend request could not start")


func append_gesture_point(screen_position: Vector2) -> void:
	if current_stroke.size() + total_gesture_points() >= max_gesture_points:
		return
	var viewport_size := get_viewport_rect().size
	var world_position := get_global_mouse_position()
	current_stroke.append({
		"t_ms": Time.get_ticks_msec() - cast_started_ms,
		"screen_x": clampf(screen_position.x / viewport_size.x, 0.0, 1.0),
		"screen_y": clampf(screen_position.y / viewport_size.y, 0.0, 1.0),
		"world_x": world_position.x / UNIT,
		"world_y": world_position.y / UNIT
	})


func total_gesture_points() -> int:
	var total := 0
	for stroke in gesture_strokes:
		total += stroke.size()
	return total


func build_cast_payload(text: String) -> Dictionary:
	var stroke_payload: Array = []
	for stroke in gesture_strokes:
		stroke_payload.append({"points": stroke})
	return {
		"request_id": "cast-%06d" % cast_counter,
		"spell_text": text,
		"seed": cast_counter,
		"caster": {
			"id": "player",
			"position": {"x": player.global_position.x / UNIT, "y": player.global_position.y / UNIT},
			"velocity": {"x": player.velocity.x / UNIT, "y": player.velocity.y / UNIT},
			"facing": {"x": player.facing.x, "y": player.facing.y}
		},
		"gesture": {"strokes": stroke_payload},
		"world": {"objects": collect_world_snapshot()},
		"options": {"debug": true}
	}


func collect_world_snapshot() -> Array:
	var objects: Array = [player.get_snapshot(UNIT)]
	if player.global_position.distance_to(water_position) <= snapshot_radius * UNIT + water_radius:
		objects.append(water_snapshot())
	for dwarf in dwarfs:
		if dwarf.visible and player.global_position.distance_to(dwarf.global_position) <= snapshot_radius * UNIT:
			objects.append(dwarf.get_snapshot(UNIT))
	for prop in props:
		if prop.visible and player.global_position.distance_to(prop.global_position) <= snapshot_radius * UNIT:
			objects.append(prop.get_snapshot(UNIT))
	return objects


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
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		cast_failed("HTTP %d / result %d" % [response_code, result])
		return
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if typeof(parsed) != TYPE_DICTIONARY:
		cast_failed("invalid JSON response")
		return
	apply_spell_response(parsed)
	finish_cast_mode()
	connection_label.text = "Backend: магия скомпилирована"
	connection_label.modulate = Color("78e08f")


func apply_spell_response(response: Dictionary) -> void:
	var plan: Dictionary = response.get("spell_plan", {})
	for action in plan.get("world_actions", []):
		apply_world_action(action)
	for descriptor in plan.get("visuals", []):
		spawn_visual(descriptor)
	last_debug = response
	update_debug_panel()


func apply_world_action(action: Dictionary) -> void:
	var action_type := str(action.get("type", ""))
	if action_type == "SPAWN_EFFECT_ENTITY":
		spawn_runtime_effect(action.get("effect", {}))
		return
	var target_id := str(action.get("target_id", ""))
	if target_id == "water_pool_01":
		match str(action.get("type", "")):
			"CHANGE_TEMPERATURE":
				water_temperature += float(action.get("amount", 0.0))
			"CHANGE_MATERIAL_STATE":
				water_state = str(action.get("material", water_state))
		return
	if object_index.has(target_id) and is_instance_valid(object_index[target_id]):
		if action_type == "DESTROY_OBJECT":
			object_index[target_id].apply_world_action({"type": "DAMAGE", "amount": 10000.0}, UNIT)
		else:
			object_index[target_id].apply_world_action(action, UNIT)


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
		"origin": {"x": player.global_position.x / UNIT, "y": player.global_position.y / UNIT},
		"direction": {"x": player.facing.x, "y": player.facing.y},
		"radius": 0.65, "speed": 0.0, "intensity": 0.35, "turbulence": 0.9, "lifetime": 0.65
	})
	last_debug = {"error": reason, "spell_text": last_spell_text}
	update_debug_panel()
	finish_cast_mode()
	connection_label.text = "Backend error • магия рассеялась"
	connection_label.modulate = Color("ff8f8f")


func finish_cast_mode() -> void:
	Engine.time_scale = 1.0
	casting = false
	waiting_for_backend = false
	drawing_gesture = false
	player.movement_enabled = true
	cast_tint.color = Color(0.16, 0.31, 0.58, 0.0)
	cast_label.visible = false
	cast_label.text = "CASTING  •  удерживайте ЛКМ и ведите мышью, затем ENTER"
	spell_input.visible = false
	spell_input.editable = true
	spell_input.release_focus()
	hint_label.text = "WASD — движение    SPACE — начать заклинание    F3 — отладка    R — сброс"
	gesture_strokes.clear()
	current_stroke = []
	queue_redraw()


func update_debug_panel() -> void:
	if not is_instance_valid(debug_text):
		return
	if last_debug.is_empty():
		debug_text.text = "[b]DEVELOPER MAGIC VIEW[/b]\n\nСотворите первое заклинание.\n\nЗдесь появятся якоря, геометрия жеста, цели, правила мира и задержка REST."
		return
	if last_debug.has("error"):
		debug_text.text = "[b][color=#ff8f8f]BACKEND ERROR[/color][/b]\n\n%s\n\nПоследний текст: %s" % [last_debug["error"], last_debug.get("spell_text", "")]
		return
	var interpretation: Dictionary = last_debug.get("interpretation", {})
	var lines: Array[String] = []
	lines.append("[b]DEVELOPER MAGIC VIEW[/b]")
	lines.append("\n[b]Текст[/b]\n\"%s\"" % last_spell_text)
	lines.append("\n[b]Coherence[/b]  %.3f" % float(interpretation.get("coherence", 0.0)))
	lines.append("\n[b]Top anchors[/b]")
	for anchor in interpretation.get("anchors", []).slice(0, 10):
		lines.append("%-16s %.3f" % [str(anchor.get("id", "")), float(anchor.get("score", 0.0))])
	var gesture: Dictionary = interpretation.get("gesture_features", {})
	lines.append("\n[b]Gesture[/b]")
	lines.append("straightness  %.3f" % float(gesture.get("straightness", 0.0)))
	lines.append("closedness    %.3f" % float(gesture.get("closedness", 0.0)))
	lines.append("speed         %.3f" % float(gesture.get("speed", 0.0)))
	lines.append("radial out/in %.3f / %.3f" % [float(gesture.get("radial_out", 0.0)), float(gesture.get("radial_in", 0.0))])
	var debug: Dictionary = last_debug.get("debug", {})
	var intent: Dictionary = debug.get("intent", {})
	lines.append("\n[b]SpellIntent[/b]")
	lines.append("matter    %s" % JSON.stringify(intent.get("matter", {})))
	lines.append("actions   %s" % JSON.stringify(intent.get("actions", {})))
	lines.append("movement  %s" % JSON.stringify(intent.get("movement", {})))
	lines.append("geometry  %s" % JSON.stringify(intent.get("geometry", {})))
	lines.append("\n[b]Targets[/b]  %s" % ", ".join(debug.get("selected_targets", [])))
	lines.append("\n[b]World rules[/b]")
	for rule in debug.get("world_rules", []):
		lines.append("• %s" % str(rule))
	lines.append("\n[b]REST latency[/b]  %.2f ms" % float(debug.get("latency_ms", 0.0)))
	debug_text.text = "\n".join(lines)


func reset_sandbox() -> void:
	water_state = "water"
	water_temperature = 0.5
	player.health = 100.0
	player.temperature = 0.5
	player.wetness = 0.0
	player.global_position = Vector2(-260, 30)
	player.states.clear()
	for dwarf in dwarfs:
		dwarf.health = 58.0
		dwarf.states.clear()
		dwarf.temperature = 0.5
		dwarf.wetness = 0.0
		dwarf.visible = true
		dwarf.global_position = dwarf.home
		dwarf.set_physics_process(true)
	for prop in props:
		prop.health = 80.0
		prop.temperature = 0.5
		prop.wetness = 0.0
		prop.states.clear()
		prop.visible = true
		prop.collision_layer = 1
		prop.set_physics_process(true)
	connection_label.text = "Sandbox reset"
	connection_label.modulate = Color("d9e5e8")


func _draw() -> void:
	draw_rect(ARENA, Color("182c2b"))
	for x in range(int(ARENA.position.x), int(ARENA.end.x), 64):
		draw_line(Vector2(x, ARENA.position.y), Vector2(x, ARENA.end.y), Color(0.25, 0.5, 0.42, 0.08), 1.0)
	for y in range(int(ARENA.position.y), int(ARENA.end.y), 64):
		draw_line(Vector2(ARENA.position.x, y), Vector2(ARENA.end.x, y), Color(0.25, 0.5, 0.42, 0.08), 1.0)
	for wall in WALLS:
		draw_rect(wall, Color("3f4650"))
		draw_rect(wall.grow(-4.0), Color("59616c"), false, 2.0)
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
	var fallback_font := ThemeDB.fallback_font
	draw_string(fallback_font, water_position + Vector2(-42, 5), water_state.to_upper(), HORIZONTAL_ALIGNMENT_CENTER, 84, 14, Color(0.88, 0.96, 1.0, 0.62))
	if casting:
		var polyline := PackedVector2Array()
		for stroke in gesture_strokes:
			polyline.clear()
			for point in stroke:
				polyline.append(Vector2(float(point["world_x"]), float(point["world_y"])) * UNIT)
			if polyline.size() > 1:
				draw_polyline(polyline, Color(0.52, 0.93, 1.0, 0.88), 5.0, true)
		polyline.clear()
		for point in current_stroke:
			polyline.append(Vector2(float(point["world_x"]), float(point["world_y"])) * UNIT)
		if polyline.size() > 1:
			draw_polyline(polyline, Color(0.73, 0.97, 1.0, 0.96), 5.0, true)


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		Engine.time_scale = 1.0
		get_tree().quit()
