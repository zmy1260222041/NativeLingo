extends Node

signal state_changed
signal needs_changed(food_value: float, warmth_value: float, energy_value: float)
signal clock_changed(day_value: int, elapsed_seconds: int)
signal objective_changed(objective: String)
signal message_requested(text: String, tone: String)
signal expression_evaluated(target_id: String, expression: Dictionary)
signal run_completed
signal day_started(day_value: int)
signal onboarding_changed(step: String, active: bool)

const SAVE_VERSION := 3
const MAX_NEED := 100.0
const DAY_DURATION := 300.0
const DAY_START_HOUR := 8.0
const DAY_END_HOUR := 22.0
## FR-30: onboarding steps are advanced by the owning input/domain edge, never by
## the UI. `speak` accepts voice, gesture, or the minimum-survival fallback so the
## guide remains completable in no-voice builds.
const ONBOARDING_STEPS: Array[String] = ["move", "look", "sprint", "jump", "interact", "speak", "sleep"]
## FR-28: voice-gated reward bands. Monotonic; below the sparse floor the NPC
## gives nothing but spends no opportunity and no state is harmed.
const SCORE_GENEROUS_MIN := 70.0
const SCORE_SPARSE_MIN := 40.0

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
## FR-30: onboarding state. Active onboarding freezes survival decay; completing or
## skipping it is the only way out. Missing keys default to false and old saves
## simply get the guide once.
var onboarding_active := false
var onboarding_step := "move"
var onboarding_completed := false
## FR-35: graded vocabulary profile. The derived index lives in VocabularyState and
## is only mirrored here as JSON-safe values for the versioned save.
var vocabulary_tier := "toddler"
var vocabulary_entries: Dictionary = {}

func _process(delta: float) -> void:
	if game_finished or interaction_time_frozen:
		return
	# FR-30 G1: the guide must never let the three needs reach zero. Freezing all
	# survival decay (and the compressed clock) during onboarding is the strongest
	# form of that guard and is released by completing or skipping the guide.
	if onboarding_active:
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


func begin_onboarding() -> void:
	if onboarding_completed:
		return
	onboarding_active = true
	onboarding_step = ONBOARDING_STEPS[0]
	onboarding_changed.emit(onboarding_step, true)
	state_changed.emit()


func skip_onboarding() -> void:
	if not onboarding_active:
		return
	onboarding_active = false
	onboarding_completed = true
	onboarding_changed.emit(onboarding_step, false)
	state_changed.emit()
	save_game()


func complete_onboarding() -> void:
	if not onboarding_active:
		return
	onboarding_active = false
	onboarding_completed = true
	onboarding_changed.emit(onboarding_step, false)
	state_changed.emit()
	save_game()


## Domain-side step matcher. The UI never advances the guide directly; input and
## world interactions call this with the observed player action. Wrong actions are
## intentionally no-ops so exploration is never penalised.
func onboarding_action(action: String) -> void:
	if not onboarding_active:
		return
	var step_index := ONBOARDING_STEPS.find(onboarding_step)
	if step_index < 0:
		complete_onboarding()
		return
	if action != onboarding_step:
		return
	if step_index >= ONBOARDING_STEPS.size() - 1:
		complete_onboarding()
		return
	onboarding_step = ONBOARDING_STEPS[step_index + 1]
	onboarding_changed.emit(onboarding_step, true)
	state_changed.emit()


func onboarding_step_index() -> int:
	return ONBOARDING_STEPS.find(onboarding_step)


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
			return tr("OBJECTIVE_ASK_FOOD") % berries
		return tr("OBJECTIVE_SLEEP_DAY_ONE")
	if day == 2:
		if scrap < 2:
			return tr("OBJECTIVE_ASK_SCRAP") % scrap
		if not heater_repaired:
			return tr("OBJECTIVE_REPAIR_HEATER")
		return tr("OBJECTIVE_SLEEP_DAY_TWO")
	if day == 3:
		if water < 1:
			return tr("OBJECTIVE_ASK_WATER")
		if not completed_steps.has("help_rowan"):
			return tr("OBJECTIVE_HELP_ROWAN")
		return tr("OBJECTIVE_COMPLETE")
	return tr("OBJECTIVE_EXPLORE")

func interact(kind: String, target_id: String, communication: String = "action", expression: Dictionary = {}) -> void:
	var previous_objective := objective_text()
	match kind:
		"npc":
			_interact_npc(target_id, communication, expression)
		"berry":
			# FR-28: forage tokens are narrative guides now; resources come only
			# from a spoken request judged by the NPC.
			message_requested.emit(tr("MSG_FORAGE_REDIRECT"), "neutral")
		"scrap":
			message_requested.emit(tr("MSG_FORAGE_REDIRECT"), "neutral")
		"water":
			message_requested.emit(tr("MSG_RESERVOIR_REDIRECT"), "neutral")
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
	onboarding_action("interact")
	state_changed.emit()
	needs_changed.emit(food, warmth, energy)
	if objective_text() != previous_objective:
		objective_changed.emit(objective_text())

func _interact_npc(npc_id: String, communication: String, expression: Dictionary) -> void:
	match npc_id:
		"mira":
			_interact_mira(communication)
			return
		"rowan":
			_interact_rowan(communication, expression)
			return
		"tavi":
			_interact_food_supplier(communication, expression)
			return
		"vesh":
			_interact_scrap_supplier(communication, expression)
			return
		"ori":
			_interact_water_supplier(communication, expression)
			return
		_:
			_emit_npc_followup(npc_id, communication)

func _interact_mira(communication: String) -> void:
	if day == 1 and not completed_steps.has("greet_mira"):
		completed_steps["greet_mira"] = true
		remember("mira", "MEMORY_GREET_MIRA", 2)
		message_requested.emit(_communication_reply(tr("NPC_MIRA"), communication, "Welcome, stranger."), "good")
		return
	_emit_npc_followup("mira", communication)

func _interact_rowan(communication: String, expression: Dictionary) -> void:
	if day == 3 and water > 0 and not completed_steps.has("help_rowan"):
		if communication == "voice":
			var score := _voice_score(expression)
			if score < SCORE_SPARSE_MIN:
				expression_evaluated.emit("rowan", expression)
				message_requested.emit(tr("MSG_NPC_DIDNT_UNDERSTAND") % tr("NPC_ROWAN"), "neutral")
				return
		water = 0
		completed_steps["help_rowan"] = true
		remember("rowan", "MEMORY_HELP_ROWAN", 3)
		game_finished = true
		message_requested.emit(_communication_reply(tr("NPC_ROWAN"), communication, "You came back. Thank you."), "good")
		save_game()
		run_completed.emit()
		return
	_emit_npc_followup("rowan", communication)

func _interact_food_supplier(communication: String, expression: Dictionary) -> void:
	if communication in ["voice", "gesture", "gesture_fallback"]:
		# FR-30: the no-voice fallback counts as the guided "ask for food" step so
		# the onboarding path never depends on a microphone or local service.
		onboarding_action("speak")
	if berries >= 2:
		_emit_npc_line("tavi", communication, tr("NPC_TAVI_SETTLED"))
		return
	if not completed_steps.has("greet_mira"):
		message_requested.emit(tr("MSG_NEED_MIRA_FIRST"), "neutral")
		return
	match communication:
		"voice":
			var score := _voice_score(expression)
			if score < SCORE_SPARSE_MIN:
				expression_evaluated.emit("tavi", expression)
				message_requested.emit(tr("MSG_NPC_DIDNT_UNDERSTAND") % tr("NPC_TAVI"), "neutral")
				return
			if score >= SCORE_GENEROUS_MIN:
				berries += 2
				food = minf(MAX_NEED, food + 14.0)
				expression_evaluated.emit("tavi", expression)
				message_requested.emit(tr("MSG_REWARD_FOOD_2") % tr("NPC_TAVI"), "good")
			else:
				berries += 1
				food = minf(MAX_NEED, food + 7.0)
				expression_evaluated.emit("tavi", expression)
				message_requested.emit(tr("MSG_REWARD_FOOD_1") % tr("NPC_TAVI"), "good")
		"gesture":
			message_requested.emit(tr("MSG_GESTURE_NO_RESOURCE") % tr("NPC_TAVI"), "neutral")
		"gesture_fallback":
			berries += 1
			food = minf(MAX_NEED, food + 6.0)
			message_requested.emit(tr("MSG_FALLBACK_FOOD") % tr("NPC_TAVI"), "good")
		_:
			_emit_npc_followup("tavi", communication)

func _interact_scrap_supplier(communication: String, expression: Dictionary) -> void:
	if day < 2:
		message_requested.emit(tr("MSG_HEATER_NOT_TODAY"), "neutral")
		return
	if scrap >= 2 and (heater_repaired or day >= 2):
		_emit_npc_line("vesh", communication, tr("NPC_VESH_SETTLED"))
		return
	match communication:
		"voice":
			var score := _voice_score(expression)
			if score < SCORE_SPARSE_MIN:
				expression_evaluated.emit("vesh", expression)
				message_requested.emit(tr("MSG_NPC_DIDNT_UNDERSTAND") % tr("NPC_VESH"), "neutral")
				return
			if score >= SCORE_GENEROUS_MIN:
				scrap += 2
				expression_evaluated.emit("vesh", expression)
				message_requested.emit(tr("MSG_REWARD_SCRAP_2") % tr("NPC_VESH"), "good")
			else:
				scrap += 1
				expression_evaluated.emit("vesh", expression)
				message_requested.emit(tr("MSG_REWARD_SCRAP_1") % tr("NPC_VESH"), "good")
		"gesture":
			message_requested.emit(tr("MSG_GESTURE_NO_RESOURCE") % tr("NPC_VESH"), "neutral")
		"gesture_fallback":
			scrap += 1
			message_requested.emit(tr("MSG_FALLBACK_SCRAP") % tr("NPC_VESH"), "good")
		_:
			_emit_npc_followup("vesh", communication)

func _interact_water_supplier(communication: String, expression: Dictionary) -> void:
	if day < 3:
		message_requested.emit(tr("MSG_WATER_NOT_TODAY"), "neutral")
		return
	if water >= 1:
		_emit_npc_line("ori", communication, tr("NPC_ORI_SETTLED"))
		return
	match communication:
		"voice":
			var score := _voice_score(expression)
			if score < SCORE_SPARSE_MIN:
				expression_evaluated.emit("ori", expression)
				message_requested.emit(tr("MSG_NPC_DIDNT_UNDERSTAND") % tr("NPC_ORI"), "neutral")
				return
			water = 1
			if score >= SCORE_GENEROUS_MIN:
				energy = minf(MAX_NEED, energy + 12.0)
				expression_evaluated.emit("ori", expression)
				message_requested.emit(tr("MSG_REWARD_WATER_2") % tr("NPC_ORI"), "good")
			else:
				energy = minf(MAX_NEED, energy + 6.0)
				expression_evaluated.emit("ori", expression)
				message_requested.emit(tr("MSG_REWARD_WATER_1") % tr("NPC_ORI"), "good")
		"gesture":
			message_requested.emit(tr("MSG_GESTURE_NO_RESOURCE") % tr("NPC_ORI"), "neutral")
		"gesture_fallback":
			water = 1
			energy = minf(MAX_NEED, energy + 6.0)
			message_requested.emit(tr("MSG_FALLBACK_WATER") % tr("NPC_ORI"), "good")
		_:
			_emit_npc_followup("ori", communication)

func _voice_score(expression: Dictionary) -> float:
	if expression.is_empty() or not expression.has("score"):
		return -1.0
	var raw: Variant = expression.get("score")
	if typeof(raw) != TYPE_FLOAT and typeof(raw) != TYPE_INT:
		return -1.0
	return clampf(float(raw), 0.0, 100.0)

func voice_band_for_score(score: float) -> String:
	if score >= SCORE_GENEROUS_MIN:
		return "generous"
	if score >= SCORE_SPARSE_MIN:
		return "sparse"
	return "none"

func _emit_npc_followup(npc_id: String, communication: String) -> void:
	_emit_npc_line(npc_id, communication, _npc_followup_line(npc_id))

func _emit_npc_line(npc_id: String, communication: String, line: String) -> void:
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
		onboarding_action("sleep")
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
	onboarding_active = false
	onboarding_step = ONBOARDING_STEPS[0]
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
		"onboarding_completed": onboarding_completed,
		"onboarding_active": onboarding_active,
		"onboarding_step": onboarding_step,
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
	if not parsed is Dictionary:
		return false
	# SAVE_VERSION 2 (FR-28) changes quest flow but not the field set, so a
	# version-1 save migrates lazily by keeping every persisted value.
	var saved_version := int(parsed.get("version", 1))
	if saved_version < 1 or saved_version > SAVE_VERSION:
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
	onboarding_completed = bool(parsed.get("onboarding_completed", false))
	onboarding_active = bool(parsed.get("onboarding_active", false)) and not onboarding_completed
	var saved_step := str(parsed.get("onboarding_step", ONBOARDING_STEPS[0]))
	onboarding_step = saved_step if saved_step in ONBOARDING_STEPS else ONBOARDING_STEPS[0]
	state_changed.emit()
	needs_changed.emit(food, warmth, energy)
	clock_changed.emit(day, int(day_time))
	objective_changed.emit(objective_text())
	onboarding_changed.emit(onboarding_step, onboarding_active)
	return true
