extends Node
## P2-02 / FR-46 / ACC-INP-001: a keyboard-only player starts a 小剧场 from the
## top bar and advances it with E / → / Space / Enter without reopening panels.
## Key events go through the viewport, so GUI focus navigation sees them first.
var failures := 0
var screen: Control
var model: Node

func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)

func _ready() -> void:
	TranslationServer.set_locale("en")
	GameState.persistence_enabled = false
	GameState.reset_run()
	SpeechAdapter.availability_override = false
	NpcVoice.availability_override = false
	screen = preload("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	screen.instant_text = true # One key press advances exactly one line.
	await get_tree().process_frame
	await _test_top_bar_entry()
	await _test_dialogue_is_not_a_tab_stop()
	await _test_phrases_entry()
	print("PASS: keyboard-only 小剧场 from the top bar" if failures == 0 else "FAIL: %d keyboard assertions" % failures)
	get_tree().quit(failures)

func _key(keycode: Key, shift := false) -> void:
	for pressed in [true, false]:
		var event := InputEventKey.new()
		event.keycode = keycode
		event.physical_keycode = keycode
		event.shift_pressed = shift
		event.pressed = pressed
		get_viewport().push_input(event)
	await get_tree().process_frame

func _focus() -> Control:
	return get_viewport().gui_get_focus_owner()

func _focused_text() -> String:
	var owner := _focus()
	return str(owner.get("text")) if owner != null and owner.get("text") != null else str(owner)

func _top_bar_button(text: String) -> Button:
	for child in screen.canvas.get_children():
		if child is Button and child.text == text: return child
	return null

func _in_scene(step: String, line: int) -> void:
	check(not screen.modal.visible and screen.modal_kind.is_empty(), step + ": no panel opens, focus on " + _focused_text())
	check(model.social_index == 0 and model.social_line == line, step + ": scene stays on line %d (got %d / %d)" % [line, model.social_index, model.social_line])

func _test_top_bar_entry() -> void:
	var theater := _top_bar_button("小剧场")
	check(theater != null, "The top bar offers 小剧场")
	theater.grab_focus()
	await _key(KEY_ENTER)
	check(screen.modal.visible and screen.modal_kind == "theater", "Enter on the top-bar entry opens the scene list")
	for attempt in range(12):
		if _focused_text().begins_with("01"): break
		await _key(KEY_TAB)
	check(_focused_text().begins_with("01"), "Tab reaches the first scene in the list")
	await _key(KEY_ENTER)
	_in_scene("Enter starts the first scene", 0)
	check(_focus() == screen.advance_button, "Focus moves to 下一句, not back to the top bar (focus on %s)" % _focused_text())
	var lines: int = model.Content.SOCIAL[0].lines.size()
	await _key(KEY_RIGHT)
	_in_scene("→ advances", 1)
	await _key(KEY_SPACE)
	_in_scene("Space advances", 2)
	await _key(KEY_E)
	_in_scene("E advances", 3)
	for line in range(4, lines):
		await _key(KEY_ENTER)
		_in_scene("Enter advances", line)
	check(is_instance_valid(screen.advance_button) and screen.advance_button.text.begins_with("回到现场"), "The last line offers the way back")
	await _key(KEY_ENTER)
	check(model.social_index == -1 and not screen.modal.visible, "The last advance returns to the scene without a panel")
	check(_focus() != null and screen.action_row.is_ancestor_of(_focus()), "Focus stays in the action row after the scene (focus on %s)" % _focused_text())
	check(not theater.has_focus(), "The top-bar entry does not take focus back")
	screen._open_panel("help")
	var help := ""
	for label in screen.modal_body.get_children():
		if label is Label: help += label.text
	check(help.contains("小剧场里按 E、→ 或空格推进下一句"), "The help names the advance keys")
	screen._close_panel()

func _test_dialogue_is_not_a_tab_stop() -> void:
	check(screen.dialogue_text.focus_mode == Control.FOCUS_NONE and screen.dialogue_text.selection_enabled, "Dialogue text stays selectable without a hidden focus stop")
	screen.place_buttons[0].grab_focus()
	var visited := false
	for attempt in range(40):
		await _key(KEY_TAB)
		if _focus() == screen.dialogue_text: visited = true
	check(not visited, "Tab never lands on the invisible dialogue text")

func _test_phrases_entry() -> void:
	model.travel("plaza")
	screen._open_panel("phrases")
	await get_tree().process_frame
	var listen: Button
	for child in screen.modal_body.get_children():
		if child is Button and child.text.begins_with("听听这段"):
			listen = child
			break
	check(listen != null, "Speaking ideas offer a scene at the plaza")
	if listen == null: return
	listen.grab_focus()
	await _key(KEY_SPACE)
	check(model.social_index >= 0 and _focus() == screen.advance_button, "A scene started from speaking ideas also focuses 下一句")
	var line: int = model.social_line
	await _key(KEY_RIGHT)
	check(model.social_line == line + 1 and not screen.modal.visible, "→ advances that scene too")
	model.cancel_activity()
	model.start(false)
