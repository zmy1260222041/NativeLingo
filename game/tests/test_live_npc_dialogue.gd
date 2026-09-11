extends SceneTree
## Opt-in desktop integration probe. Run without --headless so
## NpcDialogueService exercises its raw HTTPClient SSE path against the real
## localhost speech service.

const MAX_AUDIO_READY_MS := 3000
const TEST_TIMEOUT_MS := 15000

var failures := 0
var started_msec := 0
var audio_ready_msec := -1
var audio_finished_msec := -1
var audio_ready_line_id := ""
var audio_finished_line_id := ""
var failed_reason := ""


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	# AudioStreamPlayer3D does not advance in a bare `--script` SceneTree with no
	# 3D world/listener. Mount the real game scene so this probe observes the
	# same Camera3D, audio clock, NPC adapters, and settlement order as gameplay.
	if current_scene == null:
		var game_scene: Node = load("res://scenes/Main.tscn").instantiate()
		root.add_child(game_scene)
		current_scene = game_scene
		await process_frame
	var service := root.get_node("NpcDialogueService")
	var npc_voice := root.get_node("NpcVoice")
	service.availability_override = true
	npc_voice.availability_override = true
	if service.has_active_session():
		service.cancel()
	npc_voice.line_audio_ready.connect(_on_audio_ready)
	npc_voice.line_audio_finished.connect(_on_audio_finished)
	service.dialogue_failed.connect(_on_dialogue_failed)
	_expect(npc_voice.line_audio_finished.is_connected(service._on_reply_audio_finished), "Dialogue service listens for NPC audio completion")
	_expect(service.begin_scenario("tavi", "food_counter"), "Live Tavi scenario starts")
	# Simulate the player's V hold: both upstream connections warm while speech
	# is being recorded, before release starts the NFR-9 clock.
	service.prewarm("tavi")
	await create_timer(3.0).timeout
	var berries_before: int = root.get_node("GameState").berries
	started_msec = Time.get_ticks_msec()
	_expect(service.submit_transcript("Can I have some food, please?", {"pronunciation": 84.0}), "Generic food request enters desktop SSE")
	await _wait_for_scored_audio(service)
	var generic_text: String = str(service.current_reply_text)
	_expect(audio_ready_msec >= 0 and service._score_received, "Generic NPC turn reaches scored playback")
	_expect(not service.current_transaction_complete, "Generic category reply is not a proven handoff: " + generic_text)
	_expect(root.get_node("GameState").berries == berries_before, "Generic reply grants nothing before audio completion")
	await _wait_for_audio_finished()
	_expect(root.get_node("GameState").berries == berries_before, "Generic reply grants nothing after audio completion")
	_expect(service.has_active_session(), "Generic request keeps the conversation open")
	await _wait_for_next_turn(service)
	_expect(audio_ready_line_id == service.current_reply_id or service.current_reply_id.is_empty(), "Generic audio belongs to the active reply: ready=%s active=%s" % [audio_ready_line_id, service.current_reply_id])
	var stream_length: float = float(npc_voice.audio_player.stream.get_length()) if npc_voice.audio_player.stream != null else -1.0
	_expect(audio_finished_line_id == audio_ready_line_id, "Generic finished signal matches the playing reply: ready=%s finished=%s playing=%s position=%.3f length=%.3f paused=%s" % [audio_ready_line_id, audio_finished_line_id, npc_voice.audio_player.playing, npc_voice.audio_player.get_playback_position(), stream_length, paused])
	_expect(service.current_reply_id.is_empty(), "Generic audio completion releases the active reply id: " + str(service.current_reply_id))
	_expect(not service._stream_busy(), "Generic SSE done releases the stream client")

	audio_ready_msec = -1
	audio_finished_msec = -1
	audio_ready_line_id = ""
	audio_finished_line_id = ""
	started_msec = Time.get_ticks_msec()
	_expect(service.submit_transcript("I'll take a taco to go, please.", {"pronunciation": 84.0}), "Concrete taco request enters desktop SSE")
	await _wait_for_scored_audio(service)
	var explicit_text: String = str(service.current_reply_text)
	var explicit_act: String = str(service.current_reply_speech_act)
	var latency := audio_ready_msec - started_msec if audio_ready_msec >= 0 else -1
	_expect(failed_reason.is_empty(), "Live dialogue does not fail: " + failed_reason)
	_expect(audio_ready_msec >= 0, "Live SSE reaches line_audio_ready")
	_expect(latency >= 0 and latency <= MAX_AUDIO_READY_MS, "Live first audio is within 3 seconds: " + str(latency) + "ms")
	_expect(service.last_reply_source == "gemini", "Live reply source is Gemini, not stub: " + service.last_reply_source)
	_expect(service.last_reply_model == "gemini-3.1-flash-lite", "Live score reports Flash-Lite: " + service.last_reply_model)
	_expect(service.current_transaction_complete and service.current_confirmed_item == "taco", "Concrete turn carries named spoken handoff evidence: " + explicit_text)
	_expect(service._spoken_reply_confirms_item(explicit_text, "taco", explicit_act), "Client independently verifies the spoken taco handoff")
	_expect(root.get_node("GameState").berries == berries_before, "Confirmed taco grants nothing while NPC audio is still playing")
	await _wait_for_audio_finished()
	_expect(root.get_node("GameState").berries > berries_before, "Confirmed taco grants food only after NPC finishes speaking")
	_expect(not service.has_active_session(), "Confirmed spoken handoff closes the live conversation")
	print("LIVE_NPC_METRICS audio_ready_ms=", latency, " source=", service.last_reply_source, " model=", service.last_reply_model, " generic=", generic_text, " explicit=", explicit_text)
	if service.has_active_session():
		service.cancel()
	service.availability_override = null
	npc_voice.availability_override = null
	if failures == 0:
		print("PASS: Stranger live desktop NPC dialogue")
	quit(failures)


func _on_audio_ready(npc_id: String, line_id: String) -> void:
	if npc_id == "tavi" and audio_ready_msec < 0:
		audio_ready_msec = Time.get_ticks_msec()
		audio_ready_line_id = line_id


func _on_audio_finished(npc_id: String, line_id: String) -> void:
	if npc_id == "tavi" and audio_finished_msec < 0:
		audio_finished_msec = Time.get_ticks_msec()
		audio_finished_line_id = line_id


func _wait_for_scored_audio(service: Node) -> void:
	var deadline := started_msec + TEST_TIMEOUT_MS
	while Time.get_ticks_msec() < deadline:
		if audio_ready_msec >= 0 and service._score_received:
			return
		if not failed_reason.is_empty():
			return
		await process_frame


func _wait_for_audio_finished() -> void:
	var deadline := Time.get_ticks_msec() + TEST_TIMEOUT_MS
	while Time.get_ticks_msec() < deadline:
		if audio_finished_msec >= 0 or not failed_reason.is_empty():
			return
		await process_frame


func _wait_for_next_turn(service: Node) -> void:
	var deadline := Time.get_ticks_msec() + 2000
	while Time.get_ticks_msec() < deadline:
		if service.current_reply_id.is_empty() and not service._stream_busy():
			return
		await process_frame


func _on_dialogue_failed(_npc_id: String, reason: String) -> void:
	failed_reason = reason


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
