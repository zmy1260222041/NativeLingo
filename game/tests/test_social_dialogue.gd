extends Node

var failures := 0

func _ready() -> void:
	var simulator := SocialSimulator.new()
	simulator.name = "SocialSimulator"
	add_child(simulator)
	simulator.stop()
	_expect(simulator.SOCIAL_SCRIPTS.size() == 5, "Five ambient social scripts cover the survival essentials")
	_expect(simulator.required_expressions_covered(), "FR-34: every survival-essential expression is observable in an NPC-NPC scene")
	_expect(simulator.all_npcs_have_family(), "FR-33: all five named NPCs belong to a minimal family or partner unit")
	var coverage: Dictionary = simulator.coverage_map()
	for intent in simulator.REQUIRED_EXPRESSIONS:
		_expect(coverage.has(intent), "Coverage map contains intent " + str(intent))
	var captured: Array[String] = []
	var handler := func(text: String, _tone: String) -> void:
		captured.append(text)
	GameState.message_requested.connect(handler)
	NpcVoice.availability_override = false
	simulator.play_script(1)
	_expect(captured.size() == 2, "Social scene plays one NPC line and one reply")
	_expect(not captured[0].is_empty() and "Can I have some food" in captured[0], "Food scene exposes the exact food-request expression")
	GameState.message_requested.disconnect(handler)
	NpcVoice.availability_override = null

	# FR-38: dialogue state machine never punishes a miss.
	Dialogue.begin("mira")
	_expect(Dialogue.state_for("mira") == "opening", "Greeting opens a dialogue session")
	Dialogue.player_acted("mira", false)
	_expect(Dialogue.state_for("mira") == "clarify" and Dialogue.misses_for("mira") == 1, "A miss enters clarify, not failure")
	Dialogue.player_acted("mira", false)
	_expect(Dialogue.state_for("mira") == "clarify" and Dialogue.misses_for("mira") == 2, "Clarify retries stay free and countable")
	Dialogue.player_acted("mira", true)
	_expect(Dialogue.state_for("mira") == "idle", "An understood expression closes the session cleanly")

	# FR-38 through the real GameState command.
	GameState.completed_steps["greet_mira"] = true
	var berries_before: int = GameState.berries
	GameState.interact("npc", "tavi", "voice", _expression(30.0))
	_expect(Dialogue.state_for("tavi") == "clarify" and GameState.berries == berries_before, "Low-score voice request keeps the dialogue open and grants nothing")
	GameState.interact("npc", "tavi", "voice", _expression(100.0))
	_expect(Dialogue.state_for("tavi") == "idle" and GameState.berries > berries_before, "Understood retry closes the session and applies the monotonic reward")
	Dialogue.reset_all()
	if failures == 0:
		print("PASS: Stranger social dialogue suite")
	get_tree().quit(failures)


func _expression(score: float) -> Dictionary:
	return {
		"score": score,
		"pronunciation": score,
		"delivery": score,
		"band": "generous" if score >= 70.0 else ("sparse" if score >= 40.0 else "none"),
		"pronunciation_source": "test",
	}


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
