extends Node
var failures := 0
func check(ok: bool, label: String) -> void:
	if not ok: failures += 1; push_error(label)
	else: print("PASS: ", label)
func _ready() -> void:
	GameState.persistence_enabled = false
	GameState.reset_run()
	var screen := preload("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	var model = screen.model
	model._remember_town_exchange("mira", "[opening]", "I'm Mira. Take one thing at a time here.", true)
	var contacts: Dictionary = GameState.presentation_state.town_contacts
	check(contacts.mira.completed_exchanges == 0 and contacts.mira.history.size() == 1, "Opening is NPC history, never familiarity credit")
	model._remember_town_exchange("mira", "I'm new here.", "Tavi is a useful person to know if you need a meal.", false)
	check(contacts.mira.completed_exchanges == 1 and contacts.mira.days == [1], "Completed exchange records only actual local encounter")
	model._reply("mira", "unplayed", "This must not count before playback.")
	model.cancel_activity()
	check(contacts.mira.completed_exchanges == 1, "Unplayed or cancelled reply does not increase familiarity")
	model._remember_town_exchange("ori", "private", "private", false)
	check(not contacts.has("ori"), "Another NPC cannot inherit this encounter")
	check(NpcDialogueService.begin_scenario("mira", "market_conversation", false), "Mira session can restore local continuity")
	check(Dialogue.history_for("mira").size() == 3, "Return session contains only completed prior speech")
	NpcDialogueService.cancel()
	check(NpcDialogueService.begin_scenario("rowan", "neighbor_conversation", false), "Rowan has a real social scenario")
	check(Dialogue.history_for("rowan").is_empty(), "Rowan cannot read Mira's conversation")
	NpcDialogueService.cancel()
	GameState.presentation_state.chapter = "campus"
	model._remember_town_exchange("mira", "campus text", "campus reply", false)
	check(contacts.mira.completed_exchanges == 1, "Campus callbacks do not mutate town familiarity")
	screen.queue_free()
	await get_tree().process_frame
	print("TownBelongingTest failures=", failures)
	get_tree().quit(1 if failures else 0)
