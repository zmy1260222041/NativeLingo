extends Node
## Owns service-point conversation scoring. Grok can describe a turn; only this
## runner records turns and asks GameState to grant resources after a completed
## transaction.

signal scenario_started(npc_id: String, scenario_id: String)
signal scenario_state_changed(npc_id: String, scenario_id: String, state: String)
signal scenario_finished(npc_id: String, scenario_id: String, outcome: String)

var sessions: Dictionary = {}


func begin(npc_id: String, scenario_id: String) -> bool:
	var npc := npc_id.strip_edges().to_lower()
	var scenario_key := scenario_id.strip_edges().to_lower()
	var registry := _registry()
	if registry == null:
		return false
	var scenario: Dictionary = registry.get_scenario(scenario_key)
	if scenario.is_empty() or str(scenario.get("npc_id", "")).to_lower() != npc:
		return false
	sessions[npc] = {
		"transaction_id": get_tree().root.get_node("GameState").items.new_transaction_id(),
		"scenario_id": scenario_key,
		"scenario_state": "waiting_for_request",
		"turns": [],
	}
	scenario_started.emit(npc, scenario_key)
	return true


func game_context(npc_id: String) -> Dictionary:
	var npc := npc_id.strip_edges().to_lower()
	if not sessions.has(npc):
		return {}
	var session: Dictionary = sessions[npc]
	return {
		"scenario_state": str(session.get("scenario_state", "waiting_for_request")),
		"turns": (session.get("turns", []) as Array).size(),
		"running_score": running_score(npc),
	}


func record_player_turn(npc_id: String, pronunciation: float, idiomaticity: float) -> float:
	var npc := npc_id.strip_edges().to_lower()
	if not sessions.has(npc):
		return -1.0
	var turn_score := clampf(0.5 * pronunciation + 0.5 * idiomaticity, 0.0, 100.0)
	var session: Dictionary = sessions[npc]
	var turns: Array = session.get("turns", [])
	turns.append({
		"pronunciation": pronunciation,
		"idiomaticity": idiomaticity,
		"score": turn_score,
	})
	session["turns"] = turns
	return running_score(npc)


func running_score(npc_id: String) -> float:
	var npc := npc_id.strip_edges().to_lower()
	if not sessions.has(npc):
		return -1.0
	var turns: Array = sessions[npc].get("turns", [])
	if turns.is_empty():
		return -1.0
	var total := 0.0
	for turn in turns:
		total += float(turn.get("score", 0.0))
	return total / float(turns.size())


func apply_validated_reply(
	npc_id: String,
	scenario_id: String,
	speech_act: String,
	next_state: String,
	transaction_complete := false,
	confirmed_item := "",
) -> bool:
	var npc := npc_id.strip_edges().to_lower()
	var scenario_key := scenario_id.strip_edges().to_lower()
	if not sessions.has(npc):
		return false
	var session: Dictionary = sessions[npc]
	if str(session.get("scenario_id", "")) != scenario_key:
		return false
	var registry := _registry()
	var scenario: Dictionary = registry.get_scenario(scenario_key) if registry != null else {}
	if scenario.is_empty() or not speech_act in scenario.get("allowed_speech_acts", []):
		return false
	var clean_item := confirmed_item.strip_edges().to_lower()
	var completion_valid: bool = transaction_complete \
		and speech_act in scenario.get("completion_speech_acts", []) \
		and clean_item in scenario.get("inventory", []) \
		and not clean_item in scenario.get("generic_inventory_terms", [])
	if transaction_complete and not completion_valid:
		# Treat an unproven close as another conversational turn. Never erase the
		# session or grant a resource from a bare model boolean.
		session["scenario_state"] = "awaiting_follow_up"
		scenario_state_changed.emit(npc, scenario_key, "awaiting_follow_up")
		return true
	if next_state != "closed":
		session["scenario_state"] = "awaiting_follow_up"
		scenario_state_changed.emit(npc, scenario_key, "awaiting_follow_up")
		return true
	var score := running_score(npc)
	var outcome := "failure"
	if completion_valid:
		var game_state := get_tree().root.get_node_or_null(NodePath("GameState"))
		if game_state != null:
			var band := str(game_state.settle_service_transaction(npc, score, clean_item, str(session.transaction_id)))
			outcome = "success" if band != "none" else "failure"
			game_state.record_dialogue_scenario_result(scenario_key, outcome)
	else:
		var game_state := get_tree().root.get_node_or_null(NodePath("GameState"))
		if game_state != null:
			game_state.record_dialogue_scenario_result(scenario_key, "failure")
	sessions.erase(npc)
	scenario_finished.emit(npc, scenario_key, outcome)
	return true


func cancel(npc_id: String, scenario_id := "") -> void:
	var npc := npc_id.strip_edges().to_lower()
	if not sessions.has(npc):
		return
	var session: Dictionary = sessions[npc]
	var scenario_key := str(session.get("scenario_id", ""))
	if not scenario_id.strip_edges().is_empty() and scenario_key != scenario_id.strip_edges().to_lower():
		return
	sessions.erase(npc)
	scenario_finished.emit(npc, scenario_key, "cancelled")


func _registry() -> Node:
	return get_tree().root.get_node_or_null(NodePath("NpcScenarioRegistry"))
