extends Node
## Regression cases reproduced during the campus art playtest.
var failures := 0
var assertions := 0
var screen: Control
var model: Node

func check(ok: bool, message: String) -> void:
	assertions += 1
	if not ok:
		failures += 1
		push_error(message)

func _ready() -> void:
	TranslationServer.set_locale("zh_CN")
	GameState.persistence_enabled = false
	SpeechAdapter.availability_override = false
	NpcVoice.availability_override = false
	screen = preload("res://scenes/Campus.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	await get_tree().process_frame
	screen._inventory("bag")
	var guidance: Dictionary = model.inventory_guidance()
	check(guidance.links.size() == 1 and guidance.links[0][1] == "dining", "Campus has one accurate dining-counter supply link")
	check(not guidance.text.contains("便利店"), "Campus inventory does not advertise the town store")
	check(not model.item_description("drink_bottled_water").contains("罗文"), "Campus water does not reference a town-only character")
	screen.inventory_view.travel_requested.emit("dining")
	await get_tree().process_frame
	check(model.service_mode and model.location == "dining" and model.npc_id() == "tavi", "Supply link opens the real service counter rather than a social scene")
	check(not screen.modal.visible, "Supply travel dismisses the inventory modal")
	check(screen.send_button.disabled and not screen.input.editable, "Voice-only counter explains its input mode without accepting discarded typed text")
	model.greet()
	await get_tree().process_frame
	var items: Array = model.visible_items("counter")
	check(items.size() == 1, "Offline minimum item remains available at the campus counter")
	if not items.is_empty():
		var id: String = items[0].id
		GameState.food = 98
		GameState.warmth = 100
		GameState.energy = 100
		screen._inventory("counter")
		screen.inventory_view.action_requested.emit("consume", id, false)
		check(not screen.inventory_view.confirmation.is_empty(), "Partial-effect consumption exposes the confirmation that used to be ignored")
		check(screen.inventory_view.notice_label.visible, "Failure/confirmation feedback is visible inside the modal")
		check(GameState.food == 98 and model.visible_items("counter").size() == 1, "Requesting confirmation does not consume the item")
		await capture_inventory("inventory-confirmation")
		for button in screen.inventory_view.action_buttons:
			if button.text == "先留着": button.pressed.emit(); break
		check(screen.inventory_view.confirmation.is_empty() and model.visible_items("counter").size() == 1, "Keep-for-later cancels without consuming")
		screen.inventory_view.action_requested.emit("consume", id, false)
		screen.inventory_view._confirm()
		check(GameState.food == 100 and model.visible_items("counter").is_empty(), "Explicit confirmation consumes exactly one item and applies its capped effect")
		check(screen.inventory_view.notice_label.text.contains("已使用"), "Successful item use has a visible receipt")
		await capture_inventory("inventory-used")
		screen.inventory_view.action_requested.emit("consume", id, true)
		check(model.visible_items("counter").is_empty(), "Repeated stale item action cannot consume or mint another item")
	screen._close_modal()
	model.travel("class")
	model.select_scene("class_project_roles")
	model.travel("home")
	var turn_before: int = model.turn_serial
	model.submit_text("Are you still there?")
	check(model.pending_turn.is_empty() and model.turn_serial == turn_before, "Home cannot send to participants from the previous campus scene")
	check(screen.send_button.disabled and not screen.input.editable and screen.record_button.disabled, "Home composer does not promise unavailable conversation")
	check(not screen.scene_picker.visible and screen.visual.people.is_empty(), "Home does not expose remote scenario selection or portraits")
	screen._scenarios()
	check(not screen.modal.visible, "Home scenario picker cannot open even via a queued callback")
	var score: int = model.campus.academic
	model.study("study")
	check(model.campus.academic == score + 10, "Home conversation guard preserves independent study")
	model.travel("club")
	check(not screen.send_button.disabled and screen.input.editable and screen.scene_picker.visible, "Leaving home restores normal campus conversation")
	model.travel("class")
	model.select_scene("class_project_roles")
	model.muted = true
	screen._line("you", "What would you each like to do?")
	screen._line("alex", "I can prepare the outline.")
	screen._line("jules", "I can gather the evidence.")
	check(screen.transcript.text.contains("I can prepare") and screen.transcript.text.contains("I can gather"), "Text-only group replies remain readable together")
	check(screen.transcript.text.contains("Alex") and screen.transcript.text.contains("Jules"), "Retained replies identify each speaker")
	if DisplayServer.get_name() != "headless":
		await get_tree().process_frame
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("res://../docs/reviews/campus_art_2026-09-12/group-text-replies.png")
	screen._line("you", "What is next?")
	screen._line("alex", "Let us compare our notes.")
	check(not screen.transcript.text.contains("I can prepare") and screen.transcript.text.contains("compare our notes"), "A new player turn starts a fresh reply group")
	screen.queue_free()
	await get_tree().process_frame
	print("CampusInteractionTest: %d assertions, %d failures" % [assertions, failures])
	get_tree().quit(1 if failures else 0)

func capture_inventory(name: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await get_tree().process_frame
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	screen.modal.get_texture().get_image().save_png("res://../docs/reviews/campus_art_2026-09-12/" + name + ".png")
