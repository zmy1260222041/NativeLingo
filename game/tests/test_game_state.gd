extends SceneTree

const GameStateScript = preload("res://scripts/game_state.gd")

var failures := 0

func _init() -> void:
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	_test_day_one(state)
	_test_day_two(state)
	_test_language_fallback(state)
	_test_faint_preserves_relationships(state)
	_test_save_round_trip(state)
	if failures == 0:
		print("PASS: Stranger game-state smoke suite")
	quit(failures)

func _test_day_one(state: Node) -> void:
	_expect(state.objective_text().contains("米拉"), "Day 1 begins with Mira")
	state.interact("npc", "mira", "gesture")
	state.interact("berry", "berry_a")
	state.interact("berry", "berry_b")
	state.interact("shelter", "shelter")
	_expect(state.day == 2, "Day 1 can be completed")

func _test_day_two(state: Node) -> void:
	state.interact("scrap", "scrap_a")
	state.interact("scrap", "scrap_b")
	state.interact("heater", "heater")
	_expect(state.heater_repaired, "Heater accepts two scrap")
	state.interact("shelter", "shelter")
	_expect(state.day == 3, "Day 2 can be completed")

func _test_language_fallback(state: Node) -> void:
	state.interact("water", "reservoir")
	state.interact("npc", "rowan", "gesture")
	_expect(state.game_finished, "Gesture fallback completes the key interaction")
	_expect(int(state.relationships["rowan"]) == 3, "Helping Rowan creates relationship memory")

func _test_faint_preserves_relationships(state: Node) -> void:
	var before: int = state.relationships["rowan"]
	state.berries = 2
	state.scrap = 2
	state.faint()
	_expect(state.relationships["rowan"] == before, "Fainting never damages relationships")
	_expect(state.berries == 1 and state.scrap == 1, "Fainting loses only small common items")

func _test_save_round_trip(state: Node) -> void:
	state.persistence_enabled = true
	state.save_path = "user://stranger_smoke_test_save.json"
	_expect(state.save_game(), "Versioned save can be written")
	var restored = GameStateScript.new()
	restored.persistence_enabled = false
	restored.save_path = state.save_path
	root.add_child(restored)
	_expect(restored.load_game(), "Versioned save can be loaded")
	_expect(restored.day == state.day and restored.relationships == state.relationships, "Save preserves day and relationships")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(state.save_path))

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
