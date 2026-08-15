class_name InputGlyphs
extends RefCounted

const XBOX_LABELS := {
	JOY_BUTTON_A: "A",
	JOY_BUTTON_B: "B",
	JOY_BUTTON_X: "X",
	JOY_BUTTON_Y: "Y",
	JOY_BUTTON_LEFT_SHOULDER: "LB",
	JOY_BUTTON_RIGHT_SHOULDER: "RB",
	JOY_BUTTON_BACK: "View",
	JOY_BUTTON_START: "Menu",
	JOY_BUTTON_LEFT_STICK: "L3",
	JOY_BUTTON_RIGHT_STICK: "R3",
}

const PLAYSTATION_LABELS := {
	JOY_BUTTON_A: "×",
	JOY_BUTTON_B: "○",
	JOY_BUTTON_X: "□",
	JOY_BUTTON_Y: "△",
	JOY_BUTTON_LEFT_SHOULDER: "L1",
	JOY_BUTTON_RIGHT_SHOULDER: "R1",
	JOY_BUTTON_BACK: "Touchpad",
	JOY_BUTTON_START: "Options",
	JOY_BUTTON_LEFT_STICK: "L3",
	JOY_BUTTON_RIGHT_STICK: "R3",
}

const GENERIC_LABELS := {
	JOY_BUTTON_A: "South",
	JOY_BUTTON_B: "East",
	JOY_BUTTON_X: "West",
	JOY_BUTTON_Y: "North",
	JOY_BUTTON_LEFT_SHOULDER: "L1",
	JOY_BUTTON_RIGHT_SHOULDER: "R1",
	JOY_BUTTON_BACK: "Select",
	JOY_BUTTON_START: "Menu",
	JOY_BUTTON_LEFT_STICK: "L3",
	JOY_BUTTON_RIGHT_STICK: "R3",
}

static func for_action(action: StringName, gamepad: bool, device_id := -1) -> String:
	for event in InputMap.action_get_events(action):
		if gamepad and (event is InputEventJoypadButton or event is InputEventJoypadMotion):
			return label_for_event(event, device_id)
		if not gamepad and event is InputEventKey:
			return label_for_event(event, device_id)
	return "—"

static func label_for_event(event: InputEvent, device_id := -1) -> String:
	if event == null:
		return "—"
	if event is InputEventKey:
		var keycode: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		return OS.get_keycode_string(keycode)
	if event is InputEventJoypadButton:
		return label_for_button(event.button_index, controller_style(device_id))
	if event is InputEventJoypadMotion:
		return _motion_label(event.axis, event.axis_value)
	return event.as_text()

static func label_for_button(button_index: int, style: String) -> String:
	match style:
		"playstation":
			return PLAYSTATION_LABELS.get(button_index, "Button %d" % button_index)
		"xbox":
			return XBOX_LABELS.get(button_index, "B%d" % button_index)
		_:
			return GENERIC_LABELS.get(button_index, "Button %d" % button_index)

static func controller_style(device_id: int) -> String:
	if device_id < 0:
		return "generic"
	var joy_name := Input.get_joy_name(device_id).to_lower()
	if "playstation" in joy_name or "dualsense" in joy_name or "dualshock" in joy_name or "sony" in joy_name:
		return "playstation"
	if "xbox" in joy_name or "xinput" in joy_name or "microsoft" in joy_name:
		return "xbox"
	return "generic"

static func _motion_label(axis: int, axis_value: float) -> String:
	var direction := "−" if axis_value < 0.0 else "+"
	match axis:
		JOY_AXIS_LEFT_X:
			return "L←" if axis_value < 0.0 else "L→"
		JOY_AXIS_LEFT_Y:
			return "L↑" if axis_value < 0.0 else "L↓"
		JOY_AXIS_RIGHT_X:
			return "R←" if axis_value < 0.0 else "R→"
		JOY_AXIS_RIGHT_Y:
			return "R↑" if axis_value < 0.0 else "R↓"
		_:
			return "Axis %d%s" % [axis, direction]
