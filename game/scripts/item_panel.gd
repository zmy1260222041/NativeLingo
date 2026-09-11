extends PanelContainer
## A transient selector. All mutations go through GameState.item_command.
const Catalog := preload("res://scripts/item_catalog.gd")
const SiltInkPanelScript := preload("res://ui/silt_ink_panel.gd")
const ItemGlyphScript := preload("res://ui/item_glyph.gd")
const SETTINGS_PATH := "user://stranger_accessibility.cfg"
const COLOR_INK := Color("17243b")
const COLOR_PANEL := Color("111a2be8")
const COLOR_TEXT := Color("f5e9d2")
const COLOR_MUTED := Color("b9c4cf")
const COLOR_MINT := Color("78c9a4")
const COLOR_TEAL := Color("2f8c87")
const COLOR_GOLD := Color("ffc857")
var mode := "carried"
var location := "player"
var selected := 0
var entries: Array[Dictionary] = []
var row_buttons: Array[Button] = []
var primary: Button
var secondary: Button
var pack_all: Button
var header: Label
var subtitle: Label
var capacity: Label
var detail: Label
var status: Label
var list: VBoxContainer
var scroll: ScrollContainer
var column: VBoxContainer
var close_button: Button
var row_selection_marks: Array[ColorRect] = []
var row_normal_style: StyleBoxFlat
var row_selected_style: StyleBoxFlat
var row_focus_style: StyleBoxFlat
var primary_style: StyleBoxFlat
var secondary_style: StyleBoxFlat
var toggle_mode := false
var gamepad := false
var device_id := -1
var confirmed_waste_id := ""
var viewed_revision := -1
var previous_mouse_mode := Input.MOUSE_MODE_CAPTURED
var suppressed_hud_modulates: Dictionary = {}

func _ready() -> void:
	name = "ItemPanel"
	process_mode = Node.PROCESS_MODE_ALWAYS
	add_to_group("item_panel")
	visible = false
	mouse_filter = Control.MOUSE_FILTER_STOP
	add_theme_stylebox_override("panel", SiltInkPanelScript.new())
	_build_styles()
	column = VBoxContainer.new()
	column.add_theme_constant_override("separation", 9)
	add_child(column)
	var top := HBoxContainer.new()
	top.name = "HeaderRow"
	top.add_theme_constant_override("separation", 10)
	column.add_child(top)
	var title_stack := VBoxContainer.new()
	title_stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_stack.add_theme_constant_override("separation", 0)
	top.add_child(title_stack)
	header = Label.new()
	header.name = "Title"
	header.add_theme_font_size_override("font_size", 28)
	header.add_theme_color_override("font_color", COLOR_TEXT)
	header.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title_stack.add_child(header)
	subtitle = Label.new()
	subtitle.name = "Subtitle"
	subtitle.add_theme_font_size_override("font_size", 16)
	subtitle.add_theme_color_override("font_color", COLOR_MUTED)
	subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	title_stack.add_child(subtitle)
	close_button = Button.new()
	close_button.name = "CloseButton"
	close_button.text = "×"
	close_button.tooltip_text = _text("关闭物品界面", "Close item panel")
	close_button.custom_minimum_size = Vector2(46, 46)
	close_button.add_theme_font_size_override("font_size", 27)
	close_button.add_theme_stylebox_override("normal", secondary_style)
	close_button.add_theme_stylebox_override("hover", row_focus_style)
	close_button.add_theme_stylebox_override("focus", row_focus_style)
	close_button.add_theme_stylebox_override("pressed", row_selected_style)
	close_button.pressed.connect(close_panel)
	top.add_child(close_button)
	capacity = Label.new()
	capacity.name = "Capacity"
	capacity.add_theme_font_size_override("font_size", 17)
	capacity.add_theme_color_override("font_color", COLOR_MUTED)
	capacity.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(capacity)
	var ribbon := HBoxContainer.new()
	ribbon.name = "Ribbon"
	ribbon.add_theme_constant_override("separation", 5)
	column.add_child(ribbon)
	var ribbon_lead := ColorRect.new()
	ribbon_lead.color = COLOR_MINT
	ribbon_lead.custom_minimum_size = Vector2(48, 4)
	ribbon.add_child(ribbon_lead)
	var ribbon_tail := ColorRect.new()
	ribbon_tail.color = Color("456174")
	ribbon_tail.custom_minimum_size = Vector2(86, 2)
	ribbon.add_child(ribbon_tail)
	scroll = ScrollContainer.new()
	scroll.name = "ItemScroll"
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	list = VBoxContainer.new()
	list.name = "ItemList"
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.add_theme_constant_override("separation", 6)
	scroll.add_child(list)
	var detail_shell := PanelContainer.new()
	detail_shell.name = "DetailCard"
	detail_shell.add_theme_stylebox_override("panel", _card_style(Color("17243bcc"), COLOR_INK, 1))
	column.add_child(detail_shell)
	detail = Label.new()
	detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	detail.add_theme_font_size_override("font_size", 18)
	detail_shell.add_child(detail)
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.add_theme_font_size_override("font_size", 17)
	status.add_theme_color_override("font_color", COLOR_GOLD)
	status.visible = false
	column.add_child(status)
	primary = Button.new()
	primary.add_theme_stylebox_override("normal", primary_style)
	primary.add_theme_stylebox_override("hover", row_focus_style)
	primary.add_theme_stylebox_override("focus", row_focus_style)
	primary.add_theme_stylebox_override("pressed", row_selected_style)
	primary.pressed.connect(func(): execute(false))
	column.add_child(primary)
	secondary = Button.new()
	secondary.add_theme_stylebox_override("normal", secondary_style)
	secondary.add_theme_stylebox_override("hover", row_focus_style)
	secondary.add_theme_stylebox_override("focus", row_focus_style)
	secondary.add_theme_stylebox_override("pressed", row_selected_style)
	secondary.pressed.connect(func(): execute(true))
	column.add_child(secondary)
	pack_all = Button.new()
	pack_all.add_theme_stylebox_override("normal", secondary_style)
	pack_all.add_theme_stylebox_override("hover", row_focus_style)
	pack_all.add_theme_stylebox_override("focus", row_focus_style)
	pack_all.add_theme_stylebox_override("pressed", row_selected_style)
	pack_all.pressed.connect(_pack_all)
	column.add_child(pack_all)
	GameState.item_interaction_requested.connect(open_world)
	GameState.items_changed.connect(_on_items_changed)
	GameState.day_started.connect(func(_day): close_panel())
	GameState.item_interaction_interrupted.connect(close_panel)
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) == OK:
		toggle_mode = bool(config.get_value("accessibility", "item_toggle_mode", false))
	get_viewport().size_changed.connect(_layout)
	_layout.call_deferred()


func _build_styles() -> void:
	row_normal_style = _card_style(Color("17243ba6"), COLOR_INK, 2)
	row_selected_style = _card_style(Color("2f8c8768"), COLOR_INK, 2)
	row_focus_style = _card_style(Color("2f8c8788"), COLOR_MINT, 3)
	primary_style = _card_style(Color("2f8c877a"), COLOR_INK, 2)
	secondary_style = _card_style(Color("1c3546c9"), COLOR_INK, 2)


func _card_style(background: Color, border: Color, width: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = background
	style.border_color = border
	style.set_border_width_all(width)
	style.corner_radius_top_left = 12
	style.corner_radius_top_right = 4
	style.corner_radius_bottom_right = 12
	style.corner_radius_bottom_left = 12
	style.content_margin_left = 14
	style.content_margin_right = 14
	style.content_margin_top = 9
	style.content_margin_bottom = 9
	return style

func _text(zh: String, en: String) -> String:
	return zh if TranslationServer.get_locale().begins_with("zh") else en

func _player() -> Node:
	return get_tree().get_first_node_in_group("player")

func _blocked() -> bool:
	var service := get_tree().root.get_node_or_null("NpcDialogueService")
	return get_tree().paused or GameState.game_finished or GameState.interaction_time_frozen \
		or SpeechAdapter.is_interaction_active() or (service != null and service.has_active_session())

func _process(_delta: float) -> void:
	if not visible:
		return
	# Wrapped labels can raise minimum height during the first container layout.
	# Reapply the viewport constraint once widths have settled, including font changes.
	_layout()
	if _blocked() or (mode != "carried" and not _near_location()):
		close_panel()
		return
	if mode == "carried" and not toggle_mode and not Input.is_action_pressed("item_show"):
		close_panel()
		return
	if viewed_revision != GameState.items.revision:
		_refresh()

func _input(event: InputEvent) -> void:
	if event is InputEventJoypadButton or event is InputEventJoypadMotion:
		gamepad = true
		device_id = event.device
	elif event is InputEventKey or event is InputEventMouseButton:
		gamepad = false
	if _blocked():
		close_panel()
		return
	if event.is_action_pressed("item_show") and not event.is_echo():
		if visible:
			close_panel()
		else:
			open_carried()
		get_viewport().set_input_as_handled()
		return
	if not visible:
		return
	if event.is_action_pressed("pause") or event.is_action_pressed("push_to_talk") or event.is_action_pressed("gesture"):
		close_panel()
		return
	if event.is_action_released("item_show") and mode == "carried" and not toggle_mode:
		close_panel()
		get_viewport().set_input_as_handled()
		return
	if event.is_echo():
		return
	var handled := true
	if event.is_action_pressed("ui_cancel"):
		close_panel()
	elif event.is_action_pressed("item_next"):
		_select(selected + 1)
	elif event.is_action_pressed("item_previous"):
		_select(selected - 1)
	elif event.is_action_pressed("interact") or event.is_action_pressed("ui_accept"):
		execute(false)
	elif event.is_action_pressed("item_secondary"):
		execute(true)
	elif event.is_action_pressed("item_pack_all"):
		_pack_all()
	else:
		handled = false
	if handled:
		get_viewport().set_input_as_handled()

func open_carried() -> void:
	if _blocked():
		return
	mode = "carried"
	location = "player"
	_open()

func open_world(kind: String, target: String) -> void:
	if _blocked():
		return
	mode = "counter" if kind == "item_counter" else "home"
	location = target
	if not _near_location():
		return
	_open()

func _open() -> void:
	if not visible:
		previous_mouse_mode = Input.mouse_mode
	visible = true
	_set_background_feedback_suppressed(true)
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	selected = 0
	confirmed_waste_id = ""
	status.text = ""
	status.visible = false
	_refresh()
	_layout()
	_focus_selected.call_deferred()

func close_panel() -> void:
	if not visible:
		return
	visible = false
	confirmed_waste_id = ""
	var focus := get_viewport().gui_get_focus_owner()
	if focus != null and is_ancestor_of(focus):
		focus.release_focus()
	_set_background_feedback_suppressed(false)
	if not get_tree().paused:
		Input.mouse_mode = previous_mouse_mode


func _set_background_feedback_suppressed(active: bool) -> void:
	var ui_root := get_parent()
	if ui_root == null:
		return
	for path in [
		NodePath("SafeAreaRoot/HudRoot/InteractionAnchor"),
		NodePath("SafeAreaRoot/HudRoot/ToastAnchor"),
	]:
		var control := ui_root.get_node_or_null(path) as Control
		if control == null:
			continue
		var key := str(path)
		if active:
			if not suppressed_hud_modulates.has(key):
				suppressed_hud_modulates[key] = control.modulate
			var hidden := control.modulate
			hidden.a = 0.0
			control.modulate = hidden
		elif suppressed_hud_modulates.has(key):
			control.modulate = suppressed_hud_modulates[key]
			suppressed_hud_modulates.erase(key)

func _near_location() -> bool:
	var player := _player() as Node3D
	if player == null:
		return false
	var world := get_tree().get_first_node_in_group("item_world")
	if world == null or not world.anchors.has(location):
		return false
	var anchor: Node3D = world.anchors[location]
	var offset := player.global_position - anchor.global_position
	return Vector2(offset.x, offset.z).length() <= 4.0

func _on_items_changed() -> void:
	# Signal is emitted after a complete transaction. Defer GUI rebuild until the callback returns.
	if visible:
		_refresh.call_deferred()

func _refresh() -> void:
	viewed_revision = GameState.items.revision
	entries.clear()
	row_buttons.clear()
	row_selection_marks.clear()
	for child in list.get_children():
		list.remove_child(child)
		child.queue_free()
	for record in GameState.items.instances.values():
		if mode == "carried" and record.state == "carried":
			entries.append(record.duplicate(true))
		elif mode == "counter" and record.state == "counter" and record.location == location:
			entries.append(record.duplicate(true))
		elif mode == "home" and ((record.location == location and record.state in ["placed", "active", "storage"]) or record.state == "carried"):
			entries.append(record.duplicate(true))
	var title := _text("随身物品", "Carried items")
	var supporting := _text("可支配的生存物资", "Survival supplies you control")
	if mode == "counter":
		title = _text("柜台物资", "Counter supplies")
		supporting = _text("现场使用，或打包带走", "Use here, or pack for later")
	elif mode == "home":
		title = Catalog.label(Catalog.HOME_SLOTS[location].name)
		supporting = _text("住所用品先放置，再使用", "Place home goods before using them")
	header.text = title
	subtitle.text = supporting
	capacity.text = _text(
		"携带容量　吃喝 %d / 4　·　住所用品 %d / 1",
		"CARRY CAPACITY   FOOD + DRINK %d / 4   ·   HOME GOODS %d / 1",
	) % [GameState.items.used_slots("consumable"), GameState.items.used_slots("residence")]
	for index in range(entries.size()):
		var record: Dictionary = entries[index]
		_add_item_row(record, index)
	if entries.is_empty():
		var empty := Label.new()
		empty.text = _text(
			"这里还没有物品。\n与店员交流，获取自己能支配的生存物资。",
			"Nothing here yet.\nTalk with a shopkeeper to obtain survival supplies you can control.",
		)
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		empty.add_theme_color_override("font_color", COLOR_MUTED)
		empty.add_theme_font_size_override("font_size", 18)
		list.add_child(empty)
	selected = clampi(selected, 0, maxi(0, entries.size() - 1))
	_update_actions()
	_layout.call_deferred()


func _add_item_row(record: Dictionary, index: int) -> void:
	var definition: Dictionary = GameState.items.definitions[record.item_id]
	var row := Button.new()
	row.name = "ItemRow%d" % index
	row.text = ""
	row.custom_minimum_size.y = 52
	row.tooltip_text = "%s · %s · %d" % [Catalog.label(definition.name), _state_label(record.state), record.uses]
	row.add_theme_stylebox_override("normal", row_normal_style)
	row.add_theme_stylebox_override("hover", row_focus_style)
	row.add_theme_stylebox_override("focus", row_focus_style)
	row.add_theme_stylebox_override("pressed", row_selected_style)
	row.pressed.connect(_select.bind(index))
	list.add_child(row)
	row_buttons.append(row)
	var mark := ColorRect.new()
	mark.color = COLOR_MINT
	mark.mouse_filter = Control.MOUSE_FILTER_IGNORE
	mark.set_anchors_preset(Control.PRESET_LEFT_WIDE)
	mark.offset_right = 5
	row.add_child(mark)
	row_selection_marks.append(mark)
	var margin := MarginContainer.new()
	margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 13)
	margin.add_theme_constant_override("margin_right", 13)
	margin.add_theme_constant_override("margin_top", 5)
	margin.add_theme_constant_override("margin_bottom", 5)
	row.add_child(margin)
	var content := HBoxContainer.new()
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_theme_constant_override("separation", 10)
	margin.add_child(content)
	var glyph := ItemGlyphScript.new()
	glyph.name = "CategoryGlyph"
	glyph.kind = "home" if definition.carry_category == "residence" else definition.category
	content.add_child(glyph)
	var item_name := Label.new()
	item_name.text = Catalog.label(definition.name)
	item_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	item_name.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	item_name.add_theme_color_override("font_color", COLOR_TEXT)
	content.add_child(item_name)
	var state_text := Label.new()
	state_text.text = "%s　×%d" % [_state_label(record.state), int(record.uses)]
	state_text.add_theme_font_size_override("font_size", 16)
	state_text.add_theme_color_override("font_color", COLOR_MUTED)
	content.add_child(state_text)

func _state_label(state: String) -> String:
	var labels := {"counter": ["待领取", "Waiting"], "carried": ["随身", "Carried"], "placed": ["已放置", "Placed"], "active": ["已铺好", "Active"], "storage": ["存放中", "Stored"]}
	return Catalog.label(labels.get(state, [state, state]))

func _select(index: int) -> void:
	if entries.is_empty():
		return
	selected = posmod(index, entries.size())
	confirmed_waste_id = ""
	status.text = ""
	status.visible = false
	_update_actions()
	row_buttons[selected].grab_focus()
	scroll.ensure_control_visible(row_buttons[selected])

func _actions(record: Dictionary) -> Array:
	var definition: Dictionary = GameState.items.definitions[record.item_id]
	if record.state in ["counter", "storage"]:
		return ["consume", "pack"] if record.state == "counter" and definition.category in ["food", "drink"] else ["pack", ""]
	if record.state in ["placed", "active"]:
		return ["use_home" if record.state == "placed" else "deactivate", "reclaim"]
	if mode == "home" and (location == "home_storage" or definition.carry_category == "residence"):
		return ["place", ""]
	return ["consume", ""] if definition.category in ["food", "drink"] else ["", ""]

func _action_label(action: String) -> String:
	var labels := {"consume": ["吃 / 喝一份", "Eat / drink one"], "pack": ["打包带走", "Pack for later"], "place": ["放到这里", "Place here"],
		"use_home": ["铺好 / 安装 / 使用", "Set up / install / use"], "deactivate": ["停用，留在这里", "Deactivate, leave here"], "reclaim": ["收回随身", "Take back"], "": ["带回住处使用", "Use at home"]}
	if not entries.is_empty():
		var category: String = GameState.items.definitions[entries[selected].item_id].category
		if action == "consume":
			if mode == "counter":
				return _text("现场吃一份", "Eat one here") if category == "food" else _text("现场喝一次", "Drink one here")
			return _text("吃一份", "Eat one") if category == "food" else _text("喝一次", "Drink one")
		if action == "use_home":
			return Catalog.label({"durable": ["铺好", "Set up"], "component": ["安装", "Install"], "home_consumable": ["使用一次", "Use once"]}[category])
	return Catalog.label(labels[action])

func _update_actions() -> void:
	primary.disabled = entries.is_empty()
	secondary.visible = false
	pack_all.visible = mode == "counter" and entries.size() > 1
	pack_all.text = "[%s] %s" % [InputGlyphs.for_action("item_pack_all", gamepad, device_id), _text("全部打包带走", "Pack everything for later")]
	if entries.is_empty():
		detail.text = ""
		detail.get_parent().visible = false
		primary.text = _text("没有可用物品", "No items")
		_configure_focus_loop()
		return
	detail.get_parent().visible = true
	var record: Dictionary = entries[selected]
	var actions := _actions(record)
	primary.disabled = actions[0].is_empty()
	primary.text = "[%s] %s" % [InputGlyphs.for_action("interact", gamepad, device_id), _action_label(actions[0])]
	secondary.visible = not actions[1].is_empty()
	secondary.text = "[%s] %s" % [InputGlyphs.for_action("item_secondary", gamepad, device_id), _action_label(actions[1])]
	var definition: Dictionary = GameState.items.definitions[record.item_id]
	detail.text = Catalog.label(definition.name) + "　·　" + _state_label(record.state)
	if definition.carry_category == "residence":
		detail.text += "\n" + _text("下一步　带回住处，先放置再使用", "NEXT   Take it home, place it, then use it")
		detail.text += "\n" + _text("使用位置　", "HOME POSITION   ") + Catalog.label(Catalog.HOME_SLOTS[definition.home_slot].name)
	else:
		detail.text += "\n" + _text("恢复效果　", "RESTORES   ") + _effects_label(definition.effects)
		detail.text += "\n" + (_text("可使用 %d 次", "%d uses remaining") % int(record.uses))
	for index in range(row_buttons.size()):
		row_buttons[index].add_theme_stylebox_override("normal", row_selected_style if index == selected else row_normal_style)
		row_selection_marks[index].visible = index == selected
	_configure_focus_loop()


func _effects_label(effects: Dictionary) -> String:
	var pieces: Array[String] = []
	for key in ["food", "warmth", "energy"]:
		var value := int(effects.get(key, 0))
		if value > 0:
			var effect_labels := {"food": _text("食物", "Food"), "warmth": _text("温暖", "Warmth"), "energy": _text("精力", "Energy")}
			var label: String = effect_labels[key]
			pieces.append("%s +%d" % [label, value])
	return "　·　".join(pieces)


func _configure_focus_loop() -> void:
	var controls: Array[Button] = []
	controls.append_array(row_buttons)
	if not primary.disabled:
		controls.append(primary)
	if secondary.visible:
		controls.append(secondary)
	if pack_all.visible:
		controls.append(pack_all)
	controls.append(close_button)
	for index in range(controls.size()):
		var control := controls[index]
		var previous := controls[posmod(index - 1, controls.size())]
		var next := controls[(index + 1) % controls.size()]
		control.focus_previous = control.get_path_to(previous)
		control.focus_next = control.get_path_to(next)
		control.focus_neighbor_top = control.get_path_to(previous)
		control.focus_neighbor_bottom = control.get_path_to(next)
		control.focus_neighbor_left = control.get_path_to(previous)
		control.focus_neighbor_right = control.get_path_to(next)


func _focus_selected() -> void:
	if not visible:
		return
	if not row_buttons.is_empty():
		row_buttons[selected].grab_focus()
	else:
		close_button.grab_focus()

func execute(alternate: bool) -> void:
	if entries.is_empty() or _blocked():
		return
	var record: Dictionary = entries[selected]
	var action: String = _actions(record)[1 if alternate else 0]
	if action.is_empty():
		return
	var player := _player()
	var safe: bool = player != null and player.item_use_is_safe()
	if mode != "carried" and not _near_location():
		close_panel()
		return
	var origin: String = record.location if action == "consume" else location
	var context := {"safe": safe, "location": origin, "at_home": mode == "home", "revision": viewed_revision}
	var result: Dictionary = GameState.item_command(action, [record.id], context, confirmed_waste_id == record.id)
	if result.get("reason", "") == "waste":
		confirmed_waste_id = record.id
		status.text = _text("部分效果会浪费。再按一次使用确认，或取消保留。", "Some benefit will be wasted. Use again to confirm, or cancel to keep it.")
		status.visible = true
		return
	confirmed_waste_id = ""
	_show_result(result)
	if result.ok:
		if player.character_visual != null:
			player.character_visual.play_environment_interaction("shelter" if mode == "home" else "berry")
		_refresh()

func _pack_all() -> void:
	if mode != "counter" or not _near_location() or _blocked():
		return
	var ids: Array = entries.map(func(record): return record.id)
	var player := _player()
	var result: Dictionary = GameState.item_command("pack", ids, {"safe": player != null and player.item_use_is_safe(), "location": location, "revision": viewed_revision})
	_show_result(result)
	if result.ok:
		_refresh()

func _show_result(result: Dictionary) -> void:
	var labels := {"capacity": ["对应携带位不足。可以逐份打包或存回住处。", "Not enough category slots. Pack fewer items or store them at home."],
		"full": ["现在不需要，物品已保留。", "You do not need this now. Item kept."], "unsafe": ["请在安全、非对话状态使用。", "Use while grounded, calm and outside a conversation."],
		"home_only": ["先带回住处放置。", "Place this at home first."], "wrong_slot": ["这里不适合这件用品。", "This item does not fit here."],
		"occupied": ["这个位置已被占用。", "This spot is occupied."], "complete": ["设施已完成。", "This facility is complete."],
		"stale": ["物品状态有变化，请重新选择。", "Items changed. Please select again."]}
	status.text = _text("已完成。", "Done.") if result.ok else Catalog.label(labels.get(result.get("reason", ""), ["暂时无法操作，物品已保留。", "Cannot do that now. Item kept."]))
	status.visible = true

func _layout() -> void:
	var viewport_size := get_viewport().get_visible_rect().size
	var scale := clampf(get_theme_default_base_scale(), 1.0, 1.5)
	var visible_rows := mini(entries.size(), 3 if scale >= 1.4 else 5)
	visible_rows = maxi(1, visible_rows)
	scroll.custom_minimum_size.y = visible_rows * 54.0 * scale + maxi(0, visible_rows - 1) * 6.0
	var maximum := Vector2(viewport_size.x * 0.90, viewport_size.y * 0.75)
	var minimum_height := minf(maximum.y, 350.0 * scale)
	var desired_height := clampf(get_combined_minimum_size().y, minimum_height, maximum.y)
	size = Vector2(minf(620.0, maximum.x), desired_height)
	position = Vector2((viewport_size.x - size.x) * 0.5, (viewport_size.y - size.y) * 0.5)

func set_toggle_mode(active: bool) -> void:
	toggle_mode = active
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	config.set_value("accessibility", "item_toggle_mode", active)
	config.save(SETTINGS_PATH)
