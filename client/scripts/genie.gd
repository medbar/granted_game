extends Node2D

const FOLLOW_OFFSET := Vector2(-54.0, -54.0)
const ACCEPTANCE_PHRASES := [
	"Твоё желание — закон.",
	"Будет исполнено.",
	"Я услышал тебя.",
	"Как пожелаешь.",
	"Да свершится твоя воля.",
]

enum TravelPhase { IDLE, VANISHING, DISSOLVING, APPEARING }

var companion: CharacterBody2D
var facing := Vector2.RIGHT
var wish_active := false
var granting := false
var hover_time := 0.0
var interaction_focus_position := Vector2.ZERO
var interaction_focus_remaining := 0.0
var reflex_pulse_remaining := 0.0
var travel_phase := TravelPhase.IDLE
var travel_elapsed := 0.0
var travel_duration := 1.0
var travel_start_alpha := 1.0
var travel_destination := Vector2.ZERO
var speech_text := ""
var speech_remaining := 0.0
var speech_panel: PanelContainer
var speech_label: Label


func setup(owner: CharacterBody2D) -> void:
	companion = owner
	global_position = owner.global_position + FOLLOW_OFFSET
	queue_redraw()


func _ready() -> void:
	speech_panel = PanelContainer.new()
	speech_panel.position = Vector2(-165.0, -188.0)
	speech_panel.custom_minimum_size = Vector2(330.0, 116.0)
	speech_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	speech_panel.z_index = 50
	var bubble_style := StyleBoxFlat.new()
	bubble_style.bg_color = Color(0.025, 0.085, 0.13, 0.96)
	bubble_style.border_color = Color("f5c95c")
	bubble_style.set_border_width_all(3)
	bubble_style.set_corner_radius_all(12)
	bubble_style.content_margin_left = 14.0
	bubble_style.content_margin_right = 14.0
	bubble_style.content_margin_top = 10.0
	bubble_style.content_margin_bottom = 10.0
	speech_panel.add_theme_stylebox_override("panel", bubble_style)
	speech_label = Label.new()
	speech_label.custom_minimum_size = Vector2(296.0, 92.0)
	speech_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	speech_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	speech_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	speech_label.add_theme_font_size_override("font_size", 15)
	speech_label.add_theme_color_override("font_color", Color("fff4cf"))
	speech_panel.add_child(speech_label)
	add_child(speech_panel)
	speech_panel.visible = false


func _process(delta: float) -> void:
	hover_time += delta
	interaction_focus_remaining = maxf(0.0, interaction_focus_remaining - delta)
	reflex_pulse_remaining = maxf(0.0, reflex_pulse_remaining - delta)
	speech_remaining = maxf(0.0, speech_remaining - delta)
	if is_instance_valid(speech_panel):
		speech_panel.visible = speech_remaining > 0.0 and not speech_text.is_empty()
	var travel_controls_position := update_travel(delta)
	if travel_controls_position:
		pass
	elif interaction_focus_remaining > 0.0:
		global_position = interaction_focus_position + Vector2(0.0, -42.0 + sin(hover_time * 3.2) * 4.0)
	elif is_instance_valid(companion):
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
	travel_phase = TravelPhase.IDLE
	modulate.a = 1.0
	speech_remaining = 0.0


func appear_at_interaction(target_position: Vector2, duration: float = 1.0) -> float:
	interaction_focus_position = target_position
	interaction_focus_remaining = duration + 0.65
	travel_destination = target_position + Vector2(0.0, -42.0)
	travel_elapsed = 0.0
	if modulate.a <= 0.01:
		# The wish-acceptance animation already hid the genie. Relocate while it is
		# invisible and use the whole requested duration to manifest at the target.
		global_position = travel_destination
		travel_duration = maxf(0.2, duration) * 2.0
		travel_start_alpha = 0.0
		travel_phase = TravelPhase.APPEARING
		modulate.a = 0.0
		queue_redraw()
		# The genie is already at the target while fully invisible. The world action
		# may happen now; manifestation continues for the requested visual second.
		return 0.0
	travel_duration = maxf(0.2, duration)
	travel_start_alpha = modulate.a
	travel_phase = TravelPhase.DISSOLVING
	queue_redraw()
	return travel_duration * 0.5


func accept_wish() -> void:
	show_speech(str(ACCEPTANCE_PHRASES.pick_random()), 1.8)
	travel_duration = 1.0
	travel_elapsed = 0.0
	travel_start_alpha = modulate.a
	travel_phase = TravelPhase.VANISHING
	queue_redraw()


func show_speech(message: String, duration: float = 5.0) -> void:
	speech_text = message.strip_edges()
	speech_remaining = maxf(duration, clampf(float(speech_text.length()) / 24.0, 3.0, 10.0))
	if is_instance_valid(speech_label):
		speech_label.text = speech_text
	if is_instance_valid(speech_panel):
		speech_panel.visible = not speech_text.is_empty()
	queue_redraw()


func is_dissolved() -> bool:
	return modulate.a <= 0.01 and travel_phase == TravelPhase.IDLE


func reappear_near_companion(duration: float = 1.0) -> void:
	if not is_instance_valid(companion):
		return
	appear_at_interaction(companion.global_position + FOLLOW_OFFSET - Vector2(0.0, -42.0), duration)


func ensure_visible_near_companion(duration: float = 1.0) -> float:
	if modulate.a >= 0.99 and travel_phase == TravelPhase.IDLE:
		return 0.0
	reappear_near_companion(duration)
	return duration


func update_travel(delta: float) -> bool:
	if travel_phase == TravelPhase.IDLE:
		return false
	travel_elapsed += delta
	if travel_phase == TravelPhase.VANISHING:
		var progress := minf(1.0, travel_elapsed / travel_duration)
		modulate.a = lerpf(travel_start_alpha, 0.0, smoothstep(0.0, 1.0, progress))
		if progress >= 1.0:
			travel_phase = TravelPhase.IDLE
			modulate.a = 0.0
		return true
	var half_duration := travel_duration * 0.5
	if travel_phase == TravelPhase.DISSOLVING:
		var dissolve_progress := minf(1.0, travel_elapsed / half_duration)
		modulate.a = lerpf(travel_start_alpha, 0.0, smoothstep(0.0, 1.0, dissolve_progress))
		if dissolve_progress >= 1.0:
			global_position = travel_destination
			travel_phase = TravelPhase.APPEARING
			travel_elapsed = 0.0
			modulate.a = 0.0
		return true
	var appear_progress := minf(1.0, travel_elapsed / half_duration)
	global_position = travel_destination
	modulate.a = smoothstep(0.0, 1.0, appear_progress)
	if appear_progress >= 1.0:
		travel_phase = TravelPhase.IDLE
		modulate.a = 1.0
	return true


func acknowledge_wish() -> void:
	reflex_pulse_remaining = 0.9
	queue_redraw()


func _draw() -> void:
	var pulse := 0.5 + 0.5 * sin(hover_time * 4.2)
	draw_set_transform(Vector2(0, 36), 0.0, Vector2(1.0, 0.38))
	draw_circle(Vector2.ZERO, 22.0, Color(0.0, 0.0, 0.0, 0.25))
	draw_set_transform(Vector2.ZERO)

	if wish_active:
		var aura_alpha := 0.18 + pulse * (0.13 if granting else 0.07)
		draw_circle(Vector2(0, -9), 38.0 + pulse * 4.0, Color(0.25, 0.96, 0.9, aura_alpha))
		draw_arc(Vector2(0, -9), 32.0 + pulse * 3.0, 0.0, TAU, 36, Color(1.0, 0.77, 0.25, 0.68), 2.0)
	if reflex_pulse_remaining > 0.0:
		var reflex_progress := 1.0 - reflex_pulse_remaining / 0.9
		var reflex_radius := 38.0 + reflex_progress * 42.0
		draw_arc(Vector2(0, -9), reflex_radius, 0.0, TAU, 48, Color(0.55, 1.0, 0.92, 0.8 - reflex_progress * 0.7), 3.0)

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
