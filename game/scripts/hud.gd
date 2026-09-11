extends CanvasLayer

const COLOR_GOOD := Color("78c9a4")
const COLOR_NEUTRAL := Color("91b9c2")
const COLOR_WARNING := Color("f2a85b")
const COLOR_URGENT := Color("ff8b7f")
## FR-45 speaker subtitle salience mark: red plus underline, never colour alone.
const SPEAKER_MARK_COLOR_HEX := "#ff8b7f"
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
const SiltInkPanelScript = preload("res://ui/silt_ink_panel.gd")

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
var item_panel: PanelContainer
var item_mode_button: Button
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
var voice_expression := {}
var cloud_button: Button
var cloud_overlay: ColorRect
var cloud_code_edit: LineEdit
var cloud_status_label: Label
var cloud_activate_button: Button
var cloud_close_button: Button
var onboarding_panel: PanelContainer
var onboarding_step_label: Label
var onboarding_protected_label: Label
var onboarding_skip_button: Button
var word_unlock_overlay: ColorRect
var word_unlock_label: Label
var word_unlock_button: Button
var word_practice_panel: PanelContainer
var word_practice_prompt_label: Label
var speaker_subtitle_card: PanelContainer
var speaker_subtitle_label: RichTextLabel
var speaker_subtitle_timer: Timer
var objective_timer: Timer
var day_transition_started_msec := 0
## 测试钩子：null 表示按 OS feature 自动判断；true/false 强制覆盖 Web UI。
var web_beta_ui_override: Variant = null
## 桌面版测试钩子，作用同上。
var desktop_beta_ui_override: Variant = null

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	ui_root.theme = ui_root.theme.duplicate()
	ui_root.theme.set_stylebox("panel", "PanelContainer", SiltInkPanelScript.new())
	_create_timers()
	_connect_domain_signals()
	_connect_buttons()
	_load_settings()
	_apply_web_beta_ui()
	_build_cloud_ui()
	_build_onboarding_ui()
	_build_word_unlock_ui()
	_build_word_practice_ui()
	_build_speaker_subtitle_ui()
	item_panel = preload("res://scripts/item_panel.gd").new()
	ui_root.add_child(item_panel)
	item_mode_button = Button.new()
	speech_mode_button.get_parent().add_child(item_mode_button)
	item_mode_button.pressed.connect(_toggle_item_mode)
	_update_item_mode_label()
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
	voice_status_timer.timeout.connect(_on_voice_status_timeout)
	add_child(voice_status_timer)
	day_transition_timer = Timer.new()
	day_transition_timer.one_shot = true
	day_transition_timer.timeout.connect(_dismiss_day_transition)
	add_child(day_transition_timer)
	objective_timer = Timer.new()
	objective_timer.one_shot = true
	objective_timer.timeout.connect(_collapse_objective)
	add_child(objective_timer)
	speaker_subtitle_timer = Timer.new()
	speaker_subtitle_timer.one_shot = true
	speaker_subtitle_timer.timeout.connect(_hide_speaker_subtitle)
	add_child(speaker_subtitle_timer)

func _connect_domain_signals() -> void:
	GameState.state_changed.connect(_on_state_changed)
	GameState.needs_changed.connect(_update_needs)
	GameState.clock_changed.connect(_update_clock)
	GameState.objective_changed.connect(_update_objective)
	GameState.message_requested.connect(_show_message)
	GameState.run_completed.connect(_show_completion)
	GameState.day_started.connect(_show_day_transition)
	GameState.onboarding_changed.connect(_on_onboarding_changed)
	SpeechAdapter.recording_state_changed.connect(_on_recording_state_changed)
	SpeechAdapter.recording_progress.connect(_on_recording_progress)
	SpeechAdapter.recognition_pending.connect(_on_recognition_pending)
	SpeechAdapter.recognition_finished.connect(_on_recognition_finished)
	SpeechAdapter.session_cancelled.connect(_on_speech_cancelled)
	SpeechAdapter.word_score_finished.connect(_on_word_score_finished)
	var dynamic_service := get_tree().root.get_node_or_null(NodePath("NpcDialogueService"))
	if dynamic_service != null:
		dynamic_service.scenario_opened.connect(_on_dynamic_scenario_opened)
		dynamic_service.dialogue_pending.connect(_on_dynamic_dialogue_pending)
		dynamic_service.dialogue_ready.connect(_on_dynamic_dialogue_ready)
		dynamic_service.dialogue_failed.connect(_on_dynamic_dialogue_failed)
		dynamic_service.dialogue_closed.connect(_on_dynamic_dialogue_closed)
		dynamic_service.player_turn_displayed.connect(_on_player_turn_displayed)
		dynamic_service.player_turn_scored.connect(_on_player_turn_scored)
	var npc_voice := get_tree().root.get_node_or_null(NodePath("NpcVoice"))
	if npc_voice != null:
		npc_voice.line_audio_ready.connect(_on_npc_line_audio_ready)
		npc_voice.line_audio_finished.connect(_on_npc_line_audio_finished)
		npc_voice.line_audio_failed.connect(_on_npc_line_audio_failed)
	Vocabulary.word_spoken.connect(_show_word_unlock)
	Dialogue.word_practice_requested.connect(_on_word_practice_requested)
	Dialogue.word_practice_finished.connect(_on_word_practice_finished)

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
	if is_instance_valid(item_mode_button):
		pause_buttons.append(item_mode_button)
	if SpeechAdapter.is_available():
		pause_buttons.append(speech_mode_button)
	if is_instance_valid(cloud_button) and cloud_button.visible:
		pause_buttons.append(cloud_button)
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

func _build_cloud_ui() -> void:
	## FR-29:云评分构建在暂停菜单提供激活入口,并在 UIRoot 下创建激活浮层。
	## 所有节点程序化创建,不改动 HUD.tscn,便于 Web/桌面共用。
	if not SpeechAdapter.cloud_mode_enabled() or not is_instance_valid(controls_button):
		return
	cloud_button = Button.new()
	cloud_button.name = "CloudActivateButton"
	cloud_button.text = tr("CLOUD_MENU_ACTIVATED") if SpeechAdapter.cloud_activated() else tr("CLOUD_MENU_ACTIVATE")
	controls_button.get_parent().add_child(cloud_button)
	controls_button.get_parent().move_child(cloud_button, controls_button.get_index())
	cloud_button.pressed.connect(_open_cloud_activation)
	_build_cloud_overlay()
	SpeechAdapter.cloud_auth_finished.connect(_on_cloud_auth_finished)

func _build_cloud_overlay() -> void:
	cloud_overlay = ColorRect.new()
	cloud_overlay.name = "CloudActivationOverlay"
	cloud_overlay.color = Color(0.02, 0.03, 0.05, 0.94)
	cloud_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	cloud_overlay.visible = false
	ui_root.add_child(cloud_overlay)
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	cloud_overlay.add_child(center)
	var card := PanelContainer.new()
	card.custom_minimum_size = Vector2(520, 0)
	center.add_child(card)
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 12)
	card.add_child(content)
	var title := Label.new()
	title.text = tr("CLOUD_TITLE")
	title.add_theme_font_size_override("font_size", 26)
	content.add_child(title)
	var privacy := Label.new()
	privacy.text = tr("CLOUD_PRIVACY")
	privacy.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_child(privacy)
	cloud_code_edit = LineEdit.new()
	cloud_code_edit.placeholder_text = tr("CLOUD_CODE_HINT")
	cloud_code_edit.text_submitted.connect(func(_text: String): _submit_cloud_activation())
	content.add_child(cloud_code_edit)
	cloud_status_label = Label.new()
	cloud_status_label.text = tr("CLOUD_STATUS_ACTIVATED") if SpeechAdapter.cloud_activated() else tr("CLOUD_STATUS_PENDING")
	cloud_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	content.add_child(cloud_status_label)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	content.add_child(row)
	cloud_close_button = Button.new()
	cloud_close_button.text = tr("CLOUD_BACK")
	cloud_close_button.pressed.connect(_close_cloud_activation)
	row.add_child(cloud_close_button)
	cloud_activate_button = Button.new()
	cloud_activate_button.text = tr("CLOUD_ACTIVATE_BUTTON")
	cloud_activate_button.pressed.connect(_submit_cloud_activation)
	row.add_child(cloud_activate_button)

func _build_onboarding_ui() -> void:
	## FR-30: the guide is a non-modal, click-through band anchored above the
	## interaction card. It never pauses the world and never captures movement keys.
	if not is_instance_valid(ui_root):
		return
	onboarding_panel = PanelContainer.new()
	onboarding_panel.name = "OnboardingPanel"
	onboarding_panel.anchor_left = 0.5
	onboarding_panel.anchor_right = 0.5
	onboarding_panel.anchor_top = 1.0
	onboarding_panel.anchor_bottom = 1.0
	onboarding_panel.offset_left = -330.0
	onboarding_panel.offset_right = 330.0
	onboarding_panel.offset_top = -310.0
	onboarding_panel.offset_bottom = -184.0
	onboarding_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	onboarding_panel.visible = false
	ui_root.add_child(onboarding_panel)
	var content := VBoxContainer.new()
	content.name = "Content"
	content.add_theme_constant_override("separation", 6)
	onboarding_panel.add_child(content)
	var title := Label.new()
	title.name = "Title"
	title.text = tr("ONBOARDING_TITLE")
	title.add_theme_font_size_override("font_size", 22)
	content.add_child(title)
	onboarding_step_label = Label.new()
	onboarding_step_label.name = "Step"
	onboarding_step_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	onboarding_step_label.add_theme_font_size_override("font_size", 20)
	content.add_child(onboarding_step_label)
	onboarding_protected_label = Label.new()
	onboarding_protected_label.name = "Protected"
	onboarding_protected_label.text = tr("ONBOARDING_PROTECTED")
	onboarding_protected_label.add_theme_color_override("font_color", COLOR_NEUTRAL)
	onboarding_protected_label.add_theme_font_size_override("font_size", 17)
	content.add_child(onboarding_protected_label)
	onboarding_skip_button = Button.new()
	onboarding_skip_button.name = "SkipButton"
	onboarding_skip_button.text = tr("ONBOARDING_SKIP")
	onboarding_skip_button.pressed.connect(func(): GameState.skip_onboarding())
	content.add_child(onboarding_skip_button)
	_on_onboarding_changed(GameState.onboarding_step, GameState.onboarding_active)


func _on_onboarding_changed(_step: String, active: bool) -> void:
	if not is_instance_valid(onboarding_panel) or not is_instance_valid(onboarding_step_label):
		return
	if not active:
		onboarding_panel.visible = false
		return
	onboarding_step_label.text = tr("ONBOARDING_STEP_%s" % GameState.onboarding_step.to_upper())
	onboarding_panel.visible = true


func _build_word_unlock_ui() -> void:
	if not is_instance_valid(ui_root):
		return
	word_unlock_overlay = ColorRect.new()
	word_unlock_overlay.name = "WordUnlockOverlay"
	word_unlock_overlay.color = Color(0.02, 0.03, 0.05, 0.94)
	word_unlock_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	word_unlock_overlay.visible = false
	ui_root.add_child(word_unlock_overlay)
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	word_unlock_overlay.add_child(center)
	var card := PanelContainer.new()
	card.custom_minimum_size = Vector2(520, 0)
	center.add_child(card)
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	card.add_child(content)
	var title := Label.new()
	title.text = tr("WORD_UNLOCK_TITLE")
	title.add_theme_font_size_override("font_size", 26)
	content.add_child(title)
	word_unlock_label = Label.new()
	word_unlock_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	word_unlock_label.add_theme_font_size_override("font_size", 24)
	content.add_child(word_unlock_label)
	word_unlock_button = Button.new()
	word_unlock_button.text = tr("WORD_UNLOCK_CONTINUE")
	word_unlock_button.pressed.connect(_close_word_unlock)
	content.add_child(word_unlock_button)


func _build_speaker_subtitle_ui() -> void:
	## FR-45: bottom-centre card mirroring the player's own words. NPC lines
	## stay voice-only; nothing here takes input or blocks movement.
	if not is_instance_valid(ui_root):
		return
	speaker_subtitle_card = PanelContainer.new()
	speaker_subtitle_card.name = "SpeakerSubtitleCard"
	speaker_subtitle_card.mouse_filter = Control.MOUSE_FILTER_IGNORE
	speaker_subtitle_card.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	speaker_subtitle_card.grow_horizontal = Control.GROW_DIRECTION_BOTH
	speaker_subtitle_card.grow_vertical = Control.GROW_DIRECTION_BEGIN
	speaker_subtitle_card.offset_bottom = -96.0
	speaker_subtitle_card.custom_minimum_size = Vector2(420.0, 0.0)
	speaker_subtitle_card.visible = false
	speaker_subtitle_card.modulate.a = 0.0
	ui_root.add_child(speaker_subtitle_card)
	speaker_subtitle_label = RichTextLabel.new()
	speaker_subtitle_label.name = "SpeakerSubtitleLabel"
	speaker_subtitle_label.bbcode_enabled = true
	speaker_subtitle_label.fit_content = true
	speaker_subtitle_label.scroll_active = false
	speaker_subtitle_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	speaker_subtitle_label.add_theme_font_size_override("normal_font_size", 20)
	speaker_subtitle_card.add_child(speaker_subtitle_label)


func _on_player_turn_displayed(_npc_id: String, transcript: String) -> void:
	_show_speaker_subtitle(transcript, [])


func _on_player_turn_scored(_npc_id: String, transcript: String, errors: Array) -> void:
	if transcript.strip_edges().is_empty():
		return
	_show_speaker_subtitle(transcript, errors)


func _show_speaker_subtitle(transcript: String, error_spans: Array) -> void:
	if speaker_subtitle_card == null or speaker_subtitle_label == null:
		return
	if speaker_subtitle_timer != null:
		speaker_subtitle_timer.stop()
	var rendered := _render_speaker_subtitle(transcript, error_spans)
	if rendered.is_empty():
		return
	speaker_subtitle_label.text = rendered
	speaker_subtitle_card.visible = true
	if speaker_subtitle_card.modulate.a < 1.0:
		var tween := create_tween()
		tween.tween_property(speaker_subtitle_card, "modulate:a", 1.0, 0.12)


func _hide_speaker_subtitle() -> void:
	if speaker_subtitle_card == null:
		return
	speaker_subtitle_card.visible = false
	speaker_subtitle_card.modulate.a = 0.0


func _schedule_speaker_subtitle_hide(seconds := 3.0) -> void:
	## G-B6: the subtitle lingers three seconds after the session ends, then
	## dissolves; the next spoken turn replaces it outright.
	if speaker_subtitle_timer == null or speaker_subtitle_card == null:
		return
	if speaker_subtitle_card.visible:
		speaker_subtitle_timer.start(seconds)


func _render_speaker_subtitle(transcript: String, error_spans: Array) -> String:
	## The transcript is player speech, so brackets are neutralised rather than
	## trusted as bbcode. Each validated span marks its first occurrence only;
	## overlapping spans collapse so a word is never double-wrapped.
	var safe := transcript.replace("[", "‹").replace("]", "›").replace("\n", " ").strip_edges()
	if safe.is_empty():
		return ""
	var lower := safe.to_lower()
	var ranges: Array = []
	for span in error_spans:
		var clean := str(span).strip_edges()
		if clean.is_empty():
			continue
		var index := lower.find(clean.to_lower())
		if index < 0:
			continue
		var end := index + clean.length()
		var overlaps := false
		for range_item in ranges:
			if index < range_item[1] and range_item[0] < end:
				overlaps = true
				break
		if not overlaps:
			ranges.append([index, end])
	ranges.sort_custom(func(a, b) -> bool: return a[0] < b[0])
	var parts: PackedStringArray = PackedStringArray()
	var cursor := 0
	for range_item in ranges:
		parts.append(safe.substr(cursor, range_item[0] - cursor))
		parts.append("[color=%s][u]%s[/u][/color]" % [
			SPEAKER_MARK_COLOR_HEX,
			safe.substr(range_item[0], range_item[1] - range_item[0]),
		])
		cursor = range_item[1]
	parts.append(safe.substr(cursor))
	return "[center]%s[/center]" % "".join(parts)


func _on_word_score_finished(lexical_id: String, accepted: bool, expression: Dictionary, reason: String) -> void:
	if not accepted:
		if is_instance_valid(word_practice_prompt_label) and Dialogue.word_practice_active:
			word_practice_prompt_label.text = tr("WORD_PRACTICE_SPEAK_HINT")
		GameState.message_requested.emit(tr("WORD_PRACTICE_RETRY"), "neutral")
		return
	var score := 0.0
	if expression.has("score"):
		score = float(expression.get("score", 0.0))
	Vocabulary.record_word_spoken(lexical_id, score)
	if Dialogue.word_practice_active:
		Dialogue.finish_word_practice()


func _show_word_unlock(word: String, _score: float) -> void:
	if not is_instance_valid(word_unlock_overlay) or not is_instance_valid(word_unlock_label):
		return
	word_unlock_label.text = "%s  ·  %s" % [word, tr("WORD_UNLOCK_SPOKEN")]
	word_unlock_overlay.visible = true
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	word_unlock_button.grab_focus.call_deferred()


func _close_word_unlock() -> void:
	if not is_instance_valid(word_unlock_overlay):
		return
	word_unlock_overlay.visible = false
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_release_ui_focus()


func _build_word_practice_ui() -> void:
	if not is_instance_valid(ui_root):
		return
	word_practice_panel = PanelContainer.new()
	word_practice_panel.name = "WordPracticePanel"
	word_practice_panel.anchor_left = 0.5
	word_practice_panel.anchor_right = 0.5
	word_practice_panel.anchor_top = 1.0
	word_practice_panel.anchor_bottom = 1.0
	word_practice_panel.offset_left = -360.0
	word_practice_panel.offset_right = 360.0
	word_practice_panel.offset_top = -322.0
	word_practice_panel.offset_bottom = -198.0
	word_practice_panel.visible = false
	ui_root.add_child(word_practice_panel)
	var content := VBoxContainer.new()
	content.name = "Content"
	content.add_theme_constant_override("separation", 8)
	word_practice_panel.add_child(content)
	word_practice_prompt_label = Label.new()
	word_practice_prompt_label.name = "Prompt"
	word_practice_prompt_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	word_practice_prompt_label.add_theme_font_size_override("font_size", 20)
	content.add_child(word_practice_prompt_label)


func _on_word_practice_requested(npc_id: String, options: Array) -> void:
	var dynamic_service := get_tree().root.get_node_or_null(NodePath("NpcDialogueService"))
	if dynamic_service != null and dynamic_service.has_active_session():
		Dialogue.finish_word_practice()
		return
	if not is_instance_valid(word_practice_panel) or options.is_empty():
		return
	var words: Array[String] = []
	for option in options:
		words.append(str(option))
	var joined := ""
	if words.size() == 1:
		joined = words[0]
	elif words.size() == 2:
		joined = tr("WORD_PRACTICE_OR_TWO") % [words[0], words[1]]
	else:
		joined = tr("WORD_PRACTICE_OR_MANY") % [", ".join(words.slice(0, words.size() - 1)), words[words.size() - 1]]
	word_practice_prompt_label.text = tr("WORD_PRACTICE_NPC_ASK") % [tr("NPC_%s" % npc_id.to_upper()), joined]
	word_practice_panel.visible = true
	NpcVoice.request_line(npc_id, "word_practice_ask", "", "wav", words)


func _on_word_practice_finished(_npc_id: String) -> void:
	if not is_instance_valid(word_practice_panel):
		return
	word_practice_panel.visible = false


func _open_cloud_activation() -> void:
	if not is_instance_valid(cloud_overlay):
		return
	pause_overlay.visible = false
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	cloud_status_label.text = tr("CLOUD_STATUS_ACTIVATED") if SpeechAdapter.cloud_activated() else tr("CLOUD_STATUS_PENDING")
	cloud_code_edit.text = ""
	cloud_overlay.visible = true
	cloud_code_edit.grab_focus.call_deferred()

func _close_cloud_activation() -> void:
	if not is_instance_valid(cloud_overlay):
		return
	SpeechAdapter.cancel_activation()
	cloud_overlay.visible = false
	pause_overlay.visible = true
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	resume_button.grab_focus.call_deferred()

func _submit_cloud_activation() -> void:
	if not is_instance_valid(cloud_code_edit) or SpeechAdapter.pending_activation:
		return
	cloud_activate_button.disabled = true
	cloud_close_button.disabled = true
	cloud_status_label.text = tr("CLOUD_STATUS_WORKING")
	SpeechAdapter.activate_cloud(cloud_code_edit.text)

func _on_cloud_auth_finished(success: bool, message: String) -> void:
	if not is_instance_valid(cloud_status_label):
		return
	cloud_activate_button.disabled = false
	cloud_close_button.disabled = false
	cloud_status_label.text = message
	if success:
		cloud_button.text = tr("CLOUD_MENU_ACTIVATED")
		if SpeechAdapter.last_unavailable_reason == "VOICE_REASON_CLOUD_NOT_ACTIVATED":
			SpeechAdapter.last_unavailable_reason = ""

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
	if is_instance_valid(cloud_overlay) and cloud_overlay.visible:
		if event.is_action_pressed("ui_cancel") or event.is_action_pressed("pause"):
			_close_cloud_activation()
			get_viewport().set_input_as_handled()
		return
	if is_instance_valid(word_unlock_overlay) and word_unlock_overlay.visible:
		if event.is_action_pressed("ui_cancel") or event.is_action_pressed("pause"):
			_close_word_unlock()
			get_viewport().set_input_as_handled()
		return
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
	if event.is_action_pressed("ui_cancel"):
		var dynamic_service := get_tree().root.get_node_or_null(NodePath("NpcDialogueService"))
		if dynamic_service != null and dynamic_service.has_active_session():
			dynamic_service.cancel("VOICE_REASON_DIALOGUE_CANCELLED")
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
	objective_card.visible = true
	objective_card.modulate.a = 1.0
	objective_timer.start(3.5)
	if reduce_motion:
		return
	if objective_tween and objective_tween.is_valid():
		objective_tween.kill()
	objective_card.modulate.a = 0.5
	objective_tween = create_tween()
	objective_tween.tween_property(objective_card, "modulate:a", 1.0, 0.22).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)


func _collapse_objective() -> void:
	## FR-31 G2: after the change announcement the objective card folds away.
	## The player keeps the clock chip and explores from NPC greetings/world cues.
	if GameState.game_finished:
		return
	objective_timer.stop()
	if not objective_card.visible:
		return
	if reduce_motion:
		objective_card.visible = false
		return
	if objective_tween and objective_tween.is_valid():
		objective_tween.kill()
	objective_tween = create_tween()
	objective_tween.tween_property(objective_card, "modulate:a", 0.0, 0.16)
	objective_tween.tween_callback(func(): objective_card.visible = false)

func _update_needs(food: float, warmth: float, energy: float) -> void:
	_update_need(food_label, food_meter, food_icon, "FOOD", food)
	_update_need(warmth_label, warmth_meter, warmth_icon, "WARMTH", warmth)
	_update_need(energy_label, energy_meter, energy_icon, "ENERGY", energy)

func _update_need(label: Label, meter: NeedMeter, icon: NeedIcon, kind: String, value: float) -> void:
	var title := tr("NEED_" + kind)
	var state := tr("NEED_STABLE") if value > 50.0 else (tr("NEED_CAUTION") if value > 25.0 else tr("NEED_CRITICAL"))
	var tone := COLOR_GOOD if value > 50.0 else (COLOR_WARNING if value > 25.0 else COLOR_URGENT)
	label.text = tr("NEED_FORMAT") % [title, int(value), state]
	if value <= 50.0:
		label.text += " · " + tr("NEED_%s_ACTION" % kind)
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
		voice_expression = {}
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

func _on_recognition_finished(target_id: String, accepted: bool, transcript: String, reason: String, expression: Dictionary) -> void:
	if not SpeechAdapter.is_available():
		return
	if voice_target_name.is_empty():
		voice_target_name = player.current_target_name() if player else tr("NEARBY_RESIDENT")
	voice_transcript = transcript if _shows_speech_text() else ""
	voice_reason = tr(reason) if _shows_speech_text() else ""
	voice_expression = expression if _shows_speech_text() else {}
	if _awaits_npc_reply(target_id):
		_hold_processing(voice_target_name)
		return
	if accepted:
		voice_state = "accepted"
		_refresh_voice_card()
		_start_voice_status_timer(3.2)
	else:
		voice_state = "unavailable" if _is_unavailable_reason(reason) else "clarify"
		_refresh_voice_card()


func _on_dynamic_dialogue_pending(npc_id: String, _scenario_id: String) -> void:
	_hold_processing(tr("NPC_%s" % npc_id.to_upper()))


func _on_dynamic_scenario_opened(npc_id: String, _scenario_id: String, _text: String) -> void:
	voice_target_name = tr("NPC_%s" % npc_id.to_upper())
	voice_transcript = ""
	voice_reason = ""
	voice_state = "accepted"
	_stop_voice_status_timer()
	_refresh_voice_card()


func _on_dynamic_dialogue_ready(npc_id: String, _reply_id: String, _text: String) -> void:
	# Grok text is back; TTS may still be synthesizing. Keep the clock until audio starts.
	_hold_processing(tr("NPC_%s" % npc_id.to_upper()))


func _on_dynamic_dialogue_failed(npc_id: String, reason: String) -> void:
	voice_target_name = tr("NPC_%s" % npc_id.to_upper())
	voice_reason = tr(reason) if _shows_speech_text() else ""
	voice_state = "clarify"
	_stop_voice_status_timer()
	_refresh_voice_card()
	_schedule_speaker_subtitle_hide()


func _on_dynamic_dialogue_closed(_npc_id: String, reason: String) -> void:
	if reason in ["VOICE_REASON_DIALOGUE_CANCELLED", "completed"]:
		_clear_voice_status(true)
	_schedule_speaker_subtitle_hide()


func _on_npc_line_audio_ready(npc_id: String, _line_id: String) -> void:
	if voice_state != "transcribing":
		return
	var expected := tr("NPC_%s" % npc_id.to_upper())
	if not voice_target_name.is_empty() and voice_target_name != expected:
		return
	voice_target_name = expected
	voice_state = "accepted"
	_stop_voice_status_timer()
	_refresh_voice_card()


func _on_npc_line_audio_finished(npc_id: String, _line_id: String) -> void:
	var dynamic_service := get_tree().root.get_node_or_null(NodePath("NpcDialogueService"))
	if dynamic_service == null or not dynamic_service.is_session_active_for(npc_id):
		return
	voice_target_name = tr("NPC_%s" % npc_id.to_upper())
	voice_state = "accepted"
	_stop_voice_status_timer()
	_refresh_voice_card()


func _on_npc_line_audio_failed(npc_id: String, _line_id: String, reason: String) -> void:
	var dynamic_service := get_tree().root.get_node_or_null(NodePath("NpcDialogueService"))
	if dynamic_service != null and dynamic_service.has_active_session():
		_on_dynamic_dialogue_failed(npc_id, reason)


func _awaits_npc_reply(target_id: String) -> bool:
	var npc := target_id.strip_edges().to_lower()
	var dynamic_service := get_tree().root.get_node_or_null(NodePath("NpcDialogueService"))
	if dynamic_service == null or not dynamic_service.enabled():
		return false
	return dynamic_service.is_session_active_for(npc) or GameState.can_start_service_dialogue(npc)


func _hold_processing(npc_name: String) -> void:
	voice_target_name = npc_name
	voice_transcript = ""
	voice_reason = ""
	voice_state = "transcribing"
	_stop_voice_status_timer()
	_refresh_voice_card()


func _stop_voice_status_timer() -> void:
	if voice_status_timer != null:
		voice_status_timer.stop()


func _start_voice_status_timer(seconds: float) -> void:
	if voice_status_timer != null:
		voice_status_timer.start(seconds)

func _is_unavailable_reason(reason_key: String) -> bool:
	return reason_key in ["VOICE_REASON_MIC_UNAVAILABLE", "VOICE_REASON_SERVICE_UNAVAILABLE", "VOICE_REASON_SAVE_FAILED", "VOICE_REASON_READ_FAILED", "VOICE_REASON_RESULT_INVALID"]

func _on_speech_cancelled(_target_id: String) -> void:
	var dynamic_service := get_tree().root.get_node_or_null(NodePath("NpcDialogueService"))
	if voice_state == "transcribing" and dynamic_service != null and dynamic_service.has_active_session():
		return
	_clear_voice_status(true)

func _on_voice_status_timeout() -> void:
	if voice_state == "transcribing":
		return
	_clear_voice_status()

func _clear_voice_status(force := false) -> void:
	if not force and voice_state == "transcribing":
		return
	voice_state = "idle"
	voice_target_name = ""
	voice_transcript = ""
	voice_reason = ""
	voice_expression = {}
	_refresh_interaction_prompt()

func _shows_speech_text() -> bool:
	return not SpeechAdapter.is_available()


func _refresh_voice_card() -> void:
	voice_status_icon.set_state(voice_state)
	if not _shows_speech_text() and not voice_target_name.is_empty() and voice_state != "idle":
		_set_interaction_text(voice_target_name)
		return
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
			_set_interaction_text("%s%s%s" % [tr("VOICE_ACCEPTED") % voice_target_name, heard, _voice_score_line()])
		"clarify", "unavailable":
			var status := tr("VOICE_UNAVAILABLE") % voice_target_name if voice_state == "unavailable" else tr("VOICE_CLARIFY") % voice_target_name
			var heard := "\n%s" % (tr("VOICE_HEARD") % voice_transcript) if not voice_transcript.is_empty() else ""
			_set_interaction_text("%s%s%s\n%s\n%s" % [status, heard, _voice_score_line(), voice_reason, tr("VOICE_RECOVERY_ACTIONS") % [talk_glyph, gesture_glyph, cancel_glyph]])
		_:
			_refresh_interaction_prompt()

func _voice_score_line() -> String:
	if voice_expression.is_empty() or not voice_expression.has("score"):
		return ""
	var score := int(voice_expression.get("score", 0))
	var pronunciation := int(voice_expression.get("pronunciation", 0))
	var delivery := int(voice_expression.get("delivery", 0))
	return "\n%s" % (tr("VOICE_SCORED") % [score, pronunciation, delivery])

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
	if is_instance_valid(cloud_overlay):
		cloud_overlay.visible = false
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
	if is_instance_valid(cloud_overlay):
		cloud_overlay.visible = false
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
	if is_instance_valid(item_panel):
		item_panel.call_deferred("_layout")

func _toggle_item_mode() -> void:
	item_panel.set_toggle_mode(not item_panel.toggle_mode)
	_update_item_mode_label()

func _update_item_mode_label() -> void:
	item_mode_button.text = GameState._item_text("物品条：", "Items: ") + (GameState._item_text("切换", "Toggle") if item_panel.toggle_mode else GameState._item_text("按住", "Hold"))

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
