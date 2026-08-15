extends Node

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	TranslationServer.set_locale("zh_CN")
	await get_tree().process_frame
	var hud = $Main/HUD
	hud.ui_scale_index = 5
	hud._apply_ui_scale()
	hud._open_pause()
	await get_tree().process_frame
	hud._open_input_remap()
