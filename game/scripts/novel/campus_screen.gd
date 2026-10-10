extends Control
const Controller := preload("res://scripts/novel/campus_controller.gd")
const Palette := preload("res://scripts/novel/novel_palette.gd")
const Visual := preload("res://scripts/novel/campus_visual.gd")
const Inventory := preload("res://scripts/novel/novel_inventory.gd")
const Glyphs := preload("res://scripts/input_glyphs.gd")
@export var boot_from_save := true
var model: Node
var root: Control
var canvas: Control
var scene_title: Label
var situation: RichTextLabel
var transcript: RichTextLabel
var status: Label
var week_label: Label
var speaker_label: Label
var input: LineEdit
var record_button: Button
var send_button: Button
var action_row: HFlowContainer
var visual: Control
var meters: Array = []
var meter_labels: Array = []
var navigation: Array = []
var modal: Window
var modal_body: VBoxContainer
var profiles: Dictionary = {}
var review_text := ""
var transcript_entries: Array = []
var turn_replies: Array[String] = []
var last_scene := ""
var inventory_view: Node
var scene_picker: Button
var retry_button: Button
var connection_label: Label
var status_paper: Panel
var relation_label: Label
var large_text := false
var instant_text := false
var reduce_motion := false
var text_elapsed := 0.0
var reveal_button: Button
var previous_focus: Control
var scene_only_controls: Array[Control] = []
## P3-10: the dialogue paper shows the campus note until a line is spoken.
var showing_note := false
var example_note: Label
var example_line := ""
const SETTINGS := "user://stranger_novel_settings.cfg"

func _ready() -> void:
	# T1-03: same Chinese UI locale as the town, whatever the OS language.
	TranslationServer.set_locale(Palette.UI_LOCALE)
	_load_settings()
	set_large_text(large_text)
	var styles = preload("res://scripts/novel/novel_screen.gd").new()
	styles._build_theme()
	theme = styles.theme
	styles.free()
	var bg := ColorRect.new()
	bg.color = Palette.SURFACE
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg)
	model = Controller.new()
	model.boot_from_save = boot_from_save
	add_child(model)
	model.scene_changed.connect(_show_scene)
	model.progression_changed.connect(_refresh)
	model.line_changed.connect(_line)
	model.feedback.connect(_set_status)
	_build()
	resized.connect(_layout)
	_layout()
	model.start(false)
	_refresh()
	SpeechAdapter.recording_state_changed.connect(func(_active): _refresh())
	NpcVoice.line_audio_ready.connect(_example_audio)
	NpcVoice.line_audio_failed.connect(func(npc, line, _reason): _example_audio(npc, line, true))
	if boot_from_save and not FileAccess.file_exists(model.novel_save_path): _profile()
	if not model.save_valid: _set_status("存档读取失败，已保护原文件并停止自动保存。")
	navigation[0].grab_focus()

func _label(parent: Node, text: String, font_size := 18) -> Label:
	var node := Label.new()
	node.text = Palette.plain_quotes(text)
	node.set_meta("text_px", font_size)
	node.add_theme_font_size_override("font_size", Palette.text_px(font_size))
	node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	node.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(node)
	return node

func _button(parent: Node, text: String, action: Callable) -> Button:
	var node := Button.new()
	node.text = text
	node.custom_minimum_size.y = 40
	node.pressed.connect(func():
		if not node.is_inside_tree() or not node.is_visible_in_tree() or node.disabled: return
		if modal != null and modal.visible and not modal.is_ancestor_of(node): return
		action.call())
	parent.add_child(node)
	return node

func _rich(parent: Node, height := 0.0) -> RichTextLabel:
	var node := RichTextLabel.new()
	node.custom_minimum_size.y = height
	node.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	node.bbcode_enabled = false
	node.selection_enabled = true
	node.focus_mode = Control.FOCUS_NONE # P2-02: selectable, but never a hidden Tab stop.
	node.fit_content = height == 0
	parent.add_child(node)
	return node

func _scroll(parent: Node) -> VBoxContainer:
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.follow_focus = true
	parent.add_child(scroll)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(column)
	return column

func _clear(parent: Node) -> void:
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()

func _position(node: Control, rect: Rect2) -> void:
	node.position = rect.position
	node.size = rect.size

func _paper(rect: Rect2, opacity := 0.98) -> Panel:
	var panel := Panel.new()
	_position(panel, rect)
	var surface := Palette.style(Color(Palette.SURFACE, opacity))
	surface.shadow_color = Color(Palette.SHADOW, 0.12)
	surface.shadow_size = 16
	surface.shadow_offset = Vector2(0, 5)
	panel.add_theme_stylebox_override("panel", surface)
	canvas.add_child(panel)
	return panel

func _build() -> void:
	root = Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(root)
	canvas = Control.new()
	canvas.size = Vector2(1440, 900)
	root.add_child(canvas)
	visual = Visual.new()
	_position(visual, Rect2(0, 88, 1440, 812))
	canvas.add_child(visual)
	_paper(Rect2(0, 0, 1440, 88), 1.0)
	var brand := _label(canvas, "STRANGER", 29)
	brand.add_theme_font_override("font", Palette.font(true, 500))
	brand.add_theme_color_override("font_color", Palette.ACCENT)
	_position(brand, Rect2(30, 9, 260, 40))
	var subtitle := _label(canvas, "校园篇章  /  一点点，找到自己的位置", 18)
	subtitle.autowrap_mode = TextServer.AUTOWRAP_OFF
	_position(subtitle, Rect2(32, 50, 330, 25))
	week_label = _label(canvas, "", 18)
	_position(week_label, Rect2(367, 22, 270, 44))
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 8)
	_position(top, Rect2(660, 22, 746, 44))
	canvas.add_child(top)
	for item in [["今日安排", _plan], ["生活档案", _profile], ["记忆", _memories], ["每周回顾", _reviews], ["设置", _settings], ["返回小镇", _town]]:
		Palette.quiet(_button(top, item[0], item[1]))
	_paper(Rect2(24, 112, 244, 757))
	var where := _label(canvas, "去哪里？", 25)
	where.add_theme_font_override("font", Palette.font(true, 500))
	_position(where, Rect2(46, 126, 190, 38))
	var caption := _label(canvas, "从一件日常小事开始。", 18)
	_position(caption, Rect2(46, 163, 212, 32))
	var i := 0
	for place in Controller.PLACES:
		var button := _button(canvas, "%02d  %s" % [i + 1, Controller.PLACES[place]], func(): model.travel(place))
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.set_meta("place", place)
		_position(button, Rect2(40, 211 + i * 52, 212, 44))
		navigation.append(button)
		i += 1
	var needs_title := _label(canvas, "今日状态", 18)
	needs_title.add_theme_color_override("font_color", Palette.ACCENT)
	_position(needs_title, Rect2(46, 527, 190, 28))
	var colors := [Palette.NEED_FOOD, Palette.NEED_WARMTH, Palette.NEED_ENERGY, Palette.DRINK, Palette.HOME]
	for index in range(5):
		var label := _label(canvas, "", 18)
		_position(label, Rect2(46, 559 + index * 47, 190, 28))
		meter_labels.append(label)
		var meter := ProgressBar.new()
		meter.show_percentage = false
		meter.add_theme_stylebox_override("background", Palette.style(Palette.SURFACE_INSET, Color.TRANSPARENT, 0, 3))
		meter.add_theme_stylebox_override("fill", Palette.style(colors[index], Color.TRANSPARENT, 0, 3))
		_position(meter, Rect2(46, 591 + index * 47, 190, 6))
		canvas.add_child(meter)
		meters.append(meter)
	var study_note := _label(canvas, "学业按学习活动完成度累计", 18)
	_position(study_note, Rect2(46, 800, 220, 60))
	# Shared town paper treatment keeps context readable over detailed paintings.
	_paper(Rect2(292, 112, 445, 322), 0.95)
	scene_title = _label(canvas, "", 27)
	scene_title.add_theme_font_override("font", Palette.font(true, 500))
	scene_title.add_theme_color_override("font_color", Palette.ACCENT)
	_position(scene_title, Rect2(312, 128, 405, 72))
	scene_picker = _button(canvas, "选择今天的情景", _scenarios)
	_position(scene_picker, Rect2(1176, 120, 226, 44))
	situation = _rich(canvas, 74)
	situation.set_meta("text_px", 18)
	situation.add_theme_font_size_override("normal_font_size", Palette.text_px(18))
	situation.add_theme_color_override("default_color", Palette.TEXT)
	_position(situation, Rect2(314, 204, 401, 116))
	relation_label = _label(canvas, "", 18)
	relation_label.add_theme_color_override("font_color", Palette.MUTED)
	_position(relation_label, Rect2(314, 328, 401, 90))
	var scene_tools := HBoxContainer.new()
	_position(scene_tools, Rect2(302, 460, 720, 44))
	canvas.add_child(scene_tools)
	for item in [["行囊", func(): _inventory("bag")], ["餐饮柜台", func(): model.open_counter()], ["领取物品", func(): model.open_counter(); _inventory("counter")], ["住处物品", func(): model.travel("home"); _inventory("home")]]:
		_button(scene_tools, item[0], item[1])
	_paper(Rect2(292, 508, 1124, 48), 0.96)
	action_row = HFlowContainer.new()
	_position(action_row, Rect2(302, 510, 1100, 44))
	canvas.add_child(action_row)
	_paper(Rect2(292, 572, 1124, 296))
	speaker_label = _label(canvas, "校园手记", 22)
	speaker_label.add_theme_font_override("font", Palette.font(true, 500))
	speaker_label.add_theme_color_override("font_color", Palette.ACCENT)
	_position(speaker_label, Rect2(320, 588, 680, 34))
	# Connection state sits beside the speaker, leaving the status line full width.
	connection_label = _label(canvas, "", 18)
	connection_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_position(connection_label, Rect2(1010, 592, 256, 28))
	reveal_button = _button(canvas, "显示全文", func(): text_elapsed = 9999; transcript.visible_characters = -1; record_button.grab_focus())
	Palette.quiet(reveal_button)
	_position(reveal_button, Rect2(1278, 586, 112, 36))
	transcript = _rich(canvas, 104)
	transcript.add_theme_font_override("normal_font", Palette.font(true))
	transcript.set_meta("text_px", 26)
	transcript.add_theme_font_size_override("normal_font_size", Palette.text_px(26))
	_position(transcript, Rect2(320, 636, 1072, 102))
	var helpers := HBoxContainer.new()
	helpers.add_theme_constant_override("separation", 4)
	_position(helpers, Rect2(308, 740, 1086, 40))
	canvas.add_child(helpers)
	for item in [["开口灵感", _hints], ["重听", func(): model.listen_again()], ["回看", _history], ["表达回顾", _coaching], ["单词练习", _words], ["创作示范", _example]]:
		var helper := _button(helpers, item[0], item[1])
		Palette.quiet(helper)
		if item[0] in ["开口灵感", "重听", "创作示范"]: scene_only_controls.append(helper)
	retry_button = _button(helpers, "免费重试", func(): model.retry_last())
	Palette.quiet(retry_button)
	var mute := CheckButton.new()
	mute.text = "仅文字"
	mute.toggled.connect(func(value): model.muted = value; _refresh())
	helpers.add_child(mute)
	var compose := HBoxContainer.new()
	compose.add_theme_constant_override("separation", 12)
	_position(compose, Rect2(320, 792, 1072, 44))
	canvas.add_child(compose)
	input = LineEdit.new()
	input.placeholder_text = "输入英语，或用右侧按钮录音…"
	input.max_length = 1000
	input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input.text_submitted.connect(func(_text): _send())
	compose.add_child(input)
	send_button = _button(compose, "发送", _send)
	record_button = _button(compose, "录音 · V", func(): model.record())
	Palette.primary(record_button)
	status_paper = _paper(Rect2(292, 868, 1124, 32), 0.96)
	status = _label(canvas, "", 18)
	_position(status, Rect2(304, 869, 1100, 30))
	_set_status("阅读、录音和重试不消耗游戏时间。")
	modal = Window.new()
	modal.visible = false
	modal.title = "校园生活"
	modal.transient = true
	modal.exclusive = true
	modal.min_size = Vector2i(640, 400)
	modal.close_requested.connect(_close_modal)
	modal.window_input.connect(func(event):
		if event.is_action_pressed("ui_cancel"): _close_modal(); modal.set_input_as_handled())
	add_child(modal)
	var popup_background := ColorRect.new()
	popup_background.color = Palette.SURFACE
	popup_background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	popup_background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	modal.add_child(popup_background)
	var popup_margin := MarginContainer.new()
	popup_margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for edge in ["left", "right", "top", "bottom"]: popup_margin.add_theme_constant_override("margin_" + edge, 24)
	modal.add_child(popup_margin)
	var popup_column := VBoxContainer.new()
	popup_column.add_theme_constant_override("separation", 16)
	popup_margin.add_child(popup_column)
	var modal_close := _button(popup_column, "返回现场  ·  Esc", _close_modal)
	Palette.quiet(modal_close)
	modal_body = _scroll(popup_column)

func _layout() -> void:
	if canvas == null: return
	var ratio := minf(size.x / 1440.0, size.y / 900.0)
	canvas.scale = Vector2.ONE * ratio
	canvas.position = (size - canvas.size * ratio) * 0.5

func _process(delta: float) -> void:
	if transcript == null: return
	text_elapsed += delta
	transcript.visible_characters = -1 if instant_text or reduce_motion else int(text_elapsed * 44.0)
	reveal_button.visible = not instant_text and not reduce_motion and transcript.visible_characters < transcript.get_total_character_count()

func _close_modal() -> void:
	modal.hide()
	model._offer_opening.call_deferred()
	if is_instance_valid(previous_focus) and previous_focus.is_visible_in_tree(): previous_focus.grab_focus()
	else: record_button.grab_focus()

func _scenarios() -> void:
	if model.location == "home": return
	_open("今天，从哪件事开始？")
	var domain: String = "class" if model.location == "study" else model.location
	_label(modal_body, "选择情景 · " + str(Controller.PLACES[model.location]), 26)
	_label(modal_body, "每段交流都可以澄清、换话题或提前离开。选择情景不消耗时间。", 18)
	for card in model.campus.ranked_scenes(domain if domain != "home" else ""):
		var name: String = str(card.title) + (" · 已体验" if card.id in model.campus.week_scenes else "")
		var button := _button(modal_body, name, func(): model.select_scene(str(card.id)); _close_modal())
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		Palette.navigation(button, card.id == model.scene_id)
		if not str(card.get("personal_detail", "")).is_empty(): _label(modal_body, str(card.personal_detail), 18)

func _history() -> void:
	_open("交流记录 · 按发言顺序回看")
	var entries: Array = model.campus.dialogue_log
	if entries.is_empty(): entries = model.exchange
	if entries.is_empty(): _label(modal_body, "还没有完成的交流。可以先看开口灵感，也可以直接表达。")
	var previous_session := ""
	for entry in entries:
		if str(entry.get("session_id", "")) != previous_session:
			previous_session = str(entry.get("session_id", ""))
			_label(modal_body, "第 %d 天 · %s" % [int(entry.get("day", GameState.day)), str(model.campus.scenario(str(entry.get("scenario_id", model.scene_id))).get("title", "校园交流"))], 23)
		var speaker: String = "你" if entry.speaker_id == "player" else str(model.campus.catalog.profiles[entry.speaker_id].name)
		var target: String = str(entry.get("reply_to", "group"))
		var addressed: String = "大家" if target == "group" else ("你" if target == "player" else str(model.campus.catalog.profiles.get(target, {}).get("name", target)))
		_label(modal_body, speaker + " → " + addressed, 18)
		_label(modal_body, str(entry.text), 22)
	_button(modal_body, "开始新的一段交流", func(): model.cancel_activity(); model.new_session(); model.save(); _show_scene(); _close_modal())

func _plan() -> void:
	_open("今日安排")
	_label(modal_body, "学习、生活，也留一点时间给彼此。", 26)
	_label(modal_body, "每周课堂和自主学习各五次；当天每类计分一次，周末也可以补足。", 18)
	for kind in ["class", "study"]:
		var done: bool = model.campus.study_done.has("%d:%s" % [GameState.day, kind])
		var name := "课堂活动" if kind == "class" else "自主学习"
		_button(modal_body, name + (" · 今日已完成" if done else " · 安排 1 小时"), func(): model.travel("class" if kind == "class" else "study"); _close_modal())
	_button(modal_body, "找人参加共同活动", func(): model.travel("club"); _close_modal())
	_button(modal_body, "去餐饮区补充食物", func(): model.open_counter(); _close_modal())
	_button(modal_body, "回住处休息", func(): model.travel("home"); _close_modal())
	_label(modal_body, "今天已经做过的事", 23)
	for entry in model.campus.schedule:
		if int(entry.day) == GameState.day: _label(modal_body, "%02d:%02d  %s" % [roundi(entry.hour * 60) / 60, roundi(entry.hour * 60) % 60, entry.detail], 18)

func _settings() -> void:
	_open("阅读与声音")
	_label(modal_body, "与小镇共用阅读偏好", 26)
	_button(modal_body, "文字字号：" + ("大" if large_text else "标准"), func(): set_large_text(not large_text); _save_settings(); _settings())
	_button(modal_body, "文字即时显示：" + ("开" if instant_text else "关"), func(): instant_text = not instant_text; _save_settings(); _settings())
	_button(modal_body, "减少动态：" + ("开" if reduce_motion else "关"), func(): reduce_motion = not reduce_motion; _save_settings(); _settings())
	_button(modal_body, "重新检查语音连接", func(): model._check_local_service(); _close_modal())
	_button(modal_body, "保存校园进度", func(): _set_status("校园进度已保存。" if model.save() else "保存未完成，请检查存档。"))
	_label(modal_body, "Tab / 方向键选择，确认键执行；录音沿用小镇的按键绑定。输入文字时不会触发录音快捷键。云端激活与按键重映射在小镇设置中管理。", 18)

## P2-06: same shared text-size setting as the town; it resizes every reading
## surface on the canvas, and modal pages rebuild with it.
func set_large_text(value: bool) -> void:
	large_text = value
	Palette.text_scale = Palette.LARGE_TEXT_SCALE if large_text else 1.0
	if theme != null: theme.default_font_size = Palette.text_px(18)
	if canvas == null: return
	for node in canvas.find_children("*", "Control", true, false):
		if node.has_meta("text_px"):
			node.add_theme_font_size_override("normal_font_size" if node is RichTextLabel else "font_size", Palette.text_px(int(node.get_meta("text_px"))))
	if status != null: _set_status(status.text)

## P2-06: at the larger sizes a long notice takes a second line, growing upward
## over the empty foot of the dialogue paper instead of running off the window.
func _set_status(text: String) -> void:
	status.text = Palette.plain_quotes(text)
	status.size.y = 0.0
	status.position.y = 899.0 - status.get_combined_minimum_size().y
	status_paper.position.y = status.position.y - 2.0
	status_paper.size.y = 900.0 - status_paper.position.y

func _load_settings() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS) == OK:
		large_text = bool(config.get_value("view", "large_text", false))
		instant_text = bool(config.get_value("view", "instant_text", false))
		reduce_motion = bool(config.get_value("view", "reduce_motion", false))

func _save_settings() -> void:
	var config := ConfigFile.new()
	config.load(SETTINGS)
	config.set_value("view", "large_text", large_text)
	config.set_value("view", "instant_text", instant_text)
	config.set_value("view", "reduce_motion", reduce_motion)
	config.save(SETTINGS)

func _show_scene() -> void:
	if scene_title == null: return
	_clear(action_row)
	var scene: Dictionary = model.scene()
	if last_scene != model.session:
		_set_status("这里可以学习、整理物品，或好好休息。" if model.location == "home" else "阅读、录音和重试不消耗游戏时间。")
		transcript_entries.clear()
		turn_replies.clear()
		transcript.text = _note_text()
		speaker_label.text = "校园手记"
		showing_note = model.exchange.is_empty()
		if not model.exchange.is_empty():
			var last: Dictionary = model.exchange[-1]
			transcript.text = Palette.plain_quotes(str(last.text))
			speaker_label.text = "你" if last.speaker_id == "player" else str(model.campus.catalog.profiles[last.speaker_id].name)
		text_elapsed = 9999
		last_scene = model.session
	scene_title.text = "校园餐饮柜台" if model.service_mode else str(scene.title)
	situation.text = "先确认想要的食物。准备好后，可以在柜台直接吃，或放进行囊带走。" if model.service_mode else str(scene.trigger) + "\n" + str(scene.player_goal)
	if model.service_mode and SpeechAdapter.runtime_speech_unavailable():
		# P3-10: the counter's card says what works offline, like the town's.
		situation.text = "语音点单暂时不可用，也能继续生活。点「手势领取」获得最低份量，再在柜台直接吃，或放进行囊带走。"
	if not str(scene.get("personal_detail", "")).is_empty(): situation.text += "\n" + str(scene.personal_detail)
	situation.text = Palette.plain_quotes(situation.text)
	visual.place = model.location
	visual.people = ["tavi"] if model.service_mode else scene.participants
	if model.location == "home":
		visual.people = []
		scene_title.text = "我的住处"
		situation.text = "放下行囊，给自己一点安静的时间。\n学习、整理，或让今天在好好休息后结束。"
		if not model.faint_note.is_empty():
			# P3-18: the faint stays readable at home until the next explicit action.
			situation.text = str(model.faint_note.title) + "\n" + str(model.faint_note.detail)
	visual.active = ""
	visual.queue_redraw()
	var names := PackedStringArray()
	for id in visual.people:
		var person: Dictionary = model.campus.catalog.profiles[id]
		var familiarity: String = {"stranger": "还未认识", "acquaintance": "初识", "familiar": "熟悉"}[model.campus.relationship_for(id)]
		var availability: Array = person.get("availability", [8, 22])
		var busy_now: bool = GameState.clock_hours() < float(availability[0]) or GameState.clock_hours() >= float(availability[1])
		names.append(str(person.name) + " · " + str(person.role) + " / " + familiarity + (" · 此刻时间有限" if busy_now else ""))
	relation_label.text = "\n".join(names)
	if model.location == "class": _button(action_row, "完成今天的课堂 · 1 小时", func(): model.study("class"))
	if model.location in ["study", "home"]: _button(action_row, "完成自主学习 · 1 小时", func(): model.study("study"))
	if not model.practice_word.is_empty():
		_clear(action_row)
		_button(action_row, "结束单词练习", func(): model.cancel_activity(); _show_scene())
	elif model.location == "home":
		_button(action_row, "休息到晚上", func(): model.wait_until_evening())
		_button(action_row, "睡觉，开始新一天", func(): model.sleep())
	elif model.service_mode:
		_button(action_row, "手势领取（语音不可用时）", func(): model.greet())
	else:
		_button(action_row, "完成共同活动 · 1 小时", func(): model.joint_activity(false))
		_button(action_row, "离线参加活动 · 不评口语", _offline_activity)
	for child in action_row.get_children():
		if child is Button: Palette.quiet(child)
	_refresh()

func _refresh() -> void:
	if meters.is_empty(): return
	visual.evening = GameState.clock_hours() >= 19.0
	visual.queue_redraw()
	var minutes: int = model.clock_minutes()
	week_label.text = "第 %d 周 · 第 %d 天 · %02d:%02d" % [model.campus.week, GameState.day, minutes / 60, minutes % 60]
	var values := [GameState.food, GameState.warmth, GameState.energy, model.campus.social, model.campus.academic]
	var names := ["饮食", "温暖", "精力", "社交需求", "学业成绩"]
	for i in range(5):
		meters[i].value = values[i]
		meter_labels[i].text = "%s    %d / 100" % [names[i], roundi(values[i])]
	meters[3].tooltip_text = "每游戏小时 -2；低于 25 时精力额外 -4/小时。"
	meters[4].tooltip_text = "本周学习完成度；五次课堂与五次自主学习，每次 +10。"
	for button in navigation: Palette.navigation(button, button.get_meta("place") == model.location)
	var busy: bool = not model.conversation_block_reason().is_empty()
	var at_home: bool = model.location == "home"
	scene_picker.visible = not at_home
	for control in scene_only_controls: control.visible = not at_home
	input.editable = not at_home and not model.service_mode
	input.placeholder_text = "住处可以休息、整理或练习单词。" if at_home else ("点录音向店员下单；物品到柜台后再领取。" if model.service_mode else "输入英语，或用右侧按钮录音…")
	send_button.disabled = busy or model.service_mode or at_home
	record_button.disabled = (busy and not SpeechAdapter.is_recording()) or (at_home and model.practice_word.is_empty())
	record_button.text = ("结束录音 · " if SpeechAdapter.is_recording() else "录音 · ") + Glyphs.for_action("push_to_talk", false)
	retry_button.visible = not model.retry_text.is_empty() and not busy
	connection_label.text = "正在录音" if SpeechAdapter.is_recording() else ("正在回应…" if busy else model.connection_text())
	if at_home and model.practice_word.is_empty(): connection_label.text = "住处 · 休息与整理"
	# P3-10: a /health result or failed turn that lands later updates the note in place.
	if showing_note and transcript.text != _note_text(): transcript.text = _note_text()

## P3-10: the offline note persists like the town's card; otherwise the usual invitation.
func _note_text() -> String:
	var note: String = model.offline_note()
	return note if not note.is_empty() else "想说的话，可以从这里开始。先听听自己的想法，不必急着找到完美的句子。"

func _line(id: String, text: String) -> void:
	if transcript == null: return
	text = Palette.plain_quotes(text)
	showing_note = false
	var name: String = "你" if id == "you" else ("校园手记" if id.is_empty() else str(model.campus.catalog.profiles.get(id, {}).get("name", id)))
	transcript_entries.append(name + "\n" + text)
	if transcript_entries.size() > 60: transcript_entries.pop_front()
	if id == "you": turn_replies.clear()
	var retain_replies: bool = id != "you" and not model.service_mode and (model.muted or not NpcVoice.is_available())
	if retain_replies:
		turn_replies.append(name + "\n" + text)
	transcript.text = "\n\n".join(turn_replies) if retain_replies else text
	transcript.scroll_to_line(0)
	# Text-only streams can deliver both speakers within one frame. Keep the
	# complete exchange readable rather than replacing an unfinished typewriter.
	text_elapsed = 9999 if retain_replies else 0
	speaker_label.text = "本轮回复 · 滚动查看" if retain_replies and turn_replies.size() > 1 else name
	var target: String = str(model.conversation.playing.get("reply_to", ""))
	if not target.is_empty() and id != "you" and not (retain_replies and turn_replies.size() > 1):
		speaker_label.text += "  →  " + ("你" if target == "player" else str(model.campus.catalog.profiles.get(target, {}).get("name", "大家")))
	visual.active = id
	visual.queue_redraw()

func _send() -> void:
	if input.text.strip_edges().is_empty() or send_button.disabled: return
	model.submit_text(input.text)
	input.clear()

func _hints() -> void:
	var hints: Dictionary = model.scene().hints
	_open("开口灵感 · 想用时再展开")
	for pair in [["开场", "open"], ["接话", "follow_up"], ["深入一点", "deepen"]]:
		_label(modal_body, pair[0], 23)
		_label(modal_body, str(hints[pair[1]]), 22)
	_label(modal_body, "这些是创作的表达示例。可以改成自己的话，也可以直接说不、澄清或离开。", 18)

func _open(title: String) -> void:
	if not modal.visible: previous_focus = get_viewport().gui_get_focus_owner()
	model.cancel_activity()
	_clear(modal_body)
	modal.title = title
	modal.popup_centered(Vector2i(mini(1160, int(get_viewport_rect().size.x) - 48), mini(700, int(get_viewport_rect().size.y) - 48)))

func _profile() -> void:
	_open("生活档案 · 所有项目均可跳过")
	profiles.clear()
	_label(modal_body, "以你的校园生活为背景", 26)
	_label(modal_body, "未填写的信息保持未知。实际交流仅发送相关背景；完整经历留在本机。", 18)
	var fields := {"major": "专业", "year": "年级", "housing": "住宿方式", "courses": "课程兴趣", "interests": "日常兴趣", "clubs": "社团", "sports": "运动"}
	for key in fields:
		_label(modal_body, fields[key], 18)
		var edit := LineEdit.new()
		edit.text = str(model.campus.profile.get(key, ""))
		edit.max_length = 240
		edit.placeholder_text = "可留空"
		modal_body.add_child(edit)
		profiles[key] = edit
	_label(modal_body, "英语难度", 18)
	var level := OptionButton.new()
	for item in ["A1 · 简短表达", "A1–A2 · 日常表达", "B1 · 进阶交流", "自由表达"]: level.add_item(item)
	level.select(["infant", "toddler", "youth", "professional"].find(model.campus.profile.level))
	modal_body.add_child(level)
	_label(modal_body, "今天遇到的事 · 仅本机保存", 18)
	var experiences := TextEdit.new()
	experiences.custom_minimum_size.y = 130
	experiences.text = str(model.campus.profile.get("experiences", ""))
	experiences.placeholder_text = "当时在哪里、和谁聊、哪一步卡住了？"
	modal_body.add_child(experiences)
	_label(modal_body, "用于本次练习的情景摘要 · 会随对话发送，最多 400 字符", 18)
	var brief := TextEdit.new()
	brief.custom_minimum_size.y = 85
	brief.text = model.practice_context
	brief.placeholder_text = "例如：小组已经聊起来了，我想加入，但不知道怎样接话。不要填写身份信息。"
	modal_body.add_child(brief)
	_label(modal_body, "练习卡标题（可留空）", 18)
	var practice_title := LineEdit.new()
	practice_title.max_length = 80
	modal_body.add_child(practice_title)
	_label(modal_body, "这次想练会什么（可留空）", 18)
	var practice_goal := LineEdit.new()
	practice_goal.max_length = 240
	modal_body.add_child(practice_goal)
	var actions := HFlowContainer.new()
	modal_body.add_child(actions)
	var apply := func():
		var data := {}
		for key in profiles: data[key] = profiles[key].text
		data.level = ["infant", "toddler", "youth", "professional"][level.selected]
		data.experiences = experiences.text
		model.update_profile(data)
	_button(actions, "保存档案", func(): apply.call(); modal.hide())
	for domain in ["class", "club", "dining", "sports"]:
		_button(actions, "建立" + str(Controller.PLACES[domain]) + "练习卡", func():
			apply.call()
			if model.create_practice(brief.text, domain, practice_title.text, practice_goal.text): _close_modal())
	# P3-22: skipping counts as having seen the profile; the next launch goes straight in.
	_button(actions, "暂时跳过", func(): model.save(); _close_modal())

func _memories(notice := "") -> void:
	_open("人物记忆 · 可以更正或删除")
	if not notice.is_empty(): _label(modal_body, notice, 18).add_theme_color_override("font_color", Palette.POSITIVE)
	if model.campus.memories.is_empty(): _label(modal_body, "还没有共同记忆。交流时分享一件具体的事，对方会记住你的原话。")
	for memory in model.campus.memories:
		var owner: String = str(memory.get("speaker_id", "player"))
		var author: String = "你" if owner == "player" else str(model.campus.catalog.profiles.get(owner, {}).get("name", owner))
		var known := PackedStringArray()
		for id in memory.known_to: known.append(str(model.campus.catalog.profiles[id].name))
		var kind: String = {"shared_fact": "分享的事实", "preference": "偏好", "proposal": "尚待确认的提议", "agreement": "约定", "open_topic": "未完成的话题"}.get(str(memory.get("kind", "shared_fact")), "共同经历")
		_label(modal_body, "第 %d 天 · %s的原话 · %s\n知情者：%s" % [memory.day, author, kind, ", ".join(known)], 18)
		var edit := TextEdit.new()
		edit.custom_minimum_size.y = 90
		edit.text = memory.text
		modal_body.add_child(edit)
		var row := HBoxContainer.new()
		modal_body.add_child(row)
		_button(row, "更正", func(): model.change_memory(str(memory.id), edit.text); _memories("已更正。之后的交谈只会用到新的说法；当前的交流和进度保留。"))
		_button(row, "删除", func(): model.change_memory(str(memory.id), "", true); _memories("已删除。这句话不会再进入之后的交谈；当前的交流和进度保留。"))

## P3-16: this week, then the archived weeks (newest first), then the continuing
## experiences; people and scenes by name, never raw ids or JSON.
func _reviews() -> void:
	_open("每周回顾与连续经历")
	var campus = model.campus
	var this_week := {}
	for id in campus.relationships: this_week[id] = int(campus.relationships[id]) - int(campus.week_relationship_start.get(id, 0))
	_label(modal_body, "第 %d 周 · 学业完成度 %d / 100" % [campus.week, campus.academic], 25)
	_label(modal_body, "本周已体验 %d / 32 个情景；完成 %d 次学习活动。" % [campus.week_scenes.size(), campus.study_done.size()])
	_label(modal_body, _review_text(campus.week_scenes, this_week, campus.practice_log), 18)
	for index in range(campus.reviews.size() - 1, -1, -1):
		var review: Dictionary = campus.reviews[index]
		_label(modal_body, "第 %d 周回顾 · 学业 %d / 100 · 体验 %d 个情景" % [review.week, review.academic, review.scenarios.size()], 22)
		_label(modal_body, _review_text(review.scenarios, review.relationships, review.practice), 18)
	_label(modal_body, "连续经历", 23)
	for chain in campus.catalog.chains:
		var progress: Dictionary = campus.chains.get(chain.id, {"step": 0, "day": 0})
		var step := int(progress.step)
		_label(modal_body, "%s · %d / 4" % [chain.title, step], 21)
		if step < 4:
			var next: Dictionary = campus.scenario(str(chain.steps[step]))
			_label(modal_body, "下一次：" + str(next.title) + ("（明天继续，今天可自由练习）" if int(progress.day) == GameState.day else ""), 18)
			_button(modal_body, "前往" + str(next.title), func(): model.travel(str(next.domain)); model.select_scene(str(next.id)); modal.hide())

func _review_text(scenes: Array, relationships: Dictionary, practice: Array) -> String:
	var titles := PackedStringArray()
	for id in scenes: titles.append(str(model.campus.scenario(str(id)).get("title", "校园情景")))
	var people := PackedStringArray()
	for id in relationships:
		if int(relationships[id]) > 0: people.append("%s（%d 次进展，现在%s）" % [model.campus.catalog.profiles.get(id, {}).get("name", "同学"), int(relationships[id]), {"stranger": "还未认识", "acquaintance": "初识", "familiar": "熟悉"}[model.campus.relationship_for(id)]])
	var voice := practice.filter(func(entry): return entry.get("mode") == "voice").size()
	var lines := PackedStringArray(["体验过的情景：" + ("、".join(titles) if not titles.is_empty() else "还没有")])
	lines.append("关系进展：" + ("、".join(people) if not people.is_empty() else "这一周还没有新的进展"))
	lines.append("开口练习 %d 次（语音 %d 次，文字 %d 次）" % [practice.size(), voice, practice.size() - voice])
	if not practice.is_empty(): lines.append("你说过的一句话：" + Palette.plain_quotes(str(practice[-1].get("text", ""))))
	return "\n".join(lines)

func _example() -> void:
	_open("创作示范 · 非真实录音")
	_label(modal_body, str(model.scene().title), 25)
	_label(modal_body, "以下是为练习编写的对白；角色配音由语音服务合成。", 18)
	var scene: Dictionary = model.scene()
	# P3-22: a playback that cannot happen says so here, above the modal's lines.
	example_note = _label(modal_body, "", 18)
	example_note.add_theme_color_override("font_color", Palette.MUTED)
	for i in range(scene.example.size()):
		var line: Dictionary = scene.example[i]
		var name: String = "你" if line.speaker_id == "player" else str(model.campus.catalog.profiles.get(str(line.speaker_id), {}).get("name", "同学"))
		_label(modal_body, name + "\n" + Palette.plain_quotes(str(line.text)), 20)
		if line.speaker_id != "player":
			_button(modal_body, "听这一句", _play_example.bind(str(line.speaker_id), str(scene.get("base_scenario_id", scene.id)) + "_example_" + str(i)))

func _play_example(npc: String, line: String) -> void:
	example_line = line
	if not model.npc_voice_ready or not NpcVoice.is_available():
		example_note.text = "角色语音暂未开启，示范先以文字显示。"
		return
	example_note.text = "正在准备示范语音…"
	NpcVoice.stop_all()
	# A refused request reports through line_audio_failed as well.
	NpcVoice.request_line(npc, line)

func _example_audio(_npc: String, line: String, failed := false) -> void:
	if line != example_line or not is_instance_valid(example_note): return
	example_note.text = "示范语音暂时无法播放，可以先读文字，稍后再试。这不是你的问题。" if failed else ""

func _coaching() -> void:
	_open("表达回顾")
	if model.campus.practice_log.is_empty(): _label(modal_body, "完成一次对话后，这里会显示交流建议。")
	var entries: Array = model.campus.practice_log
	for entry in entries.slice(maxi(0, entries.size() - 12)):
		_label(modal_body, str(entry.text), 20)
		_label(modal_body, "\n".join(entry.coaching), 18)
		_label(modal_body, "语音识别参考：%d（不是发音准确度评分）" % roundi(entry.pronunciation) if entry.has("pronunciation") else "文字交流 · 无发音分数", 18)

func _words() -> void:
	_open("单词练习 · 沿用当前词汇进度")
	for word in model._practice_words():
		_button(modal_body, str(word) + " · " + model.word_progress(str(word)), func(): modal.hide(); model.begin_practice(str(word)))
	_label(modal_body, "听示范后按 V 录音，再按 V 结束；免费重试。完成后点“结束单词练习”返回现场。", 18)

func _offline_activity() -> void:
	_open("离线共同活动")
	_label(modal_body, str(model.scene().title), 25)
	_label(modal_body, "在这个情景中，你准备怎样回应？可以先想一想，再完成活动。离线参加会推进一小时并恢复社交，不生成口语成绩。")
	_label(modal_body, str(model.scene().hints.open), 21)
	_button(modal_body, "完成离线活动", func(): modal.hide(); model.joint_activity(true))

func _inventory(kind: String) -> void:
	_open({"bag": "行囊", "home": "住处物品", "counter": "菜单与柜台"}[kind])
	inventory_view = Inventory.new()
	modal_body.add_child(inventory_view)
	inventory_view.setup(model, kind)
	inventory_view.action_requested.connect(_item_action)
	inventory_view.pack_all_requested.connect(func():
		var result: Dictionary = model.pack_counter()
		inventory_view.refresh()
		_inventory_notice("柜台物品已收进行囊。" if result.get("ok", false) else "行囊空间不足，可以逐件领取或先使用一些补给。")
		_refresh())
	inventory_view.travel_requested.connect(_inventory_travel)
	inventory_view.notice.connect(_inventory_notice)

func _inventory_travel(place: String) -> void:
	_close_modal()
	if place in ["food", "store", "dining"]: model.open_counter()
	else: model.travel(place)

func _inventory_notice(text: String) -> void:
	_set_status(text)
	if is_instance_valid(inventory_view): inventory_view.show_notice(text)

func _item_action(action: String, id: String, allow_waste: bool) -> void:
	var record: Dictionary = GameState.items.instances.get(id, {})
	var title := "物品"
	if not record.is_empty(): title = GameState.items.Catalog.label(GameState.items.definitions[record.item_id].name)
	var result: Dictionary = model.use_item(action, id, allow_waste)
	if result.get("ok", false):
		inventory_view.refresh()
		var verb: String = {"pack": "已收进行囊", "store": "已存入住处", "consume": "已使用", "place": "已安放", "use_home": "已用上", "deactivate": "已收起", "reclaim": "已收回行囊"}.get(action, "已处理")
		var message := title + verb + "。"
		for key in result.get("effects", {}):
			if float(result.effects[key]) > 0:
				message += " %s +%d" % [{"food": "饮食", "warmth": "温暖", "energy": "精力"}.get(key, key), int(result.effects[key])]
		_inventory_notice(message)
	else:
		var reason := str(result.get("reason", ""))
		_inventory_notice({"waste": "当前只能恢复部分效果，请确认使用或先留着。", "capacity": "这一类行囊已满，可以先使用补给或回住处存放。", "full": "当前状态已满，可以留到需要时使用。", "missing": "物品已用完或转移，请重新选择。", "location": "请到对应柜台或住处使用这件物品。", "unsafe": "请先结束交流再使用物品。"}.get(reason, "暂时无法使用，请重新选择物品。"))
		if reason == "waste": inventory_view.request_confirmation(action, id)
	_refresh()

func _town() -> void:
	model.cancel_activity()
	model.save()
	get_tree().set_meta("campus_return_to_town", true)
	get_tree().change_scene_to_file("res://scenes/Novel.tscn")

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.echo: return
	if modal != null and modal.visible: return
	if event.is_action_pressed("ui_cancel") or event.is_action_pressed("pause"):
		_settings(); get_viewport().set_input_as_handled(); return
	if get_viewport().gui_get_focus_owner() is LineEdit or get_viewport().gui_get_focus_owner() is TextEdit: return
	if event.is_action_pressed("push_to_talk"): model.record(); get_viewport().set_input_as_handled()
	elif event.is_action_pressed("item_show"): _inventory("bag"); get_viewport().set_input_as_handled()
