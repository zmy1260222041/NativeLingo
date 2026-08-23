extends Node

const InteractableScript = preload("res://scripts/interactable.gd")

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
	_test_npc_social_walking()

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


func _test_npc_social_walking() -> void:
	# FR-33: NPCs walk to a meeting point before talking and home afterwards.
	NpcVoice.availability_override = false
	var tavi_npc := InteractableScript.new()
	tavi_npc.interaction_kind = "npc"
	tavi_npc.target_id = "tavi"
	tavi_npc.display_name = "Tavi"
	tavi_npc.position = Vector3(-1.8, 1.0, -2.75)
	add_child(tavi_npc)
	var mira_npc := InteractableScript.new()
	mira_npc.interaction_kind = "npc"
	mira_npc.target_id = "mira"
	mira_npc.display_name = "Mira"
	mira_npc.position = Vector3(0.1, 1.0, -0.4)
	add_child(mira_npc)
	var walker := SocialSimulator.new()
	walker.name = "SocialWalker"
	add_child(walker)
	_expect(NpcVoice.line_audio_finished.is_connected(walker._on_line_audio_finished), "Social scenes listen for actual line playback completion")
	# The interval timer cannot fire inside this synchronous test, so the
	# simulator stays running and its _process drives the phase machine.
	_expect(walker._try_begin_scene(), "A social scene gathers when both family NPCs are free")
	_expect(walker.phase == SocialSimulator.Phase.GATHERING and tavi_npc.is_walking() and mira_npc.is_walking(), "Both NPCs start walking toward each other")
	var talking := false
	for frame in range(160):
		tavi_npc._process(0.1)
		mira_npc._process(0.1)
		walker._process(0.1)
		if walker.phase == SocialSimulator.Phase.TALKING:
			talking = true
			break
	_expect(talking, "Gathering completes and the scene starts talking")
	_expect(not tavi_npc.is_walking() and not mira_npc.is_walking(), "Talkers stand still while the scene plays")
	_expect(walker.talk_timer.time_left > 0.0, "No-voice dialogue still keeps both NPCs together for a readable speaking pause")
	var talk_gap := tavi_npc.global_position.distance_to(mira_npc.global_position)
	_expect(talk_gap < 2.4, "NPCs stand close together while talking (was %.2f m)" % talk_gap)
	walker.pending_line_keys.assign(["tavi/test_line_one", "mira/test_line_two"])
	walker._on_line_audio_finished("tavi", "test_line_one")
	_expect(walker.phase == SocialSimulator.Phase.TALKING and walker.pending_line_keys.size() == 1, "The first finished line never makes the NPCs leave early")
	walker._on_line_audio_finished("mira", "test_line_two")
	_expect(walker.phase == SocialSimulator.Phase.DISBURSING and tavi_npc.is_walking() and mira_npc.is_walking(), "After the talk both NPCs walk home")
	var idle := false
	for frame in range(240):
		tavi_npc._process(0.1)
		mira_npc._process(0.1)
		walker._process(0.1)
		if walker.phase == SocialSimulator.Phase.IDLE:
			idle = true
			break
	_expect(idle, "Scene ends and the simulator returns to idle")
	_expect(tavi_npc.global_position.distance_to(tavi_npc.home_position) < 0.5 and mira_npc.global_position.distance_to(mira_npc.home_position) < 0.5, "NPCs return to their home positions")
	walker.stop()
	NpcVoice.availability_override = null


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
