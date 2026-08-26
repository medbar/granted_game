extends Node2D

var form := "field"
var payload: Dictionary = {}
var travel_velocity := Vector2.ZERO
var effect_radius := 24.0
var lifetime := 1.0
var elapsed := 0.0
var contact_interval := 0.4
var game: Node
var last_contact: Dictionary = {}


func setup(effect: Dictionary, unit: float, game_node: Node, interval: float) -> void:
	game = game_node
	form = str(effect.get("form", "field"))
	payload = effect.get("payload", {})
	var position_data: Array = effect.get("position", [0.0, 0.0])
	position = Vector2(float(position_data[0]), float(position_data[1])) * unit
	var velocity_data: Array = effect.get("velocity", [0.0, 0.0])
	travel_velocity = Vector2(float(velocity_data[0]), float(velocity_data[1])) * unit
	effect_radius = maxf(12.0, float(effect.get("radius", 0.5)) * unit)
	lifetime = maxf(0.15, float(effect.get("lifetime", 1.0)))
	contact_interval = maxf(0.1, interval)


func _physics_process(delta: float) -> void:
	elapsed += delta
	if form == "projectile":
		position += travel_velocity * delta
	if is_instance_valid(game):
		resolve_contacts()
	if elapsed >= lifetime:
		queue_free()


func resolve_contacts() -> void:
	for candidate in game.get_runtime_candidates():
		var target_id := str(candidate.get("id", ""))
		if target_id.is_empty():
			continue
		if target_id == "player" and elapsed < 0.18:
			continue
		if elapsed - float(last_contact.get(target_id, -100.0)) < contact_interval:
			continue
		if not contains_candidate(candidate):
			continue
		var direction := travel_velocity.normalized()
		if direction.length_squared() < 0.01:
			direction = global_position.direction_to(candidate["position"])
		game.apply_runtime_payload(target_id, payload, direction)
		last_contact[target_id] = elapsed
		if form == "projectile":
			queue_free()
			return


func contains_candidate(candidate: Dictionary) -> bool:
	var candidate_position: Vector2 = candidate["position"]
	var candidate_radius := float(candidate.get("radius", 16.0))
	match form:
		"beam":
			var direction := travel_velocity.normalized()
			if direction.length_squared() < 0.01:
				direction = Vector2.RIGHT
			var endpoint := global_position + direction * effect_radius * 5.0
			return Geometry2D.get_closest_point_to_segment(candidate_position, global_position, endpoint).distance_to(candidate_position) <= candidate_radius + effect_radius * 0.28
		"wall":
			var perpendicular := travel_velocity.normalized().orthogonal()
			if perpendicular.length_squared() < 0.01:
				perpendicular = Vector2.UP
			var start := global_position - perpendicular * effect_radius * 1.5
			var finish := global_position + perpendicular * effect_radius * 1.5
			return Geometry2D.get_closest_point_to_segment(candidate_position, start, finish).distance_to(candidate_position) <= candidate_radius + effect_radius * 0.25
		"ring":
			var distance := global_position.distance_to(candidate_position)
			return absf(distance - effect_radius) <= candidate_radius + effect_radius * 0.35
		_:
			return global_position.distance_to(candidate_position) <= effect_radius + candidate_radius
