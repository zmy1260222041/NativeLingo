extends Node

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	TranslationServer.set_locale("zh_CN")
	await get_tree().process_frame
	var hud = $Main/HUD
	hud.ui_scale_index = 5
	hud._apply_ui_scale()
	hud.voice_state = "clarify"
	hud.voice_target_name = TranslationServer.translate("NPC_MIRA")
	hud.voice_transcript = "Hello Mira, I am glad to meet you"
	hud.voice_reason = TranslationServer.translate("VOICE_REASON_CLARIFY")
	hud._refresh_voice_card()
