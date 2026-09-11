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

const STATES := ["idle", "opening", "awaiting", "awaiting_player", "generating", "speaking", "awaiting_follow_up", "understood", "clarify", "closed"]
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


func begin_scenario(npc_id: String, scenario_id: String) -> bool:
	var key := npc_id.strip_edges().to_lower()
	var scenario := scenario_id.strip_edges().to_lower()
	if key.is_empty() or scenario.is_empty():
		return false
	sessions[key] = {
		"state": "opening",
		"misses": 0,
		"dynamic": true,
		"scenario_id": scenario,
		"history": [],
		"reply_id": "",
	}
	session_changed.emit(key, "opening", "opening")
	return true


func await_player(npc_id: String, line_key := "opening") -> bool:
	var key := npc_id.strip_edges().to_lower()
	if not has_dynamic_session(key):
		return false
	var session: Dictionary = sessions[key]
	session["state"] = "awaiting_player"
	session_changed.emit(key, "awaiting_player", line_key)
	return true


func has_dynamic_session(npc_id: String) -> bool:
	var key := npc_id.strip_edges().to_lower()
	return sessions.has(key) and bool(sessions[key].get("dynamic", false))


func scenario_for(npc_id: String) -> String:
	var key := npc_id.strip_edges().to_lower()
	if not sessions.has(key):
		return ""
	return str(sessions[key].get("scenario_id", ""))


func history_for(npc_id: String) -> Array:
	var key := npc_id.strip_edges().to_lower()
	if not sessions.has(key):
		return []
	var history: Array = sessions[key].get("history", [])
	return history.duplicate(true)


func begin_generation(npc_id: String, transcript: String) -> bool:
	var key := npc_id.strip_edges().to_lower()
	if not has_dynamic_session(key):
		return false
	var session: Dictionary = sessions[key]
	if str(session.get("state", "")) not in ["awaiting_player", "awaiting_follow_up", "clarify"]:
		return false
	var history: Array = session.get("history", [])
	history.append({"role": "player", "text": transcript.strip_edges()})
	if history.size() > 8:
		history = history.slice(history.size() - 8)
	session["history"] = history
	session["state"] = "generating"
	session["misses"] = 0
	session_changed.emit(key, "generating", "generating")
	return true


func retry_generation(npc_id: String) -> bool:
	var key := npc_id.strip_edges().to_lower()
	if not has_dynamic_session(key):
		return false
	var session: Dictionary = sessions[key]
	session["state"] = "generating"
	session_changed.emit(key, "generating", "retrying")
	return true


func accept_dynamic_reply(npc_id: String, reply_id: String, text: String, next_state := "awaiting_follow_up") -> bool:
	var key := npc_id.strip_edges().to_lower()
	if not has_dynamic_session(key) or reply_id.strip_edges().is_empty() or text.strip_edges().is_empty():
		return false
	var session: Dictionary = sessions[key]
	var history: Array = session.get("history", [])
	history.append({"role": "npc", "text": text.strip_edges()})
	if history.size() > 8:
		history = history.slice(history.size() - 8)
	session["history"] = history
	session["reply_id"] = reply_id.strip_edges()
	session["next_state"] = next_state if next_state in ["awaiting_player", "awaiting_follow_up", "closed"] else "awaiting_follow_up"
	session["state"] = "speaking"
	session_changed.emit(key, str(session["state"]), reply_id.strip_edges())
	return true


func finish_speaking(npc_id: String, reply_id: String) -> String:
	var key := npc_id.strip_edges().to_lower()
	if not has_dynamic_session(key):
		return ""
	var session: Dictionary = sessions[key]
	if str(session.get("reply_id", "")) != reply_id.strip_edges():
		return ""
	var next_state := str(session.get("next_state", "awaiting_follow_up"))
	if next_state == "closed":
		close(key)
		return "closed"
	session["state"] = next_state
	session_changed.emit(key, next_state, reply_id.strip_edges())
	return next_state


func dynamic_failed(npc_id: String, reason := "") -> bool:
	var key := npc_id.strip_edges().to_lower()
	if not has_dynamic_session(key):
		return false
	var session: Dictionary = sessions[key]
	session["state"] = "clarify"
	session["misses"] = int(session.get("misses", 0)) + 1
	session_changed.emit(key, "clarify", reason if not reason.is_empty() else "clarify")
	return true


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
