extends Node

var failures := 0

@onready var hud = $HUD

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	await get_tree().process_frame
	await get_tree().process_frame
	_expect(hud.get_node_or_null("UIRoot/SafeAreaRoot/HudRoot/ObjectiveAnchor/ObjectiveCard") != null, "Objective card exists")
	_expect(hud.get_node_or_null("UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor") != null, "Needs cluster exists")
	_expect(hud.get_node_or_null("UIRoot/SafeAreaRoot/HudRoot/InteractionAnchor/InteractionCard") != null, "Context interaction card exists")
	_expect(hud.get_node_or_null("UIRoot/SafeAreaRoot/HudRoot/InteractionAnchor/InteractionCard/Content/VoiceStatusIcon") is VoiceStatusIcon, "Voice states use a semantic drawn icon")
	_expect(hud.get_node_or_null("UIRoot/PauseOverlay") != null, "Accessible full-screen pause overlay exists")
	_expect(hud.get_node_or_null("UIRoot/CompletionOverlay") != null, "Full-screen completion modal exists")
	_expect(hud.get_node_or_null("UIRoot/DayTransitionOverlay") != null, "Skippable full-screen day transition exists")
	_expect(hud.get_node_or_null("UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/FoodRow/Icon") is NeedIcon, "Food uses a drawn semantic icon")
	_expect(hud.get_node_or_null("UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/WarmthRow/Content/Meter") is NeedMeter, "Needs use segmented semantic meters")
	_expect(hud.get_node("UIRoot").theme.default_font != null, "Bundled CJK font is assigned at the shared full-screen theme root")
	_expect(not InputGlyphs.for_action("interact", false).is_empty(), "Keyboard glyph resolves from InputMap")
	_expect(not InputGlyphs.for_action("interact", true).is_empty(), "Gamepad glyph resolves from InputMap")
	_expect(InputGlyphs.for_action("ui_cancel", false) != "?" and InputGlyphs.for_action("ui_cancel", true) != "?", "Semantic cancel glyph resolves for keyboard and gamepad")
	_expect(InputGlyphs.label_for_button(JOY_BUTTON_A, "playstation") == "×" and InputGlyphs.label_for_button(JOY_BUTTON_A, "generic") == "South", "Controller glyphs distinguish PlayStation and generic layouts")
	for scale_index in [2, 5]:
		hud.ui_scale_index = scale_index
		hud._apply_ui_scale()
		var scale_percent := 100 if scale_index == 2 else 150
		for viewport_size in [Vector2i(1152, 720), Vector2i(1440, 900), Vector2i(2560, 1080)]:
			get_window().size = viewport_size
			await get_tree().process_frame
			await get_tree().process_frame
			var logical_size := Vector2i(hud.get_viewport().get_visible_rect().size)
			var objective := hud.get_node("UIRoot/SafeAreaRoot/HudRoot/ObjectiveAnchor/ObjectiveCard") as Control
			var needs := hud.get_node("UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor") as Control
			_expect(_inside_viewport(objective, logical_size), "Objective stays in viewport at %s / %d%%" % [viewport_size, scale_percent])
			_expect(_inside_viewport(needs, logical_size), "Needs stay in viewport at %s / %d%%" % [viewport_size, scale_percent])
			_expect(not objective.get_global_rect().intersects(needs.get_global_rect()), "Objective and needs do not overlap at %s / %d%%" % [viewport_size, scale_percent])
			var pause_overlay := hud.get_node("UIRoot/PauseOverlay") as Control
			pause_overlay.visible = true
			await get_tree().process_frame
			var pause_card := hud.get_node("UIRoot/PauseOverlay/Center/Card") as Control
			_expect(_inside_viewport(pause_card, logical_size), "Pause settings reflow at %s / %d%%" % [viewport_size, scale_percent])
			pause_overlay.visible = false
	hud.ui_scale_index = 2
	hud._apply_ui_scale()
	get_window().size = Vector2i(1152, 720)
	hud.ui_scale_index = 5
	hud._apply_ui_scale()
	await get_tree().process_frame
	var ui_root := hud.get_node("UIRoot") as Control
	var resume_button := hud.get_node("UIRoot/PauseOverlay/Center/Card/Content/ResumeButton") as Button
	_expect(is_equal_approx(ui_root.theme.default_base_scale, 1.5), "Shared full-screen theme root receives 150% scale")
	_expect(resume_button.get_theme_font("font") == ui_root.theme.default_font and resume_button.get_theme_font_size("font_size") >= 20, "Full-screen modal inherits the bundled font and accessible button size")
	var remap := hud.get_node("UIRoot/InputRemapOverlay") as InputRemapPanel
	hud._open_pause()
	hud._open_input_remap()
	await get_tree().process_frame
	var remap_card := hud.get_node("UIRoot/InputRemapOverlay/Center/Card") as Control
	_expect(_inside_viewport(remap_card, Vector2i(hud.get_viewport().get_visible_rect().size)), "Input remapping panel reflows at 1152x720 / 150%")
	_expect(remap.get_node("Center/Card/Content/Scroll/Actions").get_child_count() == 15, "Every core gameplay action has a remapping row")
	_expect(not hud.get_node("UIRoot/PauseOverlay").visible and remap.is_ancestor_of(hud.get_viewport().gui_get_focus_owner()), "Input remapping hides the pause layer and owns initial focus")
	var remap_focus_controls := _remap_focus_controls(remap)
	_expect(_focus_cycle_stays_inside(remap, remap_focus_controls), "Tab and Shift-Tab form a complete remapping focus loop")
	_expect(_directional_focus_stays_inside(remap, remap_focus_controls), "D-pad focus neighbors stay inside the remapping modal")
	var remap_scroll := remap.get_node("Center/Card/Content/Scroll") as ScrollContainer
	var last_binding_button := remap.binding_buttons[&"pause"]["gamepad"] as Button
	remap_scroll.scroll_vertical = 0
	last_binding_button.grab_focus()
	await get_tree().process_frame
	await get_tree().process_frame
	_expect(remap_scroll.scroll_vertical > 0 and _rect_inside(last_binding_button.get_global_rect(), remap_scroll.get_global_rect()), "Remapping list follows keyboard/gamepad focus to the final action")
	remap.reset_armed = true
	remap._request_reset()
	var original_interact := _event_for_device(&"interact", false)
	var original_sprint := _event_for_device(&"sprint", false)
	remap._start_capture(&"interact", false, remap.binding_buttons[&"interact"]["keyboard"])
	remap._handle_candidate(original_sprint.duplicate())
	_expect(remap.pending_conflict_action == &"sprint", "Binding conflicts require explicit confirmation")
	remap._handle_candidate(original_sprint.duplicate())
	_expect(InputMap.event_is_action(original_sprint, &"interact", true) and InputMap.event_is_action(original_interact, &"sprint", true), "Confirmed conflict swaps bindings instead of silently overwriting")
	remap.reset_armed = true
	remap._request_reset()
	_expect(InputMap.event_is_action(original_interact, &"interact", true) and InputMap.event_is_action(original_sprint, &"sprint", true), "Restore Defaults recovers project bindings")
	remap.close_panel()
	await get_tree().process_frame
	_expect(hud.get_node("UIRoot/PauseOverlay").visible and hud.get_viewport().gui_get_focus_owner() == hud.get_node("UIRoot/PauseOverlay/Center/Card/Content/ControlsButton"), "Closing remapping restores the pause layer and Controls focus")
	hud._close_pause()
	hud.voice_state = "clarify"
	hud.voice_target_name = "米拉 / Mira"
	hud.voice_transcript = "hello, I am trying to greet you and I brought water for the settlement"
	hud.voice_reason = TranslationServer.translate("VOICE_REASON_CLARIFY")
	hud._refresh_voice_card()
	await get_tree().process_frame
	var interaction_card := hud.get_node("UIRoot/SafeAreaRoot/HudRoot/InteractionAnchor/InteractionCard") as Control
	_expect(_inside_viewport(interaction_card, Vector2i(hud.get_viewport().get_visible_rect().size)), "Long Clarify card reflows at 1152x720 / 150%")
	hud._clear_voice_status()
	var completion_overlay := hud.get_node("UIRoot/CompletionOverlay") as Control
	completion_overlay.visible = true
	await get_tree().process_frame
	_expect(_inside_viewport(hud.get_node("UIRoot/CompletionOverlay/Center/Card"), Vector2i(hud.get_viewport().get_visible_rect().size)), "Completion card reflows at 1152x720 / 150%")
	completion_overlay.visible = false
	var day_overlay := hud.get_node("UIRoot/DayTransitionOverlay") as Control
	day_overlay.visible = true
	await get_tree().process_frame
	_expect(_inside_viewport(hud.get_node("UIRoot/DayTransitionOverlay/Center/Content"), Vector2i(hud.get_viewport().get_visible_rect().size)), "Day transition content reflows at 1152x720 / 150%")
	day_overlay.visible = false
	hud.ui_scale_index = 2
	hud._apply_ui_scale()
	hud.reduce_motion = true
	hud._show_day_transition(2)
	_expect(hud.get_node("UIRoot/DayTransitionOverlay").visible and get_tree().paused, "Day transition pauses the world")
	hud._dismiss_day_transition()
	_expect(not hud.get_node("UIRoot/DayTransitionOverlay").visible and not get_tree().paused, "Reduced-motion day transition dismisses immediately")
	hud.reduce_motion = false
	GameState.game_finished = true
	GameState.state_changed.emit()
	await get_tree().process_frame
	_expect(hud.get_node("UIRoot/CompletionOverlay").visible and get_tree().paused, "Restored completion state reopens its modal")
	hud._dismiss_completion()
	GameState.game_finished = false
	var speech_started := SpeechAdapter.start_recording("mira")
	_expect(not speech_started and SpeechAdapter.is_recovery_active() and GameState.interaction_time_frozen, "Unavailable microphone enters persistent recovery without time cost")
	SpeechAdapter.cancel_recording()
	_expect(not SpeechAdapter.is_interaction_active() and not GameState.interaction_time_frozen, "Cancelling speech recovery restores gameplay time")
	hud._open_pause()
	resume_button.grab_focus()
	hud._close_pause()
	_expect(hud.get_viewport().gui_get_focus_owner() == null and not get_tree().paused, "Closing a modal releases focus and restores gameplay")
	if failures == 0:
		print("PASS: Stranger HUD smoke suite")
	get_tree().quit(failures)

func _inside_viewport(control: Control, viewport_size: Vector2i) -> bool:
	var rect := control.get_global_rect()
	if not (rect.position.x >= 0.0 and rect.position.y >= 0.0 and rect.end.x <= viewport_size.x and rect.end.y <= viewport_size.y):
		print("  RECT  ", control.name, " ", rect, " viewport=", viewport_size)
		return false
	return true

func _rect_inside(inner: Rect2, outer: Rect2) -> bool:
	return inner.position.x >= outer.position.x and inner.position.y >= outer.position.y and inner.end.x <= outer.end.x and inner.end.y <= outer.end.y

func _remap_focus_controls(remap: InputRemapPanel) -> Array[Button]:
	var controls: Array[Button] = []
	for action_data in remap.ACTIONS:
		var action: StringName = action_data[0]
		controls.append(remap.binding_buttons[action]["keyboard"] as Button)
		controls.append(remap.binding_buttons[action]["gamepad"] as Button)
	controls.append(remap.get_node("Center/Card/Content/Footer/ResetButton") as Button)
	controls.append(remap.get_node("Center/Card/Content/Footer/CloseButton") as Button)
	return controls

func _focus_cycle_stays_inside(remap: InputRemapPanel, controls: Array[Button]) -> bool:
	var current: Button = controls.front()
	var seen := {}
	for _step in range(controls.size()):
		if not remap.is_ancestor_of(current) or seen.has(current):
			return false
		seen[current] = true
		if current.focus_next.is_empty() or current.focus_previous.is_empty():
			return false
		var previous := current.get_node_or_null(current.focus_previous) as Button
		if not previous or not remap.is_ancestor_of(previous):
			return false
		current = current.get_node_or_null(current.focus_next) as Button
		if not current:
			return false
	return current == controls.front() and seen.size() == controls.size()

func _directional_focus_stays_inside(remap: InputRemapPanel, controls: Array[Button]) -> bool:
	for control in controls:
		for neighbor_path in [control.focus_neighbor_top, control.focus_neighbor_bottom, control.focus_neighbor_left, control.focus_neighbor_right]:
			if neighbor_path.is_empty():
				return false
			var neighbor := control.get_node_or_null(neighbor_path) as Button
			if not neighbor or not remap.is_ancestor_of(neighbor):
				return false
	return true

func _event_for_device(action: StringName, gamepad: bool) -> InputEvent:
	for event in InputMap.action_get_events(action):
		if gamepad and (event is InputEventJoypadButton or event is InputEventJoypadMotion):
			return event
		if not gamepad and event is InputEventKey:
			return event
	return null

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
