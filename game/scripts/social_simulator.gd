class_name SocialSimulator
extends Node
## FR-33/FR-34: ambient NPC-to-NPC need-expression scenes. The scripts are static,
## reviewed English so the coverage tool can prove every survival-essential
## expression is observable. NPCs first walk to a meeting point near each other,
## exchange the lines as voice only (text is the no-voice-build fallback), then
## stroll home; a social line never mutates quest or relationship state.

signal script_started(script_id: String)
signal line_displayed(script_id: String, npc_id: String, line_id: String)
signal scene_finished(script_id: String)

const FAMILY_UNITS := [
	["mira", "tavi"],
	["vesh", "ori"],
	["rowan", "ori"],
]

const REQUIRED_EXPRESSIONS := {
	"greeting": ["good morning"],
	"food": ["can i have some food"],
	"scrap": ["alloy parts"],
	"water": ["canteen of water"],
	"help": ["bring me water"],
}

const SOCIAL_SCRIPTS := [
	{
		"id": "mira_tavi_morning",
		"intent": "greeting",
		"family": ["mira", "tavi"],
		"new_words": ["morning", "sleep", "hungry"],
		"lines": [
			{"npc_id": "mira", "line_id": "social_greeting", "text": "Good morning. Did you sleep well?"},
			{"npc_id": "tavi", "line_id": "social_reply_greeting", "text": "I slept. Are you hungry?"},
		],
	},
	{
		"id": "tavi_mira_food",
		"intent": "food",
		"family": ["mira", "tavi"],
		"new_words": ["food", "please", "portions"],
		"lines": [
			{"npc_id": "tavi", "line_id": "social_ask_food", "text": "Can I have some food, please?"},
			{"npc_id": "mira", "line_id": "social_reply_food", "text": "Of course. Take two portions."},
		],
	},
	{
		"id": "vesh_ori_scrap",
		"intent": "scrap",
		"family": ["vesh", "ori"],
		"new_words": ["heater", "alloy", "parts"],
		"lines": [
			{"npc_id": "vesh", "line_id": "social_ask_scrap", "text": "The heater needs two alloy parts. Do you have any?"},
			{"npc_id": "ori", "line_id": "social_reply_scrap", "text": "I have one. Ask Tavi for the other."},
		],
	},
	{
		"id": "ori_rowan_water",
		"intent": "water",
		"family": ["rowan", "ori"],
		"new_words": ["canteen", "water", "thirsty"],
		"lines": [
			{"npc_id": "ori", "line_id": "social_ask_water", "text": "I need a canteen of water."},
			{"npc_id": "rowan", "line_id": "social_reply_water", "text": "I am thirsty too. Bring me water, please."},
		],
	},
	{
		"id": "rowan_ori_help",
		"intent": "help",
		"family": ["rowan", "ori"],
		"new_words": ["help", "bring", "water"],
		"lines": [
			{"npc_id": "rowan", "line_id": "social_ask_help", "text": "I cannot walk far. Could you bring me water?"},
			{"npc_id": "ori", "line_id": "social_reply_help", "text": "I will ask the little one to help."},
		],
	},
]

## Do not pull an NPC away while the player is talking to them or about to.
const PLAYER_ENGAGE_RADIUS := 5.0
## Standing gap between the two talkers once gathered.
const TALK_STANDOFF_M := 0.7
## Upper bound for one scene's voice playback before the NPCs disperse anyway.
const TALK_SAFETY_TIMEOUT := 16.0

enum Phase { IDLE, GATHERING, TALKING, DISBURSING }

var interval_min := 16.0
var interval_max := 24.0
var timer: Timer
var talk_timer: Timer
var script_index := 0
var running := false
var phase := Phase.IDLE
var current_script: Dictionary = {}
var participants: Array = []
var pending_line_keys: Array[String] = []


func _ready() -> void:
	timer = Timer.new()
	timer.one_shot = true
	timer.timeout.connect(_on_timer)
	add_child(timer)
	talk_timer = Timer.new()
	talk_timer.one_shot = true
	talk_timer.timeout.connect(_end_talking)
	add_child(talk_timer)
	NpcVoice.line_audio_ready.connect(_on_line_audio_ready)
	NpcVoice.line_audio_failed.connect(_on_line_audio_failed)
	if not Engine.is_editor_hint():
		start()


func start() -> void:
	if running or SOCIAL_SCRIPTS.is_empty():
		return
	running = true
	_arm_timer()


func stop() -> void:
	running = false
	timer.stop()
	talk_timer.stop()
	for npc in participants:
		if is_instance_valid(npc) and npc.has_method("stop_walking"):
			npc.stop_walking()
	participants.clear()
	pending_line_keys.clear()
	current_script = {}
	phase = Phase.IDLE


func _process(_delta: float) -> void:
	if not running:
		return
	match phase:
		Phase.GATHERING:
			if _all_participants_settled():
				_begin_talking()
		Phase.DISBURSING:
			if _all_participants_settled():
				_finish_scene()


func _on_timer() -> void:
	if not running:
		return
	if not _try_begin_scene():
		# Participant missing or engaged with the player: try the next script.
		script_index = (script_index + 1) % SOCIAL_SCRIPTS.size()
	if phase == Phase.IDLE:
		_arm_timer()


func _arm_timer() -> void:
	timer.start(randf_range(interval_min, interval_max))


func _try_begin_scene() -> bool:
	if phase != Phase.IDLE or GameState.onboarding_active:
		return false
	var script: Dictionary = SOCIAL_SCRIPTS[script_index]
	var npcs := _resolve_participants(script)
	if npcs.size() != 2:
		return false
	for npc in npcs:
		if npc.is_walking() or _npc_engaged_with_player(npc):
			return false
	participants = npcs
	current_script = script
	var first: Node3D = npcs[0]
	var second: Node3D = npcs[1]
	var midpoint := (first.global_position + second.global_position) * 0.5
	var axis := second.global_position - first.global_position
	axis.y = 0.0
	axis = axis.normalized() if axis.length() > 0.001 else Vector3.RIGHT
	first.walk_to(midpoint - axis * TALK_STANDOFF_M)
	second.walk_to(midpoint + axis * TALK_STANDOFF_M)
	phase = Phase.GATHERING
	return true


func _begin_talking() -> void:
	phase = Phase.TALKING
	script_started.emit(str(current_script.get("id", "")))
	for new_word in current_script.get("new_words", []):
		Vocabulary.observe_word(str(new_word))
	pending_line_keys.clear()
	for line in current_script.get("lines", []):
		var npc_id := str(line["npc_id"])
		var line_id := str(line["line_id"])
		if NpcVoice.request_line(npc_id, line_id):
			pending_line_keys.append("%s/%s" % [npc_id, line_id])
		else:
			# No-voice builds keep the localized text narration per line.
			GameState.message_requested.emit("%s: “%s”" % [tr("NPC_%s" % npc_id.to_upper()), str(line["text"])], "neutral")
			line_displayed.emit(str(current_script.get("id", "")), npc_id, line_id)
	if pending_line_keys.is_empty():
		# Nothing went to the voice queue; the text fallback already played.
		_end_talking.call_deferred()
		return
	talk_timer.start(TALK_SAFETY_TIMEOUT)


func _on_line_audio_ready(npc_id: String, line_id: String) -> void:
	if phase != Phase.TALKING:
		return
	var key := "%s/%s" % [npc_id, line_id]
	if key in pending_line_keys:
		line_displayed.emit(str(current_script.get("id", "")), npc_id, line_id)


func _on_line_audio_failed(_npc_id: String, _line_id: String, _reason: String) -> void:
	if phase != Phase.TALKING:
		return
	_check_talk_complete("%s/%s" % [_npc_id, _line_id])


func _on_line_audio_finished(npc_id: String, line_id: String) -> void:
	if phase != Phase.TALKING:
		return
	_check_talk_complete("%s/%s" % [npc_id, line_id])


func _check_talk_complete(line_key: String) -> void:
	if not line_key in pending_line_keys:
		return
	pending_line_keys.erase(line_key)
	if pending_line_keys.is_empty():
		_end_talking()


func _end_talking() -> void:
	if phase != Phase.TALKING:
		return
	talk_timer.stop()
	pending_line_keys.clear()
	phase = Phase.DISBURSING
	for npc in participants:
		if is_instance_valid(npc):
			npc.walk_home()


func _finish_scene() -> void:
	var script_id := str(current_script.get("id", ""))
	participants.clear()
	current_script = {}
	phase = Phase.IDLE
	scene_finished.emit(script_id)
	script_index = (script_index + 1) % SOCIAL_SCRIPTS.size()
	_arm_timer()


func _all_participants_settled() -> bool:
	for npc in participants:
		if not is_instance_valid(npc):
			return false
		if npc.has_method("is_walking") and npc.is_walking():
			return false
	return true


func _resolve_participants(script: Dictionary) -> Array:
	var family: Array = script.get("family", [])
	var found: Array = []
	for npc in get_tree().get_nodes_in_group("interactable"):
		if not npc is Node3D or str(npc.get("interaction_kind")) != "npc":
			continue
		var family_index := family.find(str(npc.get("target_id")))
		if family_index >= 0:
			while found.size() <= family_index:
				found.append(null)
			found[family_index] = npc
	var resolved: Array = []
	for npc in found:
		if npc == null:
			return []
		resolved.append(npc)
	return resolved


func _npc_engaged_with_player(npc: Node3D) -> bool:
	var player := get_tree().get_first_node_in_group("player") as Node3D
	if player == null:
		return false
	if player.get("nearby_target") == npc:
		return true
	return npc.global_position.distance_to(player.global_position) < PLAYER_ENGAGE_RADIUS


func play_script(index: int) -> Dictionary:
	## Immediate playback used by tests and debug tooling: no walking, the
	## lines go out right now (voice queue when available, text otherwise).
	if index < 0 or index >= SOCIAL_SCRIPTS.size():
		return {}
	var script: Dictionary = SOCIAL_SCRIPTS[index]
	script_started.emit(script["id"])
	for new_word in script["new_words"]:
		Vocabulary.observe_word(str(new_word))
	for line in script["lines"]:
		var npc_id: String = line["npc_id"]
		var line_id: String = line["line_id"]
		if not NpcVoice.request_line(npc_id, line_id):
			GameState.message_requested.emit("%s: “%s”" % [tr("NPC_%s" % npc_id.to_upper()), str(line["text"])], "neutral")
		line_displayed.emit(script["id"], npc_id, line_id)
	return script


func script_text(index: int) -> String:
	if index < 0 or index >= SOCIAL_SCRIPTS.size():
		return ""
	var parts: Array[String] = []
	for line in SOCIAL_SCRIPTS[index]["lines"]:
		parts.append(str(line["text"]))
	return " ".join(parts)


func coverage_map() -> Dictionary:
	var found := {}
	for script in SOCIAL_SCRIPTS:
		var intent: String = script["intent"]
		var text := script_text(SOCIAL_SCRIPTS.find(script))
		if found.has(intent):
			found[intent] = str(found[intent]) + " " + text
		else:
			found[intent] = text
	return found


func required_expressions_covered() -> bool:
	var coverage := coverage_map()
	for intent in REQUIRED_EXPRESSIONS:
		if not coverage.has(intent):
			return false
		for phrase in REQUIRED_EXPRESSIONS[intent]:
			if not str(coverage[intent]).to_lower().contains(str(phrase).to_lower()):
				return false
	return true


func all_npcs_have_family() -> bool:
	var family_members := {}
	for unit in FAMILY_UNITS:
		for npc_id in unit:
			family_members[npc_id] = true
	for npc_id in ["mira", "rowan", "tavi", "vesh", "ori"]:
		if not family_members.has(npc_id):
			return false
	return true
