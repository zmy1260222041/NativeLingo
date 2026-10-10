extends Node
const Screen := preload("res://scenes/Novel.tscn")
var failures := 0
var screen: Control
var model: Node

func check(condition: bool, message: String) -> void:
	if not condition:
		failures += 1
		push_error(message)

func _ready() -> void:
	TranslationServer.set_locale("zh_CN")
	GameState.persistence_enabled = false
	GameState.reset_run()
	SpeechAdapter.availability_override = false
	NpcVoice.availability_override = false
	screen = Screen.instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	await _test_recording_playback_conflict()
	await _test_startup_and_opening()
	await _test_ux_clarity()
	await _test_default_profile_practice()
	await _test_rowan_water_action()
	await get_tree().process_frame
	screen.place_buttons[1].pressed.emit()
	check(model.location == "food", "Location button navigates through the screen")
	model.travel("plaza")
	screen.remap.open_panel()
	check(screen.remap.binding_buttons.has(&"interact") and not screen.remap.binding_buttons.has(&"move_forward"), "Remapping contains the 2D actions only")
	screen.remap.close_panel()
	screen._close_panel()
	check(not _has_3d(screen), "2D screen must not instantiate a 3D world")
	check(NpcVoice.audio_player is AudioStreamPlayer, "Novel dialogue must use non-positional audio")
	var before := Vector3(GameState.food, GameState.energy, GameState.day_time)
	await get_tree().create_timer(0.2).timeout
	check(before == Vector3(GameState.food, GameState.energy, GameState.day_time), "Reading cannot spend needs or time")
	model.travel("food")
	model.greet()
	var counter: Array = model.visible_items("counter")
	check(counter.size() == 1, "Offline gesture delivers minimum food to visible counter")
	var id: String = str(counter[0].id)
	model.travel("store")
	check(not model.use_item("consume", id, true).ok, "Remote counter use must fail")
	check(not GameState.item_command("pack", [id], {"safe": true, "location": "tavi"}).ok, "Domain must reject forged remote location")
	model.travel("food")
	check(model.use_item("pack", id).ok, "Pack food at its counter")
	model.travel("home")
	check(model.use_item("store", id).ok, "Carried supplies can be stored at home")
	check(model.use_item("pack", id).ok, "Stored supplies can be reclaimed")
	check(model.use_item("consume", id, true).ok, "Consume packed food")
	check(not model.use_item("consume", id, true).ok, "Consumed item cannot be duplicated")
	model.travel("store")
	model.greet()
	counter = model.visible_items("counter")
	check(model.use_item("pack", str(counter[0].id)).ok, "Water can be carried")
	model.travel("neighbor")
	model.greet()
	check(not GameState.completed_steps.has("help_rowan") and model.visible_items("bag").size() == 1, "A plain gesture never gives the carried water away")
	check(model.give_water().get("ok", false) and GameState.completed_steps.has("help_rowan"), "Neighbor gift and relationship transfer survive migration")
	check(GameState.relationships.rowan > 0, "Gift increases relationship")
	model.travel("parts")
	model.greet()
	counter = model.visible_items("counter")
	var part: String = str(counter[0].id)
	check(model.use_item("pack", part).ok, "Pack a heater part")
	check(not model.use_item("place", part).ok, "Cannot install at the shop")
	model.travel("home")
	check(model.use_item("place", part).ok, "Place part at home")
	check(model.use_item("use_home", part).ok, "Install part at home")
	check(GameState.items.heater_progress == 1, "Installation changes original domain progress")
	model.travel("plaza")
	Vocabulary.entries.clear() # A learner without these initial-profile words.
	model.play_social(0)
	check(Vocabulary.word_state("morning") in ["heard", "spoken", "used"], "Social scene observes original vocabulary")
	check(screen.second_portrait.visible, "Social dialogue shows two portraits")
	check(Vocabulary.word_state("hungry").is_empty(), "Future social lines cannot unlock unheard words")
	model.next_social()
	check(screen.last_speaker == "tavi", "Next advances speaker")
	for extra_line in range(model.Content.SOCIAL[0].lines.size() - 1): model.next_social()
	check(model.social_index == -1, "Social scene exits cleanly")
	model.begin_practice("food")
	check(model._replay.get("line") == "word_practice_model" and model._replay.options == ["food"], "Practice requests an exact server-known word model")
	check(Vocabulary.word_state("food") == "heard", "Listening does not forge spoken progress")
	model._listening = true
	model.record()
	check(not SpeechAdapter.is_recording(), "NPC model playback must not be captured as player speech")
	model._listening = false
	SpeechAdapter.word_score_finished.emit("food", true, {"score": 80.0}, "")
	check(Vocabulary.word_state("food") in ["spoken", "used"], "Voice practice advances vocabulary")
	screen._show_line("you", "I want water.")
	screen._show_line("ori", "Here you go.")
	screen._show_salience("ori", "I want water.", ["want"])
	check(screen.player_caption.text.contains("[u]want[/u]"), "Late salience remains visible beside the NPC reply")
	model.travel("food")
	SpeechAdapter.availability_override = true
	SpeechAdapter.last_unavailable_reason = ""
	var count: int = GameState.items.instances.size()
	model.greet()
	check(GameState.items.instances.size() == count, "Available voice forbids gesture reward bypass")
	model.talk()
	check(NpcDialogueService.is_session_active_for("tavi"), "Service role cards open in 2D")
	model.travel("store")
	check(not NpcDialogueService.has_active_session(), "Location change cancels dynamic session")
	model._recognition("tavi", true, "a burger please", "", {"score": 95.0})
	check(GameState.items.instances.size() == count, "Late old-target recognition cannot grant rewards")
	model._health_result(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify({"dialogue_ready": false, "dialogue_reason": "region_unsupported"}).to_utf8_buffer())
	check(SpeechAdapter.runtime_speech_unavailable() and model.voice_status.contains("地区"), "Running local server cannot disguise a rejected model")
	model._health_result(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify({"dialogue_ready": true}).to_utf8_buffer())
	check(not SpeechAdapter.runtime_speech_unavailable(), "Reconnection clears fallback status")
	await _test_spoken_handoff()
	SpeechAdapter.availability_override = false
	for kind in ["bag", "counter", "home", "growth", "theater", "history", "settings", "guide", "restart"]:
		screen._open_panel(kind)
		await get_tree().process_frame
		check(screen.modal.visible, "Panel opens: " + kind)
		screen._close_panel()
	# Save round trip, including all migrated fields, under a test-only path.
	GameState.persistence_enabled = true
	GameState.save_path = "user://novel_test_roundtrip.json"
	model.save()
	var saved_day: int = GameState.day
	GameState.day = 99
	check(GameState.load_game() and GameState.day == saved_day, "Novel save restores progress")
	check(GameState.presentation_state.location == model.location, "Novel saves location alongside domain snapshot")
	DirAccess.remove_absolute(GameState.save_path)
	GameState.persistence_enabled = false
	# Entire slice via actual 2D commands; no direct clock/day manipulation.
	model.restart()
	for night in range(3):
		model.travel("food")
		model.greet()
		counter = model.visible_items("counter")
		check(not counter.is_empty(), "Survival counter present each day")
		model.use_item("consume", str(counter[0].id), true)
		model.travel("store")
		model.greet()
		counter = model.visible_items("counter")
		model.use_item("consume", str(counter[0].id), true)
		model.travel("home")
		model.wait_until_evening()
		check(model.sleep(), "Night %d can finish through UI boundary" % (night + 1))
	check(GameState.game_finished and GameState.day == 4, "All three nights finish without 3D")
	check(not model.travel("food"), "Completed game cannot keep transacting")
	if "--novel-capture" in OS.get_cmdline_user_args():
		model.restart()
		await _capture("plaza")
		model.travel("food")
		await _capture("food")
		screen._open_panel("growth")
		await _capture("growth")
		screen._close_panel()
		model.travel("home")
		await _capture("home")
	print("PASS: 2D migration, inventory, vocabulary, cancellation, save, UI and three-night flow" if failures == 0 else "FAIL: %d novel assertions" % failures)
	screen.queue_free()
	await get_tree().process_frame
	await _test_legacy_import()
	get_tree().quit(failures)

func _has_3d(node: Node) -> bool:
	if node is Node3D: return true
	for child in node.get_children():
		if _has_3d(child): return true
	return false

func _capture(label: String) -> void:
	screen.instant_text = true
	await get_tree().create_timer(0.4).timeout
	await RenderingServer.frame_post_draw
	var path := "res://../docs/reviews/novel_2d_2026-09-11/%s.png" % label
	get_viewport().get_texture().get_image().save_png(path)

func _test_legacy_import() -> void:
	GameState.persistence_enabled = true
	GameState.save_path = "user://novel_test_legacy.json"
	GameState.reset_run()
	GameState.food = 43.0
	GameState.relationships.mira = 7
	GameState.save_game()
	var original := FileAccess.get_file_as_string(GameState.save_path)
	var migrated := preload("res://scripts/novel/novel_controller.gd").new()
	migrated.novel_save_path = "user://novel_test_imported.json"
	add_child(migrated)
	check(GameState.food == 43.0 and GameState.relationships.mira == 7, "First 2D boot imports legacy needs and relationships")
	migrated.travel("food")
	check(FileAccess.get_file_as_string("user://novel_test_legacy.json") == original, "2D travel/save never rewrites the legacy save")
	check(GameState.save_path == "user://novel_test_imported.json", "Imported game writes an independent save")
	migrated.queue_free()
	await get_tree().process_frame
	DirAccess.remove_absolute("user://novel_test_legacy.json")
	DirAccess.remove_absolute("user://novel_test_imported.json")
	GameState.persistence_enabled = false
	print("PASS: legacy import preserves original save" if failures == 0 else "FAIL: migration")

func _test_spoken_handoff() -> void:
	model.travel("food")
	var requests: Array = []
	NpcDialogueService.request_override = func(_url, _headers, _method, body):
		requests.append(JSON.parse_string(body))
		return OK
	model.talk()
	model._recognition("tavi", true, "Can I get a burger, please?", "", {"pronunciation": 80.0})
	check(requests.size() == 1 and requests[0].require_live_dialogue and requests[0].transcript == "Can I get a burger, please?", "2D recognized speech reaches the original dialogue boundary")
	var before: int = GameState.berries
	NpcDialogueService._streaming_response = true
	check(NpcDialogueService._apply_speaking({
		"reply_id": "reply-novel-voice-handoff", "npc_id": "tavi",
		"text": "You got it. I'll get you the burger now.",
		"speech_act": "confirm_order", "gate": {"accepted": true, "violations": []},
	}), "Validated response reaches 2D dialogue and playback")
	NpcDialogueService._apply_score({
		"reply_id": "reply-novel-voice-handoff", "npc_id": "tavi", "speech_act": "confirm_order", "next_state": "closed",
		"player_turn": {"idiomaticity": 90.0, "progress": "done", "transaction_complete": true,
			"off_inventory": false, "spoken_delivery_confirmed": true, "requested_item": "burger", "confirmed_item": "burger"},
	})
	check(NpcDialogueService._awaiting_stream_audio, "Early score must preserve pending streamed audio")
	var pcm := PackedByteArray()
	pcm.resize(9600)
	pcm.fill(0)
	for event in [
		["audio_begin", {"reply_id": "reply-novel-voice-handoff", "npc_id": "tavi", "sample_rate": 24000}],
		["audio", {"reply_id": "reply-novel-voice-handoff", "npc_id": "tavi", "seq": 0, "pcm_b64": Marshalls.raw_to_base64(pcm)}],
		["audio_end", {"reply_id": "reply-novel-voice-handoff", "npc_id": "tavi", "bytes": pcm.size()}],
	]:
		NpcDialogueService._handle_sse_block("event: " + event[0] + "\ndata: " + JSON.stringify(event[1]))

	check(GameState.berries == before, "2D spoken handoff cannot settle before audio finishes")
	check(screen.dialogue_text.text.contains("burger now"), "NPC spoken response is rendered in the 2D dialogue box")
	for attempt in range(20):
		if not NpcDialogueService.has_active_session(): break
		await get_tree().create_timer(0.1).timeout
	check(GameState.berries == before + 2, "Actual non-spatial audio completion settles the original scored transaction")
	check(not NpcDialogueService.has_active_session(), "Spoken transaction releases the 2D session")
	check(str(model.order_guidance().get("title", "")).contains("汉堡") and screen.counter_button.text.contains("2 件待取"), "Completed speech exposes the named pickup and its quantity")
	NpcDialogueService._on_reply_audio_finished("tavi", "reply-novel-voice-handoff")
	check(GameState.berries == before + 2, "Duplicate playback completion cannot grant another meal")
	check(model.pack_counter().get("ok", false), "2D bulk pack retrieves scored counter items")
	NpcScenarioRunner.begin("tavi", "food_counter")
	NpcScenarioRunner.record_player_turn("tavi", 20.0, 30.0)
	NpcScenarioRunner.apply_validated_reply("tavi", "food_counter", "confirm_order", "closed", true, "burger")
	var low_score: Dictionary = model.order_guidance()
	var digits := RegEx.new()
	digits.compile("[0-9]")
	check(model.visible_items("counter").is_empty() and str(low_score.get("title", "")).contains("还没能确认点单"), "Low score explains the failed order without delivering food")
	check(digits.search(str(low_score.get("title", "")) + str(low_score.get("detail", ""))) == null and str(low_score.get("detail", "")).contains("免费"), "FR-45: the failed order shows no score, only that retrying is free")
	NpcDialogueService.request_override = Callable()


func _test_ux_clarity() -> void:
	model.travel("store")
	model.play_social(1)
	var right: Rect2 = screen.portrait.texture.region
	var left: Rect2 = screen.second_portrait.texture.region
	model.next_social()
	check(screen.portrait.texture.region == right and screen.second_portrait.texture.region == left, "Theater cast keeps positions when the speaker changes")
	check(screen.second_portrait.modulate == Color.WHITE and screen.portrait.modulate != Color.WHITE, "The active speaker is highlighted in place")
	model.cancel_activity()
	model.start()
	screen._practice("morning")
	check(screen.order_panel.visible and screen.order_title.text.contains("morning"), "Practice mode remains visible outside the toast")
	check(screen.record_button.text.contains("录制这个词") and screen.gesture_button == null, "Practice exposes a word recording action without ambiguous gesture controls")
	var interact := InputEventAction.new()
	interact.action = "interact"
	interact.pressed = true
	screen._unhandled_input(interact)
	check(model.practice_word == "morning", "Interaction shortcut cannot silently cancel a word practice")
	screen._end_practice()
	check(model.practice_word.is_empty() and screen.record_button.text.contains("录音"), "Explicit practice exit restores conversation controls")
	model.travel("home")
	GameState.day_time = 0.0
	GameState.energy = 100.0
	screen._refresh()
	check(screen.home_action_button.text == "休息到夜晚", "Daytime primary action offers a valid rest")
	screen.home_action_button.pressed.emit()
	check(GameState._wants_sleep() and screen.home_action_button.text.contains("入睡"), "Rest changes the primary action to sleep")
	GameState.day_time = 0.0
	GameState.energy = GameState.ENERGY_TIRED - 1.0
	screen._refresh()
	check(screen.home_action_button.text.contains("入睡"), "Low energy still permits early sleep under the domain rule")
	GameState.reset_run()
	model.travel("plaza")
	await get_tree().process_frame


func _test_default_profile_practice() -> void:
	# The real default toddler profile, not a cleared one: most practice words are already known.
	check(Vocabulary.tier == "toddler" and Vocabulary.word_state("morning") == "initial" and Vocabulary.word_state("heater").is_empty(), "Default profile tells known words apart from unheard ones")
	screen._open_panel("growth")
	await get_tree().process_frame
	var rows: Array = []
	for child in screen.modal_body.get_children():
		if child is Button and str(child.text).contains("→  练习"): rows.append(str(child.text))
	var row_of := func(word: String) -> int:
		for index in rows.size():
			if str(rows[index]).begins_with(word + " "): return index
		return -1
	check(rows.size() == model._practice_words().size(), "Growth page lists every practice word")
	for row in rows:
		var word := str(row).get_slice(" ", 0)
		var known: bool = Vocabulary.entries_for_headword(word).any(func(item): return item.state == "initial")
		check(str(row).contains("已有词汇") == known and str(row).contains("尚未听见") != known, "Growth label matches the default profile: " + word)
	check(row_of.call("heater") >= 0 and row_of.call("heater") < row_of.call("morning"), "Truly new words are listed before known words")
	screen._close_panel()
	var toasts: Array = []
	var on_feedback := func(text: String): toasts.append(text)
	model.feedback.connect(on_feedback)
	model.travel("plaza")
	model.begin_practice("morning")
	SpeechAdapter.word_score_finished.emit("morning", true, {"score": 92.0}, "")
	check(str(toasts.back()).contains("你说出了「morning」") and not str(toasts.back()).contains("再试一次"), "An accepted attempt on a known word is a success")
	check(Vocabulary.word_state("morning") == "initial", "Known words never advance to spoken or used")
	SpeechAdapter.word_score_finished.emit("morning", false, {"score": 12.0}, "")
	check(str(toasts.back()).contains("再试一次"), "A rejected attempt on a known word stays a free retry")
	model.begin_practice("heater")
	check(Vocabulary.word_state("heater") == "heard", "Practising a new word starts at heard")
	SpeechAdapter.word_score_finished.emit("heater", true, {"score": 92.0}, "")
	check(str(toasts.back()).contains("你说出了「heater」") and Vocabulary.word_state("heater") == "spoken", "A new word still advances heard -> spoken")
	model.feedback.disconnect(on_feedback)
	model.cancel_activity()


## C1-02 / C1-03 / P1-08 / P2-03 / G1-10: water reaches Rowan only through the
## explicit, named item action, whether or not voice works.
func _test_rowan_water_action() -> void:
	for voice in [false, true]:
		var mode := "voice available" if voice else "voice unavailable"
		GameState.reset_run()
		SpeechAdapter.availability_override = false
		model.travel("store")
		model.greet()
		var counter: Array = model.visible_items("counter")
		check(counter.size() == 1 and model.use_item("pack", str(counter[0].id)).ok, "Carry one bottle of water to Rowan: " + mode)
		SpeechAdapter.availability_override = voice
		SpeechAdapter.last_unavailable_reason = ""
		model.travel("neighbor")
		await get_tree().process_frame
		check(is_instance_valid(screen.give_button) and screen.give_button.visible and screen.give_button.text.contains("送一份水给罗文"), "The water action is named at Rowan's porch: " + mode)
		check(screen.gesture_button.text.begins_with("手势  "), "The gesture keeps its own label: " + mode)
		screen.gesture_button.pressed.emit()
		check(model.visible_items("bag").size() == 1 and not GameState.completed_steps.has("help_rowan") and GameState.relationships.rowan == 0, "A gesture never gives the water away: " + mode)
		check(screen.dialogue_text.text.contains("Could you bring me water?"), "With water at hand, Rowan asks for it instead of 'Do not come empty-handed': " + mode)
		screen.give_button.pressed.emit()
		check(GameState.completed_steps.has("help_rowan") and GameState.relationships.rowan == 3 and model.visible_items("bag").is_empty(), "The water action completes the help event: " + mode)
		check(GameState.items.records("transferred", "rowan").size() == 1, "The bottle moves through the item ledger: " + mode)
		check(screen.feedback_label.text.contains("瓶装水已送给罗文"), "The result names the item and Rowan: " + mode)
		model.npc_voice_ready = false
		NpcVoice.line_audio_failed.emit("rowan", "remembers", "VOICE_REASON_SERVICE_UNAVAILABLE")
		check(screen.feedback_label.text.contains("瓶装水已送给罗文"), "Rowan's line failing to voice later never replaces the named result: " + mode)
		model.npc_voice_ready = true
		check(screen.speaker_label.text == "Rowan" and not screen.dialogue_text.text.contains("came back"), "Rowan thanks the actual gift, never 'You came back' at a first meeting: " + mode)
		check(not screen.give_button.visible, "The water action leaves once Rowan has the water: " + mode)
		check(not model.give_water().get("ok", false) and GameState.relationships.rowan == 3, "A second gift cannot repeat the reward: " + mode)
		model.cancel_activity()
	check(not model.item_description("drink_bottled_water").contains("交流时") and model.item_description("drink_bottled_water").contains("送一份水给罗文"), "The water description points to the real action")
	# P1-03 / P2-08: the growth page shows localized memories, never raw keys.
	GameState.remember("mira", "MEMORY_GREET_MIRA", 0)
	screen._open_panel("growth")
	await get_tree().process_frame
	var page := ""
	for child in screen.modal_body.get_children():
		if child is Label: page += str(child.text) + "\n"
	check(not page.contains("MEMORY_") and page.contains(tr("MEMORY_HELP_ROWAN")) and page.contains(tr("NPC_ROWAN")) and page.contains(tr("MEMORY_GREET_MIRA")), "Growth memories are translated with localized names")
	screen._close_panel()
	SpeechAdapter.availability_override = false
	GameState.reset_run()
	model.travel("plaza")


func _test_startup_and_opening() -> void:
	model.travel("food")
	GameState.presentation_state["guide_seen"] = true
	screen.startup_pending = true
	screen._open_panel("startup")
	screen._close_panel()
	check(screen.modal.visible and model.location == "food", "Startup choice cannot be dismissed into the saved scene")
	screen._continue_journey()
	check(not screen.modal.visible and model.location == "food", "Continue deliberately restores the saved location")
	check(model._replay.get("npc") == "tavi" and model._replay.get("line") == "service_entry", "Continue queues a replayable, server-known opening voice")
	var original_path: String = model.novel_save_path
	model.novel_save_path = "user://startup_no_save_%d.json" % Time.get_ticks_usec()
	screen._new_journey()
	check(model.location == "plaza" and GameState.day == 1 and screen.modal_kind == "guide", "A new journey returns to day-one plaza with onboarding")
	check(not GameState.presentation_state.get("guide_seen", false), "Restart clears the previous onboarding completion flag")
	screen._close_panel()
	check(model._replay.get("npc") == "mira" and model._replay.get("line") == "greet_reply", "Leaving onboarding plays the plaza welcome")
	model.novel_save_path = original_path
	await get_tree().process_frame


func _test_recording_playback_conflict() -> void:
	model.travel("food")
	model.cancel_activity()
	model.start(false)
	var opened: Array = []
	var on_open := func(npc, scenario, text): opened.append([npc, scenario, text])
	NpcDialogueService.scenario_opened.connect(on_open)
	var pcm := PackedByteArray()
	pcm.resize(24000) # Half a second of synthetic PCM, no microphone input.
	NpcVoice.feed_reply_pcm("tavi", "test-opening", pcm)
	screen._refresh_record_button()
	check(screen.record_button.disabled, "Record control is unavailable while NPC audio plays")
	var stream = NpcVoice.audio_player.stream
	for attempt in range(4):
		# Exercise the model guard even if a queued signal bypasses disabled UI.
		screen.record_button.pressed.emit()
		var key := InputEventAction.new()
		key.action = "push_to_talk"
		key.pressed = true
		screen._unhandled_input(key)
	check(NpcVoice.audio_player.stream == stream and NpcVoice.playing_line_id == "test-opening", "Repeated mouse/key attempts do not replace or restart NPC audio")
	check(not SpeechAdapter.is_recording() and opened.is_empty(), "Playback clicks neither capture NPC audio nor reopen the greeting")
	await get_tree().create_timer(0.7).timeout
	screen._refresh_record_button()
	check(not screen.record_button.disabled, "Record becomes available after the real playback-finished signal")
	NpcVoice.pending_reply_id = "pending-test-reply"
	screen._refresh_record_button()
	check(screen.record_button.disabled, "A pending dynamic reply also blocks recording")
	NpcVoice.pending_reply_id = ""
	var prior_effect = SpeechAdapter.record_effect
	var prior_available = SpeechAdapter.availability_override
	var bus := AudioServer.bus_count
	AudioServer.add_bus()
	AudioServer.set_bus_name(bus, "NovelRecordConflict")
	AudioServer.set_bus_mute(bus, true)
	SpeechAdapter.record_effect = AudioEffectRecord.new()
	AudioServer.add_bus_effect(bus, SpeechAdapter.record_effect)
	var source := AudioStreamPlayer.new()
	source.bus = "NovelRecordConflict"
	var silence := AudioStreamWAV.new()
	silence.format = AudioStreamWAV.FORMAT_16_BITS
	silence.mix_rate = 24000
	silence.data = pcm
	source.stream = silence
	add_child(source)
	source.play()
	await get_tree().create_timer(0.1).timeout
	SpeechAdapter.availability_override = true
	model.record()
	check(SpeechAdapter.is_recording() and NpcDialogueService.is_session_active_for("tavi"), "First click after playback starts recording in a valid session")
	check(opened.is_empty() and NpcVoice.playing_line_id.is_empty(), "Starting the session for recording never repeats the arrival greeting")
	screen._refresh_record_button()
	check(not screen.record_button.disabled and screen.record_button.text.contains("结束录音"), "The player's stop-recording control remains available")
	SpeechAdapter.cancel_recording()
	source.stop()
	source.queue_free()
	AudioServer.remove_bus(bus)
	SpeechAdapter.record_effect = prior_effect
	SpeechAdapter.availability_override = prior_available
	NpcDialogueService.scenario_opened.disconnect(on_open)
	model.cancel_activity()
	GameState.reset_run()
	model.travel("plaza")
