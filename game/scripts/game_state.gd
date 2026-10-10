extends Node

signal state_changed
signal needs_changed(food_value: float, warmth_value: float, energy_value: float)
signal clock_changed(day_value: int, elapsed_seconds: int)
signal objective_changed(objective: String)
signal message_requested(text: String, tone: String)
signal expression_evaluated(target_id: String, expression: Dictionary)
signal npc_line_presented(npc_id: String, text: String)
signal run_completed
signal day_started(day_value: int)
signal onboarding_changed(step: String, active: bool)
signal dialogue_scenario_changed(scenario_id: String, outcome: String)

const SAVE_VERSION := 5
const ItemStateScript := preload("res://scripts/item_state.gd")
var items = ItemStateScript.new()
signal items_changed
signal item_feedback(action: String, item_id: String)
signal item_interaction_requested(kind: String, target_id: String)
signal item_interaction_interrupted
const MAX_NEED := 100.0
const DAY_DURATION := 300.0
const DAY_START_HOUR := 8.0
const DAY_END_HOUR := 22.0
## FR-30: onboarding steps are advanced by the owning input/domain edge, never by
## the UI. Critical speech steps accept understood voice or the explicit
## minimum-survival fallback so the guide remains completable in no-voice builds.
const ONBOARDING_STEPS: Array[String] = ["move", "look", "sprint", "jump", "interact", "greet", "speak", "use_item", "sleep"]
## FR-28: voice-gated reward bands. Monotonic; below the sparse floor the NPC
## gives nothing but spends no opportunity and no state is harmed.
const SCORE_GENEROUS_MIN := 70.0
const SCORE_SPARSE_MIN := 40.0
## FR-42: Maslow layer 1, modern shops, no calendar quests. Three nights is
## only a time box for the vertical slice.
const SLICE_NIGHTS := 3
const FOOD_COMFORT := 80.0
const ENERGY_COMFORT := 80.0
const ENERGY_TIRED := 40.0
const SLEEP_HOUR := 20.0
## Need drain per second of world time. A 2D rest at home scales these.
const FOOD_DECAY := 0.42
const WARMTH_DECAY := 0.36
const WARMTH_DECAY_HEATED := 0.24
const ENERGY_DECAY := 0.2
## X1-01: a faint costs time and leaves needs low. It lifts only what reached
## zero to a floor, so the player can still walk to food; never a free refill.
const FAINT_SECONDS := 45.0
const FAINT_FOOD_FLOOR := 15.0
const FAINT_WARMTH_FLOOR := 20.0
const FAINT_ENERGY_FLOOR := 20.0
const SERVICE_SCENARIOS := {
	"tavi": "food_counter",
	"vesh": "parts_desk",
	"ori": "convenience_store",
}
const DIALOGUE_SCENARIO_IDS := [
	"food_counter",
	"convenience_store",
	"parts_desk",
]

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
## X1-01: how often this run fainted (saved), and what the last faint cost.
var faints := 0
var last_faint: Dictionary = {}
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
## Separate from completed_steps and resource state. Only NpcScenarioRunner
## writes these terminal pilot outcomes after a validated conversation closes.
var dialogue_scenario_progress: Dictionary = {}
var presentation_state: Dictionary = {}

func _process(delta: float) -> void:
	pass_time(delta)

## Advances the clock and drains needs. A 2D rest at home keeps `hunger_cost` of
## the hunger drain and `shelter_cost` of the warmth and energy drain.
func pass_time(delta: float, hunger_cost := 1.0, shelter_cost := 1.0) -> void:
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
	food = maxf(0.0, food - delta * FOOD_DECAY * hunger_cost)
	warmth = maxf(0.0, warmth - delta * (WARMTH_DECAY_HEATED if heater_repaired else WARMTH_DECAY) * shelter_cost)
	energy = maxf(0.0, energy - delta * ENERGY_DECAY * shelter_cost)
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


func service_scenario_for(npc_id: String) -> String:
	return str(SERVICE_SCENARIOS.get(npc_id.strip_edges().to_lower(), ""))


func can_start_service_dialogue(npc_id: String) -> bool:
	var key := npc_id.strip_edges().to_lower()
	return not service_scenario_for(key).is_empty()


func _try_begin_service_dialogue(npc_id: String) -> bool:
	if not can_start_service_dialogue(npc_id) or not is_inside_tree():
		return false
	var dynamic_service := get_tree().root.get_node_or_null(NodePath("NpcDialogueService"))
	if dynamic_service == null or not dynamic_service.enabled():
		return false
	return bool(dynamic_service.begin_scenario(npc_id, service_scenario_for(npc_id)))


func settle_service_transaction(npc_id: String, session_score: float, confirmed_item := "", transaction_id := "") -> String:
	var key := npc_id.strip_edges().to_lower()
	var item := confirmed_item.strip_edges().to_lower()
	if item.is_empty():
		return "none"
	var scenario_id := service_scenario_for(key)
	var scenario: Dictionary = {}
	if is_inside_tree():
		var registry := get_tree().root.get_node_or_null(NodePath("NpcScenarioRegistry"))
		if registry != null:
			scenario = registry.get_scenario(scenario_id)
	# Pure state tests and command-line tools may settle before autoload _ready.
	# Read the same server-owned role card; never skip item validation just
	# because the scene registry has not mounted yet.
	if scenario.is_empty() and not scenario_id.is_empty():
		var scenario_path := "res://data/dialogue/scenarios/%s.json" % scenario_id
		var scenario_file := FileAccess.open(scenario_path, FileAccess.READ)
		if scenario_file != null:
			var parsed = JSON.parse_string(scenario_file.get_as_text())
			if parsed is Dictionary:
				scenario = parsed
	if scenario.is_empty() \
		or str(scenario.get("npc_id", "")).strip_edges().to_lower() != key \
		or not item in scenario.get("inventory", []) \
		or item in scenario.get("generic_inventory_terms", []):
		return "none"
	if not is_finite(session_score):
		return "none"
	var score := clampf(session_score, 0.0, 100.0)
	var band := voice_band_for_score(score)
	if band == "none":
		message_requested.emit(tr("MSG_NPC_DIDNT_UNDERSTAND") % tr("NPC_%s" % key.to_upper()), "neutral")
	return _deliver_item(key, item, band, transaction_id)


func _deliver_item(npc_id: String, alias: String, band: String, transaction_id := "") -> String:
	var item_id: String = items.resolve_item(alias)
	if item_id.is_empty() or band == "none":
		return "none"
	var tx: String = transaction_id if not transaction_id.is_empty() else items.new_transaction_id()
	var quantity: int = items.offer_quantity(npc_id, item_id, band, day)
	var result: Dictionary = items.deliver(tx, npc_id, item_id, band, quantity, day)
	if not result.ok:
		message_requested.emit(_item_text("这件物品暂时无法再领取。", "This item is not available right now."), "neutral")
		return "none"
	if not result.get("duplicate", false):
		_items_did_change()
		var label: String = items.Catalog.label(items.definitions[item_id].name)
		message_requested.emit(_item_text("%s ×%d 已放到柜台。靠近物品选择现场使用或打包。", "%s ×%d is on the counter. Choose to use it here or pack it.") % [label, result.quantity], "good")
		item_feedback.emit("deliver", item_id)
		if npc_id == "tavi":
			onboarding_action("speak")
	return str(result.band)


func _fallback_item(npc_id: String, alias: String) -> void:
	if is_inside_tree():
		var adapter := get_tree().root.get_node_or_null("SpeechAdapter")
		if adapter != null and not adapter.runtime_speech_unavailable():
			return
	_deliver_item(npc_id, alias, "fallback")


func _item_text(zh: String, en: String) -> String:
	return zh if TranslationServer.get_locale().begins_with("zh") else en


func _items_did_change(persist := true) -> void:
	# Legacy counts are projections for older HUD/debug consumers, never rewards.
	berries = 0
	scrap = 0
	water = 0
	for record in items.instances.values():
		if not record.state in items.ACTIVE_STATES:
			continue
		var category: String = items.definitions[record.item_id].category
		if category == "food":
			berries += 1
		elif category == "component":
			scrap += 1
		elif category == "drink":
			water += 1
	heater_repaired = items.heater_progress >= items.heater_required
	items_changed.emit()
	state_changed.emit()
	needs_changed.emit(food, warmth, energy)
	objective_changed.emit(objective_text())
	if persist:
		save_game()


## Context is supplied by the world/input boundary, never inferred from HUD text.
func item_command(action: String, ids: Array, context: Dictionary, allow_waste := false) -> Dictionary:
	if game_finished or not bool(context.get("safe", false)) or interaction_time_frozen:
		return {"ok": false, "reason": "unsafe"}
	var novel := get_tree().get_first_node_in_group("novel_world") if is_inside_tree() else null
	if novel != null and not novel.validate_item_context(context):
		return {"ok": false, "reason": "location"}
	var location := str(context.get("location", "player"))
	# Revalidate at the command boundary: UI context is an intention, not authority.
	if is_inside_tree():
		var player := get_tree().get_first_node_in_group("player") as Node3D
		if player != null:
			if not player.item_use_is_safe():
				return {"ok": false, "reason": "unsafe"}
			if location != "player":
				var world := get_tree().get_first_node_in_group("item_world")
				if world == null or not world.anchors.has(location):
					return {"ok": false, "reason": "location"}
				var offset: Vector3 = player.global_position - world.anchors[location].global_position
				if Vector2(offset.x, offset.z).length() > 4.0:
					return {"ok": false, "reason": "location"}
	var expected := int(context.get("revision", -1))
	if expected >= 0 and expected != items.revision:
		return {"ok": false, "reason": "stale"}
	if ids.is_empty():
		return {"ok": false, "reason": "missing"}
	var id: String = ids[0]
	var needs := {"food": food, "warmth": warmth, "energy": energy}
	var result: Dictionary
	match action:
		"pack":
			result = items.pack(ids, location, expected)
		"consume":
			result = items.consume(id, needs, true, location, allow_waste)
		"place", "use_home", "reclaim", "deactivate":
			if not bool(context.get("at_home", false)):
				return {"ok": false, "reason": "home_only"}
			if action == "place":
				result = items.place(id, location)
			elif action == "use_home":
				result = items.use_home(id, location, needs, allow_waste)
			elif action == "deactivate":
				result = items.deactivate(id, location)
			else:
				result = items.reclaim(id, location)
		"give":
			var recipient := str(context.get("recipient", ""))
			if novel != null and recipient != novel.npc_id():
				return {"ok": false, "reason": "location"}
			result = _give_item(id, recipient)
		_:
			return {"ok": false, "reason": "invalid_action"}
	if result.get("ok", false):
		var effects: Dictionary = result.get("effects", {})
		food = minf(MAX_NEED, food + float(effects.get("food", 0.0)))
		warmth = minf(MAX_NEED, warmth + float(effects.get("warmth", 0.0)))
		energy = minf(MAX_NEED, energy + float(effects.get("energy", 0.0)))
		if action in ["pack", "consume"] and items.definitions[items.instances[id].item_id].category == "food":
			onboarding_action("use_item")
		_items_did_change()
		item_feedback.emit(str(result.get("action", action)), str(items.instances[id].item_id))
	return result


## Town rule 5 (2026-09-14): water reaches Rowan only through this explicit item
## action, with or without voice. Talking or gesturing never consumes the bag,
## and the help event happens once.
func _give_item(id: String, recipient: String) -> Dictionary:
	if recipient != "rowan":
		return {"ok": false, "reason": "transfer"}
	if completed_steps.has("help_rowan"):
		return {"ok": false, "reason": "given"}
	var result: Dictionary = items.transfer(id, recipient)
	if not result.ok:
		return result
	completed_steps["help_rowan"] = true
	remember("rowan", "MEMORY_HELP_ROWAN", 3)
	return result


func record_dialogue_scenario_result(scenario_id: String, outcome: String) -> bool:
	var scenario_key := scenario_id.strip_edges().to_lower()
	var clean_outcome := outcome.strip_edges().to_lower()
	if not scenario_key in DIALOGUE_SCENARIO_IDS or not clean_outcome in ["success", "failure"]:
		return false
	dialogue_scenario_progress[scenario_key] = {
		"outcome": clean_outcome,
		"day": day,
	}
	dialogue_scenario_changed.emit(scenario_key, clean_outcome)
	state_changed.emit()
	return true


func begin_onboarding() -> void:
	if onboarding_completed:
		return
	onboarding_active = true
	onboarding_step = ONBOARDING_STEPS[0]
	# FR-30: the guide's speak step must own the V key. A guided word-practice
	# turn captures push_to_talk, so any active session would stall the guide.
	if is_inside_tree():
		var dialogue := get_tree().root.get_node_or_null(NodePath("Dialogue"))
		if dialogue != null:
			dialogue.finish_word_practice()
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
	if game_finished:
		# P1-01 / G1-01: credit speech only when a spoken order really supplied the run.
		var summary := journey_summary()
		if summary.spoken_supplies:
			return tr("OBJECTIVE_COMPLETE")
		return tr("OBJECTIVE_COMPLETE_GESTURE" if summary.gesture_supplies else "OBJECTIVE_COMPLETE_EMPTY")
	if food < FOOD_COMFORT:
		return tr("OBJECTIVE_NEED_FOOD")
	if energy < ENERGY_COMFORT:
		return tr("OBJECTIVE_NEED_WATER")
	if _wants_sleep():
		return tr("OBJECTIVE_SLEEP")
	return tr("OBJECTIVE_EXPLORE")

func interact(kind: String, target_id: String, communication: String = "action", expression: Dictionary = {}) -> void:
	var previous_objective := objective_text()
	var greeted_mira_before := completed_steps.has("greet_mira")
	var dynamic_scenario_started := false
	if kind == "npc" and communication == "action":
		dynamic_scenario_started = _try_begin_service_dialogue(target_id)
	match kind:
		"npc":
			if not dynamic_scenario_started:
				_interact_npc(target_id, communication, expression)
		"berry":
			# FR-28: forage tokens are narrative guides now; resources come only
			# from a spoken request judged by the NPC.
			message_requested.emit(tr("MSG_FORAGE_REDIRECT"), "neutral")
		"scrap":
			message_requested.emit(tr("MSG_FORAGE_REDIRECT"), "neutral")
		"water":
			message_requested.emit(tr("MSG_RESERVOIR_REDIRECT"), "neutral")
		"item_counter", "item_home":
			item_interaction_requested.emit(kind, target_id)
		"heater":
			message_requested.emit(_item_text("把零件放到住处维修位，再逐件安装。", "Place parts at the home workbench, then install each one."), "neutral")
			item_interaction_requested.emit("item_home", "home_heater")
		"shelter":
			_try_sleep()
	if kind == "npc" and not dynamic_scenario_started:
		_report_dialogue(target_id, communication, expression)
	onboarding_action("interact")
	if target_id == "mira" and not greeted_mira_before and completed_steps.has("greet_mira"):
		onboarding_action("greet")
	state_changed.emit()
	needs_changed.emit(food, warmth, energy)
	if objective_text() != previous_objective:
		objective_changed.emit(objective_text())

func _interact_npc(npc_id: String, communication: String, expression: Dictionary) -> void:
	match npc_id:
		"mira":
			_interact_mira(communication, expression)
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

func _interact_mira(communication: String, expression: Dictionary) -> void:
	if _can_greet_mira():
		if not _critical_communication_understood("mira", communication, expression):
			return
		_greet_mira()
		_emit_npc_line("mira", communication, "greet_reply", "Welcome, stranger.")
		return
	_emit_npc_followup("mira", communication)

func _can_greet_mira() -> bool:
	return day == 1 and not completed_steps.has("greet_mira")

func _greet_mira() -> void:
	completed_steps["greet_mira"] = true
	remember("mira", "MEMORY_GREET_MIRA", 2)

## C1-01 / X1-06: in 2D the voice greeting is a spoken social exchange whose NPC
## reply finished playing. The client's playback edge reports it with the
## player's own recognition score, so the floor matches the legacy voice
## greeting and the model's words never change relationships.
func record_spoken_exchange(npc_id: String, score: float) -> void:
	if npc_id != "mira" or not _can_greet_mira() or not is_finite(score) or score < SCORE_SPARSE_MIN:
		return
	_greet_mira()
	onboarding_action("greet")
	state_changed.emit()
	save_game()

func _interact_rowan(communication: String, _expression: Dictionary) -> void:
	# Town rule 5: water reaches Rowan only through the explicit give action
	# (_give_item). Talking or gesturing never consumes the bag.
	_emit_npc_followup("rowan", communication)

func _interact_food_supplier(communication: String, expression: Dictionary) -> void:
	match communication:
		"gesture_fallback":
			_fallback_item("tavi", "burger")
		"gesture":
			message_requested.emit(tr("MSG_GESTURE_NO_RESOURCE") % tr("NPC_TAVI"), "neutral")
		"voice":
			# A raw pronunciation result is not a completed concrete service order.
			expression_evaluated.emit("tavi", expression)
			message_requested.emit(_item_text("请在柜台对话中确认具体物品。", "Confirm a specific item with the counter server."), "neutral")
		_:
			_emit_npc_followup("tavi", communication)

func _interact_scrap_supplier(communication: String, expression: Dictionary) -> void:
	match communication:
		"gesture_fallback":
			_fallback_item("vesh", "alloy parts")
		"gesture":
			message_requested.emit(tr("MSG_GESTURE_NO_RESOURCE") % tr("NPC_VESH"), "neutral")
		"voice":
			# A raw pronunciation result is not a completed concrete service order.
			expression_evaluated.emit("vesh", expression)
			message_requested.emit(_item_text("请在柜台对话中确认具体物品。", "Confirm a specific item with the counter server."), "neutral")
		_:
			_emit_npc_followup("vesh", communication)

func _interact_water_supplier(communication: String, expression: Dictionary) -> void:
	match communication:
		"gesture_fallback":
			_fallback_item("ori", "water")
		"gesture":
			message_requested.emit(tr("MSG_GESTURE_NO_RESOURCE") % tr("NPC_ORI"), "neutral")
		"voice":
			# A raw pronunciation result is not a completed concrete service order.
			expression_evaluated.emit("ori", expression)
			message_requested.emit(_item_text("请在柜台对话中确认具体物品。", "Confirm a specific item with the counter server."), "neutral")
		_:
			_emit_npc_followup("ori", communication)

func _grant_food(_score: float, communication: String, expression: Dictionary, _speak_line := true) -> void:
	_interact_food_supplier(communication, expression)

func _grant_scrap(_score: float, communication: String, expression: Dictionary, _speak_line := true) -> void:
	_interact_scrap_supplier(communication, expression)

func _grant_water(_score: float, communication: String, expression: Dictionary, _speak_line := true) -> void:
	_interact_water_supplier(communication, expression)

func _voice_score(expression: Dictionary) -> float:
	if expression.is_empty() or not expression.has("score"):
		return -1.0
	var raw: Variant = expression.get("score")
	if typeof(raw) != TYPE_FLOAT and typeof(raw) != TYPE_INT:
		return -1.0
	return clampf(float(raw), 0.0, 100.0)


func _critical_communication_understood(npc_id: String, communication: String, expression: Dictionary) -> bool:
	## Progress-critical social beats cannot be completed by Observe/E or by the
	## ordinary goodwill gesture. `gesture_fallback` is produced only when the
	## runtime has marked speech itself as unavailable.
	if communication == "gesture_fallback":
		return true
	if communication != "voice":
		_speak_npc_line(npc_id, "clarify")
		message_requested.emit(tr("MSG_GESTURE_NO_RESOURCE") % tr("NPC_%s" % npc_id.to_upper()), "neutral")
		return false
	var score := _voice_score(expression)
	expression_evaluated.emit(npc_id, expression)
	if score >= SCORE_SPARSE_MIN:
		return true
	_speak_npc_line(npc_id, "clarify")
	message_requested.emit(tr("MSG_NPC_DIDNT_UNDERSTAND") % tr("NPC_%s" % npc_id.to_upper()), "neutral")
	return false

func voice_band_for_score(score: float) -> String:
	if score >= SCORE_GENEROUS_MIN:
		return "generous"
	if score >= SCORE_SPARSE_MIN:
		return "sparse"
	return "none"


## FR-38: report the outcome of an NPC interaction to the Dialogue autoload.
## A low voice score is a clarify state (free retry), never a failure state.
func _report_dialogue(npc_id: String, communication: String, expression: Dictionary) -> void:
	if not is_inside_tree():
		return
	var tree := get_tree()
	if tree == null or tree.root == null:
		return
	var dialogue := tree.root.get_node_or_null(NodePath("Dialogue"))
	if dialogue == null:
		return
	if communication == "action":
		if dialogue.state_for(npc_id) == "idle":
			dialogue.begin(npc_id)
		return
	if communication in ["voice", "gesture", "gesture_fallback"]:
		var understood := communication == "gesture_fallback"
		if communication == "voice":
			understood = _voice_score(expression) >= SCORE_SPARSE_MIN
		dialogue.player_acted(npc_id, understood)
		if understood and communication == "voice":
			var vocabulary := tree.root.get_node_or_null(NodePath("Vocabulary"))
			if vocabulary != null:
				vocabulary.record_words_used_from_text(str(expression.get("text", "")))


func _emit_npc_followup(npc_id: String, communication: String) -> void:
	var entry: Dictionary = _npc_followup_line(npc_id)
	_emit_npc_line(npc_id, communication, str(entry.get("line_key", "")), str(entry.get("text", "")))

func _emit_npc_line(npc_id: String, communication: String, line_key: String, text: String = "") -> void:
	if not text.is_empty():
		npc_line_presented.emit(npc_id, text)
	## NPC dialogue is spoken (FR-32); the localized text narration is the
	## fallback for builds where the voice channel itself is unavailable.
	if _speak_npc_line(npc_id, line_key):
		return
	if text.is_empty():
		return
	var known: int = relationships.get(npc_id, 0)
	var tone := "good" if known > 0 else "neutral"
	message_requested.emit(_communication_reply(tr("NPC_%s" % npc_id.to_upper()), communication, text), tone)

func _speak_npc_line(npc_id: String, line_key: String) -> bool:
	## request_line returns false only when the voice channel is unavailable
	## (no-voice builds, unactivated cloud); late network failures stay silent
	## so a TTS hiccup never resurrects subtitles.
	if line_key.is_empty():
		return false
	if not is_inside_tree():
		return false
	var npc_voice := get_tree().root.get_node_or_null(NodePath("NpcVoice"))
	if npc_voice == null:
		return false
	return npc_voice.request_line(npc_id, line_key)

func _npc_followup_line(npc_id: String) -> Dictionary:
	## Returns {line_key, text}: the server catalog key for voice and the
	## localized text used only by the no-voice fallback.
	match npc_id:
		"mira":
			if completed_steps.has("greet_mira"):
				if food < FOOD_COMFORT:
					return {"line_key": "hint_food", "text": tr("NPC_MIRA_HINT_FOOD")}
				if energy < ENERGY_COMFORT:
					return {"line_key": "hint_rowan", "text": tr("NPC_MIRA_HINT_WATER")}
				return {"line_key": "remembers", "text": tr("NPC_MIRA_REMEMBERS")}
			return {"line_key": "", "text": tr("MSG_NPC_WARY")}
		"rowan":
			if water <= 0 and not completed_steps.has("help_rowan"):
				return {"line_key": "needs_water", "text": tr("NPC_ROWAN_NEEDS_WATER")}
			if not completed_steps.has("help_rowan"):
				# Water is at hand but not given yet: Rowan asks; the give action hands it over.
				return {"line_key": "social_ask_help", "text": "I cannot walk far. Could you bring me water?"}
			if int(relationships.get("rowan", 0)) > 0:
				return {"line_key": "remembers", "text": tr("NPC_ROWAN_REMEMBERS")}
			return {"line_key": "", "text": tr("NPC_ROWAN_WARY")}
		"tavi":
			return {"line_key": "hint_food", "text": tr("NPC_TAVI_HINT_FOOD")}
		"vesh":
			return {"line_key": "hint_scrap", "text": tr("NPC_VESH_HINT_SCRAP")}
		"ori":
			return {"line_key": "hint_water", "text": tr("NPC_ORI_HINT_WATER")}
		_:
			return {"line_key": "", "text": tr("MSG_NPC_REMEMBERS") if int(relationships.get(npc_id, 0)) > 0 else tr("MSG_NPC_WARY")}

func _communication_reply(speaker: String, communication: String, line: String) -> String:
	if communication == "voice":
		return tr("NPC_REPLY_VOICE") % [speaker, line]
	if communication in ["gesture", "gesture_fallback"]:
		var understood := tr("NPC_REPLY_GESTURE") % speaker
		if line.is_empty():
			return understood
		return "%s %s" % [understood, line]
	return tr("NPC_REPLY_OBSERVE")

func remember(npc_id: String, memory: String, relationship_gain: int) -> void:
	relationships[npc_id] = int(relationships.get(npc_id, 0)) + relationship_gain
	memories.append("%s：%s" % [npc_id, memory])

## P1-01 / G1-01: what this run actually did, for an ending that claims nothing
## more. Spoken orders come from the item ledger's voice bands; spoken social
## exchanges from the town contacts whose replies finished playing.
func journey_summary() -> Dictionary:
	var spoken_supplies := false
	var gesture_supplies := false
	var spoken: Dictionary = {}
	for transaction in items.transactions.values():
		var band := str(transaction.get("band", ""))
		if band in ["sparse", "generous"]:
			spoken_supplies = true
			spoken[str(transaction.get("service", ""))] = true
		elif band == "fallback":
			gesture_supplies = true
	var contacts = presentation_state.get("town_contacts", {})
	if contacts is Dictionary:
		for npc in contacts:
			if contacts[npc] is Dictionary and int(contacts[npc].get("completed_exchanges", 0)) > 0:
				spoken[str(npc)] = true
	var spoken_with: Array[String] = []
	var known: Array[String] = []
	for npc in relationships:
		if spoken.has(npc):
			spoken_with.append(npc)
		if spoken.has(npc) or int(relationships[npc]) > 0:
			known.append(npc)
	return {"spoken_supplies": spoken_supplies, "gesture_supplies": gesture_supplies, "spoken_with": spoken_with, "known": known, "faints": faints}

func _wants_sleep() -> bool:
	if game_finished:
		return false
	return clock_hours() >= SLEEP_HOUR or energy < ENERGY_TIRED


func _try_sleep() -> void:
	if game_finished:
		return
	if onboarding_active and onboarding_step != "sleep":
		message_requested.emit(tr("MSG_SLEEP_GUIDE"), "neutral")
		return
	if not onboarding_active and not _wants_sleep():
		message_requested.emit(tr("MSG_SLEEP_TOO_EARLY"), "neutral")
		return
	day += 1
	day_time = 0.0
	energy = MAX_NEED
	warmth = minf(MAX_NEED, warmth + 30.0 + items.sleep_warmth_bonus())
	if day > SLICE_NIGHTS:
		game_finished = true
		run_completed.emit()
	clock_changed.emit(day, 0)
	day_started.emit(day)
	onboarding_action("sleep")
	save_game()

func faint() -> void:
	item_interaction_interrupted.emit()
	var cause := "food" if food <= 0.0 else ("warmth" if warmth <= 0.0 else "energy")
	food = maxf(food, FAINT_FOOD_FLOOR)
	warmth = maxf(warmth, FAINT_WARMTH_FLOOR)
	energy = maxf(energy, FAINT_ENERGY_FLOOR)
	day_time = maxf(day_time, minf(DAY_DURATION - 30.0, day_time + FAINT_SECONDS))
	faints += 1
	# X1-01: a hunger faint never takes the meal that would have helped.
	var lost: String = items.faint_loss(cause == "food")
	last_faint = {"cause": cause, "lost": str(items.instances[lost].item_id) if not lost.is_empty() else "", "day": day}
	_items_did_change()
	message_requested.emit(tr("MSG_FAINTED"), "warning")
	state_changed.emit()
	needs_changed.emit(food, warmth, energy)
	clock_changed.emit(day, int(day_time))
	objective_changed.emit(objective_text())

func reset_run() -> void:
	item_interaction_interrupted.emit()
	if is_inside_tree():
		var dynamic_service := get_tree().root.get_node_or_null(NodePath("NpcDialogueService"))
		if dynamic_service != null and dynamic_service.has_active_session():
			dynamic_service.cancel("VOICE_REASON_DIALOGUE_CANCELLED")
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
	items = ItemStateScript.new()
	items_changed.emit()
	completed_steps.clear()
	dialogue_scenario_progress.clear()
	memories.clear()
	game_finished = false
	faints = 0
	last_faint = {}
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
	var file := FileAccess.open(save_path + ".tmp", FileAccess.WRITE)
	if file == null:
		message_requested.emit(tr("MSG_SAVE_FAILED"), "warning")
		return false
	var data := {
		"version": SAVE_VERSION,
		"items": items.snapshot(),
		"presentation_state": presentation_state,
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
		"faints": faints,
		"onboarding_completed": onboarding_completed,
		"onboarding_active": onboarding_active,
		"onboarding_step": onboarding_step,
		"vocabulary_tier": vocabulary_tier,
		"vocabulary_entries": vocabulary_entries,
		"dialogue_scenario_progress": dialogue_scenario_progress,
	}
	file.store_string(JSON.stringify(data))
	var write_error := file.get_error()
	file.close()
	if write_error != OK:
		return false
	return DirAccess.rename_absolute(ProjectSettings.globalize_path(save_path + ".tmp"), ProjectSettings.globalize_path(save_path)) == OK

## FR-35: reads only the vocabulary copy kept in another chapter's save and never
## touches the rest of it. Unreadable or newer-version saves contribute nothing.
func saved_vocabulary_entries(path: String) -> Dictionary:
	if path.is_empty() or not FileAccess.file_exists(path):
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		return {}
	var saved_version := int(parsed.get("version", 1))
	if saved_version < 1 or saved_version > SAVE_VERSION:
		return {}
	var saved_vocabulary = parsed.get("vocabulary_entries", {})
	return saved_vocabulary if saved_vocabulary is Dictionary else {}

func load_game() -> bool:
	if not FileAccess.file_exists(save_path):
		return false
	var file := FileAccess.open(save_path, FileAccess.READ)
	if file == null:
		return false
	var parsed = JSON.parse_string(file.get_as_text())
	if not parsed is Dictionary:
		return false
	# SAVE_VERSION 2 added the voice-gated quest flow, version 3 added the
	# vocabulary profile, and version 4 added isolated pilot-dialogue outcomes.
	# Migrations are lazy: missing keys keep defaults
	# and every persisted value from an older save is retained.
	var saved_version := int(parsed.get("version", 1))
	if saved_version < 1 or saved_version > SAVE_VERSION:
		return false
	var restored_items = ItemStateScript.new()
	if saved_version >= 5:
		if not parsed.get("items") is Dictionary or not restored_items.restore(parsed.items):
			return false
	else:
		restored_items.migrate(int(parsed.get("berries", 0)), int(parsed.get("scrap", 0)), int(parsed.get("water", 0)), bool(parsed.get("heater_repaired", false)))
	var saved_presentation = parsed.get("presentation_state", {})
	presentation_state = saved_presentation if saved_presentation is Dictionary else {}
	items = restored_items
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
	faints = maxi(0, int(parsed.get("faints", 0)))
	last_faint = {}
	onboarding_completed = bool(parsed.get("onboarding_completed", false))
	onboarding_active = bool(parsed.get("onboarding_active", false)) and not onboarding_completed
	var saved_step := str(parsed.get("onboarding_step", ONBOARDING_STEPS[0]))
	onboarding_step = saved_step if saved_step in ONBOARDING_STEPS else ONBOARDING_STEPS[0]
	vocabulary_tier = str(parsed.get("vocabulary_tier", "toddler"))
	var saved_vocabulary = parsed.get("vocabulary_entries", {})
	vocabulary_entries = saved_vocabulary if saved_vocabulary is Dictionary else {}
	var saved_dialogue_progress = parsed.get("dialogue_scenario_progress", {})
	dialogue_scenario_progress = saved_dialogue_progress if saved_dialogue_progress is Dictionary else {}
	state_changed.emit()
	needs_changed.emit(food, warmth, energy)
	clock_changed.emit(day, int(day_time))
	objective_changed.emit(objective_text())
	_items_did_change(false)
	onboarding_changed.emit(onboarding_step, onboarding_active)
	return true
