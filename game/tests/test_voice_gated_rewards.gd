extends SceneTree
## FR-28 / R-17 acceptance suite for the voice-gated reward mainline.
## Covers G1 voice gating, G3 monotonic reward bands, G4 no-voice fallback,
## and G5 save-version migration at the pure GameState level.

const GameStateScript = preload("res://scripts/game_state.gd")

var failures := 0

func _init() -> void:
	TranslationServer.set_locale("zh_CN")
	_test_world_objects_never_grant_resources()
	_test_food_bands_are_monotonic_and_lossless()
	_test_scrap_bands_are_monotonic_and_lossless()
	_test_water_bands_are_monotonic_and_lossless()
	_test_rowan_voice_gate()
	_test_gesture_fallback_completes_three_days()
	_test_old_save_migrates()
	_test_expression_signal_carries_both_dimensions()
	if failures == 0:
		print("PASS: Stranger voice-gated reward suite")
	quit(failures)

func _test_world_objects_never_grant_resources() -> void:
	var state := _fresh_state()
	var before := _resource_snapshot(state)
	state.interact("berry", "berry_a")
	state.interact("scrap", "scrap_a")
	state.interact("water", "reservoir")
	_expect(_resource_snapshot(state) == before, "G1: forage tokens and the reservoir never change resources")

func _test_food_bands_are_monotonic_and_lossless() -> void:
	for score_and_expected in [[30.0, 0], [39.9, 0], [40.0, 1], [69.9, 1], [70.0, 2]]:
		var state := _fresh_state()
		state.completed_steps["greet_mira"] = true
		var before := _resource_snapshot(state)
		var message := _capture_message(state, func(): state.interact("npc", "tavi", "voice", _expr(score_and_expected[0])))
		var after := _resource_snapshot(state)
		var expected_berries: int = score_and_expected[1]
		_expect(after[0] == before[0] + expected_berries,
			"G3: food reward for score %.1f is %d berry/berries" % [score_and_expected[0], expected_berries])
		if expected_berries == 0:
			_expect(after == before, "G3: below-minimum food request changes no state")
			_expect(message.contains("没听懂") or message.contains("did not understand"), "G3: low-score NPC reply stays inclusive and free")
		else:
			_expect(after[1] >= before[1], "G3: granted food also refills the food need")
		_expect(int(state.relationships["tavi"]) == 0, "G3: failed or sparse requests never harm relationships")

func _test_scrap_bands_are_monotonic_and_lossless() -> void:
	for score_and_expected in [[25.0, 0], [40.0, 1], [70.0, 2]]:
		var state := _fresh_state()
		state.day = 2
		var before := _resource_snapshot(state)
		state.interact("npc", "vesh", "voice", _expr(score_and_expected[0]))
		var after := _resource_snapshot(state)
		_expect(after[2] == before[2] + score_and_expected[1],
			"G3: scrap reward for score %.1f is %d part(s)" % [score_and_expected[0], score_and_expected[1]])
		if score_and_expected[1] == 0:
			_expect(after == before, "G3: below-minimum scrap request changes no state")

func _test_water_bands_are_monotonic_and_lossless() -> void:
	var previous_energy_gain := -1
	for score in [30.0, 40.0, 70.0]:
		var state := _fresh_state()
		state.day = 3
		var before_energy: float = state.energy
		state.interact("npc", "ori", "voice", _expr(score))
		if score < 40.0:
			_expect(state.water == 0 and state.energy == before_energy, "G3: below-minimum water request changes no state")
			continue
		_expect(state.water == 1, "G3: voiced water request fills the canteen")
		var gain: float = state.energy - before_energy
		_expect(gain > previous_energy_gain, "G3: water reward energy bonus increases with score")
		previous_energy_gain = int(gain)

func _test_rowan_voice_gate() -> void:
	var state := _fresh_state()
	state.day = 3
	state.water = 1
	state.interact("npc", "rowan", "voice", _expr(20.0))
	_expect(not state.game_finished and state.water == 1, "G3: unclear final delivery costs nothing and keeps the water")
	state.interact("npc", "rowan", "voice", _expr(45.0))
	_expect(state.game_finished and state.water == 0, "G3: a clear-enough voiced delivery completes the run")

func _test_gesture_fallback_completes_three_days() -> void:
	var state := _fresh_state()
	state.interact("npc", "mira", "gesture")
	state.interact("npc", "tavi", "gesture_fallback")
	state.interact("npc", "tavi", "gesture_fallback")
	state.interact("shelter", "shelter")
	state.interact("npc", "vesh", "gesture_fallback")
	state.interact("npc", "vesh", "gesture_fallback")
	state.interact("heater", "heater")
	state.interact("shelter", "shelter")
	state.interact("npc", "ori", "gesture_fallback")
	state.interact("npc", "rowan", "gesture")
	_expect(state.game_finished, "G4: gesture_fallback completes all three days without speech")

func _test_old_save_migrates() -> void:
	var state := _fresh_state()
	state.persistence_enabled = true
	state.save_path = "user://stranger_voice_gate_save_test.json"
	state.berries = 2
	state.scrap = 1
	state.save_game()
	var file := FileAccess.open(state.save_path, FileAccess.READ)
	var raw: Dictionary = JSON.parse_string(file.get_as_text())
	file = null
	raw["version"] = 1
	var legacy := FileAccess.open(state.save_path, FileAccess.WRITE)
	legacy.store_string(JSON.stringify(raw))
	legacy = null
	var restored := _fresh_state()
	restored.save_path = state.save_path
	_expect(restored.load_game(), "G5: a version-1 save is accepted by SAVE_VERSION 2")
	_expect(restored.berries == 2 and restored.scrap == 1, "G5: legacy resources survive migration")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(state.save_path))

func _test_expression_signal_carries_both_dimensions() -> void:
	var state := _fresh_state()
	state.completed_steps["greet_mira"] = true
	var captured := {}
	var handler := func(target_id: String, expression: Dictionary) -> void:
		captured["target"] = target_id
		captured["expression"] = expression
	state.expression_evaluated.connect(handler)
	state.interact("npc", "tavi", "voice", _expr(81.0))
	state.expression_evaluated.disconnect(handler)
	_expect(captured.get("target", "") == "tavi", "G2: expression_evaluated names the judging NPC")
	_expect(float(captured.get("expression", {}).get("pronunciation", -1.0)) == 81.0
		and float(captured.get("expression", {}).get("delivery", -1.0)) == 81.0,
		"G2: pronunciation and delivery both ride the expression result")

func _fresh_state() -> Node:
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	return state

func _resource_snapshot(state: Node) -> Array:
	return [state.berries, state.food, state.scrap, state.water, state.warmth, state.energy]

func _expr(score: float) -> Dictionary:
	return {
		"score": score,
		"pronunciation": score,
		"delivery": score,
		"band": "generous" if score >= 70.0 else ("sparse" if score >= 40.0 else "none"),
		"pronunciation_source": "test",
	}

func _capture_message(state: Node, action: Callable) -> String:
	var captured: Array[String] = [""]
	var handler := func(text: String, _tone: String) -> void:
		captured[0] = text
	state.message_requested.connect(handler)
	action.call()
	state.message_requested.disconnect(handler)
	return captured[0]

func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
