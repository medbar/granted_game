extends CharacterBody2D

const ENEMY_VIEW_DISTANCE := 280.0
const ENEMY_VIEW_HALF_ANGLE := 0.72
const ENEMY_HEARING_RADIUS := 82.0
const ENEMY_ALERT_THRESHOLD := 0.52

var object_id := "prop"
var prop_kind := "rock"
var initial_prop_kind := "rock"
var home := Vector2.ZERO
var material_name := "stone"
var health := 80.0
var mass := 2.5
var temperature := 0.5
var wetness := 0.0
var flammability := 0.0
var conductivity := 0.1
var hardness := 0.9
var brittleness := 0.6
var impulse := Vector2.ZERO
var states: Dictionary = {}
var wander_phase := 0.0
var target: Node2D
var attack_cooldown := 0.0
var collected := false
var door_installed := false
var look_direction := Vector2.LEFT
var alertness := 0.0
var alert_state := "patrol"
var last_seen_position := Vector2.ZERO
var definition_tags: Array = []
var definition_properties: Dictionary = {}
var initial_health := 80.0


func setup(id_value: String, kind_value: String, spawn_position: Vector2, target_node: Node2D = null, definition: Dictionary = {}) -> void:
	object_id = id_value
	initial_prop_kind = kind_value
	home = spawn_position
	global_position = spawn_position
	wander_phase = float(id_value.hash() % 1000) / 100.0
	target = target_node
	definition_tags = definition.get("tags", []).duplicate(true)
	definition_properties = definition.get("properties", {}).duplicate(true)
	initial_health = float(definition.get("health", 80.0))
	health = initial_health
	configure_kind(kind_value)
	var source_material: Dictionary = definition.get("material", {})
	material_name = str(source_material.get("name", material_name))
	mass = float(source_material.get("mass", mass))
	temperature = float(source_material.get("temperature", temperature))
	wetness = float(source_material.get("wetness", wetness))
	flammability = float(source_material.get("flammability", flammability))
	conductivity = float(source_material.get("conductivity", conductivity))
	hardness = float(source_material.get("hardness", hardness))
	brittleness = float(source_material.get("brittleness", brittleness))


func configure_kind(kind_value: String) -> void:
	prop_kind = kind_value
	if prop_kind != "enemy":
		alertness = 0.0
		alert_state = "patrol"
	material_name = "stone"
	mass = 2.5
	flammability = 0.0
	conductivity = 0.1
	hardness = 0.9
	brittleness = 0.6
	match prop_kind:
		"loot", "gem", "artifact":
			material_name = "crystal"
			mass = 0.25
			conductivity = 0.35
			hardness = 0.72
			brittleness = 0.35
		"blood", "blood_pool":
			material_name = "blood"
			mass = 0.2
			hardness = 0.0
			wetness = 1.0
		"sword", "key", "magic_key", "cage", "shield":
			material_name = "metal"
			mass = 1.0
			conductivity = 0.9
			hardness = 0.75
		"fire":
			material_name = "fire"
			mass = 0.01
			flammability = 0.0
			hardness = 0.0
		"crate", "wall", "trap":
			material_name = "wood"
			mass = 2.5 if prop_kind == "wall" else 0.8
			flammability = 0.9
			hardness = 0.75 if prop_kind == "wall" else 0.35
			brittleness = 0.4
		"tree":
			material_name = "wood"
			mass = 1.2
			flammability = 0.95
			hardness = 0.4
		"metal":
			material_name = "metal"
			mass = 2.0
			conductivity = 0.95
			hardness = 0.8
		"npc", "enemy":
			material_name = "organic"
			mass = 1.0
			flammability = 0.35
			conductivity = 0.2
			hardness = 0.2
			brittleness = 0.1
	if is_inside_tree():
		update_collision_shape()
	queue_redraw()


func _ready() -> void:
	# Conjured walls are real blockers; ordinary props remain non-blocking.
	collision_layer = 1 if prop_kind == "wall" else 0
	collision_mask = 1
	update_collision_shape()
	queue_redraw()


func update_collision_shape() -> void:
	var shape: CollisionShape2D = null
	for child in get_children():
		if child is CollisionShape2D:
			shape = child
			break
	if shape == null:
		shape = CollisionShape2D.new()
		add_child(shape)
	if prop_kind in ["crate", "metal", "wall"]:
		var rectangle := RectangleShape2D.new()
		rectangle.size = Vector2(72, 22) if prop_kind == "wall" else Vector2(34, 34)
		shape.shape = rectangle
	else:
		var circle := CircleShape2D.new()
		circle.radius = 20.0 if prop_kind == "tree" else 17.0
		shape.shape = circle


func _physics_process(delta: float) -> void:
	if collected:
		return
	if health <= 0.0:
		visible = false
		collision_layer = 0
		set_physics_process(false)
		return
	attack_cooldown = maxf(0.0, attack_cooldown - delta)
	if prop_kind == "npc":
		wander_phase += delta * 0.45
		var desired := Vector2(cos(wander_phase), sin(wander_phase * 0.8))
		if global_position.distance_to(home) > 75.0:
			desired = global_position.direction_to(home)
		velocity = desired.normalized() * 28.0 + impulse
	elif prop_kind == "enemy":
		var desired := Vector2.ZERO
		if is_instance_valid(target):
			var distance := global_position.distance_to(target.global_position)
			var perceived := enemy_can_perceive_target()
			if perceived:
				last_seen_position = target.global_position
				if distance <= ENEMY_HEARING_RADIUS:
					alertness = maxf(ENEMY_ALERT_THRESHOLD, minf(1.0, alertness + delta * 2.8))
				else:
					alertness = minf(1.0, alertness + delta * 1.25)
			else:
				alertness = maxf(0.0, alertness - delta * 0.3)
			alert_state = "alert" if alertness >= ENEMY_ALERT_THRESHOLD else ("suspicious" if alertness > 0.04 else "patrol")
			if alert_state == "alert" and distance < 540.0:
				desired = global_position.direction_to(target.global_position)
				if distance < 38.0 and attack_cooldown <= 0.0 and target.has_method("damage"):
					target.damage(7.0)
					attack_cooldown = 1.15
			elif alert_state == "suspicious" and global_position.distance_to(last_seen_position) > 12.0:
				desired = global_position.direction_to(last_seen_position) * 0.55
		if desired.length_squared() > 0.01:
			look_direction = desired.normalized()
		velocity = desired.normalized() * 78.0 + impulse
	else:
		velocity = impulse
	move_and_slide()
	impulse = impulse.move_toward(Vector2.ZERO, 330.0 * delta)
	for state_name in states.keys():
		states[state_name] = float(states[state_name]) - delta
		if state_name == "burning":
			health -= 3.0 * delta
		if states[state_name] <= 0.0:
			states.erase(state_name)
	queue_redraw()


func enemy_can_perceive_target() -> bool:
	if prop_kind != "enemy" or not is_instance_valid(target):
		return false
	var offset := target.global_position - global_position
	var distance := offset.length()
	if distance <= ENEMY_HEARING_RADIUS:
		return true
	if distance > ENEMY_VIEW_DISTANCE or distance <= 0.001:
		return false
	if look_direction.normalized().dot(offset.normalized()) < cos(ENEMY_VIEW_HALF_ANGLE):
		return false
	var query := PhysicsRayQueryParameters2D.create(global_position, target.global_position, 1, [self])
	var hit := get_world_2d().direct_space_state.intersect_ray(query)
	return hit.is_empty() or hit.get("collider") == target


func apply_world_action(action: Dictionary, unit: float) -> void:
	match str(action.get("type", "")):
		"DESTROY_OBJECT":
			health = 0.0
			visible = false
			velocity = Vector2.ZERO
			collision_layer = 0
			collision_mask = 0
			set_physics_process(false)
		"DAMAGE":
			health -= float(action.get("amount", 0.0))
		"HEAL":
			health += float(action.get("amount", 0.0))
		"APPLY_FORCE", "CHANGE_VELOCITY":
			var direction_data: Dictionary = action.get("direction", {})
			impulse += Vector2(float(direction_data.get("x", 0.0)), float(direction_data.get("y", 0.0))) * float(action.get("strength", 0.0)) * unit
		"CHANGE_TEMPERATURE":
			temperature += float(action.get("amount", 0.0))
		"CHANGE_WETNESS":
			wetness = clampf(wetness + float(action.get("amount", 0.0)), 0.0, 1.0)
		"CHANGE_MATERIAL_STATE":
			material_name = str(action.get("material", material_name))
			if material_name == "ice":
				hardness = 0.75
				brittleness = 0.8
			elif material_name == "water":
				hardness = 0.0
				wetness = 1.0
		"TRANSFORM_OBJECT":
			var effect: Dictionary = action.get("effect", {})
			configure_kind(str(effect.get("prototype", prop_kind)))
		"ADD_STATE":
			var state_name := str(action.get("state", "unstable"))
			states[state_name] = float(action.get("duration", 1.0))
			if state_name == "wet":
				wetness = 1.0
		"REMOVE_STATE":
			states.erase(str(action.get("state", "")))
		"INSTALL_DOOR":
			if prop_kind == "wall":
				door_installed = true
				collision_layer = 0
	queue_redraw()


func reset_prop() -> void:
	configure_kind(initial_prop_kind)
	collected = false
	door_installed = false
	global_position = home
	health = initial_health
	temperature = 0.5
	wetness = 0.0
	impulse = Vector2.ZERO
	velocity = Vector2.ZERO
	attack_cooldown = 0.0
	alertness = 0.0
	alert_state = "patrol"
	last_seen_position = home
	look_direction = Vector2.LEFT
	states.clear()
	visible = true
	collision_layer = 0
	collision_mask = 1
	set_physics_process(true)
	queue_redraw()


func is_heist_loot() -> bool:
	return initial_prop_kind in ["loot", "gem", "artifact"]


func collect_loot() -> bool:
	if collected or not is_heist_loot():
		return false
	collected = true
	visible = false
	velocity = Vector2.ZERO
	collision_layer = 0
	collision_mask = 0
	set_physics_process(false)
	return true


func get_snapshot(unit: float) -> Dictionary:
	if prop_kind == "npc" or prop_kind == "enemy":
		var role_tags := ["living", "organic", "transformed"]
		if prop_kind == "enemy":
			role_tags.append_array(["enemy", "hostile"])
			if alert_state == "alert":
				role_tags.append("alerted")
		else:
			role_tags.append_array(["npc", "villager", "friendly"])
		var creature_properties: Dictionary = definition_properties.duplicate(true)
		creature_properties["prototype"] = prop_kind
		creature_properties["initial_prototype"] = initial_prop_kind
		creature_properties["visible"] = visible
		creature_properties["removed"] = health <= 0.0
		return {
			"id": object_id,
			"kind": "creature",
			"tags": role_tags,
			"position": {"x": global_position.x / unit, "y": global_position.y / unit},
			"velocity": {"x": velocity.x / unit, "y": velocity.y / unit},
			"radius": 0.35,
			"health": health,
			"material": {"name": "organic", "mass": 1.0, "temperature": temperature, "wetness": wetness, "flammability": 0.35, "conductivity": 0.2, "hardness": 0.2, "brittleness": 0.1},
			"states": [],
			"properties": creature_properties
		}
	var tags: Array = definition_tags.duplicate(true)
	for required_tag in [material_name, "inanimate", "prop", prop_kind]:
		if not tags.has(required_tag):
			tags.append(required_tag)
	if is_heist_loot():
		tags.append_array(["loot", "valuable", "heist_objective"])
	if object_id.begins_with("created_"):
		tags.append("created")
	if prop_kind == "tree":
		tags.append_array(["plant", "tree"])
	elif prop_kind == "rock":
		tags.append("rock")
	var state_values: Array = []
	for state_name in states:
		state_values.append({"name": state_name, "strength": 1.0, "remaining_duration": states[state_name], "source": "magic"})
	var snapshot_properties: Dictionary = definition_properties.duplicate(true)
	snapshot_properties["prototype"] = prop_kind
	snapshot_properties["initial_prototype"] = initial_prop_kind
	snapshot_properties["door_installed"] = door_installed
	snapshot_properties["collected"] = collected
	snapshot_properties["visible"] = visible
	snapshot_properties["hidden"] = not visible
	snapshot_properties["removed"] = health <= 0.0
	return {
		"id": object_id,
		"kind": "prop",
		"tags": tags,
		"position": {"x": global_position.x / unit, "y": global_position.y / unit},
		"velocity": {"x": velocity.x / unit, "y": velocity.y / unit},
		"radius": 0.35,
		"health": health,
		"material": {"name": material_name, "mass": mass, "temperature": temperature, "wetness": wetness, "flammability": flammability, "conductivity": conductivity, "hardness": hardness, "brittleness": brittleness},
		"states": state_values,
		"properties": snapshot_properties
	}


func _draw() -> void:
	if states.has("levitating"):
		draw_set_transform(Vector2(0, 12), 0.0, Vector2(1.0, 0.42))
		draw_circle(Vector2.ZERO, 20.0, Color(0.0, 0.0, 0.0, 0.28))
		draw_set_transform(Vector2(0, -10))
	if material_name == "ice":
		draw_circle(Vector2.ZERO, 24.0, Color(0.55, 0.9, 1.0, 0.7))
		draw_arc(Vector2.ZERO, 24.0, 0.0, TAU, 16, Color("e4fbff"), 3.0)
		return
	if prop_kind == "blood" or prop_kind == "blood_pool":
		draw_set_transform(Vector2.ZERO, 0.0, Vector2(1.7, 0.55))
		draw_circle(Vector2.ZERO, 22.0, Color(0.48, 0.0, 0.04, 0.82))
		draw_circle(Vector2(7, -3), 11.0, Color(0.72, 0.02, 0.06, 0.66))
		draw_set_transform(Vector2.ZERO)
		return
	if prop_kind == "fire":
		var pulse := 0.78 + 0.22 * sin(Time.get_ticks_msec() * 0.008 + float(object_id.hash() % 11))
		draw_circle(Vector2(0, 11), 18.0, Color(1.0, 0.18, 0.04, 0.24))
		draw_colored_polygon(PackedVector2Array([Vector2(-15, 15), Vector2(-10, -5), Vector2(-3, 2), Vector2(1, -24 * pulse), Vector2(8, -4), Vector2(15, 15)]), Color("ff5b24"))
		draw_colored_polygon(PackedVector2Array([Vector2(-8, 14), Vector2(-3, 1), Vector2(2, -13 * pulse), Vector2(8, 14)]), Color("ffd45a"))
		return
	if prop_kind == "sword":
		draw_line(Vector2(-14, 14), Vector2(14, -14), Color("dce9ee"), 6.0)
		draw_line(Vector2(-12, 8), Vector2(-5, 15), Color("e2a93b"), 4.0)
		return
	if prop_kind == "key" or prop_kind == "magic_key":
		draw_arc(Vector2(-7, 0), 8.0, 0.0, TAU, 16, Color("f2c94c"), 4.0)
		draw_line(Vector2(1, 0), Vector2(18, 0), Color("f2c94c"), 4.0)
		draw_line(Vector2(12, 0), Vector2(12, 7), Color("f2c94c"), 3.0)
		return
	if prop_kind == "cage":
		draw_rect(Rect2(-19, -20, 38, 40), Color("9eabb7"), false, 4.0)
		for bar_x in [-10.0, 0.0, 10.0]:
			draw_line(Vector2(bar_x, -19), Vector2(bar_x, 19), Color("7d8994"), 3.0)
		return
	if prop_kind == "wall":
		draw_rect(Rect2(-36, -11, 72, 22), Color("6e5540"))
		for brick_x in [-24.0, 0.0, 24.0]:
			draw_line(Vector2(brick_x, -10), Vector2(brick_x, 10), Color("a3815d"), 2.0)
		draw_line(Vector2(-35, 0), Vector2(35, 0), Color("a3815d"), 2.0)
		if door_installed:
			draw_rect(Rect2(-20, -11, 40, 22), Color("102a33"))
			draw_rect(Rect2(-18, -9, 36, 18), Color("e1b45d"), false, 3.0)
			draw_line(Vector2(-15, 0), Vector2(15, 0), Color("73e6df"), 2.0)
		return
	if prop_kind == "trap":
		draw_colored_polygon(PackedVector2Array([Vector2(-20, 14), Vector2(-10, -14), Vector2(0, 14), Vector2(10, -14), Vector2(20, 14)]), Color("d7dce0"))
		draw_circle(Vector2.ZERO, 7.0, Color("b33a32"))
		return
	if prop_kind == "portal":
		draw_arc(Vector2.ZERO, 24.0, 0.0, TAU, 32, Color("a875ff"), 7.0)
		draw_circle(Vector2.ZERO, 17.0, Color(0.2, 0.04, 0.35, 0.55))
		return
	if prop_kind == "sleep_dust":
		for index in range(7):
			var dust_angle := float(index) / 7.0 * TAU
			draw_circle(Vector2.from_angle(dust_angle) * (8.0 + index), 4.0, Color(0.68, 0.62, 1.0, 0.62))
		return
	if prop_kind == "loot" or prop_kind == "gem" or prop_kind == "artifact":
		var gem_points := PackedVector2Array([Vector2(0, -20), Vector2(16, -5), Vector2(9, 18), Vector2(-9, 18), Vector2(-16, -5)])
		draw_colored_polygon(gem_points, Color("ffd85a"))
		draw_polyline(PackedVector2Array([Vector2(0, -20), Vector2(16, -5), Vector2(9, 18), Vector2(-9, 18), Vector2(-16, -5), Vector2(0, -20)]), Color("fff2a6"), 3.0)
		draw_line(Vector2(-15, -5), Vector2(15, -5), Color("fff7c7"), 2.0)
		draw_circle(Vector2(5, -10), 3.0, Color.WHITE)
		return
	if prop_kind == "enemy":
		var cone_color := Color(0.2, 0.82, 0.9, 0.08)
		if alert_state == "suspicious":
			cone_color = Color(1.0, 0.78, 0.18, 0.13)
		elif alert_state == "alert":
			cone_color = Color(1.0, 0.18, 0.16, 0.2)
		var cone_points := PackedVector2Array([Vector2.ZERO])
		var center_angle := look_direction.angle()
		for index in range(13):
			var ratio := float(index) / 12.0
			cone_points.append(Vector2.from_angle(center_angle - ENEMY_VIEW_HALF_ANGLE + ENEMY_VIEW_HALF_ANGLE * 2.0 * ratio) * ENEMY_VIEW_DISTANCE)
		draw_colored_polygon(cone_points, cone_color)
	if prop_kind == "npc" or prop_kind == "enemy":
		draw_circle(Vector2.ZERO, 16.0, Color("8e3f36") if prop_kind == "enemy" else Color("315c70"))
		draw_circle(Vector2(0, -5), 9.0, Color("d8a77a"))
		draw_colored_polygon(PackedVector2Array([Vector2(-10, 1), Vector2(10, 1), Vector2(7, 18), Vector2(-7, 18)]), Color("d49a43") if prop_kind == "enemy" else Color("4ca6a8"))
		draw_arc(Vector2.ZERO, 21.0, -2.7, -0.45, 12, Color("ff7b72") if prop_kind == "enemy" else Color("82e6d0"), 2.0)
		var fallback_font := ThemeDB.fallback_font
		draw_string(fallback_font, Vector2(-20, -27), "ENEMY" if prop_kind == "enemy" else "NPC", HORIZONTAL_ALIGNMENT_CENTER, 40, 11, Color("ffd0c9") if prop_kind == "enemy" else Color("c7fff1"))
		return
	if prop_kind == "rock":
		draw_colored_polygon(PackedVector2Array([Vector2(-18, 8), Vector2(-13, -12), Vector2(3, -18), Vector2(19, -5), Vector2(14, 14), Vector2(-4, 18)]), Color("776f68"))
		draw_line(Vector2(-10, -7), Vector2(5, -12), Color("aca295"), 3.0)
	elif prop_kind == "tree":
		draw_rect(Rect2(-7, -2, 14, 34), Color("795438"))
		draw_circle(Vector2(0, -13), 24.0, Color("3f7e4c"))
		draw_circle(Vector2(-13, -3), 15.0, Color("4d9658"))
		draw_circle(Vector2(13, -4), 15.0, Color("4d9658"))
	elif prop_kind == "metal":
		draw_rect(Rect2(-17, -17, 34, 34), Color("8f9aa8"))
		draw_rect(Rect2(-12, -12, 24, 24), Color("596775"), false, 3.0)
	else:
		draw_rect(Rect2(-17, -17, 34, 34), Color("a76c3d"))
		draw_line(Vector2(-16, -16), Vector2(16, 16), Color("6f432b"), 3.0)
		draw_line(Vector2(16, -16), Vector2(-16, 16), Color("6f432b"), 3.0)
	if states.has("burning"):
		draw_circle(Vector2(0, -22), 11.0, Color(1.0, 0.28, 0.05, 0.75))
		draw_circle(Vector2(4, -31), 7.0, Color(1.0, 0.78, 0.1, 0.7))
	if states.has("electrified"):
		draw_arc(Vector2.ZERO, 25.0, 0.0, TAU, 8, Color("c8f7ff"), 3.0)
