extends Node

signal state_changed
signal needs_changed(food_value: float, warmth_value: float, energy_value: float)
signal clock_changed(day_value: int, elapsed_seconds: int)
signal objective_changed(objective: String)
signal message_requested(text: String, tone: String)
signal run_completed
signal day_started(day_value: int)

const SAVE_VERSION := 1
const MAX_NEED := 100.0
const DAY_DURATION := 300.0
const DAY_START_HOUR := 8.0
const DAY_END_HOUR := 22.0

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
var interaction_time_frozen := false

func _process(delta: float) -> void:
	if game_finished or interaction_time_frozen:
		return
	var previous_needs := Vector3(floorf(food), floorf(warmth), floorf(energy))
	var previous_second := int(day_time)
	day_time += delta
	food = maxf(0.0, food - delta * 0.42)
	warmth = maxf(0.0, warmth - delta * (0.24 if heater_repaired else 0.36))
	energy = maxf(0.0, energy - delta * 0.2)
	if food <= 0.0 or warmth <= 0.0 or energy <= 0.0:
		faint()
	var current_needs := Vector3(floorf(food), floorf(warmth), floorf(energy))
	if current_needs != previous_needs:
		needs_changed.emit(food, warmth, energy)
		state_changed.emit()
	if int(day_time) != previous_second:
		clock_changed.emit(day, int(day_time))

func set_interaction_time_frozen(active: bool) -> void:
	interaction_time_frozen = active


func clock_hours() -> float:
	var span := DAY_END_HOUR - DAY_START_HOUR
	return DAY_START_HOUR + clampf(day_time / DAY_DURATION, 0.0, 1.0) * span


func clock_hms() -> Vector2i:
	var hours := clock_hours()
	var hour := int(hours)
	var minute := int((hours - float(hour)) * 60.0)
	return Vector2i(hour, minute)

func objective_text() -> String:
	if day == 1:
		if not completed_steps.has("greet_mira"):
			return tr("OBJECTIVE_GREET_MIRA")
		if berries < 2:
			return tr("OBJECTIVE_GATHER_FOOD") % berries
		return tr("OBJECTIVE_SLEEP_DAY_ONE")
	if day == 2:
		if scrap < 2:
			return tr("OBJECTIVE_GATHER_SCRAP") % scrap
		if not heater_repaired:
			return tr("OBJECTIVE_REPAIR_HEATER")
		return tr("OBJECTIVE_SLEEP_DAY_TWO")
	if day == 3:
		if water < 1:
			return tr("OBJECTIVE_FETCH_WATER")
		if not completed_steps.has("help_rowan"):
			return tr("OBJECTIVE_HELP_ROWAN")
		return tr("OBJECTIVE_COMPLETE")
	return tr("OBJECTIVE_EXPLORE")

func interact(kind: String, target_id: String, communication: String = "action") -> void:
	var previous_objective := objective_text()
	match kind:
		"npc":
			_interact_npc(target_id, communication)
		"berry":
			berries += 1
			food = minf(MAX_NEED, food + 8.0)
			completed_steps[target_id] = true
			message_requested.emit(tr("MSG_BERRY_FOUND"), "good")
		"scrap":
			scrap += 1
			completed_steps[target_id] = true
			message_requested.emit(tr("MSG_SCRAP_FOUND"), "good")
		"water":
			water = 1
			message_requested.emit(tr("MSG_WATER_FILLED"), "good")
		"heater":
			if heater_repaired:
				message_requested.emit(tr("MSG_HEATER_ALREADY"), "good")
			elif day < 2:
				message_requested.emit(tr("MSG_HEATER_NOT_TODAY"), "neutral")
			elif scrap >= 2:
				heater_repaired = true
				scrap -= 2
				warmth = minf(MAX_NEED, warmth + 25.0)
				message_requested.emit(tr("MSG_HEATER_REPAIRED"), "good")
			else:
				message_requested.emit(tr("MSG_HEATER_NEEDS_SCRAP"), "neutral")
		"shelter":
			_try_sleep()
	state_changed.emit()
	needs_changed.emit(food, warmth, energy)
	if objective_text() != previous_objective:
		objective_changed.emit(objective_text())

func _interact_npc(npc_id: String, communication: String) -> void:
	if npc_id == "mira" and day == 1 and not completed_steps.has("greet_mira"):
		completed_steps["greet_mira"] = true
		remember(npc_id, "MEMORY_GREET_MIRA", 2)
		message_requested.emit(_communication_reply(tr("NPC_MIRA"), communication, "Welcome, stranger."), "good")
		return
	if npc_id == "rowan" and day == 3 and water > 0 and not completed_steps.has("help_rowan"):
		water = 0
		completed_steps["help_rowan"] = true
		remember(npc_id, "MEMORY_HELP_ROWAN", 3)
		game_finished = true
		message_requested.emit(_communication_reply(tr("NPC_ROWAN"), communication, "You came back. Thank you."), "good")
		save_game()
		run_completed.emit()
		return
	var line := _npc_followup_line(npc_id)
	var known: int = relationships.get(npc_id, 0)
	var tone := "good" if known > 0 else "neutral"
	message_requested.emit(_communication_reply(tr("NPC_%s" % npc_id.to_upper()), communication, line), tone)


func _npc_followup_line(npc_id: String) -> String:
	match npc_id:
		"mira":
			if completed_steps.has("greet_mira"):
				if day == 1 and berries < 2:
					return tr("NPC_MIRA_HINT_FOOD")
				if day == 2 and not heater_repaired:
					return tr("NPC_MIRA_HINT_HEAT")
				if day == 3 and not completed_steps.has("help_rowan"):
					return tr("NPC_MIRA_HINT_ROWAN")
				return tr("NPC_MIRA_REMEMBERS")
			return tr("MSG_NPC_WARY")
		"rowan":
			if day == 3 and water <= 0:
				return tr("NPC_ROWAN_NEEDS_WATER")
			if int(relationships.get("rowan", 0)) > 0:
				return tr("NPC_ROWAN_REMEMBERS")
			return tr("NPC_ROWAN_WARY")
		"tavi":
			return tr("NPC_TAVI_HINT_FOOD") if berries < 2 else tr("NPC_TAVI_SETTLED")
		"vesh":
			return tr("NPC_VESH_HINT_SCRAP") if scrap < 2 and not heater_repaired else tr("NPC_VESH_SETTLED")
		"ori":
			return tr("NPC_ORI_HINT_WATER") if water < 1 else tr("NPC_ORI_SETTLED")
		_:
			return tr("MSG_NPC_REMEMBERS") if int(relationships.get(npc_id, 0)) > 0 else tr("MSG_NPC_WARY")

func _communication_reply(speaker: String, communication: String, line: String) -> String:
	if communication == "voice":
		return tr("NPC_REPLY_VOICE") % [speaker, line]
	if communication == "gesture":
		var understood := tr("NPC_REPLY_GESTURE") % speaker
		if line.is_empty():
			return understood
		return "%s %s" % [understood, line]
	return tr("NPC_REPLY_OBSERVE")

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
		clock_changed.emit(day, 0)
		day_started.emit(day)
		save_game()
	else:
		message_requested.emit(tr(_sleep_block_key()), "neutral")


func _sleep_block_key() -> String:
	if day == 1:
		if not completed_steps.has("greet_mira"):
			return "MSG_SLEEP_NEED_MIRA"
		if berries < 2:
			return "MSG_SLEEP_NEED_FOOD"
	elif day == 2:
		if not heater_repaired:
			return "MSG_SLEEP_NEED_HEATER"
	elif day >= 3:
		return "MSG_SLEEP_NEED_ROWAN"
	return "MSG_SLEEP_BLOCKED"

func faint() -> void:
	food = 35.0
	warmth = 40.0
	energy = 55.0
	day_time = minf(DAY_DURATION - 30.0, day_time + 45.0)
	berries = maxi(0, berries - 1)
	scrap = maxi(0, scrap - 1)
	message_requested.emit(tr("MSG_FAINTED"), "warning")
	state_changed.emit()
	needs_changed.emit(food, warmth, energy)
	clock_changed.emit(day, int(day_time))
	objective_changed.emit(objective_text())

func reset_run() -> void:
	interaction_time_frozen = false
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
	needs_changed.emit(food, warmth, energy)
	clock_changed.emit(day, int(day_time))
	objective_changed.emit(objective_text())

func save_game() -> bool:
	if not persistence_enabled:
		return true
	var file := FileAccess.open(save_path, FileAccess.WRITE)
	if file == null:
		message_requested.emit(tr("MSG_SAVE_FAILED"), "warning")
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
	interaction_time_frozen = false
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
	needs_changed.emit(food, warmth, energy)
	clock_changed.emit(day, int(day_time))
	objective_changed.emit(objective_text())
	return true
