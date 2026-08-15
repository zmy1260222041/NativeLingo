class_name InputRemapPanel
extends ColorRect

signal closed
signal bindings_changed

const SETTINGS_PATH := "user://stranger_accessibility.cfg"
const ACTIONS := [
	[&"move_forward", "ACTION_MOVE_FORWARD"],
	[&"move_back", "ACTION_MOVE_BACK"],
	[&"move_left", "ACTION_MOVE_LEFT"],
	[&"move_right", "ACTION_MOVE_RIGHT"],
	[&"camera_up", "ACTION_CAMERA_UP"],
	[&"camera_down", "ACTION_CAMERA_DOWN"],
	[&"camera_left", "ACTION_CAMERA_LEFT"],
	[&"camera_right", "ACTION_CAMERA_RIGHT"],
	[&"jump", "ACTION_JUMP"],
	[&"sprint", "ACTION_SPRINT"],
	[&"interact", "ACTION_INTERACT"],
	[&"push_to_talk", "ACTION_SPEAK"],
	[&"gesture", "ACTION_GESTURE"],
	[&"ui_cancel", "ACTION_CANCEL"],
	[&"pause", "ACTION_PAUSE"],
]

## 首轮网页内测不包含语音：重映射面板不展示「说话」动作。
## 桌面构建保持 15 行动作不变。
func _active_actions() -> Array:
	var actions: Array = []
	for action_data in ACTIONS:
		if action_data[0] == &"push_to_talk" and not SpeechAdapter.is_available():
			continue
		actions.append(action_data)
	return actions

@onready var status_label: Label = $Center/Card/Content/Status
@onready var scroll_container: ScrollContainer = $Center/Card/Content/Scroll
@onready var actions_container: VBoxContainer = $Center/Card/Content/Scroll/Actions
@onready var reset_button: Button = $Center/Card/Content/Footer/ResetButton
@onready var close_button: Button = $Center/Card/Content/Footer/CloseButton

var default_bindings: Dictionary = {}
var binding_buttons: Dictionary = {}
var capture_action: StringName = &""
var capture_gamepad := false
var capture_button: Button
var pending_conflict_action: StringName = &""
var pending_conflict_signature := ""
var reset_armed := false
var gamepad_device_id := -1

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_capture_defaults()
	_load_saved_bindings()
	_build_action_rows()
	reset_button.pressed.connect(_request_reset)
	close_button.pressed.connect(close_panel)

func open_panel(device_id := -1) -> void:
	gamepad_device_id = device_id
	visible = true
	scroll_container.scroll_vertical = 0
	reset_armed = false
	reset_button.text = tr("REMAP_RESET")
	status_label.text = tr("REMAP_INSTRUCTIONS")
	_refresh_buttons()
	var first_action: StringName = ACTIONS[0][0]
	var first_device := "gamepad" if gamepad_device_id >= 0 else "keyboard"
	var first_button := binding_buttons[first_action][first_device] as Button
	first_button.grab_focus.call_deferred()

func close_panel() -> void:
	if not visible:
		return
	_cancel_capture()
	visible = false
	closed.emit()

func _input(event: InputEvent) -> void:
	if not visible:
		return
	if not capture_action.is_empty():
		if (event.is_action_pressed("ui_cancel") and capture_action != &"ui_cancel") or (event.is_action_pressed("pause") and capture_action != &"pause"):
			_cancel_capture()
			get_viewport().set_input_as_handled()
			return
		var candidate := _capture_candidate(event)
		if candidate:
			_handle_candidate(candidate)
			get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("ui_cancel") or event.is_action_pressed("pause"):
		close_panel()
		get_viewport().set_input_as_handled()

func _capture_defaults() -> void:
	for action_data in _active_actions():
		var action: StringName = action_data[0]
		default_bindings[action] = {
			"keyboard": _duplicate_event(_event_for_device(action, false)),
			"gamepad": _duplicate_event(_event_for_device(action, true)),
		}

func _build_action_rows() -> void:
	for child in actions_container.get_children():
		child.queue_free()
	binding_buttons.clear()
	for action_data in _active_actions():
		var action: StringName = action_data[0]
		var label_key: String = action_data[1]
		var row := HBoxContainer.new()
		row.name = String(action)
		row.add_theme_constant_override("separation", 12)
		actions_container.add_child(row)
		var action_label := Label.new()
		action_label.custom_minimum_size = Vector2(220, 0)
		action_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		action_label.text = tr(label_key)
		row.add_child(action_label)
		var keyboard_button := Button.new()
		keyboard_button.custom_minimum_size = Vector2(170, 0)
		keyboard_button.pressed.connect(_start_capture.bind(action, false, keyboard_button))
		keyboard_button.focus_entered.connect(_ensure_binding_focus_visible.bind(keyboard_button))
		row.add_child(keyboard_button)
		var gamepad_button := Button.new()
		gamepad_button.custom_minimum_size = Vector2(170, 0)
		gamepad_button.pressed.connect(_start_capture.bind(action, true, gamepad_button))
		gamepad_button.focus_entered.connect(_ensure_binding_focus_visible.bind(gamepad_button))
		row.add_child(gamepad_button)
		binding_buttons[action] = {"keyboard": keyboard_button, "gamepad": gamepad_button}
	_configure_focus_graph()
	_refresh_buttons()

func _configure_focus_graph() -> void:
	var keyboard_buttons: Array[Button] = []
	var gamepad_buttons: Array[Button] = []
	var tab_order: Array[Button] = []
	for action_data in _active_actions():
		var action: StringName = action_data[0]
		var keyboard_button := binding_buttons[action]["keyboard"] as Button
		var gamepad_button := binding_buttons[action]["gamepad"] as Button
		keyboard_buttons.append(keyboard_button)
		gamepad_buttons.append(gamepad_button)
		tab_order.append(keyboard_button)
		tab_order.append(gamepad_button)
	tab_order.append(reset_button)
	tab_order.append(close_button)
	for index in range(tab_order.size()):
		var current := tab_order[index]
		var previous := tab_order[(index - 1 + tab_order.size()) % tab_order.size()]
		var next := tab_order[(index + 1) % tab_order.size()]
		current.focus_previous = current.get_path_to(previous)
		current.focus_next = current.get_path_to(next)
	for index in range(keyboard_buttons.size()):
		var keyboard_button := keyboard_buttons[index]
		var gamepad_button := gamepad_buttons[index]
		var keyboard_up: Button = keyboard_buttons[index - 1] if index > 0 else reset_button
		var keyboard_down: Button = keyboard_buttons[index + 1] if index + 1 < keyboard_buttons.size() else reset_button
		var gamepad_up: Button = gamepad_buttons[index - 1] if index > 0 else close_button
		var gamepad_down: Button = gamepad_buttons[index + 1] if index + 1 < gamepad_buttons.size() else close_button
		keyboard_button.focus_neighbor_top = keyboard_button.get_path_to(keyboard_up)
		keyboard_button.focus_neighbor_bottom = keyboard_button.get_path_to(keyboard_down)
		keyboard_button.focus_neighbor_left = keyboard_button.get_path_to(gamepad_button)
		keyboard_button.focus_neighbor_right = keyboard_button.get_path_to(gamepad_button)
		gamepad_button.focus_neighbor_top = gamepad_button.get_path_to(gamepad_up)
		gamepad_button.focus_neighbor_bottom = gamepad_button.get_path_to(gamepad_down)
		gamepad_button.focus_neighbor_left = gamepad_button.get_path_to(keyboard_button)
		gamepad_button.focus_neighbor_right = gamepad_button.get_path_to(keyboard_button)
	reset_button.focus_neighbor_top = reset_button.get_path_to(keyboard_buttons.back())
	reset_button.focus_neighbor_bottom = reset_button.get_path_to(keyboard_buttons.front())
	reset_button.focus_neighbor_left = reset_button.get_path_to(close_button)
	reset_button.focus_neighbor_right = reset_button.get_path_to(close_button)
	close_button.focus_neighbor_top = close_button.get_path_to(gamepad_buttons.back())
	close_button.focus_neighbor_bottom = close_button.get_path_to(gamepad_buttons.front())
	close_button.focus_neighbor_left = close_button.get_path_to(reset_button)
	close_button.focus_neighbor_right = close_button.get_path_to(reset_button)

func _ensure_binding_focus_visible(button: Button) -> void:
	scroll_container.ensure_control_visible(button)
	call_deferred("_correct_binding_focus_visibility", button)

func _correct_binding_focus_visibility(button: Button) -> void:
	if not is_instance_valid(button) or not button.has_focus():
		return
	var viewport_rect := scroll_container.get_global_rect()
	var button_rect := button.get_global_rect()
	if button_rect.end.y > viewport_rect.end.y:
		scroll_container.scroll_vertical += ceili(button_rect.end.y - viewport_rect.end.y)
	elif button_rect.position.y < viewport_rect.position.y:
		scroll_container.scroll_vertical -= ceili(viewport_rect.position.y - button_rect.position.y)

func _start_capture(action: StringName, gamepad: bool, button: Button) -> void:
	_disarm_reset()
	capture_action = action
	capture_gamepad = gamepad
	capture_button = button
	pending_conflict_action = &""
	pending_conflict_signature = ""
	status_label.text = tr("REMAP_PRESS_GAMEPAD") if gamepad else tr("REMAP_PRESS_KEY")
	button.text = tr("REMAP_LISTENING")

func _cancel_capture() -> void:
	capture_action = &""
	capture_button = null
	pending_conflict_action = &""
	pending_conflict_signature = ""
	status_label.text = tr("REMAP_INSTRUCTIONS")
	_refresh_buttons()

func _capture_candidate(event: InputEvent) -> InputEvent:
	if capture_gamepad:
		if event is InputEventJoypadButton and event.pressed:
			var button_event := InputEventJoypadButton.new()
			button_event.button_index = event.button_index
			gamepad_device_id = event.device
			return button_event
		if event is InputEventJoypadMotion and absf(event.axis_value) > 0.7:
			var motion_event := InputEventJoypadMotion.new()
			motion_event.axis = event.axis
			motion_event.axis_value = signf(event.axis_value)
			gamepad_device_id = event.device
			return motion_event
		return null
	if event is InputEventKey and event.pressed and not event.echo:
		var key_event := InputEventKey.new()
		key_event.physical_keycode = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		key_event.keycode = event.keycode
		return key_event
	return null

func _handle_candidate(candidate: InputEvent) -> void:
	var current := _event_for_device(capture_action, capture_gamepad)
	if current and current.is_match(candidate, true):
		_cancel_capture()
		return
	var conflict := _find_conflict(candidate, capture_action)
	var signature := _event_signature(candidate)
	if not conflict.is_empty():
		if pending_conflict_action == conflict and pending_conflict_signature == signature:
			_swap_binding(capture_action, conflict, candidate, current, capture_gamepad)
			_finish_binding()
		else:
			pending_conflict_action = conflict
			pending_conflict_signature = signature
			status_label.text = tr("REMAP_CONFLICT_CONFIRM") % [_action_label(conflict), InputGlyphs.label_for_event(candidate, gamepad_device_id)]
		return
	_replace_device_event(capture_action, capture_gamepad, candidate)
	_finish_binding()

func _finish_binding() -> void:
	_save_bindings()
	bindings_changed.emit()
	status_label.text = tr("REMAP_SAVED")
	capture_action = &""
	capture_button = null
	pending_conflict_action = &""
	pending_conflict_signature = ""
	_refresh_buttons()

func _swap_binding(action: StringName, conflict: StringName, candidate: InputEvent, old_event: InputEvent, gamepad: bool) -> void:
	_replace_device_event(action, gamepad, candidate)
	if old_event:
		_replace_device_event(conflict, gamepad, old_event)

func _replace_device_event(action: StringName, gamepad: bool, replacement: InputEvent) -> void:
	for existing in InputMap.action_get_events(action):
		if _is_gamepad_event(existing) == gamepad and (existing is InputEventKey or _is_gamepad_event(existing)):
			InputMap.action_erase_event(action, existing)
	if replacement:
		InputMap.action_add_event(action, replacement)

func _find_conflict(candidate: InputEvent, excluded_action: StringName) -> StringName:
	for action_data in _active_actions():
		var action: StringName = action_data[0]
		if action == excluded_action:
			continue
		for existing in InputMap.action_get_events(action):
			if existing.is_match(candidate, true):
				return action
	return &""

func _event_for_device(action: StringName, gamepad: bool) -> InputEvent:
	for event in InputMap.action_get_events(action):
		if gamepad and _is_gamepad_event(event):
			return event
		if not gamepad and event is InputEventKey:
			return event
	return null

func _is_gamepad_event(event: InputEvent) -> bool:
	return event is InputEventJoypadButton or event is InputEventJoypadMotion

func _refresh_buttons() -> void:
	for action_data in _active_actions():
		var action: StringName = action_data[0]
		if not binding_buttons.has(action):
			continue
		var buttons: Dictionary = binding_buttons[action]
		buttons["keyboard"].text = InputGlyphs.label_for_event(_event_for_device(action, false), -1)
		buttons["gamepad"].text = InputGlyphs.label_for_event(_event_for_device(action, true), gamepad_device_id)

func _request_reset() -> void:
	if not reset_armed:
		reset_armed = true
		reset_button.text = tr("REMAP_RESET_CONFIRM")
		status_label.text = tr("REMAP_RESET_WARNING")
		close_button.grab_focus()
		return
	for action_data in _active_actions():
		var action: StringName = action_data[0]
		var defaults: Dictionary = default_bindings[action]
		_replace_device_event(action, false, _duplicate_event(defaults["keyboard"]))
		_replace_device_event(action, true, _duplicate_event(defaults["gamepad"]))
	reset_armed = false
	reset_button.text = tr("REMAP_RESET")
	status_label.text = tr("REMAP_RESET_DONE")
	_save_bindings()
	_refresh_buttons()
	bindings_changed.emit()

func _disarm_reset() -> void:
	if not reset_armed:
		return
	reset_armed = false
	reset_button.text = tr("REMAP_RESET")

func _load_saved_bindings() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) != OK:
		return
	for action_data in _active_actions():
		var action: StringName = action_data[0]
		for device_name in ["keyboard", "gamepad"]:
			var data = config.get_value("input", "%s_%s" % [action, device_name], {})
			var event := _event_from_data(data)
			if event:
				_replace_device_event(action, device_name == "gamepad", event)

func _save_bindings() -> void:
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	for action_data in _active_actions():
		var action: StringName = action_data[0]
		config.set_value("input", "%s_keyboard" % action, _event_to_data(_event_for_device(action, false)))
		config.set_value("input", "%s_gamepad" % action, _event_to_data(_event_for_device(action, true)))
	config.save(SETTINGS_PATH)

func _event_to_data(event: InputEvent) -> Dictionary:
	if event is InputEventKey:
		return {"type": "key", "physical_keycode": event.physical_keycode, "keycode": event.keycode}
	if event is InputEventJoypadButton:
		return {"type": "joy_button", "button_index": event.button_index}
	if event is InputEventJoypadMotion:
		return {"type": "joy_motion", "axis": event.axis, "axis_value": signf(event.axis_value)}
	return {}

func _event_from_data(data) -> InputEvent:
	if not data is Dictionary:
		return null
	match str(data.get("type", "")):
		"key":
			var event := InputEventKey.new()
			event.physical_keycode = int(data.get("physical_keycode", 0))
			event.keycode = int(data.get("keycode", 0))
			return event
		"joy_button":
			var event := InputEventJoypadButton.new()
			event.button_index = int(data.get("button_index", 0))
			return event
		"joy_motion":
			var event := InputEventJoypadMotion.new()
			event.axis = int(data.get("axis", 0))
			event.axis_value = float(data.get("axis_value", 1.0))
			return event
	return null

func _duplicate_event(event: InputEvent) -> InputEvent:
	return event.duplicate() as InputEvent if event else null

func _event_signature(event: InputEvent) -> String:
	return JSON.stringify(_event_to_data(event))

func _action_label(action: StringName) -> String:
	for action_data in _active_actions():
		if action_data[0] == action:
			return tr(action_data[1])
	return String(action)
