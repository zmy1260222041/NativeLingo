extends SceneTree

const GameStateScript = preload("res://scripts/game_state.gd")

var failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var registry := root.get_node("NpcScenarioRegistry")
	var dialogue := root.get_node("Dialogue")
	var service := root.get_node("NpcDialogueService")
	var runner := root.get_node("NpcScenarioRunner")
	# T1-01: Mira has a social market conversation (2026-09-14), never a service counter.
	_expect(not GameStateScript.SERVICE_SCENARIOS.has("mira") and not GameStateScript.SERVICE_SCENARIOS.values().any(func(id): return id in registry.scenario_ids_for("mira")), "Mira hosts no scripted service counter")
	for scenario_id in registry.scenario_ids_for("mira"):
		var social: Dictionary = registry.get_scenario(scenario_id)
		_expect(str(social.get("conversation_mode", "")) == "social" and (social.get("inventory", []) as Array).is_empty() and (social.get("completion_speech_acts", []) as Array).is_empty(), "Mira's conversation sells nothing and completes no order: " + scenario_id)
	var tavi_ids: Array[String] = registry.scenario_ids_for("tavi")
	var ori_ids: Array[String] = registry.scenario_ids_for("ori")
	var vesh_ids: Array[String] = registry.scenario_ids_for("vesh")
	_expect(tavi_ids.size() == 1 and tavi_ids[0] == "food_counter", "Tavi hosts the food counter")
	_expect(ori_ids.size() == 1 and ori_ids[0] == "convenience_store", "Ori hosts the convenience store")
	_expect(vesh_ids.size() == 1 and vesh_ids[0] == "parts_desk", "Vesh hosts the parts desk")
	for scenario_id in ["food_counter", "convenience_store", "parts_desk"]:
		var scenario: Dictionary = registry.get_scenario(scenario_id)
		_expect(not scenario.is_empty(), "Scenario loads: " + scenario_id)
		_expect(not str(scenario.get("role", "")).is_empty(), "Scenario has a role: " + scenario_id)
		_expect(not (scenario.get("inventory", []) as Array).is_empty(), "Scenario has inventory: " + scenario_id)
		_expect(not str(scenario.get("entry_dialogue", "")).is_empty(), "Scenario has an opening: " + scenario_id)
	_expect(not str(registry.get_profile("tavi").get("persona", "")).is_empty(), "Tavi has a service persona")
	_test_locked_occupations(registry)

	_test_dynamic_service_opens_without_greeting(service)
	_expect(service.begin_scenario("tavi", "food_counter"), "Dynamic scenario session starts")
	_expect(dialogue.has_dynamic_session("tavi"), "Dynamic session is isolated from legacy dialogue")
	_expect(dialogue.scenario_for("tavi") == "food_counter", "Session records the service scenario id")
	_expect(dialogue.state_for("tavi") == "awaiting_player", "Opening advances to awaiting_player")
	service.reject_empty_transcript("VOICE_REASON_CLARIFY")
	_expect(dialogue.state_for("tavi") == "clarify", "Empty recognition becomes clarify without fabricated player text")
	_expect(dialogue.history_for("tavi").is_empty(), "Empty recognition does not enter conversation history")
	var request_bodies: Array[Dictionary] = []
	service.availability_override = true
	service.request_override = func(_url: String, _headers: PackedStringArray, _method: int, body: String) -> int:
		request_bodies.append(JSON.parse_string(body))
		return OK
	_expect(service.submit_transcript("Can I get a burger, please?", {"pronunciation": 80.0}), "Dynamic session accepts an open transcript")
	_expect(dialogue.state_for("tavi") == "generating", "Generation state stays open for the server response")
	_expect(float(request_bodies[0].get("game_context", {}).get("pronunciation", -1.0)) == 80.0, "Pronunciation travels with the transcript")
	var rejected_body := JSON.stringify({"ok": false, "reason": "VOICE_REASON_DIALOGUE_REJECTED"}).to_utf8_buffer()
	service._on_request_completed(HTTPRequest.RESULT_SUCCESS, 422, PackedStringArray(), rejected_body)
	_expect(request_bodies.size() == 2 and int(request_bodies[1].get("retry", 0)) == 1, "HTTP 422 triggers exactly one replacement-candidate retry")
	_expect(dialogue.history_for("tavi").size() == 1, "Internal retry does not duplicate the player turn")
	service._on_request_completed(HTTPRequest.RESULT_SUCCESS, 422, PackedStringArray(), rejected_body)
	_expect(request_bodies.size() == 2 and dialogue.state_for("tavi") == "clarify", "Second quality rejection stops retrying and keeps the scenario open")
	var valid_reply := {
		"reply_id": "reply-contract",
		"npc_id": "tavi",
		"text": "You got it. I'll get you the burger now.",
		"speech_act": "confirm_order",
		"next_state": "closed",
		"player_turn": {
			"idiomaticity": 82.0,
			"progress": "done",
			"transaction_complete": true,
			"off_inventory": false,
			"spoken_delivery_confirmed": true,
			"requested_item": "burger",
			"confirmed_item": "burger",
		},
		"gate": {"accepted": true, "violations": []},
	}
	_expect(bool(service._validate_reply(valid_reply).get("ok", false)), "Godot accepts the service-point reply contract")
	var teacher_talk: Dictionary = valid_reply.duplicate(true)
	teacher_talk["text"] = "Your pronunciation score is low. Repeat after me."
	_expect(not bool(service._validate_reply(teacher_talk).get("ok", false)), "Godot rejects teacher-talk NPC replies")
	var invalid_score: Dictionary = valid_reply.duplicate(true)
	invalid_score["player_turn"]["idiomaticity"] = NAN
	_expect(not bool(service._validate_reply(invalid_score).get("ok", false)), "Godot rejects non-finite idiomaticity")
	# C2-03: the service sends JSON null (idiomaticity_source=unavailable) when the
	# model gave no score; that is a valid reply, not a crash or a rejection.
	var unavailable_score: Dictionary = valid_reply.duplicate(true)
	unavailable_score["player_turn"]["idiomaticity"] = null
	unavailable_score["player_turn"]["idiomaticity_source"] = "unavailable"
	_expect(bool(service._validate_reply(unavailable_score).get("ok", false)), "Godot accepts an unavailable (null) idiomaticity")
	_expect(dialogue.accept_dynamic_reply("tavi", "reply-test", "I'll get you the burger now.", "closed"), "Validated reply can close after a completed order")
	_expect(dialogue.finish_speaking("tavi", "reply-test") == "closed", "Completed transaction closes the conversation")
	service.cancel()
	_expect(service.begin_scenario("tavi", "food_counter"), "A new session can start after cancel")
	_expect(runner.begin("tavi", "food_counter"), "Runner accepts the food counter")
	_expect(runner.record_player_turn("tavi", 80.0, 70.0) == 75.0, "Session score averages pronunciation and idiomaticity")
	var game_state := root.get_node("GameState")
	game_state.completed_steps["greet_mira"] = true
	var old_steps: Dictionary = game_state.completed_steps.duplicate(true)
	var before := Vector3i(game_state.berries, game_state.scrap, game_state.water)
	_expect(runner.apply_validated_reply("tavi", "food_counter", "confirm_order", "closed", true, "burger"), "Completed transaction can grant resources")
	_expect(game_state.berries == before.x + 2, "Generous session score grants two food portions")
	_expect(game_state.completed_steps == old_steps or game_state.completed_steps.has("greet_mira"), "Grant does not invent extra quest markers")
	_expect(str(game_state.dialogue_scenario_progress.get("food_counter", {}).get("outcome", "")) == "success", "Runner records the completed service conversation")
	service.cancel()
	service.request_override = Callable()
	service.availability_override = null
	_test_single_active_session(service, dialogue)
	_test_stream_audio_events(service, dialogue)
	_test_stream_audio_failure_falls_back(service, dialogue)
	_test_stream_score_without_audio_falls_back(service, dialogue)
	_test_spoken_settlement_gate(service, dialogue)
	_test_plural_spoken_settlement(service, dialogue)
	_test_dialogue_failure_marks_gesture_fallback(service)
	_test_prewarm(service)
	_test_speaker_subtitle_contract(service, dialogue)
	if failures == 0:
		print("PASS: Godot NPC dialogue asset suite")
	quit(failures)


func _test_locked_occupations(registry: Node) -> void:
	var expected := {
		"tavi": {"occupation": "food_counter_server", "mainline": "food", "asset": "env_market_stall_a"},
		"ori": {"occupation": "convenience_store_cashier", "mainline": "water", "asset": "pending_convenience_store"},
		"mira": {"occupation": "market_greeter", "mainline": "none", "asset": "env_plaza_market_a"},
		"vesh": {"occupation": "hardware_parts_clerk", "mainline": "none", "asset": "pending_parts_desk"},
		"rowan": {"occupation": "resident_neighbor", "mainline": "none", "asset": "env_plaza_market_a"},
	}
	var food_sellers := 0
	var water_sellers := 0
	for npc_id in expected.keys():
		var profile: Dictionary = registry.get_profile(npc_id)
		var spec: Dictionary = expected[npc_id]
		_expect(str(profile.get("occupation", "")) == spec["occupation"], npc_id + " occupation is locked")
		_expect(str(profile.get("mainline", "")) == spec["mainline"], npc_id + " mainline duty is locked")
		var workplace: Dictionary = profile.get("workplace", {})
		_expect(str(workplace.get("asset", "")) == spec["asset"], npc_id + " workplace asset is locked")
		var sells: Array = profile.get("sells", [])
		if "food" in sells:
			food_sellers += 1
		if "water" in sells:
			water_sellers += 1
	_expect(food_sellers == 1 and water_sellers == 1, "Only Tavi sells food and only Ori sells water")
	_expect((registry.get_profile("mira").get("sells", []) as Array).is_empty(), "Mira does not sell")
	var tavi_anchor: Vector3 = registry.workplace_anchor("tavi")
	_expect(tavi_anchor.distance_to(Vector3(-1.8, 1.0, -2.75)) < 0.05, "Tavi stands at the food stall")
	_expect(registry.workplace_anchor("mira").z > tavi_anchor.z, "Mira stays on the customer side of the stall")


func _test_dynamic_service_opens_without_greeting(service: Node) -> void:
	if service.has_active_session():
		service.cancel()
	var state = GameStateScript.new()
	state.persistence_enabled = false
	root.add_child(state)
	_expect(state.can_start_service_dialogue("tavi") and state.can_start_service_dialogue("ori"), "Service points open without the Mira greeting")
	var resources_before := Vector3i(state.berries, state.scrap, state.water)
	var steps_before: Dictionary = state.completed_steps.duplicate(true)
	state.interact("npc", "tavi", "action")
	_expect(service.has_active_session(), "Tavi action starts the food counter on day 1")
	_expect(Vector3i(state.berries, state.scrap, state.water) == resources_before and state.completed_steps == steps_before, "Opening a service point does not grant resources")
	service.cancel()
	state.queue_free()


func _test_stream_audio_events(service: Node, dialogue: Node) -> void:
	if service.has_active_session():
		service.cancel()
	service.begin_scenario("tavi", "food_counter")
	dialogue.begin_generation("tavi", "Can I get a burger, please?")
	service._streaming_response = true
	var ok: bool = service._apply_speaking({
		"reply_id": "reply-stream", "npc_id": "tavi", "text": "You got it.",
		"speech_act": "confirm_order", "next_state": "awaiting_follow_up",
		"gate": {"accepted": true, "violations": []},
	})
	_expect(ok and service._awaiting_stream_audio, "Stream-mode speaking defers audio to the SSE stream")
	_expect(not dialogue.begin_generation("tavi", "Another burger."), "Speaking state rejects a second V submission")
	var pcm := PackedByteArray()
	pcm.resize(9600)
	pcm.fill(3)
	var b64 := Marshalls.raw_to_base64(pcm)
	service._handle_sse_block("event: audio_begin\ndata: {\"reply_id\":\"reply-stream\",\"npc_id\":\"tavi\",\"sample_rate\":24000}")
	_expect(is_equal_approx(service.audio_fallback_timer.wait_time, service.AUDIO_STALL_SECONDS), "audio_begin switches fallback into a chunk-stall watchdog")
	service._handle_sse_block("event: audio\ndata: {\"reply_id\":\"reply-stream\",\"npc_id\":\"tavi\",\"seq\":0,\"pcm_b64\":\"" + b64 + "\"}")
	_expect(service._stream_audio.size() == pcm.size(), "Audio chunks accumulate while streaming")
	var npc_voice := root.get_node("NpcVoice")
	var ready_seen: Array[String] = []
	npc_voice.line_audio_ready.connect(func(_npc_id: String, line_id: String) -> void:
		ready_seen.append(line_id))
	service._handle_sse_block("event: audio_end\ndata: {\"reply_id\":\"reply-stream\",\"npc_id\":\"tavi\",\"bytes\":" + str(pcm.size()) + "}")
	_expect(ready_seen == ["reply-stream"], "audio_end feeds the reply straight into playback")
	_expect(npc_voice.playing_line_id == "reply-stream", "Streamed reply owns the audio player")
	service.cancel()


func _test_stream_audio_failure_falls_back(service: Node, dialogue: Node) -> void:
	if service.has_active_session():
		service.cancel()
	service.begin_scenario("tavi", "food_counter")
	dialogue.begin_generation("tavi", "One burger, please.")
	service._streaming_response = true
	service._apply_speaking({
		"reply_id": "reply-fallback", "npc_id": "tavi", "text": "You got it.",
		"speech_act": "confirm_order", "next_state": "awaiting_follow_up",
		"gate": {"accepted": true, "violations": []},
	})
	var npc_voice := root.get_node("NpcVoice")
	npc_voice.availability_override = true
	service._handle_sse_block("event: audio_failed\ndata: {\"reply_id\":\"reply-fallback\",\"npc_id\":\"tavi\"}")
	_expect(npc_voice.pending_reply_id == "reply-fallback", "audio_failed falls back to the /game/tts fetch")
	_expect(not service._awaiting_stream_audio, "Fallback clears the stream-audio wait")
	npc_voice.availability_override = null
	service.cancel()


func _test_stream_score_without_audio_falls_back(service: Node, dialogue: Node) -> void:
	if service.has_active_session():
		service.cancel()
	service.begin_scenario("tavi", "food_counter")
	dialogue.begin_generation("tavi", "One burger, please.")
	service._streaming_response = true
	service._apply_speaking({
		"reply_id": "reply-score-fb", "npc_id": "tavi", "text": "You got it.",
		"speech_act": "confirm_order", "next_state": "awaiting_follow_up",
		"gate": {"accepted": true, "violations": []},
	})
	var npc_voice := root.get_node("NpcVoice")
	npc_voice.availability_override = true
	service._apply_score({
		"reply_id": "reply-from-an-old-turn", "npc_id": "tavi", "speech_act": "confirm_order",
		"next_state": "closed",
		"player_turn": {"idiomaticity": 99.0, "progress": "done", "transaction_complete": true, "off_inventory": false},
	})
	_expect(not service._score_received and npc_voice.pending_reply_id.is_empty(), "A score from another reply cannot settle or start audio")
	service._apply_score({
		"reply_id": "reply-score-fb", "npc_id": "tavi", "speech_act": "confirm_order",
		"next_state": "awaiting_follow_up",
		"player_turn": {"idiomaticity": 80.0, "progress": "ordering", "transaction_complete": false, "off_inventory": false},
	})
	# Score and streamed audio race on independent planes: a score alone never
	# starts a /game/tts fetch while SSE audio may still arrive.
	_expect(service._score_received and service._awaiting_stream_audio and npc_voice.pending_reply_id.is_empty(), "A score alone keeps waiting for streamed audio")
	service._on_audio_fallback_timeout()
	_expect(npc_voice.pending_reply_id == "reply-score-fb", "A score without streamed audio falls back to /game/tts")
	npc_voice.availability_override = null
	service.cancel()


func _test_spoken_settlement_gate(service: Node, dialogue: Node) -> void:
	if service.has_active_session():
		service.cancel()
	var state := root.get_node("GameState")
	var before_generic: int = state.berries
	_expect(service.begin_scenario("tavi", "food_counter"), "Generic-confirmation regression session starts")
	dialogue.begin_generation("tavi", "Can I get a burger, please?")
	service.pending_pronunciation = 80.0
	service._streaming_response = true
	_expect(service._apply_speaking({
		"reply_id": "reply-generic-confirmation",
		"npc_id": "tavi",
		"text": "Sure thing.",
		"speech_act": "confirm_order",
		"gate": {"accepted": true, "violations": []},
	}), "Generic spoken reply reaches the client speaking state")
	# The live SSE contract delivers audio_end before score. This unit test
	# drives playback completion manually, so mark the stream payload as already
	# handed to NpcVoice instead of exercising the unrelated TTS fallback path.
	service._awaiting_stream_audio = false
	service._apply_score({
		"reply_id": "reply-generic-confirmation",
		"npc_id": "tavi",
		"speech_act": "confirm_order",
		"next_state": "closed",
		"player_turn": {
			"idiomaticity": 90.0,
			"progress": "done",
			"transaction_complete": true,
			"off_inventory": false,
			"spoken_delivery_confirmed": false,
			"confirmed_item": "",
		},
	})
	_expect(not service.current_transaction_complete and service._pending_next_state == "awaiting_follow_up", "Generic score is downgraded before audio completion")
	service._on_reply_audio_finished("tavi", "reply-generic-confirmation")
	_expect(state.berries == before_generic, "Generic 'Sure thing' cannot grant food even when score claims complete")
	_expect(service.has_active_session() and dialogue.state_for("tavi") == "awaiting_follow_up", "Unproven completion keeps the conversation open (state=" + dialogue.state_for("tavi") + ")")
	service.cancel()

	var before_explicit: int = state.berries
	_expect(service.begin_scenario("tavi", "food_counter"), "Explicit-confirmation regression session starts")
	dialogue.begin_generation("tavi", "Can I get a burger, please?")
	service.pending_pronunciation = 80.0
	service._streaming_response = true
	var explicit_text := "You got it. I'll get you the burger now."
	_expect(service._apply_speaking({
		"reply_id": "reply-explicit-confirmation",
		"npc_id": "tavi",
		"text": explicit_text,
		"speech_act": "confirm_order",
		"gate": {"accepted": true, "violations": []},
	}), "Explicit item handoff reaches the client speaking state")
	service._awaiting_stream_audio = false
	service._apply_score({
		"reply_id": "reply-explicit-confirmation",
		"npc_id": "tavi",
		"speech_act": "confirm_order",
		"next_state": "closed",
		"player_turn": {
			"idiomaticity": 90.0,
			"progress": "done",
			"transaction_complete": true,
			"off_inventory": false,
			"spoken_delivery_confirmed": true,
			"requested_item": "burger",
			"confirmed_item": "burger",
		},
	})
	_expect(service._spoken_reply_confirms_item(explicit_text, "burger", "confirm_order"), "Client recognizes the explicit named handoff sentence")
	_expect(service.current_transaction_complete and service.current_confirmed_item == "burger", "Explicit score retains auditable settlement evidence")
	_expect(state.berries == before_explicit, "Explicit confirmation still waits for the NPC audio to finish")
	service._on_reply_audio_finished("tavi", "reply-explicit-confirmation")
	_expect(state.berries == before_explicit + 2, "Explicit named handoff grants food only after audio finishes")
	_expect(not service.has_active_session(), "Proven handoff closes the completed conversation")


func _test_plural_spoken_settlement(service: Node, dialogue: Node) -> void:
	# C2-04: the service settles natural plural orders on the role card's form
	# ("two tacos" -> taco, "a battery" -> batteries). The client must accept the
	# same committed line, with word boundaries as strict as before.
	for case in [
		["tavi", "food_counter", "Sure thing, I'll get you two tacos.", "taco"],
		["tavi", "food_counter", "You got it. I'll get you two burgers.", "burger"],
		["tavi", "food_counter", "Sure thing, two sandwiches coming right up.", "sandwich"],
		["ori", "convenience_store", "Sure thing, I'll grab you two waters.", "water"],
		["ori", "convenience_store", "Sure thing, I'll grab you a battery.", "batteries"],
		["vesh", "parts_desk", "Sure thing, I'll get you two blankets.", "blanket"],
	]:
		if service.has_active_session():
			service.cancel()
		service.begin_scenario(case[0], case[1])
		_expect(service._spoken_reply_confirms_item(case[2], case[3], "confirm_order"), "Client accepts the inflected named handoff: " + case[2])
	for case in [
		["tavi", "food_counter", "Sure thing, I'll get you a tacoshell.", "taco"],
		["tavi", "food_counter", "Sure thing, I'll get you something burgerish.", "burger"],
		["ori", "convenience_store", "Sure thing, I'll grab you something watery.", "water"],
	]:
		if service.has_active_session():
			service.cancel()
		service.begin_scenario(case[0], case[1])
		_expect(not service._spoken_reply_confirms_item(case[2], case[3], "confirm_order"), "Inflection never loosens the word boundary: " + case[2])
	if service.has_active_session():
		service.cancel()
	var state := root.get_node("GameState")
	var records_before: int = state.items.records().size()
	_expect(service.begin_scenario("tavi", "food_counter"), "Plural-order regression session starts")
	dialogue.begin_generation("tavi", "Can I get two tacos, please?")
	service.pending_pronunciation = 80.0
	service._streaming_response = true
	var plural_text := "Sure thing, I'll get you two tacos."
	_expect(service._apply_speaking({
		"reply_id": "reply-plural-confirmation",
		"npc_id": "tavi",
		"text": plural_text,
		"speech_act": "confirm_order",
		"gate": {"accepted": true, "violations": []},
	}), "Plural handoff reaches the client speaking state")
	service._awaiting_stream_audio = false
	# The exact player_turn the service now returns for this order.
	service._apply_score({
		"reply_id": "reply-plural-confirmation",
		"npc_id": "tavi",
		"speech_act": "confirm_order",
		"next_state": "closed",
		"player_turn": {
			"idiomaticity": 80.0,
			"idiomaticity_source": "gemini",
			"progress": "done",
			"transaction_complete": true,
			"off_inventory": false,
			"spoken_delivery_confirmed": true,
			"requested_item": "taco",
			"confirmed_item": "taco",
		},
	})
	_expect(service.current_transaction_complete and service.current_confirmed_item == "taco", "A service-confirmed plural order keeps its settlement evidence")
	service._on_reply_audio_finished("tavi", "reply-plural-confirmation")
	_expect(state.items.records().size() > records_before, "The plural order delivers tacos once the NPC audio finishes")
	_expect(not service.has_active_session(), "The settled plural order closes the conversation")


func _test_single_active_session(service: Node, dialogue: Node) -> void:
	if service.has_active_session():
		service.cancel()
	_expect(service.begin_scenario("tavi", "food_counter"), "First dynamic NPC session starts")
	_expect(service.begin_scenario("ori", "convenience_store"), "A second dynamic NPC can replace the first")
	_expect(service.active_npc_id() == "ori" and not dialogue.has_dynamic_session("tavi"), "Replacing an NPC cancels the previous session")
	service.cancel()


func _test_dialogue_failure_marks_gesture_fallback(service: Node) -> void:
	if service.has_active_session():
		service.cancel()
	var speech_adapter := root.get_node("SpeechAdapter")
	var previous_reason: String = speech_adapter.last_unavailable_reason
	speech_adapter.last_unavailable_reason = ""
	service.begin_scenario("tavi", "food_counter")
	service._fail("VOICE_REASON_SERVICE_UNAVAILABLE")
	_expect(speech_adapter.runtime_speech_unavailable(), "Dialogue/TTS outage enables the survival gesture fallback")
	service.cancel()
	speech_adapter.last_unavailable_reason = previous_reason


func _test_prewarm(service: Node) -> void:
	service.availability_override = true
	service._prewarm_last_msec = 0
	_expect(service.prewarm_url() == "http://127.0.0.1:17831/game/prewarm", "Prewarm targets the local service boundary")
	service.prewarm("mira")
	_expect(service._prewarm_last_msec == 0, "Prewarm skips NPCs without a service scenario")
	service.prewarm("tavi")
	_expect(service._prewarm_last_msec != 0, "Prewarm fires for service-point NPCs")
	service.prewarm("tavi")
	service.availability_override = null


func _test_speaker_subtitle_contract(service: Node, dialogue: Node) -> void:
	if service.has_active_session():
		service.cancel()
	var vocabulary := root.get_node("Vocabulary")
	var game_state := root.get_node("GameState")
	var previous_tier: String = game_state.vocabulary_tier
	service.availability_override = true
	var request_bodies: Array[Dictionary] = []
	service.request_override = func(_url: String, _headers: PackedStringArray, _method: int, body: String) -> int:
		request_bodies.append(JSON.parse_string(body))
		return OK
	var displayed: Array = []
	service.player_turn_displayed.connect(func(_npc_id: String, transcript: String) -> void:
		displayed.append(transcript))
	var scored: Array = []
	service.player_turn_scored.connect(func(_npc_id: String, transcript: String, errors: Array) -> void:
		scored.append([transcript, errors]))
	game_state.vocabulary_tier = "toddler"
	_expect(service.begin_scenario("tavi", "food_counter"), "Subtitle contract session starts")
	vocabulary.observe_word("espresso")
	vocabulary.record_word_spoken("espresso", 85.0)
	_expect(vocabulary.word_state("espresso") == "spoken", "Precondition: espresso practised to spoken")
	_expect(service.submit_transcript("I want espresso, please.", {"pronunciation": 80.0}), "Turn submission accepted")
	_expect(displayed.size() == 1 and str(displayed[0]) == "I want espresso, please.", "G-B5: player words are mirrored the moment the turn starts")
	_expect(str(request_bodies[0].get("game_context", {}).get("player_level", "")) == "toddler", "G-A1: the tier enum travels in game_context and nowhere else")
	dialogue.accept_dynamic_reply("tavi", "reply-subtitle-1", "One espresso, coming up.", "awaiting_follow_up")
	service.current_reply_id = "reply-subtitle-1"
	service._apply_score({
		"reply_id": "reply-subtitle-1",
		"npc_id": "tavi",
		"source": "gemini",
		"player_turn": {
			"idiomaticity": 62.0,
			"errors": ["espresso"],
			"progress": "ordering",
			"transaction_complete": false,
			"off_inventory": false,
		},
	})
	_expect(scored.size() == 1 and str(scored[0][0]) == "I want espresso, please." and (scored[0][1] as Array).size() == 1 and str(scored[0][1][0]) == "espresso", "G-B2/G-B3: real scored turns carry the validated marks")
	_expect(vocabulary.word_state("espresso") == "used", "G-C1: conversational production proves used for a practised word")
	service.current_reply_id = "reply-subtitle-2"
	service._apply_score({
		"reply_id": "reply-subtitle-2",
		"npc_id": "tavi",
		"source": "stub",
		"player_turn": {
			"idiomaticity": 58.0,
			"errors": ["espresso"],
			"progress": "ordering",
			"transaction_complete": false,
			"off_inventory": false,
		},
	})
	_expect(scored.size() == 2 and (scored[1][1] as Array).is_empty(), "G-B2: stub turns never carry marks")
	dialogue.await_player("tavi")
	service.current_reply_id = ""
	game_state.vocabulary_tier = "professional"
	_expect(service.submit_transcript("Can I get a coffee?", {}), "Second turn accepted")
	_expect(str(request_bodies[1].get("game_context", {}).get("player_level", "")) == "professional", "G-A2: professional tier travels as the same enum")
	dialogue.await_player("tavi")
	service.current_reply_id = ""
	game_state.vocabulary_tier = "not-a-tier"
	_expect(service.submit_transcript("Another coffee, please.", {}), "Third turn accepted")
	_expect(not request_bodies[2].get("game_context", {}).has("player_level"), "Invalid tiers are dropped before leaving the device")
	service.cancel()
	service.availability_override = null
	service.request_override = Callable()
	game_state.vocabulary_tier = previous_tier


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
