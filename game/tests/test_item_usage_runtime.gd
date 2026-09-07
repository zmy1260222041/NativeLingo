extends SceneTree
## Main scene integration, real input dispatch, and optional viewport evidence.
var failures := 0
var checks := 0
var world: Node
var game: Node
var player: Node3D
var panel: Control

func _init() -> void:
	call_deferred("_run")

func _expect(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL: " + label)

func _frames(count := 5) -> void:
	for i in range(count):
		await physics_frame
		await process_frame

func _run() -> void:
	game = root.get_node("GameState")
	game.persistence_enabled = false
	game.save_path = "user://item_usage_integration_nonexistent.json"
	game.onboarding_completed = true
	game.reset_run()
	game.set_process(false)
	root.get_node("SpeechAdapter").availability_override = false
	ProjectSettings.set_setting("stranger_ai_dialogue/enabled", false)
	var main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)
	current_scene = main
	# Test shipped defaults, without loading or rewriting the user's custom bindings.
	for action in ["item_show", "item_previous", "item_next", "item_secondary", "item_pack_all", "interact"]:
		InputMap.action_erase_events(action)
		for event in ProjectSettings.get_setting("input/" + action).events:
			InputMap.action_add_event(action, event)
	world = get_first_node_in_group("item_world")
	player = get_first_node_in_group("player")
	panel = get_first_node_in_group("item_panel")
	_expect(world != null and panel != null, "Main mounts item world and input panel")
	if world == null or panel == null:
		quit(1)
		return
	# Prevent unrelated social audio from starting in this offline deterministic probe.
	main.get_node("SocialSimulator").set_process(false)
	for npc in get_nodes_in_group("interactable"):
		if npc.interaction_kind == "npc":
			npc.npc_greeted = true
	game.food = 35
	game.warmth = 40
	var needs := [game.food, game.warmth, game.energy]
	game.settle_service_transaction("tavi", 90, "burger", "runtime_burger")
	await _frames()
	_expect(world.anchors.tavi.visible and world.anchors.tavi.get_node("Contents").get_child_count() == 2, "Two delivered portions are visible world objects")
	_expect([game.food, game.warmth, game.energy] == needs, "World delivery gives no automatic survival effect")
	player.global_position = Vector3(-1.8, 0.15, -0.2)
	await _frames(24)
	player._find_nearby_target()
	_expect(player.nearby_target == world.anchors.tavi, "Counter goods can be targeted ahead of the clerk")
	await _action("interact", true)
	await _action("interact", false)
	await _frames(8)
	_expect(panel.visible and panel.entries.size() == 2, "Player can open the nearby counter")
	_expect(root.get_visible_rect().encloses(panel.get_global_rect()) and panel.get_global_rect().encloses(panel.pack_all.get_global_rect()), "Populated counter and pack-all fit inside viewport")
	_expect(player.item_use_is_safe(), "Player is grounded in front of the counter")
	await _screenshot("counter.png")
	await _world_screenshot("counter-objects.png", Vector3(-0.7, 2.6, 0.8), world.anchors.tavi.global_position)
	panel.execute(false)
	await _frames()
	_expect(game.food == 80.0 and game.items.records("consumed").size() == 1, "On-site eat button consumes one and restores food")
	panel.execute(true)
	await _frames()
	_expect(game.items.records("carried").size() == 1 and game.items.records("counter").is_empty(), "Pack button moves remaining portion without consuming")
	panel.close_panel()
	game.settle_service_transaction("vesh", 90, "blanket", "runtime_blanket")
	player.global_position = Vector3(2, 0.15, -6.7)
	await _frames(24)
	panel.open_world("item_counter", "vesh")
	await _joy(JOY_BUTTON_X, true)
	await _joy(JOY_BUTTON_X, false)
	await _frames()
	_expect(game.items.count_item("home_blanket", "carried") == 1, "Daily necessity is packed, not consumed at counter")
	panel.close_panel()
	panel.toggle_mode = true
	await _joy(JOY_BUTTON_RIGHT_SHOULDER, true)
	await _joy(JOY_BUTTON_RIGHT_SHOULDER, false)
	_expect(panel.visible and panel.gamepad, "Actual controller RB opens the same item selector without taking the voice LB")
	var previous_selection: int = panel.selected
	await _joy(JOY_BUTTON_DPAD_DOWN, true)
	await _joy(JOY_BUTTON_DPAD_DOWN, false)
	_expect(panel.selected != previous_selection, "Controller D-pad changes item selection")
	var blanket_index := -1
	for index in range(panel.entries.size()):
		if panel.entries[index].item_id == "home_blanket":
			blanket_index = index
	panel._select(blanket_index)
	_expect(panel.primary.disabled and (panel.detail.text.contains("Bed") or panel.detail.text.contains("床铺")), "Field item selector explains the required home position")
	panel.close_panel()
	var remote_result: Dictionary = game.item_command("place", [game.items.records("carried")[-1].id], {"safe": true, "location": "home_bed", "at_home": true})
	_expect(not remote_result.ok, "GameState rejects forged home context away from the home anchor")
	player.global_position = Vector3(-5.0, 0.15, 15.2)
	await _frames(24)
	panel.open_world("item_home", "home_bed")
	for index in range(panel.entries.size()):
		if panel.entries[index].item_id == "home_blanket":
			panel._select(index)
	panel.execute(false)
	await _frames()
	_expect(game.items.records("placed", "home_bed").size() == 1 and game.items.sleep_warmth_bonus() == 0, "Home button places blanket without activating it")
	panel.execute(false)
	await _frames()
	_expect(game.items.sleep_warmth_bonus() == 20, "Second home action sets up the blanket")
	_expect(world.anchors.home_bed.get_node("Contents").get_child_count() == 1, "Activated household item remains visible at home")
	await _screenshot("home.png")
	await _world_screenshot("home-object.png", Vector3(-2.8, 2.4, 15.8), world.anchors.home_bed.global_position)
	panel.close_panel()
	player.global_position = Vector3(-7.0, 0.15, 12.1)
	await _frames(24)
	player._find_nearby_target()
	_expect(player.nearby_target != null and player.nearby_target.interaction_kind == "shelter", "Home item anchors do not steal the reachable sleep entrance")
	panel.close_panel()
	# Hold-to-show is dispatched through the same InputMap as actual keyboard/controller events.
	panel.toggle_mode = false
	await _action("item_show", true)
	_expect(panel.visible, "Hold action opens carried selector")
	await _action("item_show", false)
	_expect(not panel.visible, "Releasing hold closes selector")
	panel.toggle_mode = true
	await _action("item_show", true)
	await _action("item_show", false)
	_expect(panel.visible, "Toggle mode survives key release")
	game.faint()
	await _frames()
	# The full system event must close any selector even when no eligible item remains.
	_expect(not panel.visible, "Faint closes the selector before inventory loss")
	game.items.migrate(4, 1, 2, false)
	game._items_did_change(false)
	panel.open_carried()
	root.size = Vector2i(1152, 648)
	main.get_node("HUD").ui_scale_index = 5
	main.get_node("HUD")._apply_ui_scale()
	await _frames(10)
	panel._layout()
	await _frames()
	var rect: Rect2 = panel.get_global_rect()
	var visible_rect: Rect2 = root.get_visible_rect()
	_expect(visible_rect.encloses(rect), "Item selector stays in viewport at 1152x648 / 150%")
	_expect(rect.encloses(panel.primary.get_global_rect()), "Primary action remains inside selector")
	await _screenshot("inventory-150.png")
	main.get_node("HUD")._open_pause()
	await _frames()
	_expect(not panel.visible, "Pause closes item selector")
	main.get_node("HUD")._close_pause()
	game.day_time = game.DAY_DURATION
	await _action("interact", true)
	await _action("interact", false)
	_expect(game.day == 2, "Actual entrance input still sleeps after household placement")
	main.get_node("HUD")._finish_day_transition()
	print("%s: Item runtime %d checks, %d failures" % ["PASS" if failures == 0 else "FAIL", checks, failures])
	main.queue_free()
	await process_frame
	quit(failures)

func _action(action: String, pressed: bool) -> void:
	var event := InputEventAction.new()
	event.action = action
	event.pressed = pressed
	Input.parse_input_event(event)
	await _frames(2)

func _joy(button: JoyButton, pressed: bool) -> void:
	var event := InputEventJoypadButton.new()
	event.button_index = button
	event.pressed = pressed
	Input.parse_input_event(event)
	await _frames(2)

func _screenshot(filename: String) -> void:
	var destination := OS.get_environment("ITEM_USAGE_EVIDENCE_DIR")
	if destination.is_empty() or DisplayServer.get_name() == "headless":
		return
	await RenderingServer.frame_post_draw
	DirAccess.make_dir_recursive_absolute(destination)
	root.get_texture().get_image().save_png(destination.path_join(filename))

func _world_screenshot(filename: String, at: Vector3, target: Vector3) -> void:
	if OS.get_environment("ITEM_USAGE_EVIDENCE_DIR").is_empty() or DisplayServer.get_name() == "headless":
		return
	var camera := Camera3D.new()
	current_scene.add_child(camera)
	camera.global_position = at
	camera.look_at(target)
	camera.make_current()
	current_scene.get_node("HUD/UIRoot").hide()
	await _frames()
	await _screenshot(filename)
	current_scene.get_node("HUD/UIRoot").show()
	player.camera.make_current()
	camera.queue_free()
