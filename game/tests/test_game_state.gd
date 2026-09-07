extends SceneTree

const GameStateScript = preload("res://scripts/game_state.gd")
const DayCycleLightingScript = preload("res://scripts/day_cycle_lighting.gd")

var failures := 0

func _init() -> void:
	TranslationServer.set_locale("zh_CN")
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	_test_day_one(state)
	_test_day_two(state)
	_test_critical_nodes_reject_silent_shortcuts()
	_test_language_fallback(state)
	_test_faint_preserves_relationships(state)
	_test_voice_wait_has_no_survival_cost()
	_test_npc_reply_is_distinct_from_transcript(state)
	_test_save_round_trip(state)
	_test_clock_and_lighting_phases(state)
	_test_memory_changes_later_feedback()
	_test_blocker_copy()
	_test_localization_resources()
	if failures == 0:
		print("PASS: Stranger game-state smoke suite")
	quit(failures)

func _test_day_one(state: Node) -> void:
	_expect(state.can_start_service_dialogue("tavi") and state.can_start_service_dialogue("ori"), "Food counter and convenience store are open on day 1")
	_expect(state.objective_text().contains("食物") or state.objective_text().contains("店"), "Day 1 objective follows hunger, not a named greeting")
	state.settle_service_transaction("tavi", 100.0, "burger")
	_expect(state.berries >= 1, "Tavi serves food before any Mira greeting")
	state.settle_service_transaction("ori", 100.0, "water")
	_expect(state.water == 2, "Ori hands over two water bottles on day 1")
	_advance_to_evening(state)
	state.interact("shelter", "shelter")
	_expect(state.day == 2 and not state.game_finished, "Sleeping at night ends day 1 without a quest checklist")

func _test_day_two(state: Node) -> void:
	_expect(not state.heater_repaired, "The heater is off the critical path")
	_advance_to_evening(state)
	state.interact("shelter", "shelter")
	_expect(state.day == 3 and not state.game_finished, "A second night advances the time box without repairing the heater")


func _test_memory_changes_later_feedback() -> void:
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	var first := _capture_message(state, func(): state.interact("npc", "mira", "voice", _expression(80.0)))
	_expect(first.contains("Welcome") or first.contains("米拉"), "First Mira beat uses an understood voice greeting")
	var later := _capture_message(state, func(): state.interact("npc", "mira", "gesture"))
	_expect(later.contains("塔维") or later.contains("Tavi") or later.contains("食物") or later.contains("food"), "After greeting, Mira points to the food supplier instead of repeating welcome")
	var tavi := _capture_message(state, func(): state.interact("npc", "tavi", "gesture"))
	_expect(tavi.contains("Tavi") or tavi.contains("塔维") or tavi.contains("暮果") or tavi.contains("duskberr"), "Tavi is identifiable and gives a food hint")


func _test_blocker_copy() -> void:
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	var heater_day1 := _capture_message(state, func(): state.interact("heater", "heater"))
	_expect(heater_day1.contains("零件") or heater_day1.contains("parts") or heater_day1.contains("alloy"), "Optional heater still asks for parts instead of a calendar lock")
	var sleep_before_night := _capture_message(state, func(): state.interact("shelter", "shelter"))
	_expect(sleep_before_night.contains("早") or sleep_before_night.contains("early") or sleep_before_night.contains("柜台"), "Daytime sleep points to shops, not a missing quest")


func _capture_message(state: Node, action: Callable) -> String:
	var captured: Array[String] = [""]
	var handler := func(text: String, _tone: String) -> void:
		captured[0] = text
	state.message_requested.connect(handler)
	action.call()
	state.message_requested.disconnect(handler)
	return captured[0]


func _advance_to_evening(state: Node) -> void:
	state.day_time = GameStateScript.DAY_DURATION * ((20.0 - GameStateScript.DAY_START_HOUR) / (GameStateScript.DAY_END_HOUR - GameStateScript.DAY_START_HOUR))


func _sleep_three_nights(state: Node) -> void:
	for _i in range(3):
		if state.game_finished:
			return
		_advance_to_evening(state)
		state.interact("shelter", "shelter")


func _expression(score: float) -> Dictionary:
	return {
		"score": score,
		"pronunciation": score,
		"delivery": score,
		"band": "generous" if score >= 70.0 else ("sparse" if score >= 40.0 else "none"),
		"pronunciation_source": "test",
	}


func _test_language_fallback(state: Node) -> void:
	state.interact("npc", "ori", "gesture_fallback")
	var pending: Array = state.items.records("counter", "ori")
	state.item_command("pack", [pending[0].id], {"safe": true, "location": "ori"})
	state.interact("npc", "rowan", "gesture_fallback")
	_expect(not state.game_finished, "Helping Rowan is optional and does not end the slice")
	_expect(int(state.relationships["rowan"]) == 3, "Helping Rowan still creates relationship memory")
	_sleep_three_nights(state)
	_expect(state.game_finished, "Three nights complete the slice")


func _test_critical_nodes_reject_silent_shortcuts() -> void:
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	state.interact("npc", "mira", "action")
	state.interact("npc", "mira", "gesture")
	_expect(not state.completed_steps.has("greet_mira"), "Mira greeting cannot be completed with Observe/E or a normal gesture")
	state.interact("npc", "mira", "voice", _expression(39.0))
	_expect(not state.completed_steps.has("greet_mira"), "A low-score greeting keeps the first critical beat open")
	state.interact("npc", "mira", "voice", _expression(40.0))
	_expect(state.completed_steps.has("greet_mira"), "A clear-enough voice greeting still records the social beat")
	state.water = 1
	state.interact("npc", "rowan", "action")
	state.interact("npc", "rowan", "gesture")
	_expect(not state.completed_steps.has("help_rowan") and state.water == 1, "Rowan delivery cannot be completed silently while speech is available")

func _test_faint_preserves_relationships(state: Node) -> void:
	var before: int = state.relationships["rowan"]
	state.items = preload("res://scripts/item_state.gd").new()
	state.items.migrate(2, 2, 0, false)
	state._items_did_change()
	state.faint()
	_expect(state.relationships["rowan"] == before, "Fainting never damages relationships")
	_expect(state.berries == 1 and state.scrap == 2, "Fainting loses only one eligible carried unit")

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

func _test_clock_and_lighting_phases(state: Node) -> void:
	state.day_time = 0.0
	_expect(is_equal_approx(state.clock_hours(), 8.0), "day starts at 08:00")
	state.day_time = GameStateScript.DAY_DURATION * ((18.0 - 8.0) / (22.0 - 8.0))
	_expect(absf(state.clock_hours() - 18.0) < 0.02, "six PM maps onto the compressed day")
	_expect(DayCycleLightingScript.phase_at(12.0) == DayCycleLightingScript.Phase.SUNNY, "noon is sunny")
	_expect(DayCycleLightingScript.phase_at(17.9) == DayCycleLightingScript.Phase.SUNNY, "just before 18:00 stays sunny")
	_expect(DayCycleLightingScript.phase_at(18.5) == DayCycleLightingScript.Phase.SUNSET, "after 18:00 is sunset")
	_expect(DayCycleLightingScript.phase_at(21.0) == DayCycleLightingScript.Phase.NIGHT, "21:00 is night")
	_expect(DayCycleLightingScript.glow_amount(12.0) < 0.01, "lantern glow stays off in daylight")
	_expect(DayCycleLightingScript.glow_amount(21.0) > 0.9, "lantern glow is on at night")


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
	_expect(localized_state.objective_text().contains("hungry") or localized_state.objective_text().contains("food"), "English objective resolves from a string ID")
	_expect(TranslationServer.translate("BTN_RESUME") == "Resume", "English UI translation resource is loaded")
	TranslationServer.set_locale("zh_CN")
	_expect(TranslationServer.translate("BTN_RESUME") == "继续游戏", "Chinese UI translation resource is loaded")

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
