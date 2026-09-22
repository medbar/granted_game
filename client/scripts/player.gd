extends CharacterBody2D

signal health_changed(value: float)

const MOVE_SPEED := 215.0
const BODY_RADIUS := 18.0
const WEAPON_SWING_DURATION := 0.24
const WEAPON_COOLDOWN_DURATION := 0.38

var health := 100.0
var facing := Vector2.RIGHT
var movement_enabled := true
var impulse := Vector2.ZERO
var states: Dictionary = {}
var temperature := 0.5
var wetness := 0.0
var inventory: Array[String] = []
var outfit := ""
var weapon_swing_remaining := 0.0
var weapon_cooldown := 0.0
var arena_bounds := Rect2(-600.0, -330.0, 1200.0, 660.0)


func _ready() -> void:
	collision_layer = 1
	collision_mask = 1
	var shape := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = BODY_RADIUS
	shape.shape = circle
	add_child(shape)
	queue_redraw()


func _physics_process(delta: float) -> void:
	weapon_swing_remaining = maxf(0.0, weapon_swing_remaining - delta)
	weapon_cooldown = maxf(0.0, weapon_cooldown - delta)
	facing = global_position.direction_to(get_global_mouse_position())
	if facing.length_squared() < 0.001:
		facing = Vector2.RIGHT
	var input_vector := Vector2.ZERO
	if movement_enabled:
		input_vector = Vector2(
			float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A)),
			float(Input.is_physical_key_pressed(KEY_S)) - float(Input.is_physical_key_pressed(KEY_W))
		).normalized()
	var slow_factor := 0.48 if states.has("slowed") else 1.0
	if states.has("frozen"):
		slow_factor = 0.1
	elif states.has("levitating"):
		slow_factor *= 0.4
	velocity = input_vector * MOVE_SPEED * slow_factor + impulse
	move_and_slide()
	global_position.x = clampf(global_position.x, arena_bounds.position.x + BODY_RADIUS, arena_bounds.end.x - BODY_RADIUS)
	global_position.y = clampf(global_position.y, arena_bounds.position.y + BODY_RADIUS, arena_bounds.end.y - BODY_RADIUS)
	impulse = impulse.move_toward(Vector2.ZERO, 520.0 * delta)
	_tick_states(delta)
	collision_mask = 0 if states.has("phased") else 1
	modulate.a = 0.22 if states.has("invisible") else 1.0
	queue_redraw()


func start_weapon_swing() -> bool:
	if not movement_enabled or weapon_cooldown > 0.0:
		return false
	weapon_swing_remaining = WEAPON_SWING_DURATION
	weapon_cooldown = WEAPON_COOLDOWN_DURATION
	queue_redraw()
	return true


func cancel_weapon_swing() -> void:
	weapon_swing_remaining = 0.0
	queue_redraw()


func _tick_states(delta: float) -> void:
	for state_name in states.keys():
		states[state_name] = float(states[state_name]) - delta
		if state_name == "burning":
			damage(3.0 * delta)
		if states[state_name] <= 0.0:
			states.erase(state_name)


func damage(amount: float) -> void:
	health = maxf(0.0, health - amount)
	health_changed.emit(health)
	if health <= 0.0:
		health = 100.0
		global_position = Vector2.ZERO
		states.clear()
		health_changed.emit(health)


func apply_world_action(action: Dictionary, unit: float) -> void:
	match str(action.get("type", "")):
		"DAMAGE":
			damage(float(action.get("amount", 0.0)))
		"HEAL":
			health = minf(100.0, health + float(action.get("amount", 0.0)))
			health_changed.emit(health)
		"APPLY_FORCE", "CHANGE_VELOCITY":
			var direction_data: Dictionary = action.get("direction", {})
			impulse += Vector2(float(direction_data.get("x", 0.0)), float(direction_data.get("y", 0.0))) * float(action.get("strength", 0.0)) * unit
		"ADD_STATE":
			var state_name := str(action.get("state", "unstable"))
			states[state_name] = float(action.get("duration", 1.0))
			if state_name == "wet":
				wetness = 1.0
		"REMOVE_STATE":
			states.erase(str(action.get("state", "")))
		"CHANGE_TEMPERATURE":
			temperature += float(action.get("amount", 0.0))
		"CHANGE_WETNESS":
			wetness = clampf(wetness + float(action.get("amount", 0.0)), 0.0, 1.0)
		"ADD_INVENTORY_ITEM":
			var effect: Dictionary = action.get("effect", {})
			var prototype := str(effect.get("prototype", "item"))
			inventory.append(prototype)
		"EQUIP_OUTFIT":
			var outfit_effect: Dictionary = action.get("effect", {})
			outfit = str(outfit_effect.get("outfit", ""))
	queue_redraw()


func get_snapshot(unit: float) -> Dictionary:
	var state_values: Array = []
	for state_name in states:
		state_values.append({"name": state_name, "strength": 1.0, "remaining_duration": states[state_name], "source": "magic"})
	var snapshot_properties := {
		"inventory": inventory.duplicate(),
		"outfit": outfit,
		"passes_walls": states.has("phased"),
		"invisible": states.has("invisible"),
		"visible": true,
		"removed": false
	}
	return {
		"id": "player",
		"kind": "creature",
		"tags": ["living", "player", "requester", "adventurer", "organic"],
		"position": {"x": global_position.x / unit, "y": global_position.y / unit},
		"velocity": {"x": velocity.x / unit, "y": velocity.y / unit},
		"radius": BODY_RADIUS / unit,
		"health": health,
		"material": {"name": "organic", "mass": 1.0, "temperature": temperature, "wetness": wetness, "flammability": 0.3, "conductivity": 0.25, "hardness": 0.2, "brittleness": 0.1},
		"states": state_values,
		"properties": snapshot_properties
	}


func _draw() -> void:
	if states.has("levitating"):
		draw_ellipse_shadow(Vector2(0, 12))
		draw_set_transform(Vector2(0, -10))
	var aura := Color("d8a854")
	if states.has("burning"):
		aura = Color("ff6b35")
	elif states.has("electrified"):
		aura = Color("a8edff")
	draw_circle(Vector2.ZERO, BODY_RADIUS + 5.0, Color(aura, 0.18))
	draw_circle(Vector2.ZERO, BODY_RADIUS, Color("493827"))
	draw_circle(Vector2(0.0, -5.0), 10.0, Color("f2c9a5"))
	match outfit:
		"dress":
			draw_colored_polygon(PackedVector2Array([Vector2(-11, 1), Vector2(11, 1), Vector2(22, 23), Vector2(-22, 23)]), Color("8f4fb3"))
			draw_polyline(PackedVector2Array([Vector2(-11, 1), Vector2(11, 1), Vector2(22, 23), Vector2(-22, 23), Vector2(-11, 1)]), Color("efc7ff"), 3.0)
			draw_circle(Vector2(0, 7), 3.0, Color("f6cf65"))
		"robe":
			draw_colored_polygon(PackedVector2Array([Vector2(-14, 1), Vector2(14, 1), Vector2(17, 22), Vector2(-17, 22)]), Color("315f9b"))
			draw_line(Vector2(0, 2), Vector2(0, 21), Color("9fc7ff"), 3.0)
		"armor":
			draw_colored_polygon(PackedVector2Array([Vector2(-16, 1), Vector2(16, 1), Vector2(12, 19), Vector2(-12, 19)]), Color("778794"))
			draw_rect(Rect2(-10, 5, 20, 10), Color("c9d4da"), false, 3.0)
		"cloak":
			draw_colored_polygon(PackedVector2Array([Vector2(-16, 0), Vector2(16, 0), Vector2(20, 23), Vector2(-20, 23)]), Color("7b263d"))
			draw_circle(Vector2(0, 3), 3.0, Color("e2b84f"))
		_:
			draw_colored_polygon(PackedVector2Array([Vector2(-13, 3), Vector2(13, 3), Vector2(8, 18), Vector2(-8, 18)]), Color("9c5f35"))
	draw_arc(Vector2(0, -7), 9.0, PI, TAU, 12, Color("4a3025"), 4.0)
	var weapon_direction := facing.normalized()
	if weapon_swing_remaining > 0.0:
		var swing_progress := 1.0 - weapon_swing_remaining / WEAPON_SWING_DURATION
		weapon_direction = weapon_direction.rotated(lerpf(-1.15, 1.15, swing_progress))
	var hand := weapon_direction * 12.0
	var guard := weapon_direction * 24.0
	var tip := weapon_direction * 48.0
	var side := weapon_direction.orthogonal()
	draw_line(Vector2.ZERO, hand, Color("e8b991"), 5.0, true)
	draw_line(hand, guard, Color("70421f"), 5.0, true)
	draw_line(guard - side * 6.0, guard + side * 6.0, Color("e2a93b"), 3.0, true)
	draw_line(guard, tip, Color("dbe9ee"), 6.0, true)
	draw_line(guard + side * 1.5, tip + side * 1.5, Color("ffffff"), 1.5, true)


func draw_ellipse_shadow(offset: Vector2) -> void:
	draw_set_transform(offset, 0.0, Vector2(1.0, 0.42))
	draw_circle(Vector2.ZERO, BODY_RADIUS, Color(0.0, 0.0, 0.0, 0.28))
	draw_set_transform(Vector2.ZERO)
