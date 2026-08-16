class_name DialogueState
extends Node
## FR-38: minimal multi-turn dialogue state. Every session keeps the no-penalty
## invariant: a miss moves to clarify, never to failure, and any number of free
## retries can follow. GameState owns resource/relationship effects; this class
## only tracks the conversational shape.

signal session_changed(npc_id: String, state: String, line_key: String)
signal word_practice_requested(npc_id: String, options: Array)
signal word_practice_selected(word: String)
signal word_practice_finished(npc_id: String)

const STATES := ["idle", "opening", "awaiting", "understood", "clarify", "closed"]
const CLOSE_AFTER_UNDERSTOOD := true

var sessions: Dictionary = {}
var word_practice_active := false
var word_practice_npc_id := ""
var word_practice_options: Array = []
var word_practice_selected_word := ""


func begin(npc_id: String) -> void:
	var key := npc_id.strip_edges().to_lower()
	sessions[key] = {"state": "opening", "misses": 0}
	session_changed.emit(key, "opening", "opening")


func player_acted(npc_id: String, understood: bool) -> void:
	var key := npc_id.strip_edges().to_lower()
	if not sessions.has(key):
		sessions[key] = {"state": "opening", "misses": 0}
	var session: Dictionary = sessions[key]
	if understood:
		session["state"] = "understood"
		session["misses"] = 0
		session_changed.emit(key, "understood", "understood")
		if CLOSE_AFTER_UNDERSTOOD:
			close(key)
		return
	session["misses"] = int(session.get("misses", 0)) + 1
	session["state"] = "clarify"
	session_changed.emit(key, "clarify", "clarify")


func state_for(npc_id: String) -> String:
	var key := npc_id.strip_edges().to_lower()
	if not sessions.has(key):
		return "idle"
	return str(sessions[key].get("state", "idle"))


func misses_for(npc_id: String) -> int:
	var key := npc_id.strip_edges().to_lower()
	if not sessions.has(key):
		return 0
	return int(sessions[key].get("misses", 0))


func close(npc_id: String) -> void:
	var key := npc_id.strip_edges().to_lower()
	if sessions.has(key):
		sessions.erase(key)
	session_changed.emit(key, "closed", "closed")


func begin_word_practice(npc_id: String, options: Array) -> bool:
	var key := npc_id.strip_edges().to_lower()
	var clean_options: Array = []
	for option in options:
		var word := str(option).strip_edges().to_lower()
		if not word.is_empty() and word not in clean_options:
			clean_options.append(word)
	if clean_options.is_empty():
		return false
	word_practice_active = true
	word_practice_npc_id = key
	word_practice_options = clean_options
	word_practice_selected_word = ""
	word_practice_requested.emit(key, clean_options)
	return true


func select_word_practice(word: String) -> bool:
	var clean := word.strip_edges().to_lower()
	if not word_practice_active or clean not in word_practice_options:
		return false
	word_practice_selected_word = clean
	word_practice_selected.emit(clean)
	return true


func finish_word_practice() -> void:
	if not word_practice_active:
		return
	var npc_id := word_practice_npc_id
	word_practice_active = false
	word_practice_npc_id = ""
	word_practice_options.clear()
	word_practice_selected_word = ""
	word_practice_finished.emit(npc_id)


func reset_all() -> void:
	sessions.clear()
	finish_word_practice()
