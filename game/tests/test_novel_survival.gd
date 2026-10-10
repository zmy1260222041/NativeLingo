extends Node
## P1-01 / P2-07 / G1-01 / X1-01: the three nights test survival honestly in 2D.
## Starving through them faints with a real cost, one meal a day is enough, a
## faint is told where scene changes cannot wipe it, and the ending only names
## what this run did. Isolated from player saves; no locale is forced.
const Screen := preload("res://scenes/Novel.tscn")
var failures := 0
var screen: Control
var model: Node

func check(value: bool, message: String) -> void:
	if not value:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func _ready() -> void:
	GameState.persistence_enabled = false
	GameState.reset_run()
	SpeechAdapter.availability_override = false
	NpcVoice.availability_override = false
	screen = Screen.instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	await get_tree().process_frame
	_test_reading_is_free()
	await _test_no_meal_run_faints()
	await _test_faint_on_the_road()
	await _test_one_meal_a_day(false)
	await _test_one_meal_a_day(true)
	await _test_spoken_ending()
	print("NovelSurvivalTest failures=", failures)
	screen.queue_free()
	await get_tree().process_frame
	get_tree().quit(1 if failures else 0)

func _restart() -> void:
	model.restart(false)
	screen._close_panel()

## Presses the home primary action (rest until evening, or sleep) like a player.
func _press_home() -> void:
	screen.home_action_button.pressed.emit()
	await get_tree().process_frame

func _test_reading_is_free() -> void:
	_restart()
	var before := [GameState.food, GameState.warmth, GameState.energy, GameState.day_time]
	for kind in ["bag", "growth", "theater", "phrases", "history", "settings", "help"]:
		screen._open_panel(kind)
		screen._close_panel()
	model.play_social(0)
	model.next_social()
	model.cancel_activity()
	model.begin_practice("food")
	model.cancel_activity()
	check(before == [GameState.food, GameState.warmth, GameState.energy, GameState.day_time], "FR-46: reading, panels and practice cost no needs or time")

## The review's 8-click run: straight home, then only rest and sleep.
func _test_no_meal_run_faints() -> void:
	_restart()
	model.travel("home")
	var first_faint_day := 0
	var presses := 0
	while not GameState.game_finished and presses < 20:
		var faints: int = GameState.faints
		await _press_home()
		presses += 1
		if GameState.faints > faints and first_faint_day == 0:
			first_faint_day = GameState.day
			check(model.location == "home", "A faint leaves the player at home")
			check(GameState.food <= GameState.FAINT_FOOD_FLOOR and GameState.food < GameState.FOOD_COMFORT, "A starving faint does not refill hunger to a comfortable level")
			check(screen.dialogue_text.text.contains("昏倒") and screen.speaker_label.text == "异乡手记", "The faint is told in the dialogue box, not only a toast")
			check(model.history.back().text.contains("昏倒"), "The faint stays in the review log")
			check(screen.order_panel.visible and screen.order_title.text.contains("昏倒"), "The home panel keeps the faint notice after the scene change")
			check(screen.feedback_label.text.contains("昏倒"), "The faint toast survives the scene change")
	check(GameState.game_finished, "The time box still ends after three nights")
	check(first_faint_day > 0 and first_faint_day <= 3, "Never eating faints before night three ends (first faint on day %d)" % first_faint_day)
	check(GameState.objective_text() == tr("OBJECTIVE_COMPLETE_EMPTY"), "The objective does not claim the player talked for food")
	var ending: String = model.history.back().text
	check(not ending.contains("开口换来") and not ending.contains("每一个名字") and ending.contains("昏倒过"), "The ending names the faints and claims no speech: " + ending)
	check(ending.contains("还没有人认识你"), "The ending does not claim the player knows anyone")

## Fainting on the road returns the player home, keeps carried food and names the loss.
func _test_faint_on_the_road() -> void:
	_restart()
	model.travel("food")
	model.greet()
	check(model.use_item("pack", str(model.visible_items("counter")[0].id)).ok, "Carry a burger")
	model.travel("store")
	model.greet()
	check(model.use_item("pack", str(model.visible_items("counter")[0].id)).ok, "Carry a bottle of water")
	var warmth: float = GameState.warmth
	GameState.food = 1.0
	var time: float = GameState.day_time
	model.travel("parts")
	check(GameState.faints == 1 and model.location == "home", "Fainting on the way returns the player home")
	check(GameState.day_time >= time + GameState.FAINT_SECONDS, "A faint costs time")
	check(is_equal_approx(GameState.food, GameState.FAINT_FOOD_FLOOR) and GameState.warmth <= warmth, "A faint is not a free refill")
	var bag: Array = model.visible_items("bag").map(func(record): return record.item_id)
	check(bag == ["food_burger"], "The carried meal is not the first thing lost")
	check(screen.dialogue_text.text.contains(GameState.items.Catalog.label(GameState.items.definitions.drink_bottled_water.name)), "The faint names the lost item")

## One gesture-minimum meal a day, eaten in the morning or after resting, never faints.
func _test_one_meal_a_day(eat_late: bool) -> void:
	_restart()
	var mode := "meal after resting" if eat_late else "morning meal"
	model.travel("home")
	for night in range(3):
		if eat_late:
			model.wait_until_evening()
		model.travel("food")
		model.greet()
		var counter: Array = model.visible_items("counter")
		check(not counter.is_empty() and model.use_item("consume", str(counter[0].id), true).ok, "Eat the day's meal: " + mode)
		model.travel("home")
		if not eat_late:
			model.wait_until_evening()
		check(model.sleep(), "Night %d ends: %s" % [night + 1, mode])
	check(GameState.game_finished and GameState.faints == 0, "One meal a day lasts three nights without fainting: %s (food %.1f)" % [mode, GameState.food])
	check(GameState.objective_text() == tr("OBJECTIVE_COMPLETE_GESTURE"), "The objective credits gestured supplies, not speech: " + mode)
	var ending: String = model.history.back().text
	check(ending.contains("手势") and not ending.contains("开口换来") and not ending.contains("昏倒"), "The ending matches a gesture-only run: " + ending)

## A run that really spoke for its food is told so, with the people it talked to.
func _test_spoken_ending() -> void:
	_restart()
	model.travel("food")
	GameState.settle_service_transaction("tavi", 80.0, "burger")
	GameState.presentation_state["town_contacts"] = {"tavi": {"completed_exchanges": 1, "days": [1], "history": []}, "mira": {"completed_exchanges": 2, "days": [1], "history": []}}
	model.use_item("consume", str(model.visible_items("counter")[0].id), true)
	model.travel("home")
	var presses := 0
	while not GameState.game_finished and presses < 20:
		await _press_home()
		presses += 1
	check(GameState.game_finished and GameState.objective_text() == tr("OBJECTIVE_COMPLETE"), "Spoken supplies keep the spoken objective")
	var ending: String = model.history.back().text
	check(ending.contains("开口") and ending.contains("Mira") and ending.contains("Tavi") and not ending.contains("Rowan"), "The ending names exactly who the player talked with: " + ending)
