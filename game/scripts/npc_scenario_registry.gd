extends Node
## Godot-only registry for service-point role cards. The runtime reads only
## res://data/dialogue and never imports desktop/backend.

const SCENARIO_DIR := "res://data/dialogue/scenarios"
const PROFILE_DIR := "res://data/dialogue/npc_profiles"

var scenarios: Dictionary = {}
var profiles: Dictionary = {}
var load_notes: Array[String] = []


func _ready() -> void:
	_reload()


func _reload() -> void:
	scenarios.clear()
	profiles.clear()
	load_notes.clear()
	_load_profiles()
	_load_scenarios()


func scenario_ids_for(npc_id: String) -> Array[String]:
	var key := npc_id.strip_edges().to_lower()
	var profile: Dictionary = profiles.get(key, {})
	var ids: Array[String] = []
	for raw_id in profile.get("scenario_ids", []):
		var id := str(raw_id).strip_edges().to_lower()
		if scenarios.has(id):
			ids.append(id)
	return ids


func next_scenario_for(npc_id: String) -> String:
	var ids := scenario_ids_for(npc_id)
	if ids.is_empty():
		return ""
	return ids[0]


func get_scenario(scenario_id: String) -> Dictionary:
	return (scenarios.get(scenario_id.strip_edges().to_lower(), {}) as Dictionary).duplicate(true)


func get_profile(npc_id: String) -> Dictionary:
	return (profiles.get(npc_id.strip_edges().to_lower(), {}) as Dictionary).duplicate(true)


func workplace_anchor(npc_id: String, fallback: Vector3 = Vector3.ZERO) -> Vector3:
	var workplace: Dictionary = get_profile(npc_id).get("workplace", {})
	var anchor = workplace.get("anchor", [])
	if anchor is Array and anchor.size() >= 3:
		return Vector3(float(anchor[0]), float(anchor[1]), float(anchor[2]))
	return fallback


func has_scenario(scenario_id: String) -> bool:
	return scenarios.has(scenario_id.strip_edges().to_lower())


func _load_profiles() -> void:
	var dir := DirAccess.open(PROFILE_DIR)
	if dir == null:
		load_notes.append("dialogue profile directory missing")
		return
	for file_name in dir.get_files():
		if not file_name.ends_with(".json"):
			continue
		var data = _read_json(PROFILE_DIR.path_join(file_name))
		if data is Dictionary and not str(data.get("npc_id", "")).strip_edges().is_empty():
			profiles[str(data["npc_id"]).strip_edges().to_lower()] = data


func _load_scenarios() -> void:
	var dir := DirAccess.open(SCENARIO_DIR)
	if dir == null:
		load_notes.append("dialogue scenario directory missing")
		return
	for file_name in dir.get_files():
		if not file_name.ends_with(".json"):
			continue
		var data = _read_json(SCENARIO_DIR.path_join(file_name))
		if not data is Dictionary:
			continue
		var id := str(data.get("godot_scenario_id", "")).strip_edges().to_lower()
		var npc_id := str(data.get("npc_id", "")).strip_edges().to_lower()
		if id.is_empty() or npc_id.is_empty():
			load_notes.append("invalid scenario: " + file_name)
			continue
		if scenarios.has(id):
			load_notes.append("duplicate scenario: " + id)
			continue
		scenarios[id] = data


func _read_json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		load_notes.append("missing: " + path)
		return null
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		load_notes.append("unreadable: " + path)
		return null
	var parsed = JSON.parse_string(file.get_as_text())
	if parsed == null:
		load_notes.append("invalid json: " + path)
	return parsed
