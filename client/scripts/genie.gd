extends Node2D

const FOLLOW_OFFSET := Vector2(-54.0, -54.0)

var companion: CharacterBody2D
var facing := Vector2.RIGHT
var wish_active := false
var granting := false
var hover_time := 0.0


func setup(owner: CharacterBody2D) -> void:
	companion = owner
	global_position = owner.global_position + FOLLOW_OFFSET
	queue_redraw()


func _process(delta: float) -> void:
	hover_time += delta
	if is_instance_valid(companion):
		var bob := Vector2(0.0, sin(hover_time * 2.6) * 5.0)
		var desired := companion.global_position + FOLLOW_OFFSET + bob
		global_position = global_position.lerp(desired, 1.0 - exp(-7.0 * delta))
	var mouse_direction := global_position.direction_to(get_global_mouse_position())
	if mouse_direction.length_squared() > 0.001:
		facing = mouse_direction
	queue_redraw()


func set_wish_state(active: bool, is_granting: bool = false) -> void:
	wish_active = active
	granting = is_granting
	queue_redraw()


func snap_to_companion() -> void:
	if is_instance_valid(companion):
		global_position = companion.global_position + FOLLOW_OFFSET


func _draw() -> void:
	var pulse := 0.5 + 0.5 * sin(hover_time * 4.2)
	draw_set_transform(Vector2(0, 36), 0.0, Vector2(1.0, 0.38))
	draw_circle(Vector2.ZERO, 22.0, Color(0.0, 0.0, 0.0, 0.25))
	draw_set_transform(Vector2.ZERO)

	if wish_active:
		var aura_alpha := 0.18 + pulse * (0.13 if granting else 0.07)
		draw_circle(Vector2(0, -9), 38.0 + pulse * 4.0, Color(0.25, 0.96, 0.9, aura_alpha))
		draw_arc(Vector2(0, -9), 32.0 + pulse * 3.0, 0.0, TAU, 36, Color(1.0, 0.77, 0.25, 0.68), 2.0)

	# A tapering magical tail makes the genie visibly airborne and distinct from the player.
	draw_circle(Vector2(0, 24), 11.0, Color("35c6c2"))
	draw_circle(Vector2(3, 33), 8.0, Color(0.2, 0.78, 0.75, 0.72))
	draw_circle(Vector2(-2, 40), 5.0, Color(0.28, 0.92, 0.86, 0.42))
	draw_colored_polygon(PackedVector2Array([
		Vector2(-18, -8), Vector2(18, -8), Vector2(13, 23), Vector2(-12, 23)
	]), Color("239da6"))
	draw_circle(Vector2(0, -20), 15.0, Color("55d6cf"))
	draw_circle(Vector2(-15, -20), 4.5, Color("55d6cf"))
	draw_circle(Vector2(15, -20), 4.5, Color("55d6cf"))
	draw_colored_polygon(PackedVector2Array([
		Vector2(-13, -29), Vector2(-7, -38), Vector2(0, -31), Vector2(8, -39), Vector2(14, -28)
	]), Color("183f61"))
	draw_arc(Vector2(0, -17), 10.0, 0.18, PI - 0.18, 16, Color("17465e"), 3.0)

	var eye_offset := facing.normalized() * 1.8
	draw_circle(Vector2(-5, -22) + eye_offset, 2.0, Color("fff5c2"))
	draw_circle(Vector2(5, -22) + eye_offset, 2.0, Color("fff5c2"))
	draw_line(Vector2(-18, -4), Vector2(-29, 5), Color("48c9c4"), 7.0, true)
	draw_line(Vector2(18, -4), Vector2(29, 5), Color("48c9c4"), 7.0, true)
	draw_circle(Vector2(-29, 5), 4.0, Color("f5be42"))
	draw_circle(Vector2(29, 5), 4.0, Color("f5be42"))
	draw_arc(Vector2(0, 7), 15.0, 0.0, TAU, 24, Color("f5be42"), 3.0)

	if granting:
		for index in range(6):
			var angle := hover_time * 2.2 + float(index) / 6.0 * TAU
			var point := Vector2.from_angle(angle) * (31.0 + pulse * 5.0) + Vector2(0, -9)
			draw_circle(point, 2.2, Color("fff1a8"))
