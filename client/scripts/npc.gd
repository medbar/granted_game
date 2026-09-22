extends CharacterBody2D

const BODY_RADIUS := 16.0
const WANDER_SPEED := 28.0
const MAX_HEALTH := 70.0

var object_id := "npc"
var home := Vector2.ZERO
var health := MAX_HEALTH
var wander_phase := 0.0
var impulse := Vector2.ZERO
var states: Dictionary = {}
var temperature := 0.5
var wetness := 0.0
var target: Node2D
var transformed_form := ""


func setup(id_value: String, spawn_position: Vector2) -> void:
	object_id = id_value
	home = spawn_position
	global_position = spawn_position
	wander_phase = float(id_value.hash() % 1000) / 100.0


func _ready() -> void:
	collision_layer = 1
	collision_mask = 1
	var collision := CollisionShape2D.new()
	var circle := CircleShape2D.new()
	circle.radius = BODY_RADIUS
	collision.shape = circle
	add_child(collision)
	queue_redraw()


func _physics_process(delta: float) -> void:
	_tick_states(delta)
	if not visible:
		return
	collision_mask = 0 if states.has("phased") else 1
	modulate.a = 0.22 if states.has("invisible") else 1.0
	wander_phase += delta * 0.45
	var desired := Vector2(cos(wander_phase), sin(wander_phase * 0.8))
	if states.has("aggressive") and is_instance_valid(target):
		desired = global_position.direction_to(target.global_position) * 2.4
	if global_position.distance_to(home) > 75.0:
		desired = global_position.direction_to(home)
	var slow_factor := 0.08 if states.has("frozen") else (0.55 if states.has("slowed") else 1.0)
	if states.has("levitating"):
		slow_factor *= 0.2
	velocity = desired.normalized() * WANDER_SPEED * slow_factor + impulse
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
		visible = false
		velocity = Vector2.ZERO
		collision_layer = 0


func apply_world_action(action: Dictionary, unit: float) -> void:
	match str(action.get("type", "")):
		"DESTROY_OBJECT":
			health = 0.0
			visible = false
			velocity = Vector2.ZERO
			collision_layer = 0
			set_physics_process(false)
		"DAMAGE":
			health -= float(action.get("amount", 0.0))
		"HEAL":
			health = minf(MAX_HEALTH, health + float(action.get("amount", 0.0)))
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
		"SET_AGGRO_TARGET":
			states["aggressive"] = 999.0
		"TRANSFORM_OBJECT":
			var transform_effect: Dictionary = action.get("effect", {})
			transformed_form = str(transform_effect.get("prototype", transformed_form))
			if transformed_form == "enemy":
				states["aggressive"] = 999.0
	_tick_states(0.0)
	queue_redraw()


func reset_actor() -> void:
	health = MAX_HEALTH
	temperature = 0.5
	wetness = 0.0
	states.clear()
	transformed_form = ""
	impulse = Vector2.ZERO
	visible = true
	collision_layer = 1
	global_position = home
	set_physics_process(true)
	queue_redraw()


func get_snapshot(unit: float) -> Dictionary:
	var state_values: Array = []
	for state_name in states:
		state_values.append({"name": state_name, "strength": 1.0, "remaining_duration": states[state_name], "source": "magic"})
	var snapshot_tags := ["living", "npc", "villager", "friendly", "organic"]
	var snapshot_kind := "creature"
	var snapshot_material := "organic"
	if not transformed_form.is_empty():
		snapshot_tags = ["transformed", "former_npc", transformed_form]
		if transformed_form == "enemy":
			snapshot_tags.append_array(["living", "enemy", "hostile", "organic"])
		else:
			snapshot_kind = "prop"
			snapshot_material = "wood" if transformed_form in ["crate", "tree"] else ("metal" if transformed_form in ["metal", "shield", "sword", "cage"] else "stone")
			snapshot_tags.append_array(["inanimate", "prop", snapshot_material])
	return {
		"id": object_id,
		"kind": snapshot_kind,
		"tags": snapshot_tags,
		"position": {"x": global_position.x / unit, "y": global_position.y / unit},
		"velocity": {"x": velocity.x / unit, "y": velocity.y / unit},
		"radius": BODY_RADIUS / unit,
		"health": health,
		"material": {"name": snapshot_material, "mass": 1.0, "temperature": temperature, "wetness": wetness, "flammability": 0.35, "conductivity": 0.2, "hardness": 0.2, "brittleness": 0.1},
		"states": state_values,
		"properties": {
			"prototype": transformed_form if not transformed_form.is_empty() else "npc",
			"initial_prototype": "npc",
			"visible": visible,
			"removed": health <= 0.0,
			"aggro_target": "player" if states.has("aggressive") else ""
		}
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
	var is_enemy := transformed_form == "enemy"
	draw_circle(Vector2.ZERO, BODY_RADIUS, Color("8e3f36") if is_enemy else Color("315c70"))
	draw_circle(Vector2(0, -5), 9.0, Color("d8a77a"))
	draw_colored_polygon(PackedVector2Array([Vector2(-10, 1), Vector2(10, 1), Vector2(7, 18), Vector2(-7, 18)]), Color("d49a43") if is_enemy else Color("4ca6a8"))
	draw_arc(Vector2.ZERO, BODY_RADIUS + 5.0, -2.7, -0.45, 12, Color("ff7b72") if is_enemy else Color("82e6d0"), 2.0)
	var fallback_font := ThemeDB.fallback_font
	draw_string(fallback_font, Vector2(-20, -27), "ENEMY" if is_enemy else "NPC", HORIZONTAL_ALIGNMENT_CENTER, 40, 11, Color("ffd0c9") if is_enemy else Color("c7fff1"))
