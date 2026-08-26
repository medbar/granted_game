extends CharacterBody2D

var object_id := "prop"
var prop_kind := "rock"
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


func setup(id_value: String, kind_value: String, spawn_position: Vector2) -> void:
	object_id = id_value
	prop_kind = kind_value
	global_position = spawn_position
	match prop_kind:
		"crate":
			material_name = "wood"
			mass = 0.8
			flammability = 0.9
			hardness = 0.35
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


func _ready() -> void:
	collision_layer = 1
	collision_mask = 1
	var shape := CollisionShape2D.new()
	if prop_kind == "crate" or prop_kind == "metal":
		var rectangle := RectangleShape2D.new()
		rectangle.size = Vector2(34, 34)
		shape.shape = rectangle
	else:
		var circle := CircleShape2D.new()
		circle.radius = 20.0 if prop_kind == "tree" else 17.0
		shape.shape = circle
	add_child(shape)
	queue_redraw()


func _physics_process(delta: float) -> void:
	if health <= 0.0:
		visible = false
		collision_layer = 0
		set_physics_process(false)
		return
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


func apply_world_action(action: Dictionary, unit: float) -> void:
	match str(action.get("type", "")):
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
		"ADD_STATE":
			states[str(action.get("state", "unstable"))] = float(action.get("duration", 1.0))
		"REMOVE_STATE":
			states.erase(str(action.get("state", "")))
	queue_redraw()


func get_snapshot(unit: float) -> Dictionary:
	var tags: Array = [material_name, "inanimate", "prop"]
	if prop_kind == "tree":
		tags.append_array(["plant", "tree"])
	elif prop_kind == "rock":
		tags.append("rock")
	var state_values: Array = []
	for state_name in states:
		state_values.append({"name": state_name, "strength": 1.0, "remaining_duration": states[state_name], "source": "magic"})
	return {
		"id": object_id,
		"kind": "prop",
		"tags": tags,
		"position": {"x": global_position.x / unit, "y": global_position.y / unit},
		"velocity": {"x": velocity.x / unit, "y": velocity.y / unit},
		"radius": 0.35,
		"health": health,
		"material": {"name": material_name, "mass": mass, "temperature": temperature, "wetness": wetness, "flammability": flammability, "conductivity": conductivity, "hardness": hardness, "brittleness": brittleness},
		"states": state_values
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
