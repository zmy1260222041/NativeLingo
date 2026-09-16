extends "res://tests/test_live_novel_speaking.gd"

func _ready() -> void:
	GameState.persistence_enabled = false
	GameState.reset_run()
	var screen := preload("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	NpcDialogueService.dialogue_ready.connect(func(_npc, _reply, text): reply_text = text)
	NpcDialogueService.dialogue_failed.connect(func(_npc, reason): dialogue_error = reason)
	NpcVoice.line_audio_finished.connect(func(_npc, line):
		if line.begins_with("reply-"): reply_audio_done = true)
	SpeechAdapter.recognition_finished.connect(func(_npc, _ok, text, _reason, _expression): recognized = text)
	var initial_items: int = GameState.items.instances.size()
	check(NpcDialogueService.start_social_opening("mira", "market_conversation", 1), "Mira can initiate without a player recording")
	await until(func(): return reply_audio_done or not dialogue_error.is_empty(), 60.0)
	check(reply_audio_done and dialogue_error.is_empty(), "Proactive opening plays to completion")
	check(Dialogue.history_for("mira").all(func(turn): return turn.role == "npc"), "Opening does not forge player speech in history")
	check(NpcScenarioRunner.sessions.get("mira", {}).get("turns", []).is_empty(), "Opening is not scored as player practice")
	check(GameState.items.instances.size() == initial_items, "Opening grants no supplies")
	print("MIRA_OPENING ", reply_text)
	var session := ""
	for index in range(2):
		reply_text = ""
		recognized = ""
		reply_audio_done = false
		await capture_fixture(FileAccess.get_file_as_bytes("/tmp/mira-test-%d.wav" % index))
		await until(func(): return reply_audio_done or not dialogue_error.is_empty(), 60.0)
		check(not recognized.is_empty(), "Mira recording reaches transcription")
		check(dialogue_error.is_empty() and reply_audio_done, "Mira dynamic reply audio finishes")
		check(not reply_text.is_empty() and reply_text != "Welcome, stranger.", "Mira responds instead of repeating the authored greeting")
		check(NpcDialogueService.last_reply_source == "gemini", "Mira reply comes from the live model")
		check(GameState.presentation_state.get("town_contacts", {}).get("mira", {}).get("completed_exchanges", 0) == index + 1, "Only a completed recorded exchange advances Mira familiarity")
		check(model.order_note.is_empty(), "Social dialogue does not show an order receipt")
		check(GameState.items.instances.size() == initial_items, "Social dialogue cannot grant supplies")
		if index == 0: session = NpcDialogueService.session_id
		else: check(session == NpcDialogueService.session_id, "Follow-up retains the same conversation session")
		print("MIRA_TURN ", index, " heard=", recognized, " reply=", reply_text)
	model.cancel_activity()
	screen.queue_free()
	await get_tree().process_frame
	print("MIRA_LIVE failures=", failures)
	get_tree().quit(1 if failures else 0)
