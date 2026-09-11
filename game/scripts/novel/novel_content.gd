extends RefCounted
## FR-46: presentation metadata; inventories and commerce remain in role cards.
const CAST := ["mira", "tavi", "ori", "vesh", "rowan"]
const PLACES := [
	{"id": "plaza", "name": "聚落广场", "en": "THE COMMONS", "npc": "mira", "role": "聚落迎宾", "hint": "认识这里的人，听一段日常。", "opening": "Welcome, stranger. Take your time. The food stall is just around the corner."},
	{"id": "food", "name": "塔维的餐摊", "en": "TAVI’S KITCHEN", "npc": "tavi", "role": "餐摊店员", "hint": "热食、闲聊，还有刚出炉的面包。", "opening": "Hey there. What can I get for you?"},
	{"id": "store", "name": "街角便利店", "en": "THE CORNER STORE", "npc": "ori", "role": "便利店店员", "hint": "补充饮水，也找找生活用品。", "opening": "Hi. Let me know what you need."},
	{"id": "parts", "name": "维什的工坊", "en": "VESH’S WORKSHOP", "npc": "vesh", "role": "零件铺店员", "hint": "给住处添一点温暖。", "opening": "Need something for your heater?"},
	{"id": "neighbor", "name": "罗文的门廊", "en": "ROWAN’S PORCH", "npc": "rowan", "role": "聚落邻居", "hint": "带上一瓶水，看看老朋友。", "opening": "Good to see you. Come sit for a while."},
	{"id": "home", "name": "我的小屋", "en": "A PLACE TO CALL HOME", "npc": "", "role": "", "hint": "放下行囊。今天又离这里近了一点。", "opening": "窗外的风轻轻吹过。这里逐渐有了家的样子。"},
]
# One authored catalog is read by both this screen and the voice service.
static var SOCIAL: Array = []

static func load_daily_life() -> void:
	if not SOCIAL.is_empty(): return
	# Exported bytecode initializes statics before packaged files are available.
	# Read the shared catalog when the controller enters the running scene tree.
	var json := JSON.new()
	var source := FileAccess.get_file_as_string("res://data/dialogue/novel_daily_life.json")
	if source.is_empty() or json.parse(source) != OK or not json.data is Array:
		push_error("The daily-life dialogue catalog could not be loaded.")
		return
	SOCIAL = json.data

static func place(id: String) -> Dictionary:
	for entry in PLACES:
		if entry.id == id:
			return entry
	return PLACES[0]
