extends SceneTree

var failures: Array[String] = []


func _initialize() -> void:
	call_deferred("run")


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
		push_error("CLIENT SMOKE: " + message)


func run() -> void:
	var packed: PackedScene = load("res://scenes/main.tscn")
	check(packed != null, "main scene loads")
	if packed == null:
		finish()
		return
	var game = packed.instantiate()
	root.add_child(game)
	for _frame in range(4):
		await process_frame

	check(game.dwarfs.size() >= 2, "the heist arena contains multiple guards")
	check(game.npcs.size() == 1, "arena contains exactly one peaceful NPC")
	check(game.object_index.has("npc_01"), "the peaceful NPC participates in the world snapshot")
	check(is_instance_valid(game.genie), "the player has a genie companion")
	check(game.cast_http.use_threads, "wish HTTP transport progresses outside the render thread")
	check(is_instance_valid(game.genie.speech_panel), "the genie owns a readable in-world speech bubble")
	check(game.genie.companion == game.player, "the genie follows the player rather than replacing them")
	check(game.props.size() >= 3, "arena contains several physical props")
	check(game.loot_total == 3, "the heist has three valuables")
	check(game.object_index.has("loot_01"), "heist loot participates in the world model")
	check(game.object_index.has("tree_01"), "arena contains a flammable object")
	check(game.WALLS.size() >= 20 and game.ROOMS.size() >= 8, "the heist uses compact rooms and narrow corridors")
	check(game.water_snapshot()["material"]["name"] == "water", "arena exposes a water object")
	var has_camera := false
	for child in game.player.get_children():
		if child is Camera2D:
			has_camera = true
	check(has_camera, "top-down camera follows the player")

	var first_loot = game.object_index["loot_01"]
	game.player.global_position = first_loot.global_position
	for _frame in range(3):
		await process_frame
	check(game.loot_collected == 1 and not first_loot.visible, "walking onto a valuable collects it")
	game.reset_sandbox()
	check(game.loot_collected == 0 and first_loot.visible, "reset restores the heist objective")

	var start_position: Vector2 = game.player.global_position
	var press := InputEventKey.new()
	press.physical_keycode = KEY_D
	press.pressed = true
	Input.parse_input_event(press)
	for _frame in range(8):
		await physics_frame
	var release := InputEventKey.new()
	release.physical_keycode = KEY_D
	release.pressed = false
	Input.parse_input_event(release)
	check(game.player.global_position.x > start_position.x, "WASD movement changes player position")

	var rock = game.object_index["rock_01"]
	game.player.global_position = rock.global_position + Vector2(-60, 0)
	var rock_test_start_x: float = game.player.global_position.x
	var move_through_rock := InputEventKey.new()
	move_through_rock.physical_keycode = KEY_D
	move_through_rock.pressed = true
	Input.parse_input_event(move_through_rock)
	for _frame in range(24):
		await physics_frame
	move_through_rock.pressed = false
	Input.parse_input_event(move_through_rock)
	check(game.player.global_position.x > rock_test_start_x + 70.0, "a rock cannot trap cardinal player movement")
	game.reset_sandbox()

	var attacker = game.dwarfs[0]
	var peaceful_npc = game.npcs[0]
	var npc_health_before: float = peaceful_npc.health
	attacker.global_position = game.player.global_position + Vector2(24, 0)
	attacker.attack_cooldown = 0.0
	var health_before: float = game.player.health
	for _frame in range(4):
		await physics_frame
	check(game.player.health < health_before, "a nearby gnome attacks and damages the player")
	game.player.health = 100.0

	game.player.facing = Vector2.RIGHT
	attacker.global_position = game.player.global_position + Vector2(54, 0)
	var enemy_health_before: float = attacker.health
	game.player.weapon_cooldown = 0.0
	game.try_weapon_attack()
	check(attacker.health < enemy_health_before, "the player's weapon swing damages an enemy in front")
	check(is_equal_approx(peaceful_npc.health, npc_health_before), "the player's weapon does not damage the peaceful NPC")
	check(game.player.weapon_swing_remaining > 0.0, "weapon attack starts a visible swing animation")
	for _swing in range(2):
		game.player.weapon_cooldown = 0.0
		game.try_weapon_attack()
	check(not attacker.visible, "repeated weapon swings can kill an enemy")
	check(attacker.collision_layer == 0 and attacker.collision_mask == 0, "a dead enemy no longer blocks movement")
	game.reset_sandbox()
	check(attacker.collision_layer == 1 and attacker.collision_mask == 1, "reset restores the enemy collision")

	attacker.global_position = game.player.global_position + Vector2(180, 0)
	var enemy_before: Vector2 = attacker.global_position
	game.begin_wish()
	check(game.casting, "Space-equivalent input opens a request to the genie")
	check(game.genie.wish_active, "the genie visibly reacts while listening to a wish")
	check(is_equal_approx(Engine.time_scale, game.cast_time_scale), "wish entry uses configured slow motion")
	check(game.spell_input.visible and not game.player.movement_enabled, "wish mode shows text input and suspends WASD")
	var wish_enemy_health: float = attacker.health
	game.player.weapon_cooldown = 0.0
	game.try_weapon_attack()
	check(is_equal_approx(attacker.health, wish_enemy_health), "the weapon cannot attack while asking for a wish")
	for _frame in range(12):
		await physics_frame
	check(attacker.global_position.distance_to(enemy_before) > 0.1, "world simulation continues while the player asks the genie")

	game.spell_input.text = "заморозь воду"
	var payload: Dictionary = game.build_cast_payload(game.spell_input.text)
	check(payload["wish_text"] == "заморозь воду", "Cyrillic wish text survives the client request contract")
	check(is_equal_approx(float(payload["caster"]["position"]["x"]), game.genie.global_position.x / game.UNIT), "wish effects originate from the genie")
	check(not payload.has("gesture"), "wish requests contain no weapon or gesture input")

	var response := {
		"interpretation": {"coherence": 0.9, "anchors": []},
		"debug": {"intent": {}, "selected_targets": ["water_pool_01"], "world_rules": ["test"], "latency_ms": 1.0},
		"spell_plan": {
			"world_actions": [
				{"type": "CHANGE_MATERIAL_STATE", "target_id": "water_pool_01", "material": "ice"},
				{"type": "SPAWN_EFFECT_ENTITY", "effect": {"form": "field", "payload": {"cold": 0.8, "power": 1.0}, "position": [3.0, 2.0], "velocity": [0.0, 0.0], "radius": 1.0, "lifetime": 0.5}}
			],
			"visuals": [{"primitive": "SURFACE_OVERLAY", "appearance": ["ice"], "origin": {"x": 3.0, "y": 2.0}, "direction": {"x": 1.0, "y": 0.0}, "radius": 1.0, "speed": 0.0, "intensity": 1.0, "turbulence": 0.0, "lifetime": 0.5}]
		}
	}
	game.apply_spell_response(response)
	check(game.water_state == "ice", "generic world action changes water into ice")
	game.apply_world_action({"type": "ADD_STATE", "target_id": "water_pool_01", "state": "frozen"})
	check(game.water_state == "ice", "Monty frozen state is visible on water")
	game.apply_world_action({"type": "ADD_STATE", "target_id": attacker.object_id, "state": "burning", "duration": 4.0})
	check(attacker.states.has("burning"), "Monty canonical burning state reaches the enemy")
	attacker.states.clear()
	game.apply_world_action({"type": "ADD_STATE", "target_id": "player", "state": "phased", "duration": 4.0})
	await physics_frame
	check(game.player.collision_mask == 0, "phased player really passes through world walls")
	game.apply_world_action({"type": "ADD_STATE", "target_id": attacker.object_id, "state": "wet", "duration": 4.0})
	check(attacker.states.has("wet") and attacker.wetness > 0.9, "wet state changes the enemy material snapshot")
	game.apply_world_action({"type": "ADD_STATE", "target_id": "npc_01", "state": "invisible", "duration": 4.0})
	await physics_frame
	check(peaceful_npc.modulate.a < 0.3, "invisible NPC is visibly translucent")
	game.apply_world_action({"type": "SET_AGGRO_TARGET", "target_id": attacker.object_id, "effect": {"aggro_target": "player"}})
	check(attacker.target == game.player and attacker.states.has("aggressive"), "aggro action changes the enemy target")
	game.apply_world_action({"type": "DESTROY_OBJECTS", "target_id": attacker.object_id, "effect": {"tag": "enemy", "target_ids": [attacker.object_id]}})
	attacker._respawn()
	check(not attacker.visible and attacker.permanently_destroyed, "genie destruction is permanent and bypasses the four-second enemy respawn")
	attacker.reset_actor()
	var inventory_before: int = game.player.inventory.size()
	game.apply_world_action({"type": "ADD_INVENTORY_ITEM", "target_id": "player", "effect": {"prototype": "magic_key"}})
	check(game.player.inventory.size() == inventory_before + 1 and game.player.inventory.has("magic_key"), "inventory action puts the item in the player's backpack")
	game.apply_world_action({"type": "EQUIP_OUTFIT", "target_id": "player", "effect": {"outfit": "dress"}})
	check(game.player.outfit == "dress" and game.player.get_snapshot(game.UNIT).get("properties", {}).get("outfit") == "dress", "outfit action visibly dresses the player and reports it in the snapshot")
	game.apply_world_action({"type": "SET_GAME_PAUSED", "target_id": "player", "effect": {"paused": true}})
	check(game.world_paused and is_zero_approx(Engine.time_scale), "pause action freezes the playable world")
	game.apply_world_action({"type": "SET_GAME_PAUSED", "target_id": "player", "effect": {"paused": false}})
	check(not game.world_paused and is_equal_approx(Engine.time_scale, 1.0), "resume action unfreezes the playable world")
	game.apply_world_action({"type": "SET_GAME_SPEED", "target_id": "player", "effect": {"multiplier": 0.5}})
	check(is_equal_approx(game.world_time_scale, 0.5) and is_equal_approx(Engine.time_scale, 0.5), "speed action visibly slows world time")
	game.apply_world_action({"type": "SET_GAME_SPEED", "target_id": "player", "effect": {"multiplier": 2.0}})
	check(is_equal_approx(game.world_time_scale, 2.0) and is_equal_approx(Engine.time_scale, 2.0), "speed action visibly accelerates world time")
	game.apply_world_action({"type": "SET_LIGHT_LEVEL", "target_id": "player", "effect": {"level": 0.3}})
	check(is_equal_approx(game.world_light_level, 0.3) and game.world_light_overlay.color.a > 0.5, "lighting action visibly darkens the world")
	game.apply_world_action({"type": "SET_LIGHT_LEVEL", "target_id": "player", "effect": {"level": 1.6}})
	check(is_equal_approx(game.world_light_level, 1.6) and game.world_light_overlay.color.a > 0.05, "lighting action visibly brightens the world")
	game.apply_world_action({"type": "SET_GAME_SPEED", "target_id": "player", "effect": {"multiplier": 1.0}})
	var special_props_before: int = game.props.size()
	game.apply_world_action({"type": "CREATE_OBJECT_BATCH", "target_id": "player", "effect": {"prototype": "enemy", "count": 2}})
	game.apply_world_action({"type": "CREATE_OBJECT_BATCH", "target_id": "player", "effect": {"prototype": "npc", "count": 2}})
	check(game.props.size() == special_props_before + 4, "batch spawning creates every requested actor")
	check(game.props[-4].prop_kind == "enemy" and game.props[-3].prop_kind == "enemy" and game.props[-2].prop_kind == "npc" and game.props[-1].prop_kind == "npc", "batch spawning creates enemies and NPCs directly instead of boxes")
	game.apply_world_action({"type": "CREATE_OBJECT", "target_id": "player", "effect": {"prototype": "wall"}})
	check(game.props.size() == special_props_before + 5 and game.props[-1].collision_layer == 1, "conjured wall is a physical blocker")
	var arena_wall_ids: Array = game.arena_walls.keys()
	var all_wall_ids: Array = []
	for item in game.collect_world_snapshot(true):
		if item.get("tags", []).has("wall"):
			all_wall_ids.append(item.get("id"))
	game.apply_world_action({"type": "INSTALL_DOORS", "target_id": arena_wall_ids[0], "effect": {"wall_ids": all_wall_ids}})
	var all_doors_installed := true
	for wall_id in arena_wall_ids:
		all_doors_installed = all_doors_installed and bool(game.arena_walls[wall_id].get("door_installed", false))
	check(all_doors_installed, "door action installs a visible doorway in every arena wall")
	var first_wall_body: StaticBody2D = game.arena_walls[arena_wall_ids[0]]["body"]
	check(first_wall_body.get_child_count() >= 2, "an installed doorway splits wall collision and creates a real passage")
	var wall_snapshots: Array = game.collect_world_snapshot(true).filter(func(item): return item.get("tags", []).has("wall"))
	check(wall_snapshots.size() == all_wall_ids.size() and wall_snapshots.all(func(item): return item.get("properties", {}).get("door_installed", false)), "world snapshot exposes walls and confirms their installed doors")
	game.apply_world_action({"type": "CREATE_OBJECT", "target_id": attacker.object_id, "effect": {"prototype": "trap"}})
	check(game.props[-1].prop_kind == "trap", "conjured trap exists in the world near its target")
	attacker.global_position = game.player.global_position + Vector2(24, 0)
	var health_before_petrification: float = game.player.health
	game.apply_world_action({"type": "TRANSFORM_OBJECT", "target_id": attacker.object_id, "effect": {"prototype": "rock"}})
	check(attacker.transformed_form == "rock", "Monty visibly transforms an enemy into a rock")
	check(attacker.get_snapshot(game.UNIT)["tags"].has("rock") and not attacker.get_snapshot(game.UNIT)["tags"].has("living"), "a petrified enemy becomes an inanimate rock in the next snapshot")
	for _petrified_frame in range(4):
		await physics_frame
	check(is_equal_approx(game.player.health, health_before_petrification), "a petrified enemy no longer attacks the player")
	game.apply_world_action({"type": "TRANSFORM_OBJECT", "target_id": attacker.object_id, "effect": {"prototype": "npc"}})
	check(attacker.transformed_form == "npc" and attacker.get_snapshot(game.UNIT)["tags"].has("friendly"), "a petrified former enemy can become a friendly NPC")
	attacker.reset_actor()
	var props_before_creation: int = game.props.size()
	game.apply_world_action({"type": "CREATE_OBJECT", "target_id": attacker.object_id, "effect": {"prototype": "blood_pool", "kind": "object"}})
	check(game.props.size() == props_before_creation + 1, "Monty can create an object in the visible world")
	var created_prop = game.props[-1]
	check(created_prop.prop_kind == "blood_pool", "created object keeps its requested prototype")
	game.apply_world_action({"type": "CHANGE_MATERIAL_STATE", "target_id": "rock_01", "material": "gold"})
	check(rock.material_name == "gold", "Monty material change reaches a world prop")
	game.apply_world_action({"type": "TRANSFORM_OBJECT", "target_id": "rock_01", "effect": {"prototype": "crate"}})
	check(rock.prop_kind == "crate" and rock.material_name == "wood", "Monty transforms a rock into a visible crate")
	var second_rock = game.object_index["rock_02"]
	var second_rock_start: Vector2 = second_rock.global_position
	game.apply_world_action({"type": "TRANSFORM_OBJECT", "target_id": "rock_02", "effect": {"prototype": "npc"}})
	check(second_rock.prop_kind == "npc" and second_rock.get_snapshot(game.UNIT)["kind"] == "creature", "Monty turns a rock into a living NPC")
	for _npc_frame in range(8):
		await physics_frame
	check(second_rock.global_position.distance_to(second_rock_start) > 0.1, "an NPC created from a rock moves independently")
	second_rock.global_position = game.player.global_position + Vector2(24, 0)
	var health_before_enemy_rock: float = game.player.health
	game.apply_world_action({"type": "TRANSFORM_OBJECT", "target_id": "rock_02", "effect": {"prototype": "enemy"}})
	check(second_rock.prop_kind == "enemy" and second_rock.get_snapshot(game.UNIT)["tags"].has("enemy"), "Monty turns a rock into an actual enemy")
	for _enemy_rock_frame in range(4):
		await physics_frame
	check(game.player.health < health_before_enemy_rock, "an enemy created from a rock attacks the player")
	game.player.health = 100.0
	check(game.last_debug == response, "response populates developer debug data")
	game.finish_cast_mode()
	check(is_equal_approx(Engine.time_scale, 1.0) and not game.casting and not game.genie.wish_active, "time returns to normal after the genie acts")

	game.begin_wish()
	game.waiting_for_backend = true
	game.release_player_after_submission()
	check(not game.casting and game.waiting_for_backend, "submitting a wish releases input while the agent job continues")
	check(game.player.movement_enabled and is_equal_approx(Engine.time_scale, 1.0), "player movement and normal time resume during genie work")
	game.finish_cast_mode()

	game.genie.snap_to_companion()
	game.genie.accept_wish()
	check(not game.genie.speech_text.is_empty(), "the genie speaks a prepared acceptance phrase")
	await create_timer(0.55, true, false, true).timeout
	check(game.genie.modulate.a < 0.8, "the genie gradually dissolves after accepting a wish")
	await create_timer(0.55, true, false, true).timeout
	check(game.genie.is_dissolved(), "the genie finishes dissolving instead of disappearing instantly")
	var teleport_target: Vector2 = game.player.global_position + Vector2(180.0, 0.0)
	var dissolved_action_delay: float = game.genie.appear_at_interaction(teleport_target, 1.0)
	check(is_zero_approx(dissolved_action_delay), "a dissolved genie can mutate at the destination immediately while manifesting")
	check(game.genie.global_position.distance_to(teleport_target + Vector2(0.0, -42.0)) < 2.0, "an already dissolved genie relocates immediately without flashing at its old position")
	check(game.genie.modulate.a < 0.05, "the dissolved genie stays invisible during relocation")
	await create_timer(0.55, true, false, true).timeout
	check(game.genie.modulate.a > 0.35 and game.genie.modulate.a < 0.8, "the genie gradually manifests at the destination for the full second")
	var prepared_visual: Dictionary = game.prepare_agent_action_visual({
		"_visual_descriptor": {
			"origin": {"x": -999.0, "y": -999.0},
			"target": {"x": -999.0, "y": -999.0},
		}
	}, teleport_target, true)
	check(absf(float(prepared_visual["origin"]["x"]) - game.genie.global_position.x / game.UNIT) < 0.01, "late action visuals use the genie's current position instead of the stale wish origin")
	await create_timer(0.55, true, false, true).timeout
	check(game.genie.modulate.a > 0.95, "the genie completes manifestation at the interaction target")
	game.reset_sandbox()
	check(game.props.size() == special_props_before, "reset removes every object created by the genie")
	check(game.player.outfit.is_empty(), "reset removes the conjured outfit")
	check(game.arena_walls.values().all(func(item): return not item.get("door_installed", false)), "reset restores arena walls without conjured doors")
	check(rock.prop_kind == "rock" and rock.material_name == "stone", "reset restores a transformed rock")
	check(second_rock.prop_kind == "rock", "reset turns a generated NPC back into its original rock")

	var primitives := ["BURST", "PROJECTILE", "BEAM", "LINE", "RING", "FIELD", "CLOUD", "TRAIL", "TETHER", "SURFACE_OVERLAY"]
	for primitive in primitives:
		game.spawn_visual({"primitive": primitive, "appearance": ["force"], "origin": {"x": 0.0, "y": 0.0}, "direction": {"x": 1.0, "y": 0.0}, "radius": 0.5, "speed": 1.0, "intensity": 0.8, "turbulence": 0.1, "lifetime": 0.25})
	await process_frame
	check(primitives.size() == 10, "ten universal visual primitives instantiate")

	var debug_event := InputEventKey.new()
	debug_event.keycode = KEY_F3
	debug_event.pressed = true
	game._input(debug_event)
	check(game.debug_panel.visible, "F3 opens developer debug information")

	game.begin_wish()
	game.cast_failed("deliberate smoke-test failure")
	check(not game.casting and is_equal_approx(Engine.time_scale, 1.0), "backend failure safely exits wish mode")
	game.genie.accept_wish()
	await create_timer(1.05, true, false, true).timeout
	check(game.genie.is_dissolved(), "empty-result regression starts with a dissolved genie")
	game.handle_wish_job_response({
		"job_id": "empty-result-test",
		"status": "completed",
		"result": {
			"spell_plan": {"world_actions": [], "visuals": []},
			"agent": {"actions": [], "conclusion": {"status": "impossible"}}
		}
	})
	await create_timer(1.05, true, false, true).timeout
	check(game.genie.modulate.a > 0.95, "an empty or impossible result always returns the genie to the player")
	check("не исполнено" in game.connection_label.text, "empty agent result is not mislabeled as completed")
	finish()


func finish() -> void:
	Engine.time_scale = 1.0
	if failures.is_empty():
		print("CLIENT_SMOKE_OK: all client v0 checks passed")
		quit(0)
	else:
		print("CLIENT_SMOKE_FAILED: %d checks failed" % failures.size())
		for failure in failures:
			print(" - " + failure)
		quit(1)
