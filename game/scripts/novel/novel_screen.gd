extends Control
## FR-46: a canvas-only visual novel. No world scene is instantiated.
const Content := preload("res://scripts/novel/novel_content.gd")
const Glyphs := preload("res://scripts/input_glyphs.gd")
const Controller := preload("res://scripts/novel/novel_controller.gd")
const BG := preload("res://assets/novel/settlement_atlas.png")
const CAST := preload("res://assets/novel/cast_atlas.png")
const Palette := preload("res://scripts/novel/novel_palette.gd")
const TEXT := Palette.TEXT
const MUTED := Palette.MUTED
const ACCENT := Palette.ACCENT
const POSITIVE := Palette.POSITIVE
const SETTINGS := "user://stranger_novel_settings.cfg"
var startup_pending := false
var model: Node
var canvas: Control
var background: TextureRect
var shade: ColorRect
var portrait: TextureRect
var second_portrait: TextureRect
var location_label: Label
var scene_caption: Label
var speaker_label: Label
var role_label: Label
var dialogue_text: RichTextLabel
var player_caption: RichTextLabel
var player_caption_box: Panel
var player_transcript := ""
var feedback_label: Label
var feedback_panel: Panel
var feedback_tween: Tween
var clock_label: Label
var objective_label: Label
var relationship_label: Label
var gesture_button: Button
var talk_button: Button
var replay_button: Button
var home_action_button: Button
var record_button: Button
var action_row: HBoxContainer
var advance_button: Button
var reveal_button: Button
var needs: Array[ProgressBar] = []
var need_labels: Array[Label] = []
var place_buttons: Array[Button] = []
var remap: Control
var modal: Panel
var modal_scrim: ColorRect
var inventory_view: VBoxContainer
var counter_button: Button
var bag_button: Button
var need_tween: Tween
var modal_title: Label
var modal_body: VBoxContainer
var modal_kind := ""
var modal_status: Label
var close_button: Button
var reduce_motion := false
var instant_text := false
var large_text := false
var text_elapsed := 0.0
var backdrop_tween: Tween
var toast_remaining := 0.0
var panel_refresh_queued := false
var last_speaker := ""
var activation_input: LineEdit
var previous_focus: Control
var order_panel: Panel
var order_title: Label
var order_detail: Label
@export var boot_from_save := true

func _ready() -> void:
	_load_settings()
	_build_theme()
	_build_screen()
	model = Controller.new()
	model.boot_from_save = boot_from_save
	model.scene_changed.connect(_show_scene)
	model.line_changed.connect(_show_line)
	model.feedback.connect(_toast)
	model.progression_changed.connect(_refresh)
	add_child(model)
	SpeechAdapter.recording_state_changed.connect(func(_active): _refresh())
	SpeechAdapter.recognition_pending.connect(func(_id): _toast("正在听清你的话…"))
	NpcDialogueService.dialogue_pending.connect(func(_npc, _scenario): _toast("对方正在回应…"))
	NpcDialogueService.player_turn_scored.connect(_show_salience)
	SpeechAdapter.cloud_auth_finished.connect(_activation_finished)
	resized.connect(_layout)
	get_viewport().gui_focus_changed.connect(_contain_modal_focus)
	_layout()
	remap = preload("res://scenes/NovelRemap.tscn").instantiate()
	canvas.add_child(remap)
	remap.closed.connect(func(): _open_panel("settings"))
	remap.bindings_changed.connect(_rebuild_actions)
	model.start(false)
	_refresh()
	var chapter_return := bool(get_tree().get_meta("campus_return_to_town", false))
	if get_tree().has_meta("campus_return_to_town"): get_tree().remove_meta("campus_return_to_town")
	if boot_from_save and not chapter_return:
		if FileAccess.file_exists(model.novel_save_path) or FileAccess.file_exists(model.old_save_path):
			startup_pending = true
			_open_panel("startup")
		else:
			_open_panel("guide")
	if modal.visible: _focus_modal()
	else: place_buttons[0].grab_focus()

func _build_theme() -> void:
	theme = Theme.new()
	var readable_font := Palette.font()
	theme.default_font = readable_font
	for type_name in ["Label", "Button", "LineEdit"]:
		theme.set_font("font", type_name, readable_font)
	theme.set_font("normal_font", "RichTextLabel", readable_font)
	theme.set_font("font", "Button", Palette.font(false, 450.0))
	theme.set_type_variation("NovelTitle", "Label")
	theme.set_font("font", "NovelTitle", Palette.font(true, 500.0))
	theme.set_font("font", "ProgressBar", readable_font)
	theme.default_font_size = 18
	theme.set_color("font_color", "Label", TEXT)
	theme.set_color("default_color", "RichTextLabel", TEXT)
	for state in ["normal", "hover", "pressed", "focus", "disabled"]:
		var fill := Palette.SURFACE_RAISED
		if state == "hover": fill = Palette.HOVER
		if state == "pressed": fill = Palette.PRESSED
		if state == "disabled": fill = Palette.DISABLED
		if state == "focus": fill = Color.TRANSPARENT
		var style := Palette.button_style(fill, Palette.BORDER)
		if state == "focus": style = _style(Color.TRANSPARENT, Palette.FOCUS, 2, 3)
		style.content_margin_left = 16
		style.content_margin_right = 16
		theme.set_stylebox(state, "Button", style)
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		theme.set_color(state, "Button", TEXT)
	theme.set_color("font_disabled_color", "Button", Palette.ON_DISABLED)
	theme.set_stylebox("normal", "LineEdit", _style(Palette.SURFACE_RAISED, Palette.BORDER, 1, 4))
	theme.set_stylebox("focus", "LineEdit", _style(Color.TRANSPARENT, Palette.FOCUS, 2, 4))
	theme.set_color("font_color", "LineEdit", TEXT)
	theme.set_color("font_placeholder_color", "LineEdit", MUTED)
	theme.set_color("caret_color", "LineEdit", TEXT)
	theme.set_color("selection_color", "LineEdit", Palette.SELECTED)
	theme.set_color("font_selected_color", "LineEdit", TEXT)
	var card := _style(Palette.SURFACE, Palette.BORDER, 1, 6)
	card.content_margin_left = 24
	card.content_margin_right = 24
	card.content_margin_top = 20
	card.content_margin_bottom = 24
	theme.set_stylebox("panel", "PanelContainer", card)
	theme.set_stylebox("panel", "TooltipPanel", card)
	theme.set_color("font_color", "TooltipLabel", TEXT)
	for name in ["scroll", "scroll_focus", "grabber", "grabber_highlight", "grabber_pressed"]:
		var style := _style(Palette.SURFACE_INSET if name.begins_with("scroll") else Palette.BORDER, Color.TRANSPARENT, 0, 3)
		style.content_margin_left = 3
		style.content_margin_right = 3
		theme.set_stylebox(name, "VScrollBar", style)

func _style(fill: Color, border := Color.TRANSPARENT, width := 0, radius := 6) -> StyleBoxFlat:
	return Palette.style(fill, border, width, radius)

func _box(parent: Node, rect: Rect2, fill: Color, border := Color.TRANSPARENT) -> Panel:
	var box := Panel.new()
	box.position = rect.position
	box.size = rect.size
	var surface := _style(fill, border, 1 if border.a > 0 else 0)
	if rect.position != Vector2.ZERO:
		surface.shadow_color = Color(Palette.SHADOW, 0.12)
		surface.shadow_size = 16
		surface.shadow_offset = Vector2(0, 5)
	box.add_theme_stylebox_override("panel", surface)
	parent.add_child(box)
	return box

func _label(parent: Node, text: String, rect: Rect2, size_px := 18, color := TEXT) -> Label:
	var label := Label.new()
	label.text = text
	label.position = rect.position
	label.size = rect.size
	label.add_theme_font_size_override("font_size", size_px)
	label.add_theme_color_override("font_color", color)
	if size_px >= 23: label.theme_type_variation = "NovelTitle"
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(label)
	return label

func _rule(parent: Node, rect: Rect2, color := Palette.BORDER) -> void:
	var line := ColorRect.new()
	line.position = rect.position
	line.size = rect.size
	line.color = color
	line.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(line)

func _button(parent: Node, text: String, callback: Callable, rect := Rect2()) -> Button:
	var button := Button.new()
	button.text = text
	button.position = rect.position
	if rect.size != Vector2.ZERO:
		button.size = rect.size
	button.custom_minimum_size.y = 44
	button.pressed.connect(_activate_button.bind(button, callback))
	parent.add_child(button)
	return button

func _activate_button(button: Button, callback: Callable) -> void:
	# Rebuilds and modal transitions can leave a pressed callback queued.
	if not button.is_inside_tree() or not button.is_visible_in_tree() or button.disabled: return
	if remap != null and remap.visible: return
	if modal != null and modal.visible and not modal.is_ancestor_of(button): return
	callback.call()

func _texture(parent: Node, rect: Rect2) -> TextureRect:
	var image := TextureRect.new()
	image.position = rect.position
	image.size = rect.size
	image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	image.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	image.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(image)
	return image

func _atlas(source: Texture2D, rect: Rect2) -> AtlasTexture:
	var texture := AtlasTexture.new()
	texture.atlas = source
	texture.region = rect
	texture.filter_clip = true
	return texture

func _cast_texture(npc: String) -> Texture2D:
	var index := Content.CAST.find(npc)
	if index < 0: return null
	# Authored atlas gutters, measured from the generated source (2172 x 724).
	const EDGES := [0.0, 443.0, 937.0, 1254.0, 1746.0, 2172.0]
	return _atlas(CAST, Rect2(EDGES[index], 0, EDGES[index + 1] - EDGES[index], 724))

func _build_screen() -> void:
	canvas = Control.new()
	canvas.size = Vector2(1440, 900)
	add_child(canvas)
	background = _texture(canvas, Rect2(0, 0, 1440, 900))
	background.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	background.clip_contents = true
	shade = ColorRect.new()
	shade.color = Color(Palette.SURFACE, 0.08)
	shade.size = canvas.size
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canvas.add_child(shade)
	var header := _box(canvas, Rect2(0, 0, 1440, 88), Color(Palette.SURFACE, 0.98))
	header.add_theme_stylebox_override("panel", _style(Color(Palette.SURFACE, 0.98), Color.TRANSPARENT, 0, 0))
	_rule(canvas, Rect2(30, 87, 1380, 1))
	_label(canvas, "STRANGER", Rect2(30, 9, 265, 42), 29, ACCENT)
	_label(canvas, "异乡人  /  一点点，成为这里的人", Rect2(32, 48, 350, 25), 13, MUTED)
	clock_label = _label(canvas, "", Rect2(363, 22, 340, 45), 18, MUTED)
	var campus_button := _button(canvas, "校园篇章", func():
		model.cancel_activity()
		model.save()
		get_tree().change_scene_to_file("res://scenes/Campus.tscn"), Rect2(750, 22, 112, 44))
	Palette.quiet(campus_button)
	for entry in [["成长", "growth"], ["行囊", "bag"], ["小剧场", "theater"], ["回看", "history"], ["设置", "settings"]]:
		var index: int = ["growth", "bag", "theater", "history", "settings"].find(entry[1])
		var button := _button(canvas, entry[0], _open_panel.bind(entry[1]), Rect2(880 + index * 106, 22, 96, 44))
		Palette.quiet(button)
		if entry[1] == "bag": bag_button = button
	_box(canvas, Rect2(24, 112, 244, 757), Color(Palette.SURFACE, 0.98))
	_label(canvas, "去哪里？", Rect2(46, 126, 190, 38), 25)
	_label(canvas, "沿着日常，慢慢熟悉。", Rect2(46, 165, 190, 32), 14, MUTED)
	_rule(canvas, Rect2(46, 204, 195, 1))
	for i in range(Content.PLACES.size()):
		var entry: Dictionary = Content.PLACES[i]
		var button := _button(canvas, "%02d   %s" % [i + 1, entry.name], _travel.bind(entry.id), Rect2(40, 214 + i * 57, 210, 47))
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		place_buttons.append(button)
	_rule(canvas, Rect2(46, 569, 195, 1))
	_label(canvas, "今日状态", Rect2(46, 580, 190, 30), 17, ACCENT)
	for i in range(3):
		need_labels.append(_label(canvas, "", Rect2(46, 624 + i * 57, 190, 25), 15))
		var bar := ProgressBar.new()
		bar.position = Vector2(46, 655 + i * 57)
		bar.size = Vector2(197, 6)
		bar.show_percentage = false
		bar.add_theme_font_size_override("font_size", 1)
		bar.add_theme_stylebox_override("background", _style(Palette.SURFACE_INSET, Color.TRANSPARENT, 0, 3))
		bar.add_theme_stylebox_override("fill", _style([Palette.NEED_FOOD, Palette.NEED_WARMTH, Palette.NEED_ENERGY][i], Color.TRANSPARENT, 0, 3))
		for style_name in ["background", "fill"]:
			var bar_style := bar.get_theme_stylebox(style_name) as StyleBoxFlat
			bar_style.set_content_margin_all(0)
		canvas.add_child(bar)
		# Before entering this themed canvas, Control clamps against the engine font.
		bar.set_deferred("size", Vector2(197, 6))
		needs.append(bar)
	objective_label = _label(canvas, "", Rect2(46, 803, 195, 49), 13, MUTED)
	location_label = _label(canvas, "", Rect2(305, 118, 790, 32), 16, Palette.ON_SCENE)
	scene_caption = _label(canvas, "", Rect2(303, 155, 660, 56), 34, Palette.ON_SCENE)
	relationship_label = _label(canvas, "", Rect2(1130, 118, 280, 43), 16, Palette.ON_SCENE)
	for label in [location_label, scene_caption, relationship_label]:
		label.add_theme_color_override("font_shadow_color", Color(Palette.SHADOW, 0.9))
		label.add_theme_constant_override("shadow_offset_y", 1)
		label.add_theme_constant_override("shadow_outline_size", 4)
	second_portrait = _texture(canvas, Rect2(390, 210, 370, 510))
	portrait = _texture(canvas, Rect2(851, 179, 442, 590))
	order_panel = _box(canvas, Rect2(310, 263, 505, 130), Color(Palette.SURFACE_RAISED, 0.96))
	order_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_rule(order_panel, Rect2(0, 17, 2, 96), Palette.ACCENT)
	order_title = _label(order_panel, "", Rect2(18, 12, 469, 30), 18, ACCENT)
	order_detail = _label(order_panel, "", Rect2(18, 49, 469, 72), 16, MUTED)
	_box(canvas, Rect2(289, 611, 1128, 258), Color(Palette.SURFACE_RAISED, 0.98), Palette.BORDER)
	_rule(canvas, Rect2(309, 623, 1088, 1), Color(Palette.BORDER, 0.6))
	var nameplate := _box(canvas, Rect2(319, 587, 174, 48), Palette.SURFACE_RAISED, Palette.BORDER)
	nameplate.add_theme_stylebox_override("panel", _style(Palette.SURFACE_RAISED, Palette.BORDER, 1, 3))
	_rule(nameplate, Rect2(17, 0, 140, 1), Palette.ACCENT)
	speaker_label = _label(nameplate, "", Rect2(18, 2, 138, 42), 26, ACCENT)
	speaker_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	role_label = _label(canvas, "", Rect2(514, 623, 720, 25), 14, MUTED)
	reveal_button = _button(canvas, "显示全文", func(): text_elapsed = 9999.0, Rect2(1252, 605, 128, 44))
	reveal_button.add_theme_font_size_override("font_size", 15)
	Palette.quiet(reveal_button)
	dialogue_text = RichTextLabel.new()
	dialogue_text.position = Vector2(328, 650)
	dialogue_text.size = Vector2(1048, 142)
	dialogue_text.add_theme_font_override("normal_font", Palette.font(true))
	dialogue_text.add_theme_font_size_override("normal_font_size", 30 if large_text else 26)
	dialogue_text.add_theme_constant_override("line_separation", 1)
	dialogue_text.bbcode_enabled = false
	dialogue_text.selection_enabled = true
	dialogue_text.mouse_filter = Control.MOUSE_FILTER_PASS
	canvas.add_child(dialogue_text)
	action_row = HBoxContainer.new()
	_rule(canvas, Rect2(328, 798, 1048, 1))
	action_row.position = Vector2(320, 811)
	action_row.size = Vector2(1060, 44)
	action_row.add_theme_constant_override("separation", 8)
	canvas.add_child(action_row)
	feedback_panel = _box(canvas, Rect2(310, 498, 1060, 74), Color(Palette.SURFACE, 0.98))
	_rule(feedback_panel, Rect2(0, 14, 2, 46), Palette.ACCENT)
	feedback_panel.visible = false
	feedback_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	feedback_label = _label(feedback_panel, "", Rect2(20, 10, 1020, 54), 18, TEXT)
	player_caption_box = _box(canvas, Rect2(316, 405, 515, 82), Color(Palette.SURFACE_RAISED, 0.98))
	player_caption_box.visible = false
	player_caption = RichTextLabel.new()
	player_caption.position = Vector2(16, 10)
	player_caption.size = Vector2(481, 64)
	player_caption.bbcode_enabled = true
	player_caption.add_theme_font_size_override("normal_font_size", 18)
	player_caption_box.add_child(player_caption)
	_build_modal()

func _build_modal() -> void:
	modal_scrim = ColorRect.new()
	modal_scrim.size = canvas.size
	modal_scrim.color = Color(Palette.SHADOW, 0.38)
	modal_scrim.mouse_filter = Control.MOUSE_FILTER_STOP
	modal_scrim.visible = false
	canvas.add_child(modal_scrim)
	modal = _box(canvas, Rect2(292, 109, 1120, 759), Palette.SURFACE, Palette.BORDER)
	modal.visible = false
	modal_title = _label(modal, "", Rect2(30, 17, 900, 54), 29, ACCENT)
	close_button = _button(modal, "返回  Esc", _close_panel, Rect2(951, 26, 140, 44))
	Palette.quiet(close_button)
	_rule(modal, Rect2(30, 78, 1060, 1))
	_rule(modal, Rect2(30, 665, 1060, 1))
	var scroll := ScrollContainer.new()
	scroll.position = Vector2(30, 92)
	scroll.size = Vector2(1060, 562)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.follow_focus = true
	modal.add_child(scroll)
	modal_body = VBoxContainer.new()
	modal_body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	modal_body.add_theme_constant_override("separation", 15)
	scroll.add_child(modal_body)
	modal_status = _label(modal, "", Rect2(32, 679, 1054, 54), 17, MUTED)

func _layout() -> void:
	if canvas == null: return
	var ratio := minf(size.x / 1440.0, size.y / 900.0)
	canvas.scale = Vector2.ONE * ratio
	canvas.position = (size - canvas.size * ratio) * 0.5

func _process(delta: float) -> void:
	if dialogue_text == null: return
	text_elapsed += delta
	dialogue_text.visible_characters = -1 if instant_text or reduce_motion else int(text_elapsed * 44.0)
	_refresh_advance()
	_refresh_record_button()
	if toast_remaining > 0.0:
		toast_remaining -= delta
		if toast_remaining <= 0.0:
			feedback_label.text = ""
			feedback_panel.visible = false

func _travel(destination: String) -> void:
	_close_panel()
	model.travel(destination)

func _show_scene() -> void:
	feedback_label.text = ""
	feedback_panel.visible = false
	player_transcript = ""
	player_caption_box.visible = false
	var entry := Content.place(str(Content.SOCIAL[model.social_index].place) if model.social_index >= 0 else model.location)
	var index: int = Content.PLACES.find(entry)
	var tile := Vector2(BG.get_width() / 2.0, BG.get_height() / 3.0)
	background.texture = _atlas(BG, Rect2(Vector2(index % 2, index / 2) * tile, tile))
	background.modulate = Color("c6cbce") if GameState.clock_hours() >= 19.0 else Color.WHITE
	location_label.text = entry.en
	scene_caption.text = entry.name
	portrait.texture = _cast_texture(entry.npc)
	portrait.visible = not str(entry.npc).is_empty()
	second_portrait.visible = false
	role_label.text = entry.role
	for i in range(place_buttons.size()):
		place_buttons[i].add_theme_color_override("font_color", TEXT)
		Palette.navigation(place_buttons[i], i == index)
	if backdrop_tween: backdrop_tween.kill()
	portrait.modulate = Color.WHITE
	if not reduce_motion:
		portrait.modulate.a = 0.0
		background.modulate.a = 0.25
		backdrop_tween = create_tween()
		backdrop_tween.tween_property(portrait, "modulate:a", 1.0, 0.3)
		backdrop_tween.parallel().tween_property(background, "modulate:a", 1.0, 0.3)
	_rebuild_actions()
	_refresh()

func _rebuild_actions() -> void:
	for child in action_row.get_children():
		action_row.remove_child(child)
		child.queue_free()
	home_action_button = null
	record_button = null
	gesture_button = null
	talk_button = null
	replay_button = null
	counter_button = null
	advance_button = null
	if model.social_index >= 0:
		replay_button = _button(action_row, "重听这一句", func(): model.listen_again())
		_button(action_row, "回到现场", func(): model.cancel_activity(); model.start())
		_action_space()
		advance_button = _button(action_row, "下一句  →", _advance)
	elif GameState.game_finished:
		_button(action_row, "这段旅程的回忆", _open_panel.bind("growth"))
		_action_space()
		_button(action_row, "开始新旅程", _open_panel.bind("restart"))
	elif not model.practice_word.is_empty():
		replay_button = _button(action_row, "重听示范", func(): model.listen_again())
		_button(action_row, "结束练习", _end_practice)
		_action_space()
		record_button = _button(action_row, "录制这个词", func(): model.record())
	elif model.location == "home":
		_button(action_row, "整理住处", _open_panel.bind("home"))
		_button(action_row, "保存", _save)
		_action_space()
		home_action_button = _button(action_row, "", func():
			if GameState._wants_sleep(): model.sleep()
			else: model.wait_until_evening(); _show_scene())
	else:
		talk_button = _button(action_row, ("交谈  " if GameState.can_start_service_dialogue(model.npc_id()) else "打招呼  ") + Glyphs.for_action("interact", false), func(): model.talk())
		gesture_button = _button(action_row, "手势  G", func(): model.greet())
		if GameState.can_start_service_dialogue(model.npc_id()):
			counter_button = _button(action_row, "查看柜台", _open_panel.bind("counter"))
		else:
			_button(action_row, "听日常", _open_panel.bind("theater"))
		_action_space()
		replay_button = _button(action_row, "重听", func(): model.listen_again())
		_button(action_row, "开口灵感", _open_panel.bind("phrases"))
		record_button = _button(action_row, "录音  V", func(): model.record())
	for child in action_row.get_children():
		if child is Button: Palette.quiet(child)
	Palette.primary(action_row.get_child(-1))
	_refresh_advance()

func _action_space() -> void:
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	action_row.add_child(spacer)

func _refresh_advance() -> void:
	if model == null: return
	var revealing := not instant_text and not reduce_motion and text_elapsed * 44.0 < dialogue_text.get_total_character_count()
	var show_reveal: bool = revealing and model.social_index < 0
	if reveal_button.has_focus() and not show_reveal:
		if is_instance_valid(record_button): record_button.grab_focus()
		else: action_row.get_child(0).grab_focus()
	reveal_button.visible = show_reveal
	if is_instance_valid(advance_button):
		var last_line: bool = model.social_line == Content.SOCIAL[model.social_index].lines.size() - 1
		advance_button.text = "显示全文" if revealing else ("回到现场  →" if last_line else "下一句  →")

func _show_line(speaker: String, text: String) -> void:
	if speaker == "you":
		player_transcript = text
		_show_salience("", text, [])
	last_speaker = speaker
	speaker_label.text = "我" if speaker == "you" else ("异乡手记" if speaker.is_empty() else speaker.capitalize())
	dialogue_text.bbcode_enabled = false
	dialogue_text.text = text
	dialogue_text.scroll_to_line(0)
	text_elapsed = 0.0
	if speaker in Content.CAST:
		portrait.visible = true
		if model.social_index >= 0:
			var lines: Array = Content.SOCIAL[model.social_index].lines
			# Bind positions to the cast of this scene, never the current turn.
			var right := str(lines[0][0])
			var left := ""
			for line in lines:
				if str(line[0]) != right:
					left = str(line[0])
					break
			portrait.texture = _cast_texture(right)
			second_portrait.texture = _cast_texture(left)
			var quiet := Color(0.87, 0.88, 0.82, 0.95)
			portrait.modulate = Color.WHITE if speaker == right else quiet
			second_portrait.modulate = Color.WHITE if speaker == left else quiet
			second_portrait.visible = not left.is_empty()
			role_label.text = "日常 · %s   %d / %d" % [Content.SOCIAL[model.social_index].title, model.social_line + 1, lines.size()]
		else:
			portrait.texture = _cast_texture(speaker)
			portrait.modulate = Color.WHITE
	_refresh()

func _show_salience(_npc: String, transcript: String, errors: Array) -> void:
	if transcript != player_transcript or transcript.is_empty(): return
	var safe := transcript.replace("[", "‹").replace("]", "›").replace("\n", " ")
	var ranges: Array = []
	for error in errors:
		var span := str(error).strip_edges()
		var index := safe.to_lower().find(span.to_lower())
		if span.is_empty() or index < 0: continue
		var end := index + span.length()
		var overlaps := false
		for item in ranges:
			if index < item[1] and item[0] < end: overlaps = true
		if not overlaps: ranges.append([index, end])
	ranges.sort_custom(func(a, b): return a[0] < b[0])
	var rendered := "我  ·  "
	var cursor := 0
	for item in ranges:
		rendered += safe.substr(cursor, item[0] - cursor)
		rendered += "[color=#" + Palette.SALIENCE.to_html(false) + "][u]" + safe.substr(item[0], item[1] - item[0]) + "[/u][/color]"
		cursor = item[1]
	rendered += safe.substr(cursor)
	player_caption.text = rendered
	player_caption_box.visible = true

func _refresh() -> void:
	if model == null: return
	var time: Vector2i = GameState.clock_hms()
	clock_label.text = "第 %d 天  ·  %02d:%02d   /   %d 夜" % [mini(GameState.day, 3), time.x, time.y, mini(GameState.day - 1, 3)]
	var values := [GameState.food, GameState.warmth, GameState.energy]
	var names := ["饱腹", "温暖", "精力"]
	if need_tween: need_tween.kill()
	if not reduce_motion: need_tween = create_tween().set_parallel(true)
	for i in range(3):
		if reduce_motion: needs[i].value = values[i]
		else: need_tween.tween_property(needs[i], "value", values[i], 0.3).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
		need_labels[i].text = "%s                       %d / 100" % [names[i], int(values[i])]
	objective_label.text = GameState.objective_text()
	var npc: String = model.npc_id()
	bag_button.text = "行囊 · %d" % model.visible_items("bag").size()
	if is_instance_valid(counter_button):
		var pending: int = model.visible_items("counter").size()
		counter_button.text = "领取 · %d 件待取" % pending if pending > 0 else "菜单 / 柜台"
		counter_button.add_theme_color_override("font_color", ACCENT if pending > 0 else TEXT)
		Palette.quiet(counter_button)
		Palette.quiet(record_button)
		if pending > 0:
			action_row.move_child(counter_button, -1)
			Palette.primary(counter_button)
		else:
			action_row.move_child(counter_button, 2)
			Palette.primary(record_button)
	var guidance: Dictionary = model.order_guidance()
	if not model.practice_word.is_empty():
		guidance = {"title": "正在练习 · " + model.practice_word,
			"detail": "听示范 → 录制这个词 → 查看反馈。结束练习后，再与角色交谈。"}
		role_label.text = "单词练习 · " + model.practice_word
	order_panel.visible = not guidance.is_empty()
	order_title.text = str(guidance.get("title", ""))
	order_detail.text = str(guidance.get("detail", ""))
	relationship_label.text = "一段日常 · 随时可以离开" if model.social_index >= 0 else ("信任  %s  ·  %d" % [npc.capitalize(), GameState.relationships.get(npc, 0)] if not npc.is_empty() else "休息 · 安顿 · 明天")
	if is_instance_valid(home_action_button):
		home_action_button.text = "入睡 · 下一天" if GameState._wants_sleep() else "休息到夜晚"
		order_panel.visible = true
		order_title.text = "可以入睡了" if GameState._wants_sleep() else "先歇一会儿"
		order_detail.text = "睡眠会进入下一天，恢复精力与温暖。" if GameState._wants_sleep() else "休息会快进到夜晚，并少量消耗饱腹、温暖和精力。"
	_refresh_record_button()
	if is_instance_valid(gesture_button):
		gesture_button.text = ("手势领取  " if SpeechAdapter.runtime_speech_unavailable() and GameState.can_start_service_dialogue(npc) else "手势  ") + Glyphs.for_action("gesture", false)
	if modal.visible and modal_kind in ["bag", "counter", "home", "growth"] and not panel_refresh_queued:
		panel_refresh_queued = true
		call_deferred("_refresh_panel")

func _refresh_record_button() -> void:
	if model == null: return
	var busy: String = model.conversation_block_reason()
	for button in [talk_button, gesture_button, replay_button]:
		if is_instance_valid(button):
			button.disabled = not busy.is_empty()
			button.tooltip_text = busy + "，结束后再操作。" if not busy.is_empty() else ""
	if not is_instance_valid(record_button): return
	var reason: String = model.recording_block_reason()
	record_button.disabled = not reason.is_empty()
	if not reason.is_empty():
		record_button.text = reason + "…"
		record_button.tooltip_text = "语音结束后即可录音；此时点击不会中断或重播。"
	else:
		var label := "录制这个词  " if not model.practice_word.is_empty() else "录音  "
		record_button.text = ("结束录音  " if SpeechAdapter.is_recording() else label) + Glyphs.for_action("push_to_talk", false)
		record_button.tooltip_text = ""

func _toast(text: String) -> void:
	feedback_label.text = text
	feedback_panel.visible = not text.is_empty()
	if feedback_tween: feedback_tween.kill()
	feedback_panel.modulate.a = 1.0 if reduce_motion else 0.0
	if not reduce_motion:
		feedback_tween = create_tween()
		feedback_tween.tween_property(feedback_panel, "modulate:a", 1.0, 0.18)
	toast_remaining = 9.0
	if modal.visible: modal_status.text = text

func _advance() -> void:
	if dialogue_text.visible_characters >= 0 and dialogue_text.visible_characters < dialogue_text.get_total_character_count():
		text_elapsed = 9999.0
		dialogue_text.visible_characters = -1
		_refresh_advance()
		return
	if model.social_index >= 0:
		model.next_social()
	else:
		_toast("选择交谈、录音或一个地点，继续今天的生活。")

func _open_panel(kind: String) -> void:
	if not modal.visible: previous_focus = get_viewport().gui_get_focus_owner()
	if kind in ["bag", "counter", "home", "theater", "phrases", "growth", "settings", "restart", "history", "help"]:
		var was_activity: bool = model.social_index >= 0 or not model.practice_word.is_empty()
		model.cancel_activity()
		if was_activity: model.start(false)
	close_button.visible = kind != "startup"
	modal_kind = kind
	modal.visible = true
	modal_scrim.visible = true
	modal_status.text = ""
	_refresh_panel()
	_focus_modal()

func _focus_modal() -> void:
	if not modal.visible: return
	if startup_pending:
		for child in modal_body.get_children():
			if child is Button:
				child.grab_focus()
				return
	else: close_button.grab_focus()

func _close_panel() -> void:
	if modal == null or not modal.visible or startup_pending: return
	var leaving_guide := modal_kind == "guide"
	modal.visible = false
	modal_scrim.visible = false
	modal_kind = ""
	if leaving_guide:
		GameState.presentation_state["guide_seen"] = true
		model.save()
		model.start()
	if is_instance_valid(previous_focus) and previous_focus.is_visible_in_tree():
		previous_focus.grab_focus()

func _contain_modal_focus(control: Control) -> void:
	if modal.visible and control != null and control != modal and not modal.is_ancestor_of(control):
		_focus_modal.call_deferred()

func _row_label(text: String, font_size := 20, color := TEXT) -> Label:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	if font_size >= 23: label.theme_type_variation = "NovelTitle"
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	modal_body.add_child(label)
	return label

func _refresh_panel() -> void:
	panel_refresh_queued = false
	if modal_kind in ["bag", "counter", "home"] and is_instance_valid(inventory_view) and inventory_view.mode == modal_kind:
		inventory_view.refresh()
		return
	inventory_view = null
	for child in modal_body.get_children():
		modal_body.remove_child(child)
		child.queue_free()
	match modal_kind:
		"startup":
			modal_title.text = "异乡人 / 开始旅程"
			_row_label("从这里继续，或重新认识这座聚落。", 28)
			_row_label("上次进度：第 %d 天 · %s" % [GameState.day, Content.place(model.location).name])
			_button(modal_body, "继续上次旅程", _continue_journey)
			_button(modal_body, "从头开始 · 重新体验引导", _new_journey)
			_row_label("从头开始会先保留旧存档副本，再回到第一天的广场。", 18, MUTED)
		"guide":
			modal_title.text = "第一天 / 先吃一顿热饭"
			_row_label("慢慢来，从一句点餐开始。", 28)
			_row_label("1  去塔维的餐摊，认识这里的店员。")
			_row_label("2  点录音说出想吃什么，再点一次结束。不会说时，看看「开口灵感」。")
			_row_label("3  对方交付后，点柜台领取：现在吃，或装进行囊。")
			_row_label("阅读不消耗时间。没有语音连接时，可用手势领取。其他操作随时在设置中查看。", 18, MUTED)
			_button(modal_body, "从广场开始第一天", _close_panel)
		"help":
			modal_title.text = "操作说明 / 按自己的节奏"
			_row_label("交谈：点录音说话，再点一次结束。对方说完交付物品后，到柜台领取。")
			_row_label("成长：听单词示范，再录制这个词；练习结束后，在交谈中使用。小剧场可以逐句重听。")
			_row_label("住处：白天休息到夜晚，再入睡。阅读和练习不扣需求，旅行与休息会推进时间。")
			_row_label("键盘：1–6 地点 · E 交谈/打招呼 · V 录音开关 · G 手势 · B 行囊 · Esc 设置/返回。Tab / 方向键选择按钮，Enter / 手柄 A 确认。", 18, MUTED)
		"bag", "counter", "home": _items_panel()
		"growth": _growth_panel()
		"theater":
			modal_title.text = "聚落日常  /  听他们怎样聊天"
			_row_label("%d 段日常，从一声问候到顺路帮忙。每段都可以慢慢听、随时重听。" % Content.SOCIAL.size(), 18, MUTED)
			for i in range(Content.SOCIAL.size()):
				var scene: Dictionary = Content.SOCIAL[i]
				_button(modal_body, "%02d   %s   ·   %d 句" % [i + 1, scene.title, scene.lines.size()], _play_social.bind(i))
				_row_label(scene.hint, 18, MUTED)
		"phrases":
			modal_title.text = "开口灵感  /  从自己的需要说起"
			_row_label("不必一字不差。听一个日常片段，再用自己的话聊聊。", 18, MUTED)
			for i in range(Content.SOCIAL.size()):
				var scene: Dictionary = Content.SOCIAL[i]
				if scene.place != model.location: continue
				_row_label(scene.hint, 18, ACCENT)
				_row_label(scene.phrase, 28)
				_button(modal_body, "听听这段：" + scene.title, _play_social.bind(i))
		"history":
			modal_title.text = "回看  /  留下的片段"
			if model.history.is_empty(): _row_label("旅程才刚刚开始。")
			for entry in model.history:
				_row_label("第 %d 天 · %s" % [entry.day, str(entry.speaker).capitalize() if not str(entry.speaker).is_empty() else "手记"], 15, ACCENT)
				_row_label(entry.text, 21)
		"settings": _settings_panel()
		"restart":
			modal_title.text = "开始新旅程？"
			_row_label("这会重置当前 2D 旅程的物品、三夜进度、关系与回忆。已习得的词汇保留，旧版 3D 存档不受影响。")
			_button(modal_body, "确认开始新旅程", _new_journey)

func _items_panel() -> void:
	modal_title.text = {"bag": "行囊  /  为下一段日常留点余地", "counter": "柜台  /  收好你的这一份", "home": "小屋  /  把日子安放好"}[modal_kind]
	inventory_view = preload("res://scripts/novel/novel_inventory.gd").new()
	modal_body.add_child(inventory_view)
	inventory_view.action_requested.connect(_item_action)
	inventory_view.travel_requested.connect(_travel)
	inventory_view.notice.connect(_toast)
	inventory_view.pack_all_requested.connect(func():
		var count: int = model.visible_items("counter").size()
		var result: Dictionary = model.pack_counter()
		_toast("已将 %d 件物品收进行囊。路上需要时，按 B 打开。" % count if result.get("ok", false) else "这一类行囊已满，可以逐件领取或先使用一些补给。")
		_refresh_panel())
	inventory_view.setup(model, modal_kind)

func _item_action(action: String, id: String, allow_waste: bool) -> void:
	var record: Dictionary = GameState.items.instances.get(id, {}).duplicate()
	var title := "这件物品"
	if not record.is_empty(): title = GameState.items.Catalog.label(GameState.items.definitions[record.item_id].name)
	var result: Dictionary = model.use_item(action, id, allow_waste)
	if result.get("ok", false):
		var message: String = {
			"pack": "%s已收进行囊。", "store": "%s已存入住处收纳箱，腾出了随身空间。",
			"consume": "%s用好了。", "place": "%s已安放，可以继续使用。",
			"use_home": "%s已用上。", "deactivate": "%s已收起。", "reclaim": "%s已收回行囊。"
		}.get(action, "%s已处理。") % title
		if action == "consume":
			var definition: Dictionary = GameState.items.definitions[record.item_id]
			if definition.category == "food": message = "吃了一份%s。" % title
			elif record.item_id == "drink_canteen":
				var remaining: int = GameState.items.instances[id].uses
				message = "喝了一口水。" + ("水壶还可喝 %d 次。" % remaining if remaining > 0 else "水壶里的水喝完了。")
			else: message = "喝了%s。" % title
		if record.item_id == "home_blanket" and action == "use_home": message = "毯子已铺好。"
		var effects: Array[String] = []
		for key in result.get("effects", {}):
			if float(result.effects[key]) > 0:
				effects.append("%s +%d" % [{"food": "饱腹", "warmth": "温暖", "energy": "精力"}[key], int(result.effects[key])])
		if not effects.is_empty(): message += "  " + " · ".join(effects)
		if result.get("action") == "install": message += " 加热器 %d / %d。" % [GameState.items.heater_progress, GameState.items.heater_required]
		if record.item_id == "home_blanket" and action == "use_home": message += " 今晚入睡时多恢复 20 点温暖。"
		_toast(message)
		_refresh_panel()
	else:
		var reason := str(result.get("reason", ""))
		_toast({"capacity": "这一类行囊已满，先使用补给或回小屋存放。", "full": "现在状态已满，留到需要时再用。", "waste": "可以先留着；现在使用会损失一部分效果。", "stale": "物品状态已变化，请重新选择。", "home_only": "回到小屋再使用。", "location": "物品已不在这里，或对话尚未结束。请重新选择。", "occupied": "这个位置已有物品，先使用或收回原来的物品。", "complete": "加热器已经修好了，不需要再安装零件。", "missing": "这件物品已经用完或转移，请选择另一件。", "unsafe": "当前不能使用物品，请先结束交流。"}.get(reason, "暂时无法使用。返回后重新选择物品试试。"))
		if reason == "waste" and is_instance_valid(inventory_view): inventory_view.request_confirmation(action, id)

func _growth_panel() -> void:
	modal_title.text = "成长手记  /  每一句，都算数"
	_row_label("旅程   %d / 3 夜     ·     词汇阶段   %s" % [mini(GameState.day - 1, 3), {"infant": "初识", "toddler": "起步", "youth": "日常交流", "professional": "熟练表达"}.get(Vocabulary.tier, "起步")], 25)
	_row_label("这是当前的词汇起点。听见新词、练习说出，再在交谈中使用，逐步积累自己的词汇。", 18, MUTED)
	for npc in Content.CAST:
		_row_label("%s    信任 %d" % [npc.capitalize(), GameState.relationships.get(npc, 0)], 19, ACCENT)
	for memory in GameState.memories:
		_row_label(tr(memory), 18, MUTED)
	_row_label("练习角  /  听见 → 说出 → 使用", 23)
	_row_label("练习不会扣状态。只有真实语音评分和真实对话会推进习得。", 17, MUTED)
	var words := {}
	for entry in Content.SOCIAL:
		for word in entry.words: words[word] = true
	for word in words:
		var state: String = Vocabulary.word_state(word)
		var label: String = {"": "尚未听见", "initial": "已有词汇", "heard": "听见", "spoken": "说出", "used": "使用"}.get(state, state)
		var button := _button(modal_body, "%s     ·     %s     →  练习" % [word, label], _practice.bind(word))
		button.disabled = GameState.game_finished

func _settings_panel() -> void:
	modal_title.text = "设置  /  按自己的节奏"
	_button(modal_body, "减少动态：" + ("开" if reduce_motion else "关"), func(): reduce_motion = not reduce_motion; _save_settings(); _refresh_panel())
	_button(modal_body, "文字显示：" + ("立即显示" if instant_text else "逐字出现"), func(): instant_text = not instant_text; _save_settings(); _refresh_panel())
	_button(modal_body, "对话字号：" + ("大" if large_text else "标准"), func(): large_text = not large_text; dialogue_text.add_theme_font_size_override("normal_font_size", 30 if large_text else 26); _save_settings(); _refresh_panel())
	_button(modal_body, "键盘 / 手柄按键设置", func(): _close_panel(); remap.open_panel())
	_button(modal_body, "保存进度", _save)
	_button(modal_body, "载入上次存档", _load_game)
	_button(modal_body, "操作说明", _open_panel.bind("help"))
	_button(modal_body, "开始新旅程…", _open_panel.bind("restart"))
	if SpeechAdapter.cloud_mode_enabled():
		_row_label("云端语音：" + ("已激活" if SpeechAdapter.cloud_activated() else "未激活"), 18, ACCENT)
		activation_input = LineEdit.new()
		activation_input.placeholder_text = "输入一次性激活码"
		activation_input.secret = true
		activation_input.custom_minimum_size.y = 46
		modal_body.add_child(activation_input)
		_button(modal_body, "激活语音", func():
			if not SpeechAdapter.activate_cloud(activation_input.text): modal_status.text = "请输入有效激活码，或稍后重试。"
			else: modal_status.text = "正在激活…")
	else:
		_row_label(model.voice_status, 17, MUTED)
		_button(modal_body, "重新检查语音连接", func(): model._check_local_service(); _refresh_panel())

func _activation_finished(success: bool, message: String) -> void:
	if modal_kind == "settings":
		modal_status.text = "激活完成。" if success else tr(message)
	_refresh()

func _play_social(index: int) -> void:
	_close_panel()
	model.play_social(index)

func _practice(word: String) -> void:
	_close_panel()
	if model.location == "home": model.travel("plaza")
	model.begin_practice(word)
	_refresh()
	record_button.grab_focus()

func _continue_journey() -> void:
	startup_pending = false
	_close_panel()
	if not bool(GameState.presentation_state.get("guide_seen", false)):
		_open_panel("guide")
	else:
		model.start()

func _new_journey() -> void:
	if FileAccess.file_exists(model.novel_save_path):
		var backup := str(model.novel_save_path) + ".backup-" + str(Time.get_unix_time_from_system())
		if DirAccess.copy_absolute(model.novel_save_path, backup) != OK:
			_toast("旧存档副本保存失败，尚未重置。请检查磁盘空间。")
			return
	startup_pending = false
	_close_panel()
	model.restart(false)
	_open_panel("guide")

func _end_practice() -> void:
	model.cancel_activity()
	model.start()
	_toast("练习已结束，可以继续交谈。")

func _save() -> void:
	_toast("进度已保存。" if model.save() else "保存失败，请检查磁盘空间后重试。")

func _load_game() -> void:
	model.cancel_activity()
	if GameState.load_game():
		model.location = str(Content.place(str(GameState.presentation_state.get("location", "plaza"))).id)
		model.history = GameState.presentation_state.get("history", []).duplicate(true)
		GameState.onboarding_active = false
		Vocabulary.sync_from_game_state()
		_close_panel()
		model.start()
		_toast("已载入进度。")
	else: _toast("没有可读取的存档。")

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.echo: return
	if event.is_action_pressed("pause") or event.is_action_pressed("ui_cancel"):
		if modal.visible: _close_panel()
		else: _open_panel("settings")
		get_viewport().set_input_as_handled()
		return
	if modal.visible or (remap != null and remap.visible): return
	if model.social_index >= 0:
		if event.is_action_pressed("interact") or (event is InputEventKey and event.pressed and event.keycode in [KEY_RIGHT, KEY_SPACE]): _advance()
		elif event.is_action_pressed("item_show"): _open_panel("bag")
		return
	if event.is_action_pressed("push_to_talk"): model.record()
	elif event.is_action_pressed("gesture"):
		if model.practice_word.is_empty(): model.greet()
		else: _toast("正在练词；点「结束练习」后再打招呼。")
	elif event.is_action_pressed("interact"):
		if model.practice_word.is_empty(): model.talk()
		else: _toast("正在练词；点「结束练习」后再交谈。")
	elif event.is_action_pressed("item_show"): _open_panel("bag")
	elif event is InputEventKey and event.pressed:
		if event.keycode >= KEY_1 and event.keycode <= KEY_6:
			_travel(Content.PLACES[event.keycode - KEY_1].id)
		elif event.keycode == KEY_B: _open_panel("bag")
		elif event.keycode == KEY_RIGHT or event.keycode == KEY_SPACE: _advance()

func _load_settings() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS) == OK:
		reduce_motion = bool(config.get_value("view", "reduce_motion", false))
		instant_text = bool(config.get_value("view", "instant_text", false))
		large_text = bool(config.get_value("view", "large_text", false))

func _save_settings() -> void:
	var config := ConfigFile.new()
	config.set_value("view", "reduce_motion", reduce_motion)
	config.set_value("view", "instant_text", instant_text)
	config.set_value("view", "large_text", large_text)
	config.save(SETTINGS)

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST and model != null and not startup_pending:
		model.cancel_activity()
		model.save()
