extends Node
## Opt-in localhost/US-TTS/Gemini probe. Uses a synthetic WAV, never the user's mic.
## Exit 2 means online dialogue is blocked; exit 1 means a local contract failed.
var failures := 0
var audio_done := false
var word_done := false
var recognized := ""
var dialogue_error := ""
var model: Node
var reply_audio_done := false
var reply_text := ""
var dialogue_started := 0
var reply_ready_ms := -1
var reward_before := 0

func check(ok: bool, label: String) -> void:
	print("OK: " + label if ok else "FAIL: " + label)
	if not ok: failures += 1

func _ready() -> void:
	GameState.persistence_enabled = false
	GameState.reset_run()
	var screen := preload("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	Vocabulary.entries.clear()
	NpcVoice.line_audio_finished.connect(func(npc, line):
		if npc == "mira" and line == "word_practice_model": audio_done = true)
	SpeechAdapter.word_score_finished.connect(func(word, accepted, expression, _reason):
		if word == "water":
			word_done = true
			check(accepted and expression.get("pronunciation_source") == "reference_dtw", "Actual reference-DTW word scoring")
			print("LIVE_WORD ", JSON.stringify(expression)))
	SpeechAdapter.recognition_finished.connect(func(_npc, _accepted, text, _reason, _expression): recognized = text)
	NpcVoice.line_audio_ready.connect(func(_npc, line):
		if line.begins_with("reply-"):
			reply_ready_ms = Time.get_ticks_msec() - dialogue_started
			check(GameState.items.instances.size() == reward_before, "Resources unchanged before reply playback finishes"))
	NpcVoice.line_audio_finished.connect(func(_npc, line):
		if line.begins_with("reply-"): reply_audio_done = true)
	NpcDialogueService.dialogue_pending.connect(func(_npc, _scenario): dialogue_started = Time.get_ticks_msec())
	NpcDialogueService.dialogue_ready.connect(func(_npc, _reply, text): reply_text = text)
	NpcDialogueService.dialogue_failed.connect(func(_npc, reason): dialogue_error = reason)
	var before: int = GameState.items.instances.size()
	model.begin_practice("water")
	await until(func(): return audio_done, 20.0)
	check(audio_done and not model._listening, "US TTS model really plays and finishes in the 2D AudioStreamPlayer")
	check(Vocabulary.word_state("water") == "heard", "Listening alone does not become spoken")
	var http := HTTPRequest.new()
	http.timeout = 20.0
	add_child(http)
	http.request("http://127.0.0.1:17831/game/tts", ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify({"npc_id": "mira", "line_id": "word_practice_model", "options": ["water"]}))
	var response: Array = await http.request_completed
	check(response[1] == 200, "Synthetic word WAV available for scoring fixture")
	if response[1] != 200:
		get_tree().quit(1)
		return
	await capture_fixture(response[3])
	await until(func(): return word_done, 45.0)
	check(word_done and Vocabulary.word_state("water") == "spoken", "Actual scoring advances 2D practice heard to spoken")
	check(GameState.items.instances.size() == before, "Word practice grants no survival supplies")
	model.travel("store")
	model.talk()
	await until(func(): return not model._listening, 20.0)
	var wav := FileAccess.get_file_as_bytes("res://speech_service/reference_audio/ori.wav")
	reward_before = before
	await capture_fixture(wav)
	await until(func(): return not recognized.is_empty(), 45.0)
	check(not recognized.is_empty(), "Actual WAV transcription reaches the 2D controller")
	print("LIVE_TRANSCRIPT ", recognized)
	await until(func(): return not dialogue_error.is_empty() or (reply_audio_done and not NpcDialogueService.has_active_session()), 30.0)
	var blocked := not dialogue_error.is_empty()
	if blocked:
		check(GameState.items.instances.size() == before, "Failed online turn cannot issue supplies")
		check(Vocabulary.word_state("water") == "spoken", "Failed dialogue does not forge used progression")
		print("BLOCKED: real online dialogue rejected: ", dialogue_error)
	else:
		check(NpcDialogueService.last_reply_source == "gemini", "Real dialogue provider is Gemini")
		check(reply_audio_done and not NpcDialogueService.has_active_session(), "Real reply finishes and closes the named water handoff")
		check(GameState.items.instances.size() > before, "Spoken handoff yields real counter supplies")
		check(Vocabulary.word_state("water") == "used", "Practiced word becomes used through a real Gemini-scored request")
		check(reply_ready_ms >= 0 and reply_ready_ms <= 3000, "Warmed actual playback starts within 3 seconds")
		print("ONLINE_RESPONSE: ", reply_text, "; playback_ready_ms=", reply_ready_ms)
		check(model.pack_counter().get("ok", false), "The spoken reward can be packed")
		var carried: Array = model.visible_items("bag")
		if not carried.is_empty():
			check(model.use_item("consume", str(carried[0].id), true).get("ok", false), "The spoken reward is usable for survival")
		await food_conversation()
	model.cancel_activity()
	screen.queue_free()
	await get_tree().process_frame
	print("LIVE_NOVEL: local speech checks=", "passed" if failures == 0 else "failed", "; online=", "blocked" if blocked else "full speaking loop passed")
	get_tree().quit(1 if failures > 0 else (2 if blocked else 0))

func until(condition: Callable, seconds: float) -> void:
	var deadline := Time.get_ticks_msec() + int(seconds * 1000)
	while not condition.call() and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame

func capture_fixture(wav: PackedByteArray) -> void:
	# Real recording effect + finish_recording transport, with synthetic input on
	# the muted capture bus. Physical microphone is disconnected for this probe.
	model.record()
	check(SpeechAdapter.is_recording(), "The 2D record button starts an audio capture session")
	if not SpeechAdapter.is_recording(): return
	SpeechAdapter.microphone_player.stop()
	var source := AudioStreamPlayer.new()
	source.stream = AudioStreamWAV.load_from_buffer(wav)
	source.bus = "SpeechRecord"
	add_child(source)
	await get_tree().create_timer(0.1).timeout
	source.play()
	await source.finished
	await get_tree().create_timer(0.15).timeout
	model.record()
	source.queue_free()

func food_conversation() -> void:
	var args := OS.get_cmdline_user_args()
	var fixture := ""
	for arg in args:
		if arg.begins_with("--taco-wav="): fixture = arg.trim_prefix("--taco-wav=")
	check(not fixture.is_empty() and FileAccess.file_exists(fixture), "Concrete-order fixture was supplied")
	if fixture.is_empty() or not FileAccess.file_exists(fixture): return
	model.travel("food")
	model.talk()
	await until(func(): return not model._listening, 20.0)
	reward_before = GameState.items.instances.size()
	reply_audio_done = false
	reply_text = ""
	dialogue_error = ""
	await capture_fixture(FileAccess.get_file_as_bytes("res://speech_service/reference_audio/tavi.wav"))
	await until(func(): return not dialogue_error.is_empty() or (reply_audio_done and NpcDialogueService.current_reply_id.is_empty()), 30.0)
	check(dialogue_error.is_empty() and reply_audio_done, "Generic request receives a real audible response")
	check(NpcDialogueService.last_reply_source == "gemini" and NpcDialogueService.has_active_session(), "Generic request keeps a genuine multi-turn conversation open")
	check(GameState.items.instances.size() == reward_before, "Generic food request grants nothing")
	print("GENERIC_RESPONSE: ", reply_text)
	reply_audio_done = false
	await capture_fixture(FileAccess.get_file_as_bytes(fixture))
	await until(func(): return not dialogue_error.is_empty() or (reply_audio_done and not NpcDialogueService.has_active_session()), 30.0)
	check(dialogue_error.is_empty() and reply_audio_done and not NpcDialogueService.has_active_session(), "Concrete second spoken turn completes the conversation")
	check(GameState.items.instances.size() > reward_before, "Second turn's named handoff yields supplies after playback")
	check(reply_ready_ms >= 0 and reply_ready_ms <= 3000, "Second turn opens within the 3-second target")
	print("CONCRETE_RESPONSE: ", reply_text, "; playback_ready_ms=", reply_ready_ms)
	if not dialogue_error.is_empty() or NpcDialogueService.has_active_session(): return
	var screen = model.get_parent()
	check(not model.visible_items("counter").is_empty() and screen.counter_button.text.contains("领取"), "The live handoff exposes a visible pickup action")
	for arg in args:
		if arg.begins_with("--order-capture-dir="):
			var directory := arg.trim_prefix("--order-capture-dir=")
			DirAccess.make_dir_recursive_absolute(directory)
			screen.instant_text = true
			await get_tree().create_timer(0.4).timeout
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png(directory + "/live-order-ready.png")
	screen.counter_button.pressed.emit()
	var inventory = screen.inventory_view
	var item_id: String = inventory.selected_group().record.id
	var food_before: float = GameState.food
	for button in inventory.action_buttons:
		if button.get_meta("inventory_focus", "") == "action:consume":
			button.pressed.emit()
			break
	if not inventory.confirmation.is_empty(): inventory._confirm()
	check(GameState.items.instances[item_id].state == "consumed" and GameState.food > food_before, "The actual counter action eats the spoken order and restores hunger")
