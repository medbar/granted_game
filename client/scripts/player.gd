extends CharacterBody2D

signal health_changed(value: float)

const MOVE_SPEED := 215.0
const BODY_RADIUS := 18.0

var health := 100.0
var facing := Vector2.RIGHT
var movement_enabled := true
var impulse := Vector2.ZERO
var states: Dictionary = {}
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
	velocity = input_vector * MOVE_SPEED * slow_factor + impulse
	move_and_slide()
	global_position.x = clampf(global_position.x, arena_bounds.position.x + BODY_RADIUS, arena_bounds.end.x - BODY_RADIUS)
	global_position.y = clampf(global_position.y, arena_bounds.position.y + BODY_RADIUS, arena_bounds.end.y - BODY_RADIUS)
	impulse = impulse.move_toward(Vector2.ZERO, 520.0 * delta)
	_tick_states(delta)
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
			states[str(action.get("state", "unstable"))] = float(action.get("duration", 1.0))
		"REMOVE_STATE":
			states.erase(str(action.get("state", "")))


func get_snapshot(unit: float) -> Dictionary:
	var state_values: Array = []
	for state_name in states:
		state_values.append({"name": state_name, "strength": 1.0, "remaining_duration": states[state_name], "source": "magic"})
	return {
		"id": "player",
		"kind": "creature",
		"tags": ["living", "player", "mage", "organic"],
		"position": {"x": global_position.x / unit, "y": global_position.y / unit},
		"velocity": {"x": velocity.x / unit, "y": velocity.y / unit},
		"radius": BODY_RADIUS / unit,
		"health": health,
		"material": {"name": "organic", "mass": 1.0, "temperature": 0.5, "wetness": 0.0, "flammability": 0.3, "conductivity": 0.25, "hardness": 0.2, "brittleness": 0.1},
		"states": state_values
	}


func _draw() -> void:
	var aura := Color("7f5af0")
	if states.has("burning"):
		aura = Color("ff6b35")
	elif states.has("electrified"):
		aura = Color("a8edff")
	draw_circle(Vector2.ZERO, BODY_RADIUS + 6.0, Color(aura, 0.24))
	draw_circle(Vector2.ZERO, BODY_RADIUS, Color("29234f"))
	draw_circle(Vector2(0.0, -5.0), 10.0, Color("f2c9a5"))
	draw_colored_polygon(PackedVector2Array([Vector2(-13, 3), Vector2(13, 3), Vector2(8, 18), Vector2(-8, 18)]), Color("634bb3"))
	draw_line(facing * 4.0, facing * 30.0, Color("d7b56d"), 4.0, true)
	draw_circle(facing * 32.0, 4.5, Color("b8f1ff"))

