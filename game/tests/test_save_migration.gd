extends SceneTree

const GameStateScript = preload("res://scripts/game_state.gd")

var failures := 0

func _init() -> void:
	var path := "/tmp/nl_stranger_save_migration_test.json"
	_remove(path)
	var legacy := {
		"version": 2,
		"day": 2,
		"day_time": 40.0,
		"food": 55.0,
		"warmth": 60.0,
		"energy": 70.0,
		"berries": 1,
		"scrap": 1,
		"water": 0,
		"heater_repaired": false,
		"relationships": {"mira": 2, "rowan": 0, "tavi": 0, "vesh": 0, "ori": 0},
		"memories": ["mira：MEMORY_GREET_MIRA"],
		"completed_steps": {"greet_mira": true},
		"game_finished": false,
		"onboarding_completed": true,
	}
	var legacy_state = GameStateScript.new()
	legacy_state.persistence_enabled = true
	legacy_state.save_path = path
	root.add_child(legacy_state)
	var file := FileAccess.open(path, FileAccess.WRITE)
	_expect(file != null, "Migration probe can create a version-2 save in the OS temp dir")
	if file != null:
		file.store_string(JSON.stringify(legacy))
		file.close()
	_expect(legacy_state.load_game(), "Version-2 save loads into SAVE_VERSION 3")
	_expect(legacy_state.day == 2 and legacy_state.food == 55.0 and int(legacy_state.relationships["mira"]) == 2, "Legacy quest/relationship values are preserved")
	_expect(legacy_state.vocabulary_tier == "toddler" and legacy_state.vocabulary_entries.is_empty(), "Missing vocabulary fields lazily default to an empty toddler profile")
	legacy_state.vocabulary_entries = {"portions|observed": {"headword": "portions", "pos": "observed", "cefr": "", "ngsl_rank": -1, "source": "observed_npc", "state": "heard"}}
	_expect(legacy_state.save_game(), "SAVE_VERSION 3 save can be written")
	var restored = GameStateScript.new()
	restored.persistence_enabled = true
	restored.save_path = path
	root.add_child(restored)
	_expect(restored.load_game(), "Version-3 save round-trips")
	_expect(restored.vocabulary_entries.has("portions|observed") and restored.vocabulary_tier == "toddler", "Vocabulary profile survives the save round-trip")
	_remove(path)
	if failures == 0:
		print("PASS: Stranger save migration suite")
	quit(failures)


func _remove(path: String) -> void:
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(path)


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
