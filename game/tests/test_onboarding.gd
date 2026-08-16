extends SceneTree

const GameStateScript = preload("res://scripts/game_state.gd")

var failures := 0

func _init() -> void:
	TranslationServer.set_locale("zh_CN")
	_test_guided_flow()
	_test_wrong_actions_are_noops()
	_test_needs_guard_and_decay_resume()
	_test_skip_guard_and_decay_resume()
	if failures == 0:
		print("PASS: Stranger onboarding suite")
	quit(failures)


func _new_state() -> Node:
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	return state


func _test_guided_flow() -> void:
	var state := _new_state()
	state.begin_onboarding()
	_expect(state.onboarding_active and state.onboarding_step == "move", "Guide starts on move with active guard")
	state.onboarding_action("move")
	_expect(state.onboarding_step == "look", "Move advances to look")
	state.onboarding_action("look")
	state.onboarding_action("sprint")
	state.onboarding_action("jump")
	_expect(state.onboarding_step == "interact", "Look/sprint/jump advance in authored order")
	state.interact("npc", "mira", "gesture")
	_expect(state.onboarding_step == "speak" and state.completed_steps.has("greet_mira"), "First interaction completes the interact step without skipping the greeting rule")
	state.interact("npc", "tavi", "voice", _expression(100.0))
	_expect(state.onboarding_step == "sleep" and state.berries >= 2, "Voiced food request advances to sleep and keeps FR-28 rewards")
	state.interact("shelter", "shelter")
	_expect(state.onboarding_completed and not state.onboarding_active and state.day == 2, "Successful first-night sleep completes the guide and advances the day")


func _test_wrong_actions_are_noops() -> void:
	var state := _new_state()
	state.begin_onboarding()
	state.onboarding_action("sprint")
	state.onboarding_action("speak")
	_expect(state.onboarding_step == "move", "Wrong actions never move the guide backwards or sideways")
	state.onboarding_action("move")
	state.onboarding_action("move")
	_expect(state.onboarding_step == "look", "Repeat of the completed action is harmless and does not double-advance")


func _test_needs_guard_and_decay_resume() -> void:
	var state := _new_state()
	state.begin_onboarding()
	state.food = 12.0
	state.warmth = 12.0
	state.energy = 12.0
	state.day_time = 10.0
	state._process(60.0)
	_expect(is_equal_approx(state.food, 12.0) and is_equal_approx(state.warmth, 12.0) and is_equal_approx(state.energy, 12.0) and is_equal_approx(state.day_time, 10.0), "Active guide freezes all three needs and the survival clock")
	for _index in range(6):
		state.onboarding_action(state.onboarding_step)
	state.completed_steps["greet_mira"] = true
	state.berries = 2
	state.interact("shelter", "shelter")
	_expect(state.onboarding_completed and not state.onboarding_active, "Completing the guide releases the guard")
	var food_before: float = state.food
	state._process(5.0)
	_expect(state.food < food_before and state.food > 0.0, "Survival decay resumes after the guide")


func _test_skip_guard_and_decay_resume() -> void:
	var state := _new_state()
	state.begin_onboarding()
	state.skip_onboarding()
	_expect(state.onboarding_completed and not state.onboarding_active, "Skipping the guide is equivalent to completing it")
	var food_before: float = state.food
	state._process(2.0)
	_expect(state.food < food_before, "Skipped guide releases survival decay immediately")
	state.begin_onboarding()
	_expect(not state.onboarding_active, "A completed guide never starts again")


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
