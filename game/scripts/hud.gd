extends CanvasLayer

const COLOR_GOOD := Color("78c9a4")
const COLOR_NEUTRAL := Color("91b9c2")
const COLOR_WARNING := Color("f2a85b")
const COLOR_URGENT := Color("ff8b7f")
const SETTINGS_PATH := "user://stranger_accessibility.cfg"
const UI_SCALES := [0.8, 0.9, 1.0, 1.1, 1.25, 1.5]
const WEB_BETA_FEATURE := "web_beta_no_voice"
const WEB_BUILD_LABEL_SETTING := "web_beta/build_label"
const WEB_BUILD_LABEL_DEFAULT := "web-beta.1"
const WEB_SURVEY_URL_SETTING := "web_beta/survey_url"
const DESKTOP_BETA_FEATURE := "desktop_beta_no_voice"
const DESKTOP_BUILD_LABEL_SETTING := "desktop_beta/build_label"
const DESKTOP_BUILD_LABEL_DEFAULT := "desktop-beta.1"
const DESKTOP_SURVEY_URL_SETTING := "desktop_beta/survey_url"

@onready var ui_root: Control = $UIRoot
@onready var clock_label: Label = $UIRoot/SafeAreaRoot/HudRoot/ObjectiveAnchor/ClockChip/ClockLabel
@onready var objective_card: PanelContainer = $UIRoot/SafeAreaRoot/HudRoot/ObjectiveAnchor/ObjectiveCard
@onready var objective_label: Label = $UIRoot/SafeAreaRoot/HudRoot/ObjectiveAnchor/ObjectiveCard/Content/ObjectiveLabel
@onready var food_label: Label = $UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/FoodRow/Content/Label
@onready var food_meter: NeedMeter = $UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/FoodRow/Content/Meter
@onready var food_icon: NeedIcon = $UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/FoodRow/Icon
@onready var warmth_label: Label = $UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/WarmthRow/Content/Label
@onready var warmth_meter: NeedMeter = $UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/WarmthRow/Content/Meter
@onready var warmth_icon: NeedIcon = $UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/WarmthRow/Icon
@onready var energy_label: Label = $UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/EnergyRow/Content/Label
@onready var energy_meter: NeedMeter = $UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/EnergyRow/Content/Meter
@onready var energy_icon: NeedIcon = $UIRoot/SafeAreaRoot/HudRoot/NeedsAnchor/NeedsRows/EnergyRow/Icon
@onready var interaction_card: PanelContainer = $UIRoot/SafeAreaRoot/HudRoot/InteractionAnchor/InteractionCard
@onready var interaction_label: Label = $UIRoot/SafeAreaRoot/HudRoot/InteractionAnchor/InteractionCard/Content/InteractionLabel
@onready var voice_status_icon: VoiceStatusIcon = $UIRoot/SafeAreaRoot/HudRoot/InteractionAnchor/InteractionCard/Content/VoiceStatusIcon
@onready var toast_panel: PanelContainer = $UIRoot/SafeAreaRoot/HudRoot/ToastAnchor/ToastPanel
@onready var toast_label: Label = $UIRoot/SafeAreaRoot/HudRoot/ToastAnchor/ToastPanel/ToastLabel
@onready var safe_area: MarginContainer = $UIRoot/SafeAreaRoot
@onready var day_transition_overlay: ColorRect = $UIRoot/DayTransitionOverlay
@onready var day_label: Label = $UIRoot/DayTransitionOverlay/Center/Content/DayLabel
@onready var day_body: Label = $UIRoot/DayTransitionOverlay/Center/Content/Body
@onready var pause_overlay: ColorRect = $UIRoot/PauseOverlay
@onready var resume_button: Button = $UIRoot/PauseOverlay/Center/Card/Content/ResumeButton
@onready var reduce_motion_button: Button = $UIRoot/PauseOverlay/Center/Card/Content/ReduceMotionButton
@onready var ui_scale_button: Button = $UIRoot/PauseOverlay/Center/Card/Content/UIScaleButton
@onready var speech_mode_button: Button = $UIRoot/PauseOverlay/Center/Card/Content/SpeechModeButton
@onready var controls_button: Button = $UIRoot/PauseOverlay/Center/Card/Content/ControlsButton
@onready var pause_survey_button: Button = $UIRoot/PauseOverlay/Center/Card/Content/SurveyButton
@onready var no_voice_notice: Label = $UIRoot/PauseOverlay/Center/Card/Content/NoVoiceNotice
@onready var save_note: Label = $UIRoot/PauseOverlay/Center/Card/Content/SaveNote
@onready var build_tag: Label = $UIRoot/SafeAreaRoot/HudRoot/BuildTag
@onready var input_remap_overlay: InputRemapPanel = $UIRoot/InputRemapOverlay
@onready var completion_overlay: ColorRect = $UIRoot/CompletionOverlay
@onready var continue_button: Button = $UIRoot/CompletionOverlay/Center/Card/Content/ContinueButton
@onready var restart_button: Button = $UIRoot/CompletionOverlay/Center/Card/Content/RestartButton
@onready var completion_survey_button: Button = $UIRoot/CompletionOverlay/Center/Card/Content/SurveyButton

var player: PlayerController
var toast_timer: Timer
var voice_status_timer: Timer
var day_transition_timer: Timer
var toast_tween: Tween
var objective_tween: Tween
var interaction_tween: Tween
var overlay_tween: Tween
var toast_queue: Array[Dictionary] = []
var toast_active := false
var gamepad_active := false
var gamepad_device_id := -1
var reduce_motion := false
var restart_armed := false
var ui_scale_index := 2
var speech_toggle_mode := false
var voice_state := "idle"
var voice_target_name := ""
var voice_elapsed := 0.0
var voice_transcript := ""
var voice_reason := ""
var day_transition_started_msec := 0
## 测试钩子：null 表示按 OS feature 自动判断；true/false 强制覆盖 Web UI。
var web_beta_ui_override: Variant = null
## 桌面版测试钩子，作用同上。
var desktop_beta_ui_override: Variant = null

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	ui_root.theme = ui_root.theme.duplicate()
	_create_timers()
	_connect_domain_signals()
	_connect_buttons()
	_load_settings()
	_apply_web_beta_ui()
	_configure_focus_cycles()
	get_viewport().size_changed.connect(_apply_safe_frame)
	call_deferred("_bind_player")
	call_deferred("_apply_safe_frame")
	_update_clock(GameState.day, int(GameState.day_time))
	_update_objective(GameState.objective_text())
	_update_needs(GameState.food, GameState.warmth, GameState.energy)

func _create_timers() -> void:
	toast_timer = Timer.new()
	toast_timer.one_shot = true
	toast_timer.timeout.connect(_hide_toast)
	add_child(toast_timer)
	voice_status_timer = Timer.new()
	voice_status_timer.one_shot = true
	voice_status_timer.timeout.connect(_clear_voice_status)
	add_child(voice_status_timer)
	day_transition_timer = Timer.new()
	day_transition_timer.one_shot = true
	day_transition_timer.timeout.connect(_dismiss_day_transition)
	add_child(day_transition_timer)

func _connect_domain_signals() -> void:
	GameState.state_changed.connect(_on_state_changed)
	GameState.needs_changed.connect(_update_needs)
	GameState.clock_changed.connect(_update_clock)
	GameState.objective_changed.connect(_update_objective)
	GameState.message_requested.connect(_show_message)
	GameState.run_completed.connect(_show_completion)
	GameState.day_started.connect(_show_day_transition)
	SpeechAdapter.recording_state_changed.connect(_on_recording_state_changed)
	SpeechAdapter.recording_progress.connect(_on_recording_progress)
	SpeechAdapter.recognition_pending.connect(_on_recognition_pending)
	SpeechAdapter.recognition_finished.connect(_on_recognition_finished)
	SpeechAdapter.session_cancelled.connect(_on_speech_cancelled)

func _connect_buttons() -> void:
	continue_button.pressed.connect(_dismiss_completion)
	restart_button.pressed.connect(_request_restart)
	resume_button.pressed.connect(_close_pause)
	reduce_motion_button.pressed.connect(_toggle_reduce_motion)
	ui_scale_button.pressed.connect(_cycle_ui_scale)
	speech_mode_button.pressed.connect(_toggle_speech_mode)
	controls_button.pressed.connect(_open_input_remap)
	pause_survey_button.pressed.connect(_open_survey)
	completion_survey_button.pressed.connect(_open_survey)
	input_remap_overlay.closed.connect(_on_input_remap_closed)
	input_remap_overlay.bindings_changed.connect(_on_bindings_changed)

func _configure_focus_cycles() -> void:
	var pause_buttons: Array[Button] = [resume_button, reduce_motion_button, ui_scale_button]
	if SpeechAdapter.is_available():
		pause_buttons.append(speech_mode_button)
	pause_buttons.append(controls_button)
	if pause_survey_button.visible:
		pause_buttons.append(pause_survey_button)
	_link_focus_cycle(pause_buttons)
	var completion_buttons: Array[Button] = [continue_button, restart_button]
	if completion_survey_button.visible:
		completion_buttons.append(completion_survey_button)
	_link_focus_cycle(completion_buttons)

func _is_web_beta_build() -> bool:
	if web_beta_ui_override != null:
		return bool(web_beta_ui_override)
	return OS.has_feature("web") or OS.has_feature(WEB_BETA_FEATURE)

func _is_desktop_beta_build() -> bool:
	if desktop_beta_ui_override != null:
		return bool(desktop_beta_ui_override)
	return OS.has_feature(DESKTOP_BETA_FEATURE)

func _is_beta_build() -> bool:
	return _is_web_beta_build() or _is_desktop_beta_build()

func _apply_web_beta_ui() -> void:
	var is_beta := _is_beta_build()
	var is_desktop := _is_desktop_beta_build()
	build_tag.visible = is_beta
	if is_beta:
		var label_setting := DESKTOP_BUILD_LABEL_SETTING if is_desktop else WEB_BUILD_LABEL_SETTING
		var label_default := DESKTOP_BUILD_LABEL_DEFAULT if is_desktop else WEB_BUILD_LABEL_DEFAULT
		build_tag.text = str(ProjectSettings.get_setting(label_setting, label_default))
	if not SpeechAdapter.is_available():
		# 首轮内测不包含语音：隐藏语音入口，保留手势/观察完整流程。
		speech_mode_button.visible = false
		speech_toggle_mode = false
		no_voice_notice.text = tr("DESKTOP_NO_VOICE_NOTICE") if is_desktop else tr("WEB_BETA_NO_VOICE_NOTICE")
	no_voice_notice.visible = not SpeechAdapter.is_available()
	if is_beta:
		save_note.text = tr("DESKTOP_SAVE_NOTE") if is_desktop else tr("WEB_SAVE_NOTE")
	save_note.visible = is_beta
	var survey_setting := DESKTOP_SURVEY_URL_SETTING if is_desktop else WEB_SURVEY_URL_SETTING
	var survey_url := str(ProjectSettings.get_setting(survey_setting, "")).strip_edges()
	pause_survey_button.visible = not survey_url.is_empty()
	completion_survey_button.visible = not survey_url.is_empty()

func _open_survey() -> void:
	var survey_setting := DESKTOP_SURVEY_URL_SETTING if _is_desktop_beta_build() else WEB_SURVEY_URL_SETTING
	var survey_url := str(ProjectSettings.get_setting(survey_setting, "")).strip_edges()
	if survey_url.is_empty():
		return
	var error := OS.shell_open(survey_url)
	if error != OK:
		GameState.message_requested.emit(tr("WEB_SURVEY_OPEN_FAILED"), "warning")

func _link_focus_cycle(buttons: Array[Button]) -> void:
	for index in range(buttons.size()):
		var current := buttons[index]
		var previous := buttons[(index - 1 + buttons.size()) % buttons.size()]
		var next := buttons[(index + 1) % buttons.size()]
		current.focus_neighbor_top = current.get_path_to(previous)
		current.focus_neighbor_left = current.get_path_to(previous)
		current.focus_neighbor_bottom = current.get_path_to(next)
		current.focus_neighbor_right = current.get_path_to(next)

func _unhandled_input(event: InputEvent) -> void:
	_update_active_device(event)
	if day_transition_overlay.visible:
		if _is_overlay_cancel_event(event):
			if reduce_motion or Time.get_ticks_msec() - day_transition_started_msec >= 300:
				_dismiss_day_transition()
			get_viewport().set_input_as_handled()
		return
	if completion_overlay.visible:
		if event.is_action_pressed("ui_cancel") or event.is_action_pressed("pause"):
			_dismiss_completion()
			get_viewport().set_input_as_handled()
		return
	if SpeechAdapter.is_interaction_active() and event.is_action_pressed("ui_cancel"):
		SpeechAdapter.cancel_recording()
		get_viewport().set_input_as_handled()
		return
	if pause_overlay.visible and event.is_action_pressed("ui_cancel"):
		_close_pause()
		get_viewport().set_input_as_handled()
		return
	if event.is_action_pressed("pause"):
		if pause_overlay.visible:
			_close_pause()
		else:
			_open_pause()
		get_viewport().set_input_as_handled()

func _is_overlay_cancel_event(event: InputEvent) -> bool:
	return event.is_action_pressed("ui_accept") or event.is_action_pressed("ui_cancel") or event.is_action_pressed("interact") or event.is_action_pressed("pause")

func _update_active_device(event: InputEvent) -> void:
	var next_gamepad := gamepad_active
	if event is InputEventJoypadButton and event.pressed:
		next_gamepad = true
		gamepad_device_id = event.device
	elif event is InputEventJoypadMotion and absf(event.axis_value) > 0.28:
		next_gamepad = true
		gamepad_device_id = event.device
	elif event is InputEventKey and event.pressed:
		next_gamepad = false
	elif event is InputEventMouseButton and event.pressed:
		next_gamepad = false
	elif event is InputEventMouseMotion and event.relative.length() > 1.5:
		next_gamepad = false
	if next_gamepad != gamepad_active:
		gamepad_active = next_gamepad
		_refresh_interaction_prompt()

func _bind_player() -> void:
	player = get_tree().get_first_node_in_group("player") as PlayerController
	if player:
		player.interaction_prompt_changed.connect(_on_interaction_prompt_changed)
		if SpeechAdapter.is_available():
			player.set_speech_toggle_mode(speech_toggle_mode)
		player.set_reduce_motion(reduce_motion)
		_refresh_interaction_prompt()

func _update_clock(day_value: int, _elapsed_seconds: int) -> void:
	var clock := GameState.clock_hms()
	clock_label.text = tr("HUD_CLOCK") % [day_value, clock.x, clock.y]

func _update_objective(objective: String) -> void:
	objective_label.text = objective
	if GameState.game_finished and not completion_overlay.visible:
		call_deferred("_show_completion")
	if reduce_motion:
		objective_card.modulate.a = 1.0
		return
	if objective_tween and objective_tween.is_valid():
		objective_tween.kill()
	objective_card.modulate.a = 0.5
	objective_tween = create_tween()
	objective_tween.tween_property(objective_card, "modulate:a", 1.0, 0.22).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)

func _update_needs(food: float, warmth: float, energy: float) -> void:
	_update_need(food_label, food_meter, food_icon, tr("NEED_FOOD"), food)
	_update_need(warmth_label, warmth_meter, warmth_icon, tr("NEED_WARMTH"), warmth)
	_update_need(energy_label, energy_meter, energy_icon, tr("NEED_ENERGY"), energy)

func _update_need(label: Label, meter: NeedMeter, icon: NeedIcon, title: String, value: float) -> void:
	var state := tr("NEED_STABLE") if value > 50.0 else (tr("NEED_CAUTION") if value > 25.0 else tr("NEED_CRITICAL"))
	var tone := COLOR_GOOD if value > 50.0 else (COLOR_WARNING if value > 25.0 else COLOR_URGENT)
	label.text = tr("NEED_FORMAT") % [title, int(value), state]
	label.modulate = tone
	icon.set_tone(tone)
	meter.set_need(value, reduce_motion)

func _on_interaction_prompt_changed(_prompt: String) -> void:
	if voice_state in ["clarify", "unavailable"] and SpeechAdapter.is_recovery_active():
		return
	_refresh_interaction_prompt()

func _refresh_interaction_prompt() -> void:
	if voice_state != "idle":
		_refresh_voice_card()
		return
	voice_status_icon.set_state("idle")
	if not player:
		return
	var prompt := player.interaction_prompt("gamepad" if gamepad_active else "keyboard", gamepad_device_id)
	_set_interaction_text(prompt)

func _set_interaction_text(text: String) -> void:
	if text.is_empty():
		if reduce_motion:
			interaction_card.visible = false
			return
		if not interaction_card.visible:
			return
		if interaction_tween and interaction_tween.is_valid():
			interaction_tween.kill()
		interaction_tween = create_tween()
		interaction_tween.tween_property(interaction_card, "modulate:a", 0.0, 0.1)
		interaction_tween.tween_callback(func(): interaction_card.visible = false)
		return
	interaction_label.text = text
	if interaction_card.visible:
		interaction_card.modulate.a = 1.0
		return
	interaction_card.visible = true
	if reduce_motion:
		interaction_card.modulate.a = 1.0
		return
	interaction_card.modulate.a = 0.0
	if interaction_tween and interaction_tween.is_valid():
		interaction_tween.kill()
	interaction_tween = create_tween()
	interaction_tween.tween_property(interaction_card, "modulate:a", 1.0, 0.12).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)

func _on_recording_state_changed(active: bool) -> void:
	if not SpeechAdapter.is_available():
		return
	if active:
		voice_state = "listening"
		voice_target_name = player.current_target_name() if player else tr("NEARBY_RESIDENT")
		voice_elapsed = 0.0
		voice_transcript = ""
		voice_reason = ""
		_refresh_voice_card()
	elif voice_state == "listening":
		voice_state = "idle"
		_refresh_interaction_prompt()

func _on_recording_progress(elapsed_seconds: float, _maximum_seconds: float) -> void:
	if not SpeechAdapter.is_available():
		return
	voice_elapsed = elapsed_seconds
	if voice_state == "listening":
		_refresh_voice_card()

func _on_recognition_pending(_target_id: String) -> void:
	if not SpeechAdapter.is_available():
		return
	voice_state = "transcribing"
	_refresh_voice_card()

func _on_recognition_finished(_target_id: String, accepted: bool, transcript: String, reason: String) -> void:
	if not SpeechAdapter.is_available():
		return
	if voice_target_name.is_empty():
		voice_target_name = player.current_target_name() if player else tr("NEARBY_RESIDENT")
	voice_transcript = transcript
	voice_reason = tr(reason)
	if accepted:
		voice_state = "accepted"
		_refresh_voice_card()
		voice_status_timer.start(3.2)
	else:
		voice_state = "unavailable" if _is_unavailable_reason(reason) else "clarify"
		_refresh_voice_card()

func _is_unavailable_reason(reason_key: String) -> bool:
	return reason_key in ["VOICE_REASON_MIC_UNAVAILABLE", "VOICE_REASON_SERVICE_UNAVAILABLE", "VOICE_REASON_SAVE_FAILED", "VOICE_REASON_READ_FAILED", "VOICE_REASON_RESULT_INVALID"]

func _on_speech_cancelled(_target_id: String) -> void:
	_clear_voice_status()

func _clear_voice_status() -> void:
	voice_state = "idle"
	voice_target_name = ""
	voice_transcript = ""
	voice_reason = ""
	_refresh_interaction_prompt()

func _refresh_voice_card() -> void:
	voice_status_icon.set_state(voice_state)
	var talk_glyph := InputGlyphs.for_action("push_to_talk", gamepad_active, gamepad_device_id)
	var gesture_glyph := InputGlyphs.for_action("gesture", gamepad_active, gamepad_device_id)
	var cancel_glyph := InputGlyphs.for_action("ui_cancel", gamepad_active, gamepad_device_id)
	match voice_state:
		"listening":
			var finish_verb := tr("VOICE_FINISH_TOGGLE") if speech_toggle_mode else tr("VOICE_FINISH_HOLD")
			_set_interaction_text("%s\n%s" % [tr("VOICE_LISTENING") % [voice_target_name, voice_elapsed], tr("VOICE_LISTENING_ACTIONS") % [talk_glyph, finish_verb, gesture_glyph, cancel_glyph]])
		"transcribing":
			_set_interaction_text("%s\n%s" % [tr("VOICE_TRANSCRIBING") % voice_target_name, tr("VOICE_TRANSCRIBING_ACTIONS") % [gesture_glyph, cancel_glyph]])
		"accepted":
			var heard := "\n%s" % (tr("VOICE_HEARD") % voice_transcript) if not voice_transcript.is_empty() else ""
			_set_interaction_text("%s%s" % [tr("VOICE_ACCEPTED") % voice_target_name, heard])
		"clarify", "unavailable":
			var status := tr("VOICE_UNAVAILABLE") % voice_target_name if voice_state == "unavailable" else tr("VOICE_CLARIFY") % voice_target_name
			var heard := "\n%s" % (tr("VOICE_HEARD") % voice_transcript) if not voice_transcript.is_empty() else ""
			_set_interaction_text("%s%s\n%s\n%s" % [status, heard, voice_reason, tr("VOICE_RECOVERY_ACTIONS") % [talk_glyph, gesture_glyph, cancel_glyph]])
		_:
			_refresh_interaction_prompt()

func _show_message(message_text: String, tone: String) -> void:
	var item := {"text": message_text, "tone": tone}
	if toast_active:
		if toast_queue.size() >= 2:
			toast_queue.pop_front()
		toast_queue.append(item)
		return
	_display_toast(item)

func _display_toast(item: Dictionary) -> void:
	toast_active = true
	var tone := str(item.get("tone", "neutral"))
	var prefix := tr("TOAST_INFO")
	var color := COLOR_NEUTRAL
	var duration := 3.2
	if tone == "good":
		prefix = tr("TOAST_DONE")
		color = COLOR_GOOD
	elif tone == "warning":
		prefix = tr("TOAST_WARNING")
		color = COLOR_WARNING
		duration = 6.0
	toast_label.text = "%s · %s" % [prefix, str(item.get("text", ""))]
	toast_label.modulate = color
	toast_panel.visible = true
	toast_panel.modulate.a = 0.0
	if toast_tween and toast_tween.is_valid():
		toast_tween.kill()
	toast_tween = create_tween()
	toast_tween.tween_property(toast_panel, "modulate:a", 1.0, 0.08 if reduce_motion else 0.18)
	toast_timer.start(duration)

func _hide_toast() -> void:
	if not toast_panel.visible:
		_finish_toast()
		return
	if reduce_motion:
		toast_panel.visible = false
		_finish_toast()
		return
	if toast_tween and toast_tween.is_valid():
		toast_tween.kill()
	toast_tween = create_tween()
	toast_tween.tween_property(toast_panel, "modulate:a", 0.0, 0.14)
	toast_tween.tween_callback(_finish_toast)

func _finish_toast() -> void:
	toast_panel.visible = false
	toast_active = false
	if not toast_queue.is_empty():
		_display_toast(toast_queue.pop_front())

func _show_day_transition(day_value: int) -> void:
	if completion_overlay.visible:
		return
	day_label.text = tr("DAY_LABEL") % day_value
	day_body.text = tr("DAY_TWO_BODY") if day_value == 2 else tr("DAY_THREE_BODY")
	day_transition_overlay.visible = true
	day_transition_overlay.modulate.a = 0.0
	day_transition_started_msec = Time.get_ticks_msec()
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if overlay_tween and overlay_tween.is_valid():
		overlay_tween.kill()
	overlay_tween = create_tween()
	overlay_tween.tween_property(day_transition_overlay, "modulate:a", 1.0, 0.08 if reduce_motion else 0.22)
	day_transition_timer.start(0.75 if reduce_motion else 1.25)

func _dismiss_day_transition() -> void:
	if not day_transition_overlay.visible:
		return
	day_transition_timer.stop()
	if reduce_motion:
		_finish_day_transition()
		return
	if overlay_tween and overlay_tween.is_valid():
		overlay_tween.kill()
	overlay_tween = create_tween()
	overlay_tween.tween_property(day_transition_overlay, "modulate:a", 0.0, 0.18)
	overlay_tween.tween_callback(_finish_day_transition)

func _finish_day_transition() -> void:
	day_transition_overlay.visible = false
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _on_state_changed() -> void:
	if GameState.game_finished and not completion_overlay.visible:
		_show_completion()

func _show_completion() -> void:
	if completion_overlay.visible:
		return
	day_transition_overlay.visible = false
	pause_overlay.visible = false
	completion_overlay.visible = true
	completion_overlay.modulate.a = 0.0
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	var tween := create_tween()
	tween.tween_property(completion_overlay, "modulate:a", 1.0, 0.1 if reduce_motion else 0.28)
	continue_button.grab_focus.call_deferred()

func _dismiss_completion() -> void:
	completion_overlay.visible = false
	_release_ui_focus()
	get_tree().paused = false
	restart_armed = false
	restart_button.text = tr("BTN_RESTART")
	continue_button.text = tr("BTN_COMPLETE_CONTINUE")
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _request_restart() -> void:
	if not restart_armed:
		restart_armed = true
		restart_button.text = tr("BTN_RESTART_CONFIRM")
		continue_button.text = tr("BTN_RESTART_CANCEL")
		continue_button.grab_focus()
		return
	get_tree().paused = false
	GameState.reset_run()
	GameState.save_game()
	get_tree().reload_current_scene()

func _open_pause() -> void:
	SpeechAdapter.cancel_recording()
	pause_overlay.visible = true
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	resume_button.grab_focus.call_deferred()

func _close_pause() -> void:
	pause_overlay.visible = false
	_release_ui_focus()
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _release_ui_focus() -> void:
	var focus_owner := get_viewport().gui_get_focus_owner()
	if focus_owner:
		focus_owner.release_focus()

func _toggle_reduce_motion() -> void:
	reduce_motion = not reduce_motion
	reduce_motion_button.text = tr("SETTING_REDUCE_MOTION") % (tr("SETTING_ON") if reduce_motion else tr("SETTING_OFF"))
	if player:
		player.set_reduce_motion(reduce_motion)
	_update_needs(GameState.food, GameState.warmth, GameState.energy)
	_save_settings()
	reduce_motion_button.grab_focus()

func _cycle_ui_scale() -> void:
	ui_scale_index = (ui_scale_index + 1) % UI_SCALES.size()
	_apply_ui_scale()
	_save_settings()
	ui_scale_button.grab_focus()

func _apply_ui_scale() -> void:
	var scale_value: float = UI_SCALES[ui_scale_index]
	ui_root.theme.default_base_scale = scale_value
	ui_scale_button.text = tr("SETTING_UI_SCALE") % int(scale_value * 100.0)
	call_deferred("_apply_safe_frame")

func _toggle_speech_mode() -> void:
	if not SpeechAdapter.is_available():
		return
	speech_toggle_mode = not speech_toggle_mode
	if player:
		player.set_speech_toggle_mode(speech_toggle_mode)
	speech_mode_button.text = tr("SETTING_SPEECH_MODE") % (tr("SETTING_TOGGLE") if speech_toggle_mode else tr("SETTING_HOLD"))
	_refresh_interaction_prompt()
	_save_settings()
	speech_mode_button.grab_focus()

func _open_input_remap() -> void:
	pause_overlay.visible = false
	input_remap_overlay.open_panel(gamepad_device_id if gamepad_active else -1)

func _on_input_remap_closed() -> void:
	pause_overlay.visible = true
	_refresh_interaction_prompt()
	controls_button.grab_focus.call_deferred()

func _on_bindings_changed() -> void:
	_refresh_interaction_prompt()

func _apply_safe_frame() -> void:
	var viewport_size := get_viewport().get_visible_rect().size
	if viewport_size.x <= 0.0 or viewport_size.y <= 0.0:
		return
	var target_aspect := 16.0 / 9.0
	var frame_size := viewport_size
	if viewport_size.x / viewport_size.y > target_aspect:
		frame_size.x = viewport_size.y * target_aspect
	elif viewport_size.x / viewport_size.y < target_aspect:
		frame_size.y = viewport_size.x / target_aspect
	var base_margin := clampf(viewport_size.x * 0.04, 24.0, 72.0)
	var scale_value: float = UI_SCALES[ui_scale_index]
	var left_right := ((viewport_size.x - frame_size.x) * 0.5 + base_margin) / scale_value
	var top_bottom := ((viewport_size.y - frame_size.y) * 0.5 + base_margin * 0.78) / scale_value
	safe_area.add_theme_constant_override("margin_left", int(left_right))
	safe_area.add_theme_constant_override("margin_right", int(left_right))
	safe_area.add_theme_constant_override("margin_top", int(top_bottom))
	safe_area.add_theme_constant_override("margin_bottom", int(top_bottom))

func _load_settings() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) == OK:
		reduce_motion = bool(config.get_value("accessibility", "reduce_motion", false))
		ui_scale_index = clampi(int(config.get_value("accessibility", "ui_scale_index", 2)), 0, UI_SCALES.size() - 1)
		speech_toggle_mode = bool(config.get_value("accessibility", "speech_toggle_mode", false))
	reduce_motion_button.text = tr("SETTING_REDUCE_MOTION") % (tr("SETTING_ON") if reduce_motion else tr("SETTING_OFF"))
	speech_mode_button.text = tr("SETTING_SPEECH_MODE") % (tr("SETTING_TOGGLE") if speech_toggle_mode else tr("SETTING_HOLD"))
	_apply_ui_scale()

func _save_settings() -> void:
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	config.set_value("accessibility", "reduce_motion", reduce_motion)
	config.set_value("accessibility", "ui_scale_index", ui_scale_index)
	config.set_value("accessibility", "speech_toggle_mode", speech_toggle_mode)
	config.save(SETTINGS_PATH)
