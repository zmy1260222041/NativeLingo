extends Node
## FR-47: inspect actual controls, state transitions and rendered layouts.
var failures := 0
var screen: Control
var model: Node
const OUTPUT := "res://../docs/reviews/everyday_inventory_2026-09-11/"

func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)

func _ready() -> void:
	get_window().size = Vector2i(1440, 900)
	TranslationServer.set_locale("zh_CN")
	GameState.persistence_enabled = false
	GameState.reset_run()
	SpeechAdapter.availability_override = false
	NpcVoice.availability_override = false
	screen = preload("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	model.travel("food")
	GameState.settle_service_transaction("tavi", 90, "burger", "everyday-burgers")
	GameState.settle_service_transaction("tavi", 90, "coffee", "everyday-coffee")
	check(screen.counter_button.text.contains("4 件待取"), "Visible receipt reflects the actual counter count")
	await capture("order-ready")
	await click(screen.counter_button)
	check(screen.modal.visible and screen.modal_kind == "counter", "The highlighted pickup opens the actual counter")
	await get_tree().process_frame
	var view = screen.inventory_view
	check(view.groups.size() == 2 and view.groups[0].ids.size() == 2, "Counter groups identical physical items without losing quantity")
	check(screen.modal_scrim.visible and screen.modal_scrim.mouse_filter == Control.MOUSE_FILTER_STOP, "Inventory blocks background pointer input")
	screen.place_buttons[0].grab_focus()
	await get_tree().process_frame
	check(screen.modal.is_ancestor_of(get_viewport().gui_get_focus_owner()), "Modal traps keyboard focus")
	var location_before: String = model.location
	await click(screen.place_buttons[0])
	check(model.location == location_before and screen.modal.visible, "Real pointer click cannot activate a place behind the modal")
	for step in range(12):
		var key := InputEventKey.new()
		key.keycode = KEY_TAB
		key.pressed = true
		get_viewport().push_input(key)
		await get_tree().process_frame
		check(screen.modal.is_ancestor_of(get_viewport().gui_get_focus_owner()), "Tab navigation remains in the inventory")
	await capture("counter")
	view.pack_all_requested.emit()
	check(model.visible_items("bag").size() == 4 and model.visible_items("counter").is_empty(), "Bulk pack moves each physical item exactly once")
	screen._open_panel("bag")
	view = screen.inventory_view
	check(view.row_buttons.size() == 2, "Bag renders grouped buttons")
	view._filter("drink")
	check(view.groups.size() == 1 and view.selected_group().record.item_id == "drink_coffee", "Category selects matching drink")
	view._filter("food")
	var id: String = view.selected_group().record.id
	GameState.food = 100
	GameState.warmth = 100
	view.refresh()
	var consume := action_button(view, "consume")
	check(consume != null and consume.disabled, "Full needs disable consumption before spending an item")
	GameState.food = 82
	GameState.warmth = 90
	view.refresh()
	consume = action_button(view, "consume")
	consume.pressed.emit()
	check(GameState.items.instances[id].state == "carried" and not view.confirmation.is_empty(), "Waste warning leaves the item untouched")
	await capture("confirmation")
	view._confirm()
	check(GameState.items.instances[id].state == "consumed", "Explicit waste confirmation consumes exactly one item")
	check(screen.modal_status.text.contains("汉堡") and screen.modal_status.text.contains("饱腹 +18"), "Receipt names the item and its real capped effect")
	check(model.item_groups("bag", "food")[0].ids.size() == 1, "Other unit in the group remains available")
	GameState.food = 40
	GameState.warmth = 40
	GameState.state_changed.emit()
	view._filter("all")
	await capture("bag")
	action_button(view, "consume").grab_focus()
	await capture("primary-focus")
	# Revisions invalidate pending confirmation; it cannot become a blanket permission.
	view._filter("food")
	id = view.selected_group().record.id
	view.request_confirmation("consume", id)
	GameState.items.revision += 1
	view._confirm()
	check(GameState.items.instances[id].state == "carried", "A stale confirmation never consumes an item")
	screen._close_panel()
	model.travel("store")
	GameState.settle_service_transaction("ori", 90, "canteen", "everyday-canteens")
	model.pack_counter()
	var canteens: Array = model.item_groups("bag", "drink")
	var canteen_id := ""
	for group in canteens:
		if group.record.item_id == "drink_canteen": canteen_id = str(group.record.id)
	GameState.energy = 30
	check(model.use_item("consume", canteen_id).ok, "Canteen is usable")
	canteens = model.item_groups("bag", "drink")
	check(canteens.size() == 3, "Partly used canteen separates from full canteen and coffee")
	check(GameState.items.instances[canteen_id].uses == 1, "Canteen retains one use")
	screen._open_panel("bag")
	view = screen.inventory_view
	view._filter("drink")
	view._select(canteens[-1].key)
	await capture("canteen")
	screen._close_panel()
	GameState.settle_service_transaction("ori", 90, "water", "everyday-full-counter")
	screen._open_panel("counter")
	view = screen.inventory_view
	check(action_button(view, "pack").disabled, "A full consumable bag disables another counter pickup")
	check(not model.pack_counter().ok, "Domain also refuses bulk pickup when the carry category is full")
	await capture("full-counter")
	screen._close_panel()
	model.travel("parts")
	GameState.settle_service_transaction("vesh", 90, "blanket", "everyday-blanket")
	model.pack_counter()
	model.travel("home")
	screen._open_panel("home")
	view = screen.inventory_view
	view._filter("home")
	id = view.selected_group().record.id
	action_button(view, "place").pressed.emit()
	action_button(view, "use_home").pressed.emit()
	check(GameState.items.sleep_warmth_bonus() == 20, "Blanket activation uses original sleep bonus")
	await capture("home")
	action_button(view, "reclaim").pressed.emit()
	check(GameState.items.sleep_warmth_bonus() == 0, "Reclaim removes blanket's future warmth bonus")
	action_button(view, "store").pressed.emit()
	check(GameState.items.used_slots("residence") == 0, "Home storage frees its carry category")
	check(model.visible_items("home").any(func(record): return record.id == id and record.state == "storage"), "Stored item remains visible and recoverable")
	view._filter("food")
	await capture("home-storage")
	await check_reading_sizes(18, "standard")
	# Small viewport + larger text setting: inspect rendered extents too.
	get_window().size = Vector2i(1152, 720)
	screen.set_large_text(true)
	screen.reduce_motion = true
	await check_reading_sizes(21, "large")
	check(screen.dialogue_text.get_theme_font_size("normal_font_size") == 30 and screen.objective_label.get_theme_font_size("font_size") == 21, "Large text scales the sidebar as well as the dialogue")
	screen._open_panel("bag")
	await get_tree().process_frame
	await get_tree().process_frame
	check(screen.get_viewport_rect().encloses(screen.modal.get_global_rect()), "Inventory fits the smaller viewport")
	await capture("bag-1152")
	screen._close_panel()
	model.restart()
	model.travel("food")
	screen._open_panel("bag")
	view = screen.inventory_view
	check(view.groups.is_empty() and view.action_buttons.size() >= 2, "Empty inventory offers reachable food and water destinations")
	view.action_buttons[1].pressed.emit()
	check(model.location == "store" and not screen.modal.visible, "Empty-state destination performs real navigation")
	screen._open_panel("bag")
	await capture("empty")
	screen._open_panel("theater")
	await capture("theater")
	screen._close_panel()
	# All scenes, all displayed words, no resources granted for listening.
	Vocabulary.entries.clear()
	var before := GameState.items.snapshot()
	for i in range(model.Content.SOCIAL.size()):
		var scene: Dictionary = model.Content.SOCIAL[i]
		model.play_social(i)
		for line_index in range(scene.lines.size()):
			if line_index > 0: model.next_social()
			check(screen.dialogue_text.text == scene.lines[line_index][2], "Social text matches catalog: %s/%d" % [scene.id, line_index])
			check(screen.second_portrait.visible, "Both speakers remain present through longer scenes")
			for word in scene.words:
				check(Vocabulary.word_state(word) not in ["spoken", "used"], "Listening cannot forge spoken skill")
		model.next_social()
		check(model.social_index == -1, "Every scene has an ending")
	check(GameState.items.snapshot() == before, "Listening to all daily scenes never awards items")
	await check_reading_controls()
	model.play_social(1)
	await capture("daily-dialogue")
	if "--everyday-capture" in OS.get_cmdline_user_args():
		model.cancel_activity()
		model.travel("food")
		model.start()
		await capture("day-scene")
		get_window().size = Vector2i(1440, 900)
		screen.set_large_text(false)
		await capture("day-scene-1440")
		get_window().size = Vector2i(1152, 720)
		screen.set_large_text(true)
		screen._open_panel("settings")
		await capture("settings")
		screen._close_panel()
		screen.remap.open_panel()
		await capture("remap")
		screen.remap.close_panel()
		screen._close_panel()
		model.travel("home")
		model.wait_until_evening()
		screen._show_scene()
		await capture("night-scene")
	print("PASS: everyday inventory, controls, feedback, scene catalog and small viewport" if failures == 0 else "FAIL: %d everyday assertions" % failures)
	screen.queue_free()
	await get_tree().process_frame
	get_tree().quit(failures)

func check_reading_controls() -> void:
	# The visual-novel forward action completes a reveal before changing the line.
	screen.instant_text = false
	screen.reduce_motion = false
	model.play_social(0)
	screen._process(0.0)
	var ledger := GameState.items.snapshot()
	check(screen.advance_button.text == "显示全文", "Social forward action explains the first click")
	await click(screen.advance_button)
	check(model.social_line == 0 and screen.dialogue_text.visible_characters >= screen.dialogue_text.get_total_character_count(), "First reading click reveals without skipping dialogue")
	await click(screen.advance_button)
	check(model.social_line == 1, "Second reading click advances one line")
	screen.instant_text = true
	screen.reduce_motion = true
	model.next_social()
	model.next_social()
	await get_tree().process_frame
	check(screen.advance_button.text.contains("回到现场"), "Final line identifies the return to the location")
	await click(screen.advance_button)
	check(model.social_index == -1 and GameState.items.snapshot() == ledger, "Finishing the reading sequence never grants items")
	model.travel("food")
	screen.instant_text = false
	screen.reduce_motion = false
	screen._show_line("tavi", "Take your time. What would you like to have today?")
	screen._process(0.0)
	check(screen.reveal_button.visible, "Live conversation offers an explicit full-text reveal")
	screen.reveal_button.grab_focus()
	await click(screen.reveal_button)
	check(not screen.reveal_button.visible and screen.record_button.has_focus(), "Finishing a reveal leaves keyboard focus on the speech action")
	check(GameState.items.snapshot() == ledger, "Revealing live text never settles a transaction")
	screen.instant_text = true
	screen.reduce_motion = true
	# The longest shipped daily line fits at the large setting in the small window.
	var longest := ""
	for scene in model.Content.SOCIAL:
		for line in scene.lines:
			if str(line[2]).length() > longest.length(): longest = str(line[2])
	screen._show_line("tavi", longest)
	await get_tree().process_frame
	check(screen.dialogue_text.get_content_height() <= screen.dialogue_text.size.y, "Longest daily line fits the large-font reading area")
	check(screen.dialogue_text.get_global_rect().end.y < screen.action_row.get_global_rect().position.y, "Long dialogue and actions occupy separate areas")
	for child in screen.action_row.get_children():
		if child is Button: check(screen.get_viewport_rect().encloses(child.get_global_rect()), "Dialogue action stays inside the smaller window")
	await capture("long-dialogue-1152")
	screen._show_line("", "窗外的风轻轻吹过。\n将今日的疲惫留在门边，\n给明天的一声问候，留一点从容。")
	await get_tree().process_frame
	check(screen.dialogue_text.get_content_height() <= screen.dialogue_text.size.y, "Three Chinese lines fit without clipping at the large setting")
	await capture("chinese-dialogue-1152")
	# Unexpectedly verbose responses remain scrollable, and each new line starts at its top.
	screen._show_line("tavi", (longest + "\n").repeat(8))
	await get_tree().process_frame
	var scroll: VScrollBar = screen.dialogue_text.get_v_scroll_bar()
	check(scroll.visible, "Overflow dialogue provides a readable scrolling path")
	scroll.value = scroll.max_value
	screen._show_line("tavi", "See you tomorrow.")
	await get_tree().process_frame
	check(scroll.value == 0, "New dialogue resets the previous long response's scroll position")

## P2-06: every reading surface meets the size floor (18 canvas px is about 14 px
## at 1152×720), and the text-size setting reaches sidebar, cards, toasts and panels.
func check_reading_sizes(minimum: int, mode: String) -> void:
	var location: String = model.location
	model.travel("food")
	screen._toast("汉堡 ×1 已放到柜台。打开柜台选择现场使用或打包。")
	await get_tree().process_frame
	var smallest := {"px": 999, "text": "", "where": ""}
	var inspect := func(root: Node, where: String):
		for node in root.find_children("*", "Control", true, false):
			if not (node is Label or node is Button or node is RichTextLabel) or not node.is_visible_in_tree(): continue
			var px: int = node.get_theme_font_size("normal_font_size" if node is RichTextLabel else "font_size")
			if px < smallest.px: smallest = {"px": px, "text": str(node.get("text")).left(24), "where": where}
	inspect.call(screen.canvas, "scene")
	for kind in ["counter", "bag", "growth", "theater", "phrases", "history", "settings", "help"]:
		screen._open_panel(kind)
		await get_tree().process_frame
		inspect.call(screen.modal, kind)
		screen._close_panel()
	check(smallest.px >= minimum, "%s text is at least %d canvas px; smallest is %d in %s: %s" % [mode, minimum, smallest.px, smallest.where, smallest.text])
	model.travel(location)

func action_button(view: Node, action: String) -> Button:
	for button in view.action_buttons:
		if button.get_meta("inventory_focus", "") == "action:" + action: return button
	return null

func capture(label: String) -> void:
	if not "--everyday-capture" in OS.get_cmdline_user_args(): return
	screen.instant_text = true
	await get_tree().create_timer(0.35).timeout
	await RenderingServer.frame_post_draw
	var destination := OUTPUT
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--capture-dir="): destination = argument.trim_prefix("--capture-dir=").trim_suffix("/") + "/"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(destination))
	get_viewport().get_texture().get_image().save_png(destination + label + ".png")

func click(control: Control) -> void:
	# A freshly rebuilt HBox needs a layout pass before its hit target is stable.
	await get_tree().process_frame
	await get_tree().process_frame
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		event.position = control.get_global_rect().get_center()
		get_viewport().push_input(event, true)
		await get_tree().process_frame
	await get_tree().process_frame
