extends Node
## 桌面无语音内测模式（desktop_beta_no_voice）的 headless 验收：
##  - SpeechAdapter 不可用，不录音、不冻结时间、不创建 HTTP 客户端；
##  - NPC 提示、暂停菜单、输入重映射均不再出现语音入口；
##  - 桌面存档/无语音文案与构建标签正确；
##  - G 手势可完成完整三日流程。

var failures := 0

func _ready() -> void:
	await get_tree().process_frame
	await get_tree().physics_frame
	SpeechAdapter.availability_override = false
	SpeechAdapter.http_request = null
	SpeechAdapter.record_effect = null
	SpeechAdapter.recording_session_active = false
	var player := $Main/Player as PlayerController
	var hud := $Main/HUD
	var remap := hud.input_remap_overlay as InputRemapPanel
	hud.desktop_beta_ui_override = true
	hud.web_beta_ui_override = false
	hud._apply_web_beta_ui()
	hud._configure_focus_cycles()

	_expect(not SpeechAdapter.is_available(), "Desktop no-voice mode reports speech unavailable")
	var started := SpeechAdapter.start_recording("mira")
	_expect(not started and not SpeechAdapter.is_recording() and not GameState.interaction_time_frozen,
		"SpeechAdapter never starts recording or freezes time in desktop no-voice mode")
	_expect(SpeechAdapter.http_request == null, "SpeechAdapter creates no HTTPRequest in desktop no-voice mode")

	_expect(not hud.speech_mode_button.visible, "Pause menu hides the speech-mode setting")
	_expect(hud.no_voice_notice.visible, "Pause menu shows the no-voice explanation")
	_expect(hud.no_voice_notice.text.contains("桌面"), "Desktop no-voice notice is desktop-specific")
	_expect(hud.save_note.visible, "Pause menu shows the desktop save note")
	_expect(hud.save_note.text.contains("本机"), "Desktop save note explains local persistence")
	_expect(hud.build_tag.visible and hud.build_tag.text == "desktop-beta.1", "Desktop build tag is visible and correct")

	var actions: Array = remap._active_actions()
	_expect(actions.size() == 14, "Remap panel exposes 14 actions in desktop no-voice mode")
	var speak_row_found := false
	for action_data in actions:
		if action_data[0] == &"push_to_talk":
			speak_row_found = true
	_expect(not speak_row_found, "Remap panel removes the Speak action")

	var target := _first_npc()
	_expect(target != null, "World exposes an NPC target")
	if target:
		var prompt := target.get_interaction_prompt("keyboard", false)
		_expect((prompt.contains("手势") or prompt.contains("Gesture")), "NPC prompt keeps the gesture path")
		_expect(not prompt.contains("说话") and not prompt.contains("Speak"), "NPC prompt removes the speak path")

	var talk_event := InputEventAction.new()
	talk_event.action = &"push_to_talk"
	talk_event.pressed = true
	player._unhandled_input(talk_event)
	_expect(not SpeechAdapter.is_recording() and not SpeechAdapter.is_interaction_active(), "Speak key is ignored in desktop no-voice mode")

	_expect(_gesture_completes_three_day_run(), "Gesture fallback completes the full three-day flow")

	SpeechAdapter.availability_override = null
	hud.desktop_beta_ui_override = null
	hud.web_beta_ui_override = null
	if failures == 0:
		print("PASS: Stranger desktop-beta no-voice suite")
	get_tree().quit(failures)

func _first_npc() -> WorldInteractable:
	for candidate in get_tree().get_nodes_in_group("interactable"):
		if candidate is WorldInteractable and candidate.interaction_kind == "npc":
			return candidate
	return null

func _gesture_completes_three_day_run() -> bool:
	GameState.persistence_enabled = false
	GameState.reset_run()
	GameState.interact("npc", "mira", "gesture")
	GameState.interact("berry", "berry_a")
	GameState.interact("berry", "berry_b")
	GameState.interact("shelter", "shelter")
	if GameState.day != 2:
		return false
	GameState.interact("scrap", "scrap_a")
	GameState.interact("scrap", "scrap_b")
	GameState.interact("heater", "heater")
	GameState.interact("shelter", "shelter")
	if GameState.day != 3:
		return false
	GameState.interact("water", "reservoir")
	GameState.interact("npc", "rowan", "gesture")
	return GameState.game_finished

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
