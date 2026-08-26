extends CharacterBody2D

const BODY_RADIUS := 16.0
const CHASE_SPEED := 78.0
const AGGRO_RADIUS := 540.0

var object_id := "dwarf"
var target: Node2D
var home := Vector2.ZERO
var health := 58.0
var attack_cooldown := 0.0
var wander_phase := 0.0
var impulse := Vector2.ZERO
var states: Dictionary = {}
var dead_for := 0.0
var temperature := 0.5
var wetness := 0.0


func setup(id_value: String, spawn_position: Vector2, player: Node2D) -> void:
	object_id = id_value
	home = spawn_position
	global_position = spawn_position
	target = player
	wander_phase = float(id_value.hash() % 1000) / 100.0


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
	if dead_for > 0.0:
		dead_for -= delta
		if dead_for <= 0.0:
			health = 58.0
			global_position = home
			visible = true
			set_physics_process(true)
		return
	attack_cooldown = maxf(0.0, attack_cooldown - delta)
	_tick_states(delta)
	var desired := Vector2.ZERO
	if is_instance_valid(target):
		var distance := global_position.distance_to(target.global_position)
		if distance < AGGRO_RADIUS:
			desired = global_position.direction_to(target.global_position)
			if distance < 38.0 and attack_cooldown <= 0.0 and target.has_method("damage"):
				target.damage(7.0)
				attack_cooldown = 1.15
		else:
			wander_phase += delta * 0.7
			desired = Vector2(cos(wander_phase), sin(wander_phase * 0.73)) * 0.35
	var slow_factor := 0.08 if states.has("frozen") else (0.55 if states.has("slowed") else 1.0)
	if states.has("levitating"):
		slow_factor *= 0.2
	velocity = desired.normalized() * CHASE_SPEED * slow_factor + impulse
	move_and_slide()
	impulse = impulse.move_toward(Vector2.ZERO, 380.0 * delta)
	queue_redraw()


func _tick_states(delta: float) -> void:
	for state_name in states.keys():
		states[state_name] = float(states[state_name]) - delta
		if state_name == "burning":
			health -= 5.0 * delta
		if state_name == "poisoned":
			health -= 2.0 * delta
		if states[state_name] <= 0.0:
			states.erase(state_name)
	if health <= 0.0:
		_die()


func _die() -> void:
	visible = false
	velocity = Vector2.ZERO
	impulse = Vector2.ZERO
	states.clear()
	dead_for = 4.0
	set_physics_process(false)
	var timer := get_tree().create_timer(4.0)
	timer.timeout.connect(_respawn)


func _respawn() -> void:
	health = 58.0
	global_position = home
	visible = true
	dead_for = 0.0
	set_physics_process(true)


func apply_world_action(action: Dictionary, unit: float) -> void:
	match str(action.get("type", "")):
		"DAMAGE":
			health -= float(action.get("amount", 0.0))
		"HEAL":
			health = minf(58.0, health + float(action.get("amount", 0.0)))
		"APPLY_FORCE", "CHANGE_VELOCITY":
			var direction_data: Dictionary = action.get("direction", {})
			impulse += Vector2(float(direction_data.get("x", 0.0)), float(direction_data.get("y", 0.0))) * float(action.get("strength", 0.0)) * unit
		"ADD_STATE":
			states[str(action.get("state", "unstable"))] = float(action.get("duration", 1.0))
		"REMOVE_STATE":
			states.erase(str(action.get("state", "")))
		"CHANGE_TEMPERATURE":
			temperature += float(action.get("amount", 0.0))
		"CHANGE_WETNESS":
			wetness = clampf(wetness + float(action.get("amount", 0.0)), 0.0, 1.0)
	if health <= 0.0:
		_die()
	queue_redraw()


func get_snapshot(unit: float) -> Dictionary:
	var state_values: Array = []
	for state_name in states:
		state_values.append({"name": state_name, "strength": 1.0, "remaining_duration": states[state_name], "source": "magic"})
	return {
		"id": object_id,
		"kind": "creature",
		"tags": ["living", "enemy", "dwarf", "organic"],
		"position": {"x": global_position.x / unit, "y": global_position.y / unit},
		"velocity": {"x": velocity.x / unit, "y": velocity.y / unit},
		"radius": BODY_RADIUS / unit,
		"health": health,
		"material": {"name": "organic", "mass": 1.0, "temperature": temperature, "wetness": wetness, "flammability": 0.35, "conductivity": 0.2, "hardness": 0.2, "brittleness": 0.1},
		"states": state_values
	}


func _draw() -> void:
	if not visible:
		return
	if states.has("levitating"):
		draw_set_transform(Vector2(0, 12), 0.0, Vector2(1.0, 0.42))
		draw_circle(Vector2.ZERO, BODY_RADIUS, Color(0.0, 0.0, 0.0, 0.28))
		draw_set_transform(Vector2(0, -10))
	if states.has("burning"):
		draw_circle(Vector2.ZERO, BODY_RADIUS + 7.0, Color(1.0, 0.25, 0.08, 0.3))
	if states.has("electrified"):
		draw_arc(Vector2.ZERO, BODY_RADIUS + 6.0, 0.0, TAU, 12, Color("c8f7ff"), 3.0)
	draw_circle(Vector2.ZERO, BODY_RADIUS, Color("8e3f36"))
	draw_circle(Vector2(0, -5), 9.0, Color("d8a77a"))
	draw_colored_polygon(PackedVector2Array([Vector2(-10, 1), Vector2(10, 1), Vector2(6, 18), Vector2(0, 13), Vector2(-6, 18)]), Color("d49a43"))
	draw_line(Vector2(-9, -12), Vector2(9, -12), Color("3c2c2a"), 5.0)
	var health_width := 30.0 * clampf(health / 58.0, 0.0, 1.0)
	draw_rect(Rect2(-15, -28, 30, 3), Color("3a2026"))
	draw_rect(Rect2(-15, -28, health_width, 3), Color("ff6b6b"))
