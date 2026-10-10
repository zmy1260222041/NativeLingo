extends Node
const State := preload("res://scripts/novel/campus_state.gd")
const Screen := preload("res://scenes/Campus.tscn")
var failures := 0
var assertions := 0
var screen: Control
var model: Node
var faint_count := 0

func check(ok: bool, message: String) -> void:
	assertions += 1
	if not ok: failures += 1; push_error(message)

func _ready() -> void:
	TranslationServer.set_locale("zh_CN")
	GameState.persistence_enabled = false
	SpeechAdapter.availability_override = false
	NpcVoice.availability_override = false
	_test_state()
	_test_memory_and_personalization()
	TranslationServer.set_locale("en") # T1-03: an English OS; the campus screen pins the Chinese UI.
	screen = Screen.instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	await get_tree().process_frame
	check(TranslationServer.get_locale() == "zh_CN" and GameState.items.Catalog.label(["汉堡", "Burger"]) == "汉堡", "Campus pins the Chinese UI locale over an English OS")
	check(model.location == "class", "Empty profile starts on campus")
	check(model.campus.catalog.scenarios.size() == 32, "32 scenarios load in actual screen")
	var snapshot := Vector3(GameState.day_time, GameState.energy, model.campus.social)
	await get_tree().create_timer(0.1).timeout
	check(snapshot == Vector3(GameState.day_time, GameState.energy, model.campus.social), "Reading costs no time or needs")
	for card in model.campus.catalog.scenarios:
		model.travel(card.domain)
		model.select_scene(card.id)
		check(model.scene_id == card.id and screen.scene_title.text == card.title, "Scene reachable: " + str(card.id))
	model.travel("class")
	model.select_scene("class_project_roles")
	check(screen.visual.people.size() == 3, "Three character group is rendered")
	await capture("group")
	_test_late_and_duplicate()
	await _test_group_audio()
	screen._profile()
	check(screen.profiles.size() == 7 and screen.modal.visible, "Optional profile controls are reachable")
	await capture("profile")
	screen.modal.hide()
	model.update_profile({"major": "Computer science", "sports": "tennis", "clubs": "photography"})
	check(model.campus.relevant_profile(model.scene()).get("major") == "Computer science", "Course context uses selected major")
	model.campus.remember_quote("I like tennis", ["alex"], "class_before_class", 1)
	model.topic_summary = "I like tennis"
	var memory_id: String = model.campus.memories[-1].id
	model.change_memory(memory_id, "I prefer swimming")
	check(model.topic_summary.is_empty() and model.campus.memories[-1].text == "I prefer swimming", "Memory edits invalidate active topic")
	model.change_memory(memory_id, "", true)
	check(not model.campus.memories.any(func(m): return m.id == memory_id), "Memory deletion persists locally")
	_test_two_weeks()
	model.travel("sports")
	model.select_scene("sports_mistake")
	screen.instant_text = true
	await check_reading_sizes(18, "standard")
	screen.set_large_text(true)
	await check_reading_sizes(21, "large")
	screen._line("alex", "I’m glad we’re in the same group.")
	check(screen.transcript.text.contains("I'm glad we're in the same group.") and not screen.transcript.text.contains("’"), "P2-14: campus English uses Latin-width apostrophes")
	screen._line("casey", "I saw it differently, but I could have missed the first part. Could we talk through what happened before we decide how to continue? I would rather agree on a fair way forward than argue over who was right.")
	get_window().size = Vector2i(960, 640)
	await get_tree().process_frame
	await capture("small-long-dialogue")
	check(screen.record_button.get_global_rect().end.y <= screen.size.y, "Composer remains within the window")
	check(screen.root.size.x <= screen.size.x, "Layout fits window width")
	check(screen.transcript.get_line_count() >= 2, "Long dialogue wraps in the paper reading area")
	get_window().size = Vector2i(1152, 720)
	await capture("dialogue-1152")
	get_window().size = Vector2i(1440, 900)
	screen._reviews()
	await capture("weekly-review")
	screen.modal.hide()
	screen._words()
	var word_rows: Array = screen.modal_body.get_children().filter(func(c): return c is Button).map(func(c): return str(c.text))
	check(word_rows.size() == model._practice_words().size() and not word_rows.any(func(text): return str(text).ends_with("· ")), "Campus word practice shows a status for every word")
	check(word_rows.has("morning · 已有词汇") and word_rows.has("heater · 尚未听见"), "Campus word practice uses the town's progress labels")
	screen.modal.hide()
	_test_save()
	_test_shared_vocabulary()
	print("CampusTest: %d assertions, %d failures" % [assertions, failures])
	get_tree().quit(1 if failures else 0)

func _test_state() -> void:
	var state = State.new()
	state.social = 27
	check(is_equal_approx(state.advance_social(2), 4) and state.social == 23, "Integrates only one hour below threshold")
	state.social = 25
	check(is_equal_approx(state.advance_social(0.5), 2), "Threshold starts extra cost immediately")
	var scene: Dictionary = state.scenario("sports_join")
	state.social = 20
	for i in range(5): state.reward_event("event-%d" % i, scene, ["casey"], 1, 8)
	check(state.social == 44, "Per-person cap is 24 per day")
	check(not state.reward_event("event-0", scene, ["casey"], 1, 8), "Duplicate receipt never rewards again")
	check(not state.settle_conversation("sports_join", 1, [], {"scenario_id": "sports_join", "source": "stub"}), "Stub cannot settle")
	for day in range(1, 6):
		check(state.complete_study("class", day) and state.complete_study("study", day), "Both daily academic activities")
		check(not state.complete_study("class", day), "Study deduplication")
	check(state.academic == 100, "Ten weekly activities total 100")
	check(not state.complete_study("class", 6), "Five weekly classes remain capped on weekends")
	state.begin_day(8)
	check(state.week == 2 and state.academic == 0 and state.reviews[0].academic == 100, "Weekly archive and reset")
	for chain in state.catalog.chains:
		for i in range(4):
			var step: Dictionary = state.scenario(chain.steps[i])
			state.reward_event("chain:" + step.id, step, step.participants, i + 10, 8)
		check(state.chains[chain.id].step == 4, "Four cross-day steps: " + chain.id)
	var restored = State.new()
	check(restored.restore(state.serialize()) and restored.chains == state.chains, "Roundtrip preserves all chains")
	check(not restored.restore({"version": 999}), "Future save rejected")
	var makeup = State.new()
	for day in [1, 2, 4, 6, 7]: check(makeup.complete_study("class", day), "Weekend can make up a missed weekday")
	check(makeup.academic == 50 and not makeup.complete_study("class", 7), "Weekend makeup preserves daily and weekly limits")
	var legacy: Dictionary = makeup.serialize()
	legacy.version = 1
	legacy.week = 2
	legacy.study_done = {"0:class": true, "4:study": true}
	check(restored.restore(legacy) and restored.study_done.has("8:class") and restored.study_done.has("12:study"), "v1 weekday keys migrate to calendar days")

func _test_memory_and_personalization() -> void:
	var state = State.new()
	state.set_profile({"major": "computer science"})
	check(state.ranked_scenes("class")[0].id == "class_project_roles", "Actual major content changes recommendation")
	state.set_profile({"sports": "tennis"})
	check(state.relevance(state.scenario("sports_level")) > state.relevance(state.scenario("sports_join")), "Actual sport content changes ranking")
	var practice: String = state.create_practice("I missed a project handoff and need to explain why.", "class", "Missed handoff", "Explain and propose a next step.")
	var card: Dictionary = state.scenario(practice)
	check(card.title == "Missed handoff" and card.trigger.contains("handoff") and card.has("base_scenario_id"), "An experience creates a distinct editable practice card")
	var lines := [{"speaker_id": "alex", "text": "I can meet Thursday at three.", "reply_to": "player"}]
	var receipt := {"memory_candidates": [{"speaker_id": "alex", "text": lines[0].text, "kind": "proposal"}, {"speaker_id": "sam", "text": "An invented promise.", "kind": "agreement"}]}
	state.remember_exchange("class_project_roles", 1, "Could we meet again?", lines, receipt)
	check(state.memories.size() == 1 and state.memories[0].speaker_id == "alex", "Only an actually spoken NPC proposal enters memory")
	check(state.relevant_memories(state.scenario("dining_story")).is_empty(), "An absent character does not receive a private proposal")
	state.conversation = {"topic_summary": "Thursday at three"}
	var restored = State.new()
	check(restored.restore(state.serialize()) and restored.memories[0].text.contains("Thursday") and not restored.conversation.is_empty(), "NPC proposal and active conversation survive save")
	restored.edit_memory(str(restored.memories[0].id), "I can meet Friday at four.")
	check(restored.conversation.is_empty() and not JSON.stringify(restored.relevant_memories(restored.scenario("class_project_roles"))).contains("Thursday"), "Correction removes obsolete active context")
	restored.delete_memory(str(restored.memories[0].id))
	check(restored.memories.is_empty(), "Deleted proposal no longer reaches a new conversation")
	var echoes = State.new()
	var echo_lines := [{"speaker_id": "alex", "text": "We can meet at Cedar Hall.", "reply_to": "player"}]
	echoes.remember_exchange("class_before_class", 1, "I prefer Cedar Hall.", echo_lines, {"memory_candidates": [{"speaker_id": "player", "text": "I prefer Cedar Hall."}, {"speaker_id": "alex", "text": echo_lines[0].text}]})
	check(echoes.memories.size() == 2, "Player fact and NPC retelling both have quoted sources")
	echoes.edit_memory(str(echoes.memories[0].id), "I prefer Willow Library.")
	check(echoes.memories.size() == 1 and not JSON.stringify(echoes.memories).contains("Cedar Hall"), "Correction invalidates same-turn NPC retelling too")

func _test_late_and_duplicate() -> void:
	var transport: Node = model.conversation
	transport.text_only = true
	transport.busy = true
	transport.active_turn = "current"
	transport.accept_event("speaking", {"turn_id": "old", "speaker_id": "alex", "reply_id": "late", "text": "Late"})
	check(transport.lines.is_empty(), "Late turn never enters playback")
	transport.accept_event("speaking", {"turn_id": "current", "speaker_id": "alex", "reply_id": "one", "text": "Current"})
	transport.accept_event("speaking", {"turn_id": "current", "speaker_id": "alex", "reply_id": "one", "text": "Current"})
	check(transport.lines.size() == 1, "Duplicate speaking event is ignored")
	model.cancel_activity()
	transport.accept_event("done", {"turn_id": "current", "source": "gemini"})
	check(not transport.busy and transport.receipt.is_empty(), "Cancellation rejects late completion")
	var snapshot: String = JSON.stringify(model.campus.serialize())
	model.pending_turn = "rejected"
	model.pending_text = "I would like to compare our examples."
	model._campus_complete({"turn_id": "rejected", "session_id": model.session, "scenario_id": model.scene_id, "source": "stub", "memory_candidates": [{"speaker_id":"player", "text":model.pending_text}]}, [{"speaker_id":"alex", "reply_to":"player", "text":"A fabricated reply."}])
	check(JSON.stringify(model.campus.serialize()) == snapshot, "A fabricated receipt cannot save memories, practice or rewards")
	model.retry_text = "Please clarify that example."
	model.conversation._fail()
	check(model.retry_text == "Please clarify that example." and JSON.stringify(model.campus.serialize()) == snapshot, "Service failure preserves retry text without changing progress")
	model.cancel_activity()

func _test_two_weeks() -> void:
	GameState.reset_run()
	GameState.set_process(false)
	GameState.onboarding_active = false
	model.campus = State.new()
	model.cancel_activity()
	GameState.item_interaction_interrupted.connect(func(): faint_count += 1)
	model.travel("home")
	for day in range(1, 15):
		check(GameState.day == day and not GameState.game_finished, "Campus remains playable on day %d" % day)
		# Follow actual navigation and minimum offline meals; no invented scores or teleporting.
		for part in range(3):
			var before: float = GameState.clock_hours()
			var was_dining: bool = model.location == "dining"
			model.open_counter()
			check(was_dining or is_equal_approx(GameState.clock_hours() - before, 0.25), "Counter travel consumes the normal commute")
			model.greet()
			var meals: Array = model.visible_items("counter")
			check(meals.size() == 1, "Unavailable speech provides one real minimum meal")
			for record in meals: check(model.use_item("consume", str(record.id), true).get("ok", false), "Minimum meal is consumed through inventory")
			var selected: String = ["class_before_class", "club_first_visit", "sports_join"][part]
			model.travel(["class", "club", "sports"][part])
			model.select_scene(selected)
			model.joint_activity(true)
			if part == 0:
				model.study("class")
				model.travel("study")
				model.study("study")
		model.travel("home")
		model.wait_until_evening()
		check(GameState.food > 0 and GameState.energy > 0 and model.campus.social > 25, "Daily routine sustains food, energy and social needs")
		model.sleep()
		check(model.campus.social >= 25, "Overnight social needs remain manageable")
	check(model.campus.reviews.size() == 2 and model.campus.week == 3, "Two weekly reviews, no third-night ending")
	check(model.campus.reviews[0].academic == 100 and model.campus.reviews[1].academic == 100, "Two weeks of balanced learning complete")
	check(faint_count == 0, "Two-week normal route never relies on faint recovery")

func _test_group_audio() -> void:
	var transport: Node = model.conversation
	var original_player: Callable = transport.play_reply
	var started_speakers: Array = []
	var completed: Array = []
	var on_complete := func(receipt, _lines): completed.append(receipt)
	transport.completed.connect(on_complete)
	transport.cancel()
	transport.text_only = false
	transport.busy = true
	transport.active_turn = "audio-test"
	transport.play_reply = func(npc, reply):
		started_speakers.append(npc)
		var pcm := PackedByteArray()
		pcm.resize(4800)
		return NpcVoice.feed_reply_pcm(npc, reply, pcm)
	transport.accept_event("speaking", {"turn_id":"audio-test", "speaker_id":"alex", "reply_id":"audio-a", "reply_to":"player", "text":"I can help with the outline."})
	transport.accept_event("speaking", {"turn_id":"audio-test", "speaker_id":"jules", "reply_id":"audio-b", "reply_to":"alex", "text":"I would rather compare examples first."})
	transport.accept_event("done", {"turn_id":"audio-test", "source":"gemini"})
	check(started_speakers == ["alex"] and completed.is_empty(), "Second speaker waits and receipt cannot settle while audio plays")
	transport._audio_finished("sam", "audio-a")
	check(started_speakers == ["alex"], "Unrelated speaker completion cannot advance the queue")
	var deadline := Time.get_ticks_msec() + 3000
	while completed.is_empty() and Time.get_ticks_msec() < deadline: await get_tree().process_frame
	check(started_speakers == ["alex", "jules"] and completed.size() == 1, "Real audio completion plays both NPCs in order then releases the receipt once")
	transport.completed.disconnect(on_complete)
	transport.play_reply = original_player
	transport.cancel()

func _test_save() -> void:
	var path := "user://campus-test-%d.json" % Time.get_ticks_usec()
	var old: String = GameState.save_path
	GameState.persistence_enabled = true
	GameState.save_path = path
	model.exchange = [{"speaker_id":"player", "reply_to":"group", "text":"Could we continue tomorrow?"}, {"speaker_id":"casey", "reply_to":"player", "text":"I can check after class."}]
	model.topic_summary = "A tentative follow-up, not yet a confirmed appointment."
	model.history.append({"speaker":"casey", "text":"I can check after class.", "day":GameState.day})
	model.save()
	var expected: float = model.campus.social
	GameState.presentation_state.clear()
	check(GameState.load_game(), "Campus domain writes and loads shared item format")
	var restored = State.new()
	check(restored.restore(GameState.presentation_state.campus) and restored.social == expected, "Campus payload restores separately")
	var reloaded = preload("res://scripts/novel/campus_controller.gd").new()
	reloaded.novel_save_path = path
	reloaded.boot_from_save = true
	add_child(reloaded)
	reloaded.start(false)
	check(reloaded.exchange.size() == 2 and reloaded.exchange[-1].reply_to == "player" and reloaded.topic_summary == model.topic_summary, "Controller restores active speakers, addressees and topic summary")
	check(not reloaded.history.is_empty(), "Older local display history survives controller reload")
	reloaded.free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	GameState.save_path = old
	GameState.persistence_enabled = false

func _chapter(script: Script, path: String, other: String) -> Node:
	var chapter: Node = script.new()
	chapter.novel_save_path = path
	chapter.other_chapter_save_path = other
	add_child(chapter)
	return chapter

func _saved_word_state(path: String, word: String) -> String:
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	var entry = parsed.vocabulary_entries.get(word + "|observed", {}) if parsed is Dictionary else {}
	return str(entry.get("state", ""))

func _test_shared_vocabulary() -> void:
	# C1-05 / X1-04: town -> campus -> town keeps every word either chapter learned.
	var town_script := preload("res://scripts/novel/novel_controller.gd")
	var campus_script := preload("res://scripts/novel/campus_controller.gd")
	var stamp := Time.get_ticks_usec()
	var town_path := "user://vocab-town-%d.json" % stamp
	var campus_path := "user://vocab-campus-%d.json" % stamp
	var old: String = GameState.save_path
	GameState.persistence_enabled = true
	GameState.save_path = town_path
	GameState.save_game()
	var town := _chapter(town_script, town_path, campus_path)
	Vocabulary.observe_word("zebra")
	Vocabulary.record_word_spoken("zebra", 85.0)
	town.save()
	town.free()
	var campus := _chapter(campus_script, campus_path, town_path)
	check(Vocabulary.word_state("zebra") == "spoken", "Campus keeps a word spoken in town")
	Vocabulary.observe_word("giraffe")
	Vocabulary.record_word_spoken("zebra", 90.0)
	Vocabulary.record_word_used("zebra")
	campus.save()
	campus.free()
	town = _chapter(town_script, town_path, campus_path)
	check(Vocabulary.word_state("giraffe") == "heard" and Vocabulary.word_state("zebra") == "used", "Returning to town keeps words heard and used on campus")
	Vocabulary.observe_word("kettle")
	town.save()
	town.free()
	campus = _chapter(campus_script, campus_path, town_path)
	check(Vocabulary.word_state("kettle") == "heard" and Vocabulary.word_state("giraffe") == "heard", "Re-entering campus keeps later town words and earlier campus words")
	Vocabulary.observe_word("otter")
	campus.save()
	campus.free()
	check(_saved_word_state(town_path, "giraffe") == "heard" and _saved_word_state(town_path, "zebra") == "used", "Town save keeps the merged vocabulary")
	check(_saved_word_state(campus_path, "kettle") == "heard" and _saved_word_state(campus_path, "zebra") == "used", "Campus save keeps the merged vocabulary")
	# Quitting on campus and relaunching into the town: memory is empty, only the saves remain.
	GameState.vocabulary_entries = {}
	Vocabulary.entries.clear()
	town = _chapter(town_script, town_path, campus_path)
	check(Vocabulary.word_state("otter") == "heard" and Vocabulary.word_state("zebra") == "used", "Relaunching into the town merges progress saved only on campus")
	check(Vocabulary.word_state("morning") == "initial", "Merged vocabulary keeps the starting profile")
	town.free()
	for path in [town_path, campus_path]:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	GameState.save_path = old
	GameState.persistence_enabled = false

## P2-06: campus reading text meets the 18 canvas px floor, and the shared text-size
## setting scales the sidebar, scene card, status line and pop-up pages too.
func check_reading_sizes(minimum: int, mode: String) -> void:
	var smallest := {"px": 999, "text": "", "where": ""}
	var inspect := func(root: Node, where: String):
		for node in root.find_children("*", "Control", true, false):
			if not (node is Label or node is Button or node is RichTextLabel) or not node.is_visible_in_tree(): continue
			var px: int = node.get_theme_font_size("normal_font_size" if node is RichTextLabel else "font_size")
			if px < smallest.px: smallest = {"px": px, "text": str(node.get("text")).left(24), "where": where}
	inspect.call(screen.canvas, "scene")
	for page in [screen._plan, screen._settings, screen._hints, screen._words, screen._coaching, screen._history, screen._reviews, screen._example]:
		page.call()
		await get_tree().process_frame
		inspect.call(screen.modal, page.get_method())
		screen.modal.hide()
	check(smallest.px >= minimum, "%s campus text is at least %d canvas px; smallest is %d in %s: %s" % [mode, minimum, smallest.px, smallest.where, smallest.text])

func capture(name: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var folder := "res://../docs/reviews/campus_unified_2026-09-12"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder))
	get_viewport().get_texture().get_image().save_png(folder + "/" + name + ".png")
