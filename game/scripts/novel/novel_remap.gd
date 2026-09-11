extends "res://scripts/input_remap_panel.gd"
const Palette := preload("res://scripts/novel/novel_palette.gd")

func _ready() -> void:
	super._ready()
	color = Color(Palette.SHADOW, 0.38)
	$Center/Card/Content/Title.add_theme_color_override("font_color", Palette.TEXT)
	$Center/Card/Content/Title.theme_type_variation = "NovelTitle"

## Reuse conflict resolution/persistence, expose only actions used in 2D.
func _active_actions() -> Array:
	var result: Array = []
	for action in super._active_actions():
		if action[0] in [&"interact", &"push_to_talk", &"gesture", &"item_show", &"pause", &"ui_cancel"]:
			result.append(action)
	return result

func open_panel(device_id := -1) -> void:
	gamepad_device_id = device_id
	visible = true
	scroll_container.scroll_vertical = 0
	reset_armed = false
	reset_button.text = tr("REMAP_RESET")
	status_label.text = tr("REMAP_INSTRUCTIONS")
	_refresh_buttons()
	binding_buttons[&"interact"]["gamepad" if device_id >= 0 else "keyboard"].grab_focus.call_deferred()
