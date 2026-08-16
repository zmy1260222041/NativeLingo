class_name SocialSimulator
extends Node
## FR-33/FR-34: ambient NPC-to-NPC need-expression scenes. The scripts are static,
## reviewed English so the coverage tool can prove every survival-essential
## expression is observable. Playback is toast + optional NpcVoice audio; a
## social line never mutates quest or relationship state.

signal script_started(script_id: String)
signal line_displayed(script_id: String, npc_id: String, line_id: String)

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

var interval_min := 16.0
var interval_max := 24.0
var timer: Timer
var script_index := 0
var running := false


func _ready() -> void:
	timer = Timer.new()
	timer.one_shot = true
	timer.timeout.connect(_on_timer)
	add_child(timer)
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


func _on_timer() -> void:
	if not running:
		return
	play_script(script_index)
	script_index = (script_index + 1) % SOCIAL_SCRIPTS.size()
	_arm_timer()


func _arm_timer() -> void:
	timer.start(randf_range(interval_min, interval_max))


func play_script(index: int) -> Dictionary:
	if index < 0 or index >= SOCIAL_SCRIPTS.size():
		return {}
	var script: Dictionary = SOCIAL_SCRIPTS[index]
	script_started.emit(script["id"])
	for new_word in script["new_words"]:
		Vocabulary.observe_word(str(new_word))
	for line in script["lines"]:
		var npc_id: String = line["npc_id"]
		var line_id: String = line["line_id"]
		GameState.message_requested.emit("%s: “%s”" % [tr("NPC_%s" % npc_id.to_upper()), str(line["text"])], "neutral")
		NpcVoice.request_line(npc_id, line_id)
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
