extends CharacterBody2D

const BODY_RADIUS := 16.0
const CHASE_SPEED := 78.0
const AGGRO_RADIUS := 540.0
const VIEW_DISTANCE := 310.0
const VIEW_HALF_ANGLE := 0.72
const HEARING_RADIUS := 82.0
const ALERT_THRESHOLD := 0.52

var object_id := "dwarf"
var target: Node2D
var home := Vector2.ZERO
var health := 58.0
var attack_cooldown := 0.0
var wander_phase := 0.0
var impulse := Vector2.ZERO
var states: Dictionary = {}
var dead_for := 0.0
var permanently_destroyed := false
var temperature := 0.5
var wetness := 0.0
var transformed_form := ""
var look_direction := Vector2.LEFT
var alertness := 0.0
var alert_state := "patrol"
var last_seen_position := Vector2.ZERO


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
	collision_mask = 0 if states.has("phased") else 1
	modulate.a = 0.22 if states.has("invisible") else 1.0
	if not transformed_form.is_empty():
		if transformed_form == "npc":
			wander_phase += delta * 0.45
			var desired := Vector2(cos(wander_phase), sin(wander_phase * 0.8))
			if global_position.distance_to(home) > 75.0:
				desired = global_position.direction_to(home)
			velocity = desired.normalized() * 28.0 + impulse
		else:
			velocity = impulse
		move_and_slide()
		impulse = impulse.move_toward(Vector2.ZERO, 380.0 * delta)
		queue_redraw()
		return
	var desired := Vector2.ZERO
	if states.has("pacified") or states.has("influenced") or states.has("friendly"):
		alertness = move_toward(alertness, 0.0, delta * 1.5)
		alert_state = "patrol"
		desired = Vector2.ZERO
	elif is_instance_valid(target):
		var distance := global_position.distance_to(target.global_position)
		var perceived := states.has("aggressive") or can_perceive_target()
		if perceived:
			last_seen_position = target.global_position
			if distance <= HEARING_RADIUS:
				alertness = maxf(ALERT_THRESHOLD, minf(1.0, alertness + delta * 2.8))
			else:
				alertness = minf(1.0, alertness + delta * 1.25)
		else:
			alertness = maxf(0.0, alertness - delta * 0.3)
		if alertness >= ALERT_THRESHOLD:
			alert_state = "alert"
		elif alertness > 0.04:
			alert_state = "suspicious"
		else:
			alert_state = "patrol"
		if alert_state == "alert" and distance < AGGRO_RADIUS:
			desired = global_position.direction_to(target.global_position)
			if distance < 38.0 and attack_cooldown <= 0.0 and target.has_method("damage"):
				target.damage(7.0)
				attack_cooldown = 1.15
		elif alert_state == "suspicious" and global_position.distance_to(last_seen_position) > 12.0:
			desired = global_position.direction_to(last_seen_position) * 0.55
		else:
			wander_phase += delta * 0.7
			desired = Vector2(cos(wander_phase), sin(wander_phase * 0.73)) * 0.35
	if desired.length_squared() > 0.01:
		look_direction = desired.normalized()
	var slow_factor := 0.08 if states.has("frozen") else (0.55 if states.has("slowed") else 1.0)
	if states.has("levitating"):
		slow_factor *= 0.2
	velocity = desired.normalized() * CHASE_SPEED * slow_factor + impulse
	move_and_slide()
	impulse = impulse.move_toward(Vector2.ZERO, 380.0 * delta)
	queue_redraw()


func can_perceive_target() -> bool:
	if not is_instance_valid(target):
		return false
	var offset := target.global_position - global_position
	var distance := offset.length()
	if distance <= HEARING_RADIUS:
		return true
	if distance > VIEW_DISTANCE or distance <= 0.001:
		return false
	if look_direction.normalized().dot(offset.normalized()) < cos(VIEW_HALF_ANGLE):
		return false
	var query := PhysicsRayQueryParameters2D.create(global_position, target.global_position, 1, [self])
	var hit := get_world_2d().direct_space_state.intersect_ray(query)
	return hit.is_empty() or hit.get("collider") == target


func is_alerted() -> bool:
	return alert_state == "alert"


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
	collision_layer = 0
	collision_mask = 0
	velocity = Vector2.ZERO
	impulse = Vector2.ZERO
	states.clear()
	dead_for = 4.0
	set_physics_process(false)
	var timer := get_tree().create_timer(4.0)
	timer.timeout.connect(_respawn)


func _respawn() -> void:
	if permanently_destroyed:
		return
	health = 58.0
	global_position = home
	visible = true
	collision_layer = 1
	collision_mask = 1
	dead_for = 0.0
	set_physics_process(true)
	transformed_form = ""
	update_collision_shape()


func apply_world_action(action: Dictionary, unit: float) -> void:
	match str(action.get("type", "")):
		"DESTROY_OBJECT":
			permanently_destroyed = true
			health = 0.0
			visible = false
			collision_layer = 0
			collision_mask = 0
			velocity = Vector2.ZERO
			impulse = Vector2.ZERO
			states.clear()
			set_physics_process(false)
		"DAMAGE":
			health -= float(action.get("amount", 0.0))
		"HEAL":
			health = minf(58.0, health + float(action.get("amount", 0.0)))
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
		"TRANSFORM_OBJECT":
			var effect: Dictionary = action.get("effect", {})
			var requested_form := str(effect.get("prototype", "rock"))
			transformed_form = "" if requested_form == "enemy" else requested_form
			states.clear()
			velocity = Vector2.ZERO
			impulse = Vector2.ZERO
			update_collision_shape()
		"SET_AGGRO_TARGET":
			states["aggressive"] = 999.0
			alertness = 1.0
			alert_state = "alert"
	if health <= 0.0:
		_die()
	queue_redraw()


func get_snapshot(unit: float) -> Dictionary:
	var state_values: Array = []
	for state_name in states:
		state_values.append({"name": state_name, "strength": 1.0, "remaining_duration": states[state_name], "source": "magic"})
	if not transformed_form.is_empty():
		var transformed_material := "organic" if transformed_form == "npc" else ("wood" if transformed_form in ["crate", "tree"] else ("metal" if transformed_form in ["cage", "key", "metal", "shield", "sword"] else "stone"))
		var transformed_tags := ["inanimate", "prop", transformed_form, transformed_material, "former_enemy"]
		var transformed_kind := "prop"
		if transformed_form == "npc":
			transformed_kind = "creature"
			transformed_tags = ["living", "npc", "villager", "friendly", "organic", "former_enemy", "transformed"]
		return {
			"id": object_id,
			"kind": transformed_kind,
			"tags": transformed_tags,
			"position": {"x": global_position.x / unit, "y": global_position.y / unit},
			"velocity": {"x": velocity.x / unit, "y": velocity.y / unit},
			"radius": BODY_RADIUS / unit,
			"health": health,
			"material": {"name": transformed_material, "mass": 2.5, "temperature": temperature, "wetness": wetness, "flammability": 0.8 if transformed_material == "wood" else 0.0, "conductivity": 0.9 if transformed_material == "metal" else 0.1, "hardness": 0.9, "brittleness": 0.6},
			"states": state_values,
			"properties": {
				"prototype": transformed_form,
				"initial_prototype": "enemy",
				"visible": visible,
				"removed": permanently_destroyed or health <= 0.0
			}
		}
	if alert_state != "patrol":
		state_values.append({"name": alert_state, "strength": alertness, "remaining_duration": 0.0, "source": "perception"})
	var guard_tags := ["living", "enemy", "guard", "dwarf", "organic"]
	if alert_state == "alert":
		guard_tags.append("alerted")
	return {
		"id": object_id,
		"kind": "creature",
		"tags": guard_tags,
		"position": {"x": global_position.x / unit, "y": global_position.y / unit},
		"velocity": {"x": velocity.x / unit, "y": velocity.y / unit},
		"radius": BODY_RADIUS / unit,
		"health": health,
		"material": {"name": "organic", "mass": 1.0, "temperature": temperature, "wetness": wetness, "flammability": 0.35, "conductivity": 0.2, "hardness": 0.2, "brittleness": 0.1},
		"states": state_values,
		"properties": {
			"prototype": "enemy",
			"visible": visible,
			"removed": permanently_destroyed or health <= 0.0,
			"aggro_target": "player" if states.has("aggressive") else ""
		}
	}


func _draw() -> void:
	if not visible:
		return
	if not transformed_form.is_empty():
		draw_transformed_form()
		return
	if states.has("levitating"):
		draw_set_transform(Vector2(0, 12), 0.0, Vector2(1.0, 0.42))
		draw_circle(Vector2.ZERO, BODY_RADIUS, Color(0.0, 0.0, 0.0, 0.28))
		draw_set_transform(Vector2(0, -10))
	if states.has("burning"):
		draw_circle(Vector2.ZERO, BODY_RADIUS + 7.0, Color(1.0, 0.25, 0.08, 0.3))
	if states.has("blood_soaked"):
		draw_circle(Vector2(0, 7), BODY_RADIUS + 5.0, Color(0.45, 0.0, 0.04, 0.72))
		draw_circle(Vector2(-9, -4), 5.0, Color(0.72, 0.02, 0.06, 0.82))
		draw_circle(Vector2(8, 1), 4.0, Color(0.62, 0.0, 0.04, 0.86))
	if states.has("electrified"):
		draw_arc(Vector2.ZERO, BODY_RADIUS + 6.0, 0.0, TAU, 12, Color("c8f7ff"), 3.0)
	var cone_color := Color(0.2, 0.82, 0.9, 0.08)
	if alert_state == "suspicious":
		cone_color = Color(1.0, 0.78, 0.18, 0.13)
	elif alert_state == "alert":
		cone_color = Color(1.0, 0.18, 0.16, 0.2)
	var cone_points := PackedVector2Array([Vector2.ZERO])
	var center_angle := look_direction.angle()
	for index in range(13):
		var ratio := float(index) / 12.0
		cone_points.append(Vector2.from_angle(center_angle - VIEW_HALF_ANGLE + VIEW_HALF_ANGLE * 2.0 * ratio) * VIEW_DISTANCE)
	draw_colored_polygon(cone_points, cone_color)
	draw_arc(Vector2.ZERO, VIEW_DISTANCE, center_angle - VIEW_HALF_ANGLE, center_angle + VIEW_HALF_ANGLE, 24, Color(cone_color, 0.32), 1.5)
	draw_circle(Vector2.ZERO, BODY_RADIUS, Color("8e3f36"))
	draw_circle(Vector2(0, -5), 9.0, Color("d8a77a"))
	draw_colored_polygon(PackedVector2Array([Vector2(-10, 1), Vector2(10, 1), Vector2(6, 18), Vector2(0, 13), Vector2(-6, 18)]), Color("d49a43"))
	draw_line(Vector2(-9, -12), Vector2(9, -12), Color("3c2c2a"), 5.0)
	var health_width := 30.0 * clampf(health / 58.0, 0.0, 1.0)
	draw_rect(Rect2(-15, -28, 30, 3), Color("3a2026"))
	draw_rect(Rect2(-15, -28, health_width, 3), Color("ff6b6b"))
	if states.has("pacified") or states.has("influenced") or states.has("friendly"):
		draw_arc(Vector2(0, -10), BODY_RADIUS + 9.0, 0.0, TAU, 18, Color("8ff0c8"), 2.0)
	elif alert_state != "patrol":
		var fallback_font := ThemeDB.fallback_font
		draw_string(fallback_font, Vector2(-7, -36), "!", HORIZONTAL_ALIGNMENT_CENTER, 14, 22, Color("ff4f4f") if alert_state == "alert" else Color("ffd45a"))


func update_collision_shape() -> void:
	var collision: CollisionShape2D = null
	for child in get_children():
		if child is CollisionShape2D:
			collision = child
			break
	if collision == null:
		return
	if transformed_form in ["crate", "cage", "metal"]:
		var rectangle := RectangleShape2D.new()
		rectangle.size = Vector2(34, 34)
		collision.shape = rectangle
	else:
		var circle := CircleShape2D.new()
		circle.radius = BODY_RADIUS
		collision.shape = circle


func draw_transformed_form() -> void:
	match transformed_form:
		"npc":
			draw_circle(Vector2.ZERO, BODY_RADIUS, Color("315c70"))
			draw_circle(Vector2(0, -5), 9.0, Color("d8a77a"))
			draw_colored_polygon(PackedVector2Array([Vector2(-10, 1), Vector2(10, 1), Vector2(7, 18), Vector2(-7, 18)]), Color("4ca6a8"))
			draw_arc(Vector2.ZERO, BODY_RADIUS + 5.0, -2.7, -0.45, 12, Color("82e6d0"), 2.0)
			var fallback_font := ThemeDB.fallback_font
			draw_string(fallback_font, Vector2(-16, -27), "NPC", HORIZONTAL_ALIGNMENT_CENTER, 32, 11, Color("c7fff1"))
		"rock":
			draw_colored_polygon(PackedVector2Array([Vector2(-18, 8), Vector2(-13, -12), Vector2(3, -18), Vector2(19, -5), Vector2(14, 14), Vector2(-4, 18)]), Color("776f68"))
			draw_line(Vector2(-10, -7), Vector2(5, -12), Color("aca295"), 3.0)
		"tree":
			draw_rect(Rect2(-7, -2, 14, 34), Color("795438"))
			draw_circle(Vector2(0, -13), 24.0, Color("3f7e4c"))
		"metal":
			draw_rect(Rect2(-17, -17, 34, 34), Color("8f9aa8"))
			draw_rect(Rect2(-12, -12, 24, 24), Color("596775"), false, 3.0)
		"sword":
			draw_line(Vector2(-14, 14), Vector2(14, -14), Color("dce9ee"), 6.0)
			draw_line(Vector2(-12, 8), Vector2(-5, 15), Color("e2a93b"), 4.0)
		"key":
			draw_arc(Vector2(-7, 0), 8.0, 0.0, TAU, 16, Color("f2c94c"), 4.0)
			draw_line(Vector2(1, 0), Vector2(18, 0), Color("f2c94c"), 4.0)
		"shield":
			draw_colored_polygon(PackedVector2Array([Vector2(-16, -16), Vector2(16, -16), Vector2(13, 9), Vector2(0, 21), Vector2(-13, 9)]), Color("9eabb7"))
		"cage":
			draw_rect(Rect2(-19, -20, 38, 40), Color("9eabb7"), false, 4.0)
			for bar_x in [-10.0, 0.0, 10.0]:
				draw_line(Vector2(bar_x, -19), Vector2(bar_x, 19), Color("7d8994"), 3.0)
		_:
			draw_rect(Rect2(-17, -17, 34, 34), Color("a76c3d"))
			draw_line(Vector2(-16, -16), Vector2(16, 16), Color("6f432b"), 3.0)
			draw_line(Vector2(16, -16), Vector2(-16, 16), Color("6f432b"), 3.0)


func reset_actor() -> void:
	permanently_destroyed = false
	health = 58.0
	dead_for = 0.0
	attack_cooldown = 0.0
	alertness = 0.0
	alert_state = "patrol"
	last_seen_position = home
	look_direction = Vector2.LEFT
	states.clear()
	transformed_form = ""
	temperature = 0.5
	wetness = 0.0
	impulse = Vector2.ZERO
	velocity = Vector2.ZERO
	visible = true
	collision_layer = 1
	collision_mask = 1
	global_position = home
	set_physics_process(true)
	update_collision_shape()
	queue_redraw()
