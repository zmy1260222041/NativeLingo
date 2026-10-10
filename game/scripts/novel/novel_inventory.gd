extends VBoxContainer
## FR-47: browsable belongings. The controller and item ledger own all mutations.
signal action_requested(action: String, id: String, allow_waste: bool)
signal travel_requested(destination: String)
signal pack_all_requested
signal notice(text: String)
const Glyph := preload("res://ui/item_glyph.gd")
const Palette := preload("res://scripts/novel/novel_palette.gd")
const TEXT := Palette.TEXT
const MUTED := Palette.MUTED
const ACCENT := Palette.ACCENT
const POSITIVE := Palette.POSITIVE
const STATES := {"carried": "随身携带", "counter": "柜台待领取", "storage": "住处收纳箱", "placed": "已安放", "active": "使用中"}
const FILTERS := [["all", "全部"], ["food", "食物"], ["drink", "饮品"], ["home", "住所用品"]]
var model: Node
var mode := "bag"
var category := "all"
var selected := ""
var groups: Array = []
var list: VBoxContainer
var details: VBoxContainer
var summary: Label
var tabs: HBoxContainer
var confirmation: Dictionary = {}
var notice_label: Label
var row_buttons: Array[Button] = []
var action_buttons: Array[Button] = []

func setup(controller: Node, kind: String) -> void:
	model = controller
	mode = kind
	add_theme_constant_override("separation", 12)
	custom_minimum_size = Vector2(1056, 548)
	summary = _text(self, "", 17, MUTED)
	notice_label = _text(self, "", 17, ACCENT)
	notice_label.visible = false
	tabs = HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 8)
	add_child(tabs)
	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation", 22)
	columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_child(columns)
	list = _scroll_column(columns, 385)
	details = _scroll_column(columns, 638)
	details.add_theme_constant_override("separation", 10)
	refresh()

func _scroll_column(parent: Node, width: float) -> VBoxContainer:
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(width, 433)
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.follow_focus = true
	parent.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 10)
	scroll.add_child(column)
	return column

func _text(parent: Node, value: String, font_size := 20, color := TEXT) -> Label:
	var label := Label.new()
	label.text = value
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	if font_size >= 23: label.theme_type_variation = "NovelTitle"
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(label)
	return label

func _button(parent: Node, value: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = value
	button.custom_minimum_size.y = 44
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _clear(parent: Node) -> void:
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()

func refresh() -> void:
	var focused := get_viewport().gui_get_focus_owner()
	var focus_key: String = str(focused.get_meta("inventory_focus", "")) if focused != null and is_ancestor_of(focused) else ""
	if not confirmation.is_empty() and int(confirmation.revision) != GameState.items.revision:
		confirmation.clear()
	summary.text = "食物与饮品  %d / %d 格     ·     住所用品  %d / %d 格     ·     加热器  %d / %d" % [GameState.items.used_slots("consumable"), GameState.items.capacity.consumable, GameState.items.used_slots("residence"), GameState.items.capacity.residence, GameState.items.heater_progress, GameState.items.heater_required]
	_clear(tabs)
	for filter in FILTERS:
		var count := 0
		for group in model.item_groups(mode, filter[0]): count += group.ids.size()
		var button := _button(tabs, "%s  %d" % [filter[1], count], _filter.bind(filter[0]))
		button.set_meta("inventory_focus", "filter:" + filter[0])
		Palette.navigation(button, category == filter[0], true)
	if mode == "counter":
		var ids: Array = []
		for item in model.visible_items("counter"): ids.append(item.id)
		if ids.size() > 1:
			var all := _button(tabs, "全部收好 · %d 件" % ids.size(), func(): pack_all_requested.emit())
			all.disabled = not GameState.items.can_pack(ids) or GameState.game_finished
			all.set_meta("inventory_focus", "pack_all")
			all.tooltip_text = "全部装下需要更多空间；也可以逐件领取。" if all.disabled else "收好柜台上的全部物品"
	groups = model.item_groups(mode, category)
	if not groups.any(func(group): return group.key == selected):
		selected = str(groups[0].key) if not groups.is_empty() else ""
	_clear(list)
	row_buttons.clear()
	for group in groups:
		var definition: Dictionary = GameState.items.definitions[group.record.item_id]
		var title: String = GameState.items.Catalog.label(definition.name)
		var button := _button(list, "", _select.bind(group.key))
		button.custom_minimum_size.y = 92
		button.set_meta("inventory_focus", "item:" + group.key)
		Palette.navigation(button, selected == group.key)
		var glyph := Glyph.new()
		glyph.kind = _category(definition)
		glyph.ink_color = Palette.TEXT
		glyph.food_color = Palette.FOOD
		glyph.drink_color = Palette.DRINK
		glyph.home_color = Palette.HOME
		glyph.position = Vector2(14, 22)
		glyph.size = Vector2(46, 46)
		button.add_child(glyph)
		var label := _text(button, "%s  ×%d" % [title, group.ids.size()], 21)
		label.position = Vector2(76, 12)
		label.size = Vector2(290, 31)
		label = _text(button, str(STATES.get(group.record.state, "")) + (" · 剩余 %d 次" % group.record.uses if int(definition.uses) > 1 else ""), 16, MUTED)
		label.position = Vector2(76, 51)
		label.size = Vector2(290, 27)
		row_buttons.append(button)
	if groups.is_empty():
		_text(list, "还没有这类物品" if category != "all" else "留一点位置，装下今天。", 23, ACCENT)
		_text(list, "选择其他分类看看。" if category != "all" else "在柜台收好补给，路上饿了或渴了就能用。", 18, MUTED)
	_build_details()
	if not focus_key.is_empty():
		var candidates: Array = tabs.get_children() + row_buttons + action_buttons
		var restored := false
		for button in candidates:
			if str(button.get_meta("inventory_focus", "")) == focus_key and not button.disabled:
				button.grab_focus()
				restored = true
				break
		if not restored:
			if not row_buttons.is_empty(): row_buttons[0].grab_focus()
			else: tabs.get_child(0).grab_focus()

func _category(definition: Dictionary) -> String:
	return str(definition.category) if definition.category in ["food", "drink"] else "home"

func _filter(value: String) -> void:
	category = value
	selected = ""
	confirmation.clear()
	refresh()

func _select(key: String) -> void:
	selected = key
	confirmation.clear()
	refresh()

func selected_group() -> Dictionary:
	for group in groups:
		if group.key == selected: return group
	return {}

func _build_details() -> void:
	_clear(details)
	action_buttons.clear()
	var group := selected_group()
	if group.is_empty():
		if mode == "counter":
			_menu()
			return
		_text(details, "下一份日常，从这里开始。", 28)
		var guidance: Dictionary = model.inventory_guidance()
		_text(details, str(guidance.text), 20, MUTED)
		for link in guidance.links: _link(str(link[0]), str(link[1]))
		if mode == "counter": _menu()
		return
	var record: Dictionary = group.record
	var definition: Dictionary = GameState.items.definitions[record.item_id]
	var title: String = GameState.items.Catalog.label(definition.name)
	_text(details, str(definition.name[1]).to_upper() + "  /  " + str(STATES.get(record.state, "")), 15, ACCENT)
	_text(details, title, 32)
	if not confirmation.is_empty() and confirmation.id == record.id:
		_text(details, "现在使用会损失一部分效果。仍然使用？", 19, ACCENT)
		var confirm := _button(details, "确认使用这 1 件", _confirm)
		confirm.set_meta("inventory_focus", "confirm")
		action_buttons.append(confirm)
		var cancel := _button(details, "先留着", func(): confirmation.clear(); refresh())
		action_buttons.append(cancel)
	var sources: Array[String] = []
	for id in group.ids:
		var source: String = str(GameState.items.instances[id].source_service).capitalize()
		if source.is_empty() or source == "Player": source = "旅程中带来"
		if not sources.has(source): sources.append(source)
	_text(details, "来自 " + "、".join(sources) + "   ·   共 %d 件" % group.ids.size(), 16, MUTED)
	_text(details, model.item_description(record.item_id), 20)
	if definition.category in ["food", "drink", "home_consumable"]:
		var preview: Dictionary = GameState.items.effect_preview(record.id, {"food": GameState.food, "warmth": GameState.warmth, "energy": GameState.energy})
		_text(details, "这次使用能恢复", 16, ACCENT)
		var parts: Array[String] = []
		for key in ["food", "warmth", "energy"]:
			if float(definition.effects[key]) <= 0.0: continue
			var current: float = GameState.get(key)
			parts.append("%s  %s → %s  (+%s)" % [{"food": "饱腹", "warmth": "温暖", "energy": "精力"}[key], str(snappedf(current, 0.1)), str(snappedf(current + float(preview.effects[key]), 0.1)), str(snappedf(preview.effects[key], 0.1))])
		_text(details, "    ·    ".join(parts), 20, POSITIVE)
		if not preview.ok: _text(details, "现在状态已满，留到需要时再用。", 17, MUTED)
		elif preview.waste_ratio >= 0.25: _text(details, "当前只能恢复部分效果。可以先带着，晚些再用。", 17, MUTED)
		if int(definition.uses) > 1: _text(details, "这一件还可使用 %d 次。每次只消耗一次。" % record.uses, 17, MUTED)
	if record.state in ["counter", "storage"]:
		_action("装进行囊 · 1 件", "pack", record.id, not GameState.items.can_pack([record.id]))
		if not GameState.items.can_pack([record.id]):
			_text(details, "这一类行囊已满。先使用随身补给，或回小屋存放。", 17, ACCENT)
	if definition.category in ["food", "drink"] and record.state != "storage":
		var full := not bool(GameState.items.effect_preview(record.id, {"food": GameState.food, "warmth": GameState.warmth, "energy": GameState.energy}).ok)
		_action(("喝一口" if int(definition.uses) > 1 else "现在喝") if definition.category == "drink" else "现在吃", "consume", record.id, full)
	if model.location == "home":
		if record.state == "carried":
			if definition.carry_category == "residence": _action("安放到" + str(GameState.items.Catalog.HOME_SLOTS[definition.home_slot].name[0]), "place", record.id)
			_action("存入住处收纳箱", "store", record.id)
		if record.state == "placed": _action({"durable": "铺好毯子", "component": "安装这件零件", "home_consumable": "使用电池"}.get(definition.category, "使用"), "use_home", record.id)
		if record.state == "active": _action("暂时收起", "deactivate", record.id)
		if record.state in ["placed", "active"]: _action("收回行囊", "reclaim", record.id, not GameState.items.can_pack([record.id]))
	elif definition.carry_category == "residence" and record.state == "carried":
		_link("回小屋安放", "home")

func _action(title: String, action: String, id: String, disabled := false) -> void:
	var button := _button(details, title, func(): action_requested.emit(action, id, false))
	if action in ["pack", "use_home"] or (action == "consume" and mode != "counter"):
		Palette.primary(button)
	button.disabled = disabled or GameState.game_finished
	button.set_meta("inventory_focus", "action:" + action)
	action_buttons.append(button)

func _link(title: String, destination: String) -> void:
	var button := _button(details, title, func(): travel_requested.emit(destination))
	button.disabled = GameState.game_finished
	action_buttons.append(button)

func _menu() -> void:
	var titles: Array[String] = []
	var scenario: Dictionary = NpcScenarioRegistry.get_scenario(GameState.service_scenario_for(model.npc_id()))
	for alias in scenario.get("inventory", []):
		var id: String = GameState.items.resolve_item(alias)
		if id.is_empty(): continue
		var definition: Dictionary = GameState.items.definitions[id]
		var title: String = "%s / %s" % [GameState.items.Catalog.label(definition.name), str(definition.name[1])]
		if not titles.has(title): titles.append(title)
	_text(details, "怎样领取", 23)
	var example: String = {"tavi": "Burger", "ori": "Water", "vesh": "Blanket"}.get(model.npc_id(), "Burger")
	_text(details, "说出具体商品名就可以，不必照念完整句式。比如 “%s, please.”。店员确认并说完后，物品会放到柜台；再选择现在使用或装包。" % example, 18)
	_text(details, "店员确认了你要的东西就会交付，说得越清楚自然，常常能多拿一份。没有听清可以免费重试；语音不可用时用手势领取最低份量。", 16, MUTED)
	_text(details, "这里可以买到", 23, ACCENT)
	_text(details, "\n".join(titles), 18, MUTED)

func request_confirmation(action: String, id: String) -> void:
	confirmation = {"action": action, "id": id, "revision": GameState.items.revision}
	refresh()
	for button in action_buttons:
		if button.get_meta("inventory_focus", "") == "confirm": _focus_confirmation.call_deferred(weakref(button))

func _focus_confirmation(reference: WeakRef) -> void:
	var button = reference.get_ref()
	if button != null and button.is_inside_tree(): button.grab_focus()

func show_notice(text: String) -> void:
	notice_label.text = text
	notice_label.visible = not text.is_empty()

func _confirm() -> void:
	if confirmation.is_empty(): return
	var pending := confirmation.duplicate()
	confirmation.clear()
	if int(pending.revision) != GameState.items.revision:
		notice.emit("物品已变化，请重新选择。")
		refresh()
		return
	action_requested.emit(pending.action, pending.id, true)
