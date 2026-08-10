extends Node

signal state_changed
signal message_requested(text: String, tone: String)
signal run_completed

const SAVE_VERSION := 1
const MAX_NEED := 100.0
const DAY_DURATION := 300.0

var day := 1
var day_time := 0.0
var food := 78.0
var warmth := 72.0
var energy := 82.0
var berries := 0
var scrap := 0
var water := 0
var heater_repaired := false
var relationships := {
	"mira": 0,
	"rowan": 0,
	"tavi": 0,
	"vesh": 0,
	"ori": 0,
}
var memories: Array[String] = []
var completed_steps: Dictionary = {}
var game_finished := false
var persistence_enabled := true
var save_path := "user://stranger_save.json"

func _process(delta: float) -> void:
	if game_finished:
		return
	day_time += delta
	food = maxf(0.0, food - delta * 0.42)
	warmth = maxf(0.0, warmth - delta * (0.24 if heater_repaired else 0.36))
	energy = maxf(0.0, energy - delta * 0.2)
	if food <= 0.0 or warmth <= 0.0 or energy <= 0.0:
		faint()
	state_changed.emit()

func objective_text() -> String:
	if day == 1:
		if not completed_steps.has("greet_mira"):
			return "找到米拉，用英语问候，或用手势确认善意"
		if berries < 2:
			return "在聚落边缘收集食物（%d/2）" % berries
		return "回到庇护所休息，结束第一天"
	if day == 2:
		if scrap < 2:
			return "收集加热器零件（%d/2）" % scrap
		if not heater_repaired:
			return "在加热器旁完成修理"
		return "回到庇护所休息，结束第二天"
	if day == 3:
		if water < 1:
			return "从蓄水器取水"
		if not completed_steps.has("help_rowan"):
			return "把水带给罗文，并表达你的帮助意图"
		return "纵向切片完成：你在异乡有了第一个立足点"
	return "继续探索聚落"

func interact(kind: String, target_id: String, communication: String = "action") -> void:
	match kind:
		"npc":
			_interact_npc(target_id, communication)
		"berry":
			berries += 1
			food = minf(MAX_NEED, food + 8.0)
			completed_steps[target_id] = true
			message_requested.emit("找到可食用的蓝莓果。", "good")
		"scrap":
			scrap += 1
			completed_steps[target_id] = true
			message_requested.emit("捡到一块还能用的合金零件。", "good")
		"water":
			water = 1
			message_requested.emit("装满了一壶水。", "good")
		"heater":
			if day >= 2 and scrap >= 2:
				heater_repaired = true
				scrap -= 2
				warmth = minf(MAX_NEED, warmth + 25.0)
				message_requested.emit("加热器恢复运转，庇护所暖了起来。", "good")
			else:
				message_requested.emit("需要两块合金零件。", "neutral")
		"shelter":
			_try_sleep()
	state_changed.emit()

func _interact_npc(npc_id: String, communication: String) -> void:
	if npc_id == "mira" and day == 1 and not completed_steps.has("greet_mira"):
		completed_steps["greet_mira"] = true
		remember(npc_id, "在第一天主动表达了善意", 2)
		message_requested.emit(_communication_reply("Mira", communication, "Welcome, stranger."), "good")
	elif npc_id == "rowan" and day == 3 and water > 0 and not completed_steps.has("help_rowan"):
		water = 0
		completed_steps["help_rowan"] = true
		remember(npc_id, "缺水时送来了一壶水", 3)
		game_finished = true
		message_requested.emit(_communication_reply("Rowan", communication, "You came back. Thank you."), "good")
		save_game()
		run_completed.emit()
	else:
		var known: int = relationships.get(npc_id, 0)
		var reply := "他们记得你。" if known > 0 else "他们谨慎地打量着这位异乡人。"
		message_requested.emit(reply, "neutral")

func _communication_reply(speaker: String, communication: String, line: String) -> String:
	if communication == "voice":
		return "%s 听懂了你的英语：“%s”" % [speaker, line]
	if communication == "gesture":
		return "%s 看懂了你的手势。你随时可以免费重试英语。" % speaker
	return "靠近后按 V 说英语，或按 G 用手势确认。"

func remember(npc_id: String, memory: String, relationship_gain: int) -> void:
	relationships[npc_id] = int(relationships.get(npc_id, 0)) + relationship_gain
	memories.append("%s：%s" % [npc_id, memory])

func _try_sleep() -> void:
	var can_sleep := false
	if day == 1:
		can_sleep = completed_steps.has("greet_mira") and berries >= 2
	elif day == 2:
		can_sleep = heater_repaired
	if can_sleep:
		day += 1
		day_time = 0.0
		energy = MAX_NEED
		warmth = minf(MAX_NEED, warmth + 30.0)
		message_requested.emit("新的一天开始了。", "good")
		save_game()
	else:
		message_requested.emit("今天还有重要的事没有完成。", "neutral")

func faint() -> void:
	food = 35.0
	warmth = 40.0
	energy = 55.0
	day_time = minf(DAY_DURATION - 30.0, day_time + 45.0)
	berries = maxi(0, berries - 1)
	scrap = maxi(0, scrap - 1)
	message_requested.emit("你昏倒后被送回庇护所。时间流逝了，但关系没有受损。", "warning")
	state_changed.emit()

func reset_run() -> void:
	day = 1
	day_time = 0.0
	food = 78.0
	warmth = 72.0
	energy = 82.0
	berries = 0
	scrap = 0
	water = 0
	heater_repaired = false
	completed_steps.clear()
	memories.clear()
	game_finished = false
	for key in relationships:
		relationships[key] = 0
	state_changed.emit()

func save_game() -> bool:
	if not persistence_enabled:
		return true
	var file := FileAccess.open(save_path, FileAccess.WRITE)
	if file == null:
		message_requested.emit("无法保存进度，但可以继续本次游戏。", "warning")
		return false
	var data := {
		"version": SAVE_VERSION,
		"day": day,
		"day_time": day_time,
		"food": food,
		"warmth": warmth,
		"energy": energy,
		"berries": berries,
		"scrap": scrap,
		"water": water,
		"heater_repaired": heater_repaired,
		"relationships": relationships,
		"memories": memories,
		"completed_steps": completed_steps,
		"game_finished": game_finished,
	}
	file.store_string(JSON.stringify(data))
	return true

func load_game() -> bool:
	if not FileAccess.file_exists(save_path):
		return false
	var file := FileAccess.open(save_path, FileAccess.READ)
	if file == null:
		return false
	var parsed = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary or int(parsed.get("version", -1)) != SAVE_VERSION:
		return false
	day = int(parsed.get("day", 1))
	day_time = float(parsed.get("day_time", 0.0))
	food = float(parsed.get("food", 78.0))
	warmth = float(parsed.get("warmth", 72.0))
	energy = float(parsed.get("energy", 82.0))
	berries = int(parsed.get("berries", 0))
	scrap = int(parsed.get("scrap", 0))
	water = int(parsed.get("water", 0))
	heater_repaired = bool(parsed.get("heater_repaired", false))
	var saved_relationships: Dictionary = parsed.get("relationships", {})
	for npc_id in relationships:
		relationships[npc_id] = int(saved_relationships.get(npc_id, relationships[npc_id]))
	memories.assign(parsed.get("memories", []))
	completed_steps.assign(parsed.get("completed_steps", {}))
	game_finished = bool(parsed.get("game_finished", false))
	state_changed.emit()
	return true
