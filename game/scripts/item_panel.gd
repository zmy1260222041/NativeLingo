extends PanelContainer
## A transient selector. All mutations go through GameState.item_command.
const Catalog := preload("res://scripts/item_catalog.gd")
const SETTINGS_PATH := "user://stranger_accessibility.cfg"
var mode := "carried"
var location := "player"
var selected := 0
var entries: Array[Dictionary] = []
var row_buttons: Array[Button] = []
var primary: Button
var secondary: Button
var pack_all: Button
var header: Label
var detail: Label
var status: Label
var list: VBoxContainer
var scroll: ScrollContainer
var toggle_mode := false
var gamepad := false
var device_id := -1
var confirmed_waste_id := ""
var viewed_revision := -1
var previous_mouse_mode := Input.MOUSE_MODE_CAPTURED

func _ready() -> void:
	name = "ItemPanel"
	process_mode = Node.PROCESS_MODE_ALWAYS
	add_to_group("item_panel")
	visible = false
	var style := StyleBoxFlat.new()
	style.bg_color = Color("292d32")
	style.border_color = Color("9dbea6")
	style.set_border_width_all(2)
	style.set_corner_radius_all(12)
	style.content_margin_left = 16
	style.content_margin_right = 16
	style.content_margin_top = 14
	style.content_margin_bottom = 14
	add_theme_stylebox_override("panel", style)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 7)
	add_child(column)
	header = Label.new()
	header.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(header)
	scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)
	list = VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
	detail = Label.new()
	detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(detail)
	primary = Button.new()
	primary.pressed.connect(func(): execute(false))
	column.add_child(primary)
	secondary = Button.new()
	secondary.pressed.connect(func(): execute(true))
	column.add_child(secondary)
	pack_all = Button.new()
	pack_all.pressed.connect(_pack_all)
	column.add_child(pack_all)
	status = Label.new()
	status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status.add_theme_color_override("font_color", Color("efc995"))
	column.add_child(status)
	var close := Button.new()
	close.text = _text("关闭", "Close")
	close.pressed.connect(close_panel)
	column.add_child(close)
	GameState.item_interaction_requested.connect(open_world)
	GameState.items_changed.connect(_on_items_changed)
	GameState.day_started.connect(func(_day): close_panel())
	GameState.item_interaction_interrupted.connect(close_panel)
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) == OK:
		toggle_mode = bool(config.get_value("accessibility", "item_toggle_mode", false))
	get_viewport().size_changed.connect(_layout)
	_layout.call_deferred()

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
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	selected = 0
	confirmed_waste_id = ""
	status.text = ""
	_refresh()
	_layout()

func close_panel() -> void:
	if not visible:
		return
	visible = false
	confirmed_waste_id = ""
	var focus := get_viewport().gui_get_focus_owner()
	if focus != null and is_ancestor_of(focus):
		focus.release_focus()
	if not get_tree().paused:
		Input.mouse_mode = previous_mouse_mode

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
	if mode == "counter":
		title = _text("柜台 · 逐份处理", "Counter · choose each portion")
	elif mode == "home":
		title = Catalog.label(Catalog.HOME_SLOTS[location].name)
	header.text = title + "\n" + (_text("吃喝 %d/4 位 · 住所用品 %d/1 位", "Food/drink %d/4 slots · Home goods %d/1 slots") % [GameState.items.used_slots("consumable"), GameState.items.used_slots("residence")])
	for index in range(entries.size()):
		var record: Dictionary = entries[index]
		var definition: Dictionary = GameState.items.definitions[record.item_id]
		var row := Button.new()
		row.alignment = HORIZONTAL_ALIGNMENT_LEFT
		row.text = "%s  ·  %s  ·  %d" % [Catalog.label(definition.name), _state_label(record.state), record.uses]
		row.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		row.tooltip_text = row.text
		row.pressed.connect(_select.bind(index))
		list.add_child(row)
		row_buttons.append(row)
	if entries.is_empty():
		var empty := Label.new()
		empty.text = _text("这里没有物品。可以和店员交流获取。", "No items here. Ask a shopkeeper for supplies.")
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		list.add_child(empty)
	selected = clampi(selected, 0, maxi(0, entries.size() - 1))
	_update_actions()

func _state_label(state: String) -> String:
	var labels := {"counter": ["待领取", "Waiting"], "carried": ["随身", "Carried"], "placed": ["已放置", "Placed"], "active": ["已铺好", "Active"], "storage": ["存放中", "Stored"]}
	return Catalog.label(labels.get(state, [state, state]))

func _select(index: int) -> void:
	if entries.is_empty():
		return
	selected = posmod(index, entries.size())
	confirmed_waste_id = ""
	status.text = ""
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
	var labels := {"consume": ["吃 / 喝一份", "Eat / drink one"], "pack": ["打包一份", "Pack one"], "place": ["放到这里", "Place here"],
		"use_home": ["铺好 / 安装 / 使用", "Set up / install / use"], "deactivate": ["停用，留在这里", "Deactivate, leave here"], "reclaim": ["收回随身", "Take back"], "": ["带回住处使用", "Use at home"]}
	if not entries.is_empty():
		var category: String = GameState.items.definitions[entries[selected].item_id].category
		if action == "consume":
			return _text("吃一份", "Eat one") if category == "food" else _text("喝一次", "Drink once")
		if action == "use_home":
			return Catalog.label({"durable": ["铺好", "Set up"], "component": ["安装", "Install"], "home_consumable": ["使用一次", "Use once"]}[category])
	return Catalog.label(labels[action])

func _update_actions() -> void:
	primary.disabled = entries.is_empty()
	secondary.visible = false
	pack_all.visible = mode == "counter" and entries.size() > 1
	pack_all.text = "[%s] %s" % [InputGlyphs.for_action("item_pack_all", gamepad, device_id), _text("整批打包", "Pack all")]
	if entries.is_empty():
		detail.text = ""
		primary.text = _text("没有可用物品", "No items")
		return
	var record: Dictionary = entries[selected]
	var actions := _actions(record)
	primary.disabled = actions[0].is_empty()
	primary.text = "[%s] %s" % [InputGlyphs.for_action("interact", gamepad, device_id), _action_label(actions[0])]
	secondary.visible = not actions[1].is_empty()
	secondary.text = "[%s] %s" % [InputGlyphs.for_action("item_secondary", gamepad, device_id), _action_label(actions[1])]
	var definition: Dictionary = GameState.items.definitions[record.item_id]
	detail.text = Catalog.label(definition.name) + " · " + _state_label(record.state)
	if definition.carry_category == "residence":
		detail.text += "\n" + _text("带回住处，先放置再使用：", "At home, place first, then use: ") + Catalog.label(Catalog.HOME_SLOTS[definition.home_slot].name)
	else:
		detail.text += "\n" + _text("食物 / 温暖 / 精力：", "Food / warmth / energy: ") + "%d / %d / %d" % [definition.effects.food, definition.effects.warmth, definition.effects.energy]
		detail.text += "\n" + (_text("剩余 %d 次", "%d uses left") % int(record.uses))
	for index in range(row_buttons.size()):
		row_buttons[index].modulate = Color.WHITE if index == selected else Color("a5aeb4")

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

func _layout() -> void:
	var viewport_size := get_viewport().get_visible_rect().size
	size = Vector2(minf(560.0, viewport_size.x * 0.88), viewport_size.y * 0.72)
	position = Vector2((viewport_size.x - size.x) * 0.5, viewport_size.y * 0.12)

func set_toggle_mode(active: bool) -> void:
	toggle_mode = active
	var config := ConfigFile.new()
	config.load(SETTINGS_PATH)
	config.set_value("accessibility", "item_toggle_mode", active)
	config.save(SETTINGS_PATH)
