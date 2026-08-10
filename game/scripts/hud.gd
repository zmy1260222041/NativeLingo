extends CanvasLayer

var title_label: Label
var day_label: Label
var objective_label: Label
var needs_label: Label
var prompt_label: Label
var message_panel: PanelContainer
var message_label: Label
var message_timer: Timer

func _ready() -> void:
	_build_ui()
	GameState.state_changed.connect(_refresh)
	GameState.message_requested.connect(_show_message)
	GameState.run_completed.connect(_show_completion)
	_refresh()

func _process(_delta: float) -> void:
	var player := get_tree().get_first_node_in_group("player") as PlayerController
	if player:
		prompt_label.text = player.interaction_prompt()

func _build_ui() -> void:
	var root := Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(root)

	var top_panel := PanelContainer.new()
	top_panel.position = Vector2(28, 24)
	top_panel.custom_minimum_size = Vector2(465, 0)
	root.add_child(top_panel)
	var top_box := VBoxContainer.new()
	top_box.add_theme_constant_override("separation", 6)
	top_panel.add_child(top_box)
	title_label = Label.new()
	title_label.text = "异乡人  /  STRANGER"
	title_label.add_theme_font_size_override("font_size", 28)
	top_box.add_child(title_label)
	day_label = Label.new()
	day_label.add_theme_font_size_override("font_size", 17)
	top_box.add_child(day_label)
	objective_label = Label.new()
	objective_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	objective_label.custom_minimum_size = Vector2(430, 42)
	objective_label.add_theme_font_size_override("font_size", 18)
	top_box.add_child(objective_label)

	needs_label = Label.new()
	needs_label.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	needs_label.position = Vector2(-330, 28)
	needs_label.size = Vector2(300, 90)
	needs_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	needs_label.add_theme_font_size_override("font_size", 17)
	root.add_child(needs_label)

	prompt_label = Label.new()
	prompt_label.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	prompt_label.position = Vector2(-330, -92)
	prompt_label.size = Vector2(660, 44)
	prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	prompt_label.add_theme_font_size_override("font_size", 20)
	root.add_child(prompt_label)

	var help := Label.new()
	help.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	help.position = Vector2(26, -62)
	help.size = Vector2(650, 34)
	help.text = "WASD 移动 · Shift 冲刺 · Space 跳跃 · 鼠标观察 · Esc 释放鼠标 · F9 重置切片"
	help.add_theme_font_size_override("font_size", 14)
	root.add_child(help)

	message_panel = PanelContainer.new()
	message_panel.set_anchors_preset(Control.PRESET_CENTER)
	message_panel.position = Vector2(-330, 120)
	message_panel.custom_minimum_size = Vector2(660, 74)
	message_panel.visible = false
	root.add_child(message_panel)
	message_label = Label.new()
	message_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	message_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	message_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	message_label.add_theme_font_size_override("font_size", 19)
	message_panel.add_child(message_label)
	message_timer = Timer.new()
	message_timer.one_shot = true
	message_timer.wait_time = 4.5
	message_timer.timeout.connect(func(): message_panel.visible = false)
	add_child(message_timer)

func _refresh() -> void:
	day_label.text = "第 %d 天  ·  %02d:%02d" % [GameState.day, 7 + int(GameState.day_time / 60.0), int(GameState.day_time) % 60]
	objective_label.text = "当前目标：%s" % GameState.objective_text()
	needs_label.text = "食物  %3d%%\n温暖  %3d%%\n精力  %3d%%" % [GameState.food, GameState.warmth, GameState.energy]

func _show_message(text: String, _tone: String) -> void:
	message_label.text = text
	message_panel.visible = true
	message_timer.start()

func _show_completion() -> void:
	_show_message("你活过了三天，也第一次被这里的人称作朋友。\n《异乡人 / Stranger》纵向切片完成。", "good")
