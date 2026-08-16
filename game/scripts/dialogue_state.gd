class_name DialogueState
extends Node
## FR-38: minimal multi-turn dialogue state. Every session keeps the no-penalty
## invariant: a miss moves to clarify, never to failure, and any number of free
## retries can follow. GameState owns resource/relationship effects; this class
## only tracks the conversational shape.

signal session_changed(npc_id: String, state: String, line_key: String)

const STATES := ["idle", "opening", "awaiting", "understood", "clarify", "closed"]
const CLOSE_AFTER_UNDERSTOOD := true

var sessions: Dictionary = {}


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


func reset_all() -> void:
	sessions.clear()
