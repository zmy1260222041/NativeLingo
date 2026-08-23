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
	_expect(registry.scenario_ids_for("mira").is_empty(), "Mira no longer hosts scripted service counters")
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
		"text": "You got it.",
		"speech_act": "confirm_order",
		"next_state": "closed",
		"player_turn": {"idiomaticity": 82.0, "progress": "done", "transaction_complete": true, "off_inventory": false},
		"gate": {"accepted": true, "violations": []},
	}
	_expect(bool(service._validate_reply(valid_reply).get("ok", false)), "Godot accepts the service-point reply contract")
	var teacher_talk: Dictionary = valid_reply.duplicate(true)
	teacher_talk["text"] = "Your pronunciation score is low. Repeat after me."
	_expect(not bool(service._validate_reply(teacher_talk).get("ok", false)), "Godot rejects teacher-talk NPC replies")
	var invalid_score: Dictionary = valid_reply.duplicate(true)
	invalid_score["player_turn"]["idiomaticity"] = NAN
	_expect(not bool(service._validate_reply(invalid_score).get("ok", false)), "Godot rejects non-finite idiomaticity")
	_expect(dialogue.accept_dynamic_reply("tavi", "reply-test", "You got it.", "closed"), "Validated reply can close after a completed order")
	_expect(dialogue.finish_speaking("tavi", "reply-test") == "closed", "Completed transaction closes the conversation")
	service.cancel()
	_expect(service.begin_scenario("tavi", "food_counter"), "A new session can start after cancel")
	_expect(runner.begin("tavi", "food_counter"), "Runner accepts the food counter")
	_expect(runner.record_player_turn("tavi", 80.0, 70.0) == 75.0, "Session score averages pronunciation and idiomaticity")
	var game_state := root.get_node("GameState")
	game_state.completed_steps["greet_mira"] = true
	var old_steps: Dictionary = game_state.completed_steps.duplicate(true)
	var before := Vector3i(game_state.berries, game_state.scrap, game_state.water)
	_expect(runner.apply_validated_reply("tavi", "food_counter", "confirm_order", "closed", true), "Completed transaction can grant resources")
	_expect(game_state.berries == before.x + 2, "Generous session score grants two food portions")
	_expect(game_state.completed_steps == old_steps or game_state.completed_steps.has("greet_mira"), "Grant does not invent extra quest markers")
	_expect(str(game_state.dialogue_scenario_progress.get("food_counter", {}).get("outcome", "")) == "success", "Runner records the completed service conversation")
	service.cancel()
	service.request_override = Callable()
	service.availability_override = null
	_test_stream_audio_events(service, dialogue)
	_test_stream_audio_failure_falls_back(service, dialogue)
	_test_stream_score_without_audio_falls_back(service, dialogue)
	_test_prewarm(service)
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
	var pcm := PackedByteArray()
	pcm.resize(9600)
	pcm.fill(3)
	var b64 := Marshalls.raw_to_base64(pcm)
	service._handle_sse_block("event: audio_begin\ndata: {\"reply_id\":\"reply-stream\",\"npc_id\":\"tavi\",\"sample_rate\":24000}")
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
		"reply_id": "reply-score-fb", "npc_id": "tavi", "speech_act": "confirm_order",
		"next_state": "awaiting_follow_up",
		"player_turn": {"idiomaticity": 80.0, "progress": "ordering", "transaction_complete": false, "off_inventory": false},
	})
	_expect(npc_voice.pending_reply_id == "reply-score-fb", "A score without streamed audio falls back to /game/tts")
	npc_voice.availability_override = null
	service.cancel()


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


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
