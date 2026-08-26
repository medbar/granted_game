extends Node2D

var primitive := "BURST"
var appearances: Array = ["force"]
var direction := Vector2.RIGHT
var radius := 32.0
var speed := 0.0
var intensity := 1.0
var turbulence := 0.0
var lifetime := 1.0
var elapsed := 0.0
var target_position := Vector2.ZERO
var has_target := false

const COLORS := {
	"fire": Color("ff6b35"), "water": Color("3aa7ff"), "ice": Color("a8edff"),
	"steam": Color("d9e5e8"), "air": Color("b8f1de"), "stone": Color("9a9083"),
	"metal": Color("d5dae2"), "light": Color("fff29c"), "darkness": Color("5a3f82"),
	"electricity": Color("c8f7ff"), "poison": Color("86d645"), "life": Color("78e08f"),
	"decay": Color("7b5b42"), "force": Color("c99cff")
}


func setup(descriptor: Dictionary, unit: float) -> void:
	primitive = str(descriptor.get("primitive", "BURST"))
	appearances = descriptor.get("appearance", ["force"])
	var origin: Dictionary = descriptor.get("origin", {})
	global_position = Vector2(float(origin.get("x", 0.0)), float(origin.get("y", 0.0))) * unit
	var direction_data: Dictionary = descriptor.get("direction", {})
	direction = Vector2(float(direction_data.get("x", 1.0)), float(direction_data.get("y", 0.0))).normalized()
	radius = maxf(12.0, float(descriptor.get("radius", 0.5)) * unit)
	speed = float(descriptor.get("speed", 0.0)) * unit
	intensity = float(descriptor.get("intensity", 1.0))
	turbulence = float(descriptor.get("turbulence", 0.0))
	lifetime = maxf(0.2, float(descriptor.get("lifetime", 1.0)))
	if descriptor.get("target") != null:
		var target_data: Dictionary = descriptor["target"]
		target_position = Vector2(float(target_data.get("x", 0.0)), float(target_data.get("y", 0.0))) * unit
		has_target = true
	queue_redraw()


func _process(delta: float) -> void:
	elapsed += delta
	if primitive in ["PROJECTILE", "TRAIL"]:
		global_position += direction * speed * delta
	if elapsed >= lifetime:
		queue_free()
	else:
		queue_redraw()


func _color() -> Color:
	var first: Color = COLORS.get(str(appearances[0]) if not appearances.is_empty() else "force", COLORS["force"])
	if appearances.size() > 1:
		return first.lerp(COLORS.get(str(appearances[1]), first), 0.35)
	return first


func _draw() -> void:
	var progress := clampf(elapsed / lifetime, 0.0, 1.0)
	var alpha := (1.0 - progress) * (0.55 + intensity * 0.4)
	var color := Color(_color(), alpha)
	var bright := Color(_color().lightened(0.35), alpha)
	match primitive:
		"PROJECTILE":
			draw_circle(Vector2.ZERO, radius * 0.45, color)
			draw_circle(Vector2.ZERO, radius * 0.18, bright)
			draw_line(-direction * radius * 1.7, Vector2.ZERO, Color(color, alpha * 0.5), radius * 0.25, true)
		"BEAM":
			var beam_end := to_local(target_position) if has_target else direction * maxf(180.0, radius * 4.0)
			draw_line(Vector2.ZERO, beam_end, Color(color, alpha * 0.3), radius * 0.42, true)
			draw_line(Vector2.ZERO, beam_end, bright, maxf(2.0, radius * 0.12), true)
		"LINE":
			var perpendicular := direction.orthogonal()
			draw_line(-perpendicular * radius * 1.5, perpendicular * radius * 1.5, color, maxf(7.0, radius * 0.3), true)
			draw_line(-perpendicular * radius * 1.5, perpendicular * radius * 1.5, bright, 2.0, true)
		"RING":
			draw_arc(Vector2.ZERO, radius * (0.35 + progress * 0.85), 0.0, TAU, 64, color, maxf(3.0, radius * 0.12), true)
		"FIELD":
			draw_circle(Vector2.ZERO, radius * (0.8 + sin(elapsed * 5.0) * 0.05), Color(color, alpha * 0.28))
			draw_arc(Vector2.ZERO, radius, 0.0, TAU, 48, bright, 3.0, true)
		"CLOUD":
			for index in range(8):
				var angle := float(index) / 8.0 * TAU + elapsed * 0.35
				var offset := Vector2.from_angle(angle) * radius * (0.25 + float(index % 3) * 0.16)
				draw_circle(offset, radius * (0.24 + float(index % 2) * 0.08), Color(color, alpha * 0.35))
		"TRAIL":
			draw_line(-direction * radius * 2.2, direction * radius * 0.35, color, maxf(4.0, radius * 0.16), true)
		"TETHER":
			var tether_end := to_local(target_position) if has_target else direction * radius * 3.0
			var points := PackedVector2Array()
			for index in range(9):
				var ratio := float(index) / 8.0
				points.append(tether_end * ratio + direction.orthogonal() * sin(ratio * TAU * 2.0 + elapsed * 12.0) * radius * 0.12)
			draw_polyline(points, color, 4.0, true)
		"SURFACE_OVERLAY":
			draw_circle(Vector2.ZERO, radius, Color(color, alpha * 0.22))
			for index in range(4):
				draw_line(Vector2(-radius, -radius * 0.6 + index * radius * 0.4), Vector2(radius, -radius * 0.6 + index * radius * 0.4), Color(bright, alpha * 0.45), 2.0)
		_:
			draw_circle(Vector2.ZERO, radius * (0.25 + progress), Color(color, alpha * 0.28))
			draw_arc(Vector2.ZERO, radius * (0.25 + progress), 0.0, TAU, 36, bright, maxf(2.0, radius * 0.08), true)

