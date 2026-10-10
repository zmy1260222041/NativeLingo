extends Node
## FR-46/48, NFR-8 UI duty: voice failures in the 2D town stay honest and current.
## Offline only: every service answer is simulated; the one network check dials a
## port that was just closed on this machine.
const Palette := preload("res://scripts/novel/novel_palette.gd")
var failures := 0
var screen: Control
var model: Node
var toasts: Array = []
var requests: Array = []

func check(ok: bool, label: String) -> void:
	if ok: print("PASS: " + label)
	else:
		failures += 1
		push_error("FAIL: " + label)

func _ready() -> void:
	# Deliberately no locale override: 2D copy must read the same on any system.
	GameState.persistence_enabled = false
	GameState.reset_run()
	SpeechAdapter.availability_override = true
	SpeechAdapter.last_unavailable_reason = ""
	NpcVoice.availability_override = false
	screen = preload("res://scenes/Novel.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	model.feedback.connect(func(text): toasts.append(text))
	NpcDialogueService.request_override = func(_url, _headers, _method, body):
		requests.append(JSON.parse_string(body))
		return OK
	await get_tree().process_frame
	await _test_failed_transcription_panel()
	await _test_interrupted_delivery()
	await _test_word_practice_reasons()
	await _test_health_status()
	await _test_offline_openings()
	await _test_dialogue_service_faults()
	_test_missing_idiomaticity()
	NpcDialogueService.request_override = Callable()
	NpcDialogueService.availability_override = null
	SpeechAdapter.availability_override = null
	NpcVoice.availability_override = null
	print("PASS: novel voice status" if failures == 0 else "FAIL: %d novel voice status checks" % failures)
	screen.queue_free()
	await get_tree().process_frame
	get_tree().quit(failures)

func _transcription(body: Variant, code := 200) -> void:
	SpeechAdapter.session_generation += 1
	SpeechAdapter.pending_target_id = model.npc_id()
	SpeechAdapter.request_generation = SpeechAdapter.session_generation
	var bytes := PackedByteArray() if body == null else JSON.stringify(body).to_utf8_buffer()
	SpeechAdapter._on_request_completed(HTTPRequest.RESULT_SUCCESS, code, PackedStringArray(), bytes)

func _no_english(text: String) -> bool:
	var regex := RegEx.new()
	regex.compile("[A-Za-z]{4,}")
	return regex.search(text) == null

func _reply(reply_id: String, text: String, act: String, turn: Dictionary, next_state := "awaiting_follow_up", seconds := 0.2) -> void:
	NpcDialogueService._streaming_response = true
	NpcDialogueService._apply_speaking({"reply_id": reply_id, "npc_id": model.npc_id(), "text": text, "speech_act": act, "gate": {"accepted": true, "violations": []}})
	NpcDialogueService._apply_score({"reply_id": reply_id, "npc_id": model.npc_id(), "speech_act": act, "next_state": next_state, "player_turn": turn})
	var pcm := PackedByteArray()
	pcm.resize(int(48000 * seconds))
	for event in [
		["audio_begin", {"reply_id": reply_id, "npc_id": model.npc_id(), "sample_rate": 24000}],
		["audio", {"reply_id": reply_id, "npc_id": model.npc_id(), "seq": 0, "pcm_b64": Marshalls.raw_to_base64(pcm)}],
		["audio_end", {"reply_id": reply_id, "npc_id": model.npc_id(), "bytes": pcm.size()}],
	]:
		NpcDialogueService._handle_sse_block("event: " + event[0] + "\ndata: " + JSON.stringify(event[1]))

## P1-04 / C1-06 / T1-04: a failed attempt is not "still listening".
func _test_failed_transcription_panel() -> void:
	model.travel("food")
	check(NpcDialogueService.begin_scenario("tavi", "food_counter", false), "Recording opens the counter session")
	toasts.clear()
	_transcription(null, 503)
	await get_tree().process_frame
	var guidance: Dictionary = model.order_guidance()
	check(not str(guidance.get("title", "")).contains("正在听清") and not str(guidance.get("detail", "")).contains("不用再录"), "A 503 transcription no longer reads as in-progress work")
	check(screen.order_title.text == str(guidance.get("title", "")) and screen.order_title.text.contains("语音服务"), "The order panel itself refreshes to the real cause")
	check(screen.order_detail.text.contains("不是你说得不好") and screen.order_detail.text.contains("手势领取"), "A service fault never blames the player and names the working fallback")
	check(toasts.size() == 1 and str(toasts[0]).count("重试") <= 1 and _no_english(str(toasts[0])), "One Chinese toast, retry offered once")
	model._replay = {"npc": "tavi", "line": "service_entry", "options": []}
	var attempts: Array = []
	var on_failed := func(npc, line, _reason): attempts.append([npc, line])
	NpcVoice.line_audio_failed.connect(on_failed)
	model.listen_again()
	NpcVoice.line_audio_failed.disconnect(on_failed)
	check(attempts == [["tavi", "service_entry"]], "Replay works after a failed recording instead of silently doing nothing")
	SpeechAdapter.last_unavailable_reason = ""
	_transcription({"accepted": false, "text": "", "reason": "VOICE_REASON_CLARIFY"})
	await get_tree().process_frame
	check(screen.order_title.text.contains("没有听清") and not screen.order_detail.text.contains("不是你说得不好"), "An empty transcript says it was not heard and offers a free retry")
	check(not screen.order_title.text.contains("正在听清"), "An empty transcript never shows the processing state")
	requests.clear()
	_transcription({"accepted": false, "text": "uh burger", "reason": "VOICE_REASON_CLARIFY", "pronunciation": 30.0})
	check(requests.size() == 1 and screen.order_title.text.contains("正在听清"), "An unclear but non-empty transcript is real in-flight dialogue")
	_reply("reply-voice-status-clarify", "Sure. Which one do you want?", "clarify_request", {"idiomaticity": 50.0, "transaction_complete": false, "requested_item": "burger"})
	for attempt in range(30):
		if Dialogue.state_for("tavi") == "awaiting_follow_up": break
		await get_tree().create_timer(0.05).timeout
	await get_tree().process_frame
	check(Dialogue.state_for("tavi") == "awaiting_follow_up" and not screen.order_title.text.contains("正在听清"), "After the reply plays, the panel leaves the processing state")
	model.cancel_activity()

## P1-09 / C1-07: a panel that cancels a confirmed delivery says what happened.
func _test_interrupted_delivery() -> void:
	model.travel("store")
	model.travel("food")
	NpcDialogueService.begin_scenario("tavi", "food_counter", false)
	model._recognition("tavi", true, "Can I get a burger, please?", "", {"pronunciation": 80.0})
	_reply("reply-voice-status-confirm", "You got it. I'll get you the burger now.", "confirm_order",
		{"idiomaticity": 90.0, "transaction_complete": true, "off_inventory": false, "spoken_delivery_confirmed": true, "requested_item": "burger", "confirmed_item": "burger"},
		"closed", 2.0)
	await get_tree().process_frame
	check(NpcDialogueService.current_transaction_complete and NpcVoice.audio_player.playing, "The clerk's confirmed delivery is still playing")
	toasts.clear()
	screen._open_panel("bag")
	await get_tree().process_frame
	await get_tree().process_frame
	check(model.visible_items("counter").is_empty() and not NpcDialogueService.has_active_session(), "FR-46: the panel still cancels the delivery")
	check(screen.modal_status.text.contains("没有交付") and toasts.size() == 1, "The open panel says once that nothing was delivered")
	screen._close_panel()
	await get_tree().process_frame
	check(not screen.order_title.text.contains("店员已确认") and screen.order_title.text.contains("没有交付"), "The order panel no longer claims a confirmed delivery")
	check(screen.order_detail.text.contains("不消耗"), "Re-ordering is explained as free")
	screen._open_panel("bag")
	screen._close_panel()
	check(not screen.order_title.text.contains("没有交付"), "A later panel with nothing in progress raises no new interruption")
	# NFR-9 speaks first: the named handoff can be playing before its score arrives.
	NpcDialogueService.begin_scenario("tavi", "food_counter", false)
	model._recognition("tavi", true, "A burger, please.", "", {"pronunciation": 80.0})
	NpcDialogueService._streaming_response = true
	NpcDialogueService._apply_speaking({"reply_id": "reply-voice-status-early", "npc_id": "tavi", "text": "You got it. I'll get you the burger now.", "speech_act": "confirm_order", "gate": {"accepted": true, "violations": []}})
	toasts.clear()
	screen._open_panel("settings")
	await get_tree().process_frame
	screen._close_panel()
	check(toasts.size() == 1 and screen.order_title.text.contains("没有交付"), "A spoken handoff interrupted before its score is also reported once")
	model.cancel_activity()

## P1-07 / P2-04 / C1-11: word scoring faults are not pronunciation feedback.
func _test_word_practice_reasons() -> void:
	model.travel("plaza")
	model.begin_practice("heater")
	var cases := {
		"VOICE_REASON_SERVICE_UNAVAILABLE": "不是你的发音问题",
		"VOICE_REASON_MIC_UNAVAILABLE": "麦克风",
		"VOICE_REASON_CLARIFY": "没有听到",
		"VOICE_REASON_SCORE_LOW": "再试一次",
	}
	for reason in cases:
		SpeechAdapter.word_score_finished.emit("heater", false, {}, reason)
		var said := str(toasts.back())
		check(said.contains(cases[reason]) and _no_english(said.replace("heater", "")), "Word practice explains %s honestly" % reason)
		if reason != "VOICE_REASON_SCORE_LOW":
			check(not said.contains("听一听，再试一次"), "%s is not presented as a pronunciation retry" % reason)
	check(Vocabulary.word_state("heater") == "heard", "A failed scoring attempt never advances the word")
	# A word attempt is no proof that the dialogue path works; a fault re-arms the fallback.
	var effect = SpeechAdapter.record_effect
	var bus := AudioServer.bus_count
	AudioServer.add_bus()
	AudioServer.set_bus_name(bus, "VoiceStatusWords")
	AudioServer.set_bus_mute(bus, true)
	SpeechAdapter.record_effect = AudioEffectRecord.new()
	AudioServer.add_bus_effect(bus, SpeechAdapter.record_effect)
	SpeechAdapter.mark_runtime_unavailable("VOICE_REASON_SERVICE_UNAVAILABLE")
	check(SpeechAdapter.start_word_recording("heater") and SpeechAdapter.runtime_speech_unavailable(), "Starting word practice keeps the known outage armed")
	SpeechAdapter.cancel_recording()
	SpeechAdapter.last_unavailable_reason = ""
	SpeechAdapter.session_generation += 1
	SpeechAdapter.pending_word_mode = true
	SpeechAdapter.pending_word_lexical_id = "heater"
	SpeechAdapter.pending_word_options = ["heater"]
	SpeechAdapter.request_generation = SpeechAdapter.session_generation
	SpeechAdapter._on_request_completed(HTTPRequest.RESULT_SUCCESS, 503, PackedStringArray(), JSON.stringify({"accepted": false, "reason": "VOICE_REASON_SERVICE_UNAVAILABLE"}).to_utf8_buffer())
	check(SpeechAdapter.runtime_speech_unavailable() and str(toasts.back()).contains("不是你的发音问题"), "A 503 word score arms the gesture fallback and is explained as a service fault")
	AudioServer.remove_bus(bus)
	SpeechAdapter.record_effect = effect
	SpeechAdapter.last_unavailable_reason = ""
	model.cancel_activity()

func _health(data: Variant, result := HTTPRequest.RESULT_SUCCESS) -> void:
	var body := PackedByteArray() if data == null else JSON.stringify(data).to_utf8_buffer()
	model._health_result(result, 200 if data != null else 0, PackedStringArray(), body)

## C2-08 / T1-05 / P1-05 / P2-12 / P1-17 / X1-03: one honest, current status.
func _test_health_status() -> void:
	model.travel("food")
	_health({"ok": true, "dialogue_ready": true, "asr_ready": false, "asr_reason": "model_missing", "tts_configured": true})
	check(model.voice_status.contains("录音可以进行，但语音识别暂不可用") and SpeechAdapter.runtime_speech_unavailable(), "asr_ready=false is reported and arms the gesture minimum")
	await get_tree().process_frame
	check((screen.gesture_button.get_theme_stylebox("normal") as StyleBoxFlat).bg_color == Palette.PRIMARY, "P1-14: the working gesture action leads while voice is down")
	model.greet()
	check(model.visible_items("counter").size() == 1, "FR-46: with recognition down the gesture fallback delivers the minimum")
	check(model.pack_counter().get("ok", false), "The fallback meal can be packed")
	_health({"ok": true, "dialogue_ready": true})
	check(not SpeechAdapter.runtime_speech_unavailable() and model.voice_status.contains("已连接"), "An older service without asr_ready keeps the previous meaning")
	await get_tree().process_frame
	check((screen.record_button.get_theme_stylebox("normal") as StyleBoxFlat).bg_color == Palette.PRIMARY, "Recording leads again once voice works")
	for case in [null, {"ok": true, "dialogue_ready": false, "dialogue_reason": "not_configured"}, {"ok": true, "dialogue_ready": false, "asr_ready": false, "tts_configured": false}]:
		_health(case, HTTPRequest.RESULT_CANT_CONNECT if case == null else HTTPRequest.RESULT_SUCCESS)
		check(not model.voice_status.contains("配置") and _no_english(model.voice_status) and model.voice_status.contains("手势"), "Status is player-facing Chinese: " + model.voice_status)
	model.voice_status = "正在检查语音连接…"
	screen._open_panel("settings")
	var label: Label = screen.voice_status_label
	check(label != null and label.text.begins_with("正在检查"), "Settings shows the pending check")
	_health({"ok": true, "dialogue_ready": true})
	await get_tree().process_frame
	check(label.text == model.voice_status and label.text.contains("已连接"), "Settings replaces 正在检查语音连接… with the result")
	var privacy := _modal_text()
	check(privacy.contains("隐私") and privacy.contains("录音只在这台电脑上") and privacy.contains("在线对话模型") and privacy.contains("配音服务"), "Local mode discloses what leaves the machine")
	screen._close_panel()
	ProjectSettings.set_setting("stranger_cloud/enabled", true)
	screen._open_panel("settings")
	check(_modal_text().contains("录音会上传到评分服务器"), "Cloud mode discloses that recordings are uploaded")
	screen._close_panel()
	ProjectSettings.set_setting("stranger_cloud/enabled", false)
	SpeechAdapter.last_unavailable_reason = ""

func _modal_text() -> String:
	var parts: Array[String] = []
	for child in screen.modal_body.get_children():
		if child is Label or child is Button: parts.append(str(child.text))
	return "\n".join(parts)

## C1-17 / P2-10 / P1-14 / G1-09: known-down dialogue shows authored lines, once-stated.
func _test_offline_openings() -> void:
	model.boot_from_save = true
	model.travel("plaza")
	model.social_openings.clear()
	_health({"ok": true, "dialogue_ready": false, "dialogue_reason": "not_configured", "tts_configured": false})
	toasts.clear()
	requests.clear()
	model.travel("neighbor")
	check(requests.is_empty() and not model._preparing_opening, "X1-02: no opening request while health says dialogue is down")
	check(screen.dialogue_text.text == "You look tired. Find water and warmth first.", "Rowan greets with the authored opening offline")
	var voice_toasts := toasts.filter(func(text): return str(text).contains("语音") or str(text).contains("交谈") or str(text).contains("未能"))
	check(voice_toasts == [model.voice_status], "The first offline arrival shows one consolidated status")
	toasts.clear()
	model.travel("plaza")
	voice_toasts = toasts.filter(func(text): return str(text).contains("语音") or str(text).contains("交谈") or str(text).contains("未能"))
	check(screen.dialogue_text.text == "Welcome, stranger." and voice_toasts.is_empty(), "Later arrivals stay quiet when NPC voice is known off")
	model.listen_again()
	check(toasts.size() == 1 and str(toasts[0]).contains("角色语音暂未开启"), "An explicit replay explains that NPC voice is off")
	model.boot_from_save = false
	_health({"ok": true, "dialogue_ready": true})

## X1-02 / C1-08: a dead service fails fast, is not the player's miss, and speaks 2D Chinese.
func _test_dialogue_service_faults() -> void:
	var closed := TCPServer.new()
	closed.listen(0, "127.0.0.1")
	var port := closed.get_local_port()
	closed.stop()
	var previous_url: String = ProjectSettings.get_setting("stranger_cloud/base_url", "")
	ProjectSettings.set_setting("stranger_cloud/enabled", true)
	ProjectSettings.set_setting("stranger_cloud/base_url", "http://127.0.0.1:%d" % port)
	NpcDialogueService.request_override = Callable()
	model.cancel_activity()
	check(model.location == "plaza" and NpcDialogueService.begin_scenario("mira", "market_conversation", false), "Mira opening session starts")
	Dialogue.begin_generation("mira", "[NPC opens conversation]", false)
	NpcDialogueService.pending_transcript = "[NPC opens conversation]"
	NpcDialogueService.current_turn_is_opening = true
	model._preparing_opening = true
	# Desktop SSE path: the raw HTTPClient dials the closed port.
	check(NpcDialogueService._begin_dialogue_stream(PackedStringArray(["Content-Type: application/json"]), "{}") == OK, "Stream dials the closed port")
	NpcDialogueService._streaming_response = true
	NpcDialogueService.set_process(true)
	toasts.clear()
	var started := Time.get_ticks_msec()
	while NpcDialogueService.has_active_session() and Time.get_ticks_msec() - started < 5000:
		await get_tree().process_frame
	check(not NpcDialogueService.has_active_session() and Time.get_ticks_msec() - started < 5000, "STATUS_CANT_CONNECT fails the opening at once instead of after 90 s")
	check(screen.dialogue_text.text == "Welcome, stranger." and not model._preparing_opening, "The failed opening falls back to Mira's authored line")
	check(not toasts.is_empty() and _no_english(str(toasts.back()).replace("Mira", "")) and not str(toasts.back()).contains("这次回应"), "The opening failure is one Chinese note, not a 'this reply failed' toast")
	ProjectSettings.set_setting("stranger_cloud/enabled", false)
	ProjectSettings.set_setting("stranger_cloud/base_url", previous_url)
	NpcDialogueService.request_override = func(_url, _headers, _method, body):
		requests.append(JSON.parse_string(body))
		return OK
	model.boot_from_save = true
	model.travel("neighbor")
	requests.clear()
	model.travel("plaza")
	check(requests.is_empty() and screen.dialogue_text.text == "Welcome, stranger." and not model._preparing_opening, "A failed opening is not re-requested on every arrival that day")
	NpcDialogueService.request_override = func(_url, _headers, _method, _body): return ERR_CANT_CONNECT
	toasts.clear()
	model.talk()
	check(screen.dialogue_text.text == "Welcome, stranger." and str(toasts.back()).contains("在线问候") and not str(toasts.back()).contains("不是你说得不好") and not model._preparing_opening, "Greeting Mira while the request cannot even start falls back to her authored line")
	NpcDialogueService.request_override = func(_url, _headers, _method, body):
		requests.append(JSON.parse_string(body))
		return OK
	model.boot_from_save = false
	model.travel("food")
	NpcDialogueService.begin_scenario("tavi", "food_counter", false)
	NpcDialogueService.reject_empty_transcript("VOICE_REASON_SERVICE_UNAVAILABLE")
	check(Dialogue.misses_for("tavi") == 0, "A service outage is not counted as the player's miss")
	NpcDialogueService.reject_empty_transcript("VOICE_REASON_CLARIFY")
	check(Dialogue.misses_for("tavi") == 1, "An unclear recording still counts as a free, countable miss")
	toasts.clear()
	NpcDialogueService.dialogue_failed.emit("tavi", "VOICE_REASON_DIALOGUE_TIMEOUT")
	var said: String = str(toasts.back()) + screen.order_detail.text
	check(not said.contains("米拉") and not said.contains("Mira") and not said.contains("靠近") and not said.contains("连接") and _no_english(said), "Timeout copy is 2D Chinese, not 'approach Mira again'")
	model.cancel_activity()
	SpeechAdapter.last_unavailable_reason = ""

## C2-03: a missing model score is never replaced by a fabricated value.
func _test_missing_idiomaticity() -> void:
	NpcDialogueService.begin_scenario("tavi", "food_counter", false)
	Dialogue.begin_generation("tavi", "One burger, please.")
	NpcDialogueService.pending_pronunciation = 70.0
	NpcDialogueService.current_turn_is_opening = false
	NpcDialogueService._streaming_response = true
	NpcDialogueService._apply_speaking({"reply_id": "reply-no-idiom", "npc_id": "tavi", "text": "Sure. Anything else?", "speech_act": "offer_choice", "gate": {"accepted": true, "violations": []}})
	NpcDialogueService._apply_score({"reply_id": "reply-no-idiom", "npc_id": "tavi", "speech_act": "offer_choice", "next_state": "awaiting_follow_up",
		"source": "gemini", "player_turn": {"idiomaticity": null, "idiomaticity_source": "unavailable", "transaction_complete": false}})
	check(NpcDialogueService._score_received, "A null idiomaticity is a valid, unavailable score")
	check(is_equal_approx(NpcScenarioRunner.running_score("tavi"), 70.0), "The turn counts on pronunciation alone (running=%.1f)" % NpcScenarioRunner.running_score("tavi"))
	var turns: Array = NpcScenarioRunner.sessions["tavi"].turns
	check(turns.size() == 1 and float(turns[0].idiomaticity) < 0.0, "No idiomaticity value is invented for the turn")
	NpcDialogueService.cancel()
	NpcDialogueService.begin_scenario("tavi", "food_counter", false)
	Dialogue.begin_generation("tavi", "Burger.")
	NpcDialogueService.pending_pronunciation = -1.0
	NpcDialogueService._apply_speaking({"reply_id": "reply-no-evidence", "npc_id": "tavi", "text": "Sure. Anything else?", "speech_act": "offer_choice", "gate": {"accepted": true, "violations": []}})
	NpcDialogueService._apply_score({"reply_id": "reply-no-evidence", "npc_id": "tavi", "speech_act": "offer_choice", "next_state": "awaiting_follow_up",
		"player_turn": {"idiomaticity": null, "idiomaticity_source": "unavailable", "transaction_complete": false}})
	check(NpcScenarioRunner.running_score("tavi") < 0.0, "Without pronunciation or idiomaticity no turn score is recorded")
	NpcDialogueService.cancel()
