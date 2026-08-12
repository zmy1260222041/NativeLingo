extends SceneTree

const GameStateScript = preload("res://scripts/game_state.gd")

var failures := 0

func _init() -> void:
	TranslationServer.set_locale("zh_CN")
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	_test_day_one(state)
	_test_day_two(state)
	_test_language_fallback(state)
	_test_faint_preserves_relationships(state)
	_test_voice_wait_has_no_survival_cost()
	_test_npc_reply_is_distinct_from_transcript(state)
	_test_save_round_trip(state)
	_test_localization_resources()
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

func _test_voice_wait_has_no_survival_cost() -> void:
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	var before := Vector4(state.day_time, state.food, state.warmth, state.energy)
	state.set_interaction_time_frozen(true)
	state._process(18.0)
	var after := Vector4(state.day_time, state.food, state.warmth, state.energy)
	_expect(before == after, "Voice listening, transcription, and recovery never drain survival state")

func _test_npc_reply_is_distinct_from_transcript(state: Node) -> void:
	var reply: String = state._communication_reply("Mira", "voice", "Welcome, stranger.")
	_expect(reply.contains("Mira") and reply.contains("Welcome, stranger.") and not reply.contains("你的英语"), "NPC reply is not mislabeled as the player's transcript")

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

func _test_localization_resources() -> void:
	TranslationServer.set_locale("en")
	var localized_state = GameStateScript.new()
	localized_state.persistence_enabled = false
	root.add_child(localized_state)
	_expect(localized_state.objective_text().contains("Mira"), "English objective resolves from a string ID")
	_expect(TranslationServer.translate("BTN_RESUME") == "Resume", "English UI translation resource is loaded")
	TranslationServer.set_locale("zh_CN")
	_expect(TranslationServer.translate("BTN_RESUME") == "继续游戏", "Chinese UI translation resource is loaded")

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
