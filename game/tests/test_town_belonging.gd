extends Node
var failures := 0
var serial := 0
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
	await _test_spoken_greeting(model)
	await _test_text_only_replies(model)
	screen.queue_free()
	await get_tree().process_frame
	print("TownBelongingTest failures=", failures)
	get_tree().quit(1 if failures else 0)

## C1-01 / X1-06: the first spoken exchange with Mira whose reply fully played is
## the voice greeting. An opening, an unclear turn, an unplayed reply or a gesture
## while voice works earn nothing, and the model never sets the reward.
func _test_spoken_greeting(model: Node) -> void:
	GameState.reset_run()
	GameState.presentation_state.clear()
	SpeechAdapter.availability_override = true
	SpeechAdapter.last_unavailable_reason = ""
	NpcVoice.availability_override = false
	NpcDialogueService.request_override = func(_url, _headers, _method, _body): return OK
	model.cancel_activity()
	model.location = "plaza"
	model.greet()
	check(GameState.relationships.mira == 0 and not GameState.completed_steps.has("greet_mira"), "A gesture while voice works earns no greeting")
	check(NpcDialogueService.start_social_opening("mira", "market_conversation", GameState.day), "Mira can open the conversation")
	await _play_reply("mira", "Hi, I'm Mira. Take your time settling in.")
	check(GameState.relationships.mira == 0 and model.social_openings.has("mira:1"), "Mira's own opening is not the player's greeting")
	model._recognition("mira", false, "hi", "VOICE_REASON_SCORE_LOW", {"pronunciation": 30.0, "score": 30.0})
	await _play_reply("mira", "Hi there. Tavi runs the food stall if you get hungry.")
	check(GameState.presentation_state.town_contacts.mira.completed_exchanges == 1 and GameState.relationships.mira == 0, "An unclear turn below the floor completes the exchange but earns nothing")
	model._recognition("mira", true, "Hi Mira, I just arrived.", "", {"pronunciation": 85.0, "score": 85.0})
	_inject_reply("mira", "Welcome. Ori keeps water at the corner store.")
	model.cancel_activity()
	check(GameState.relationships.mira == 0 and GameState.presentation_state.town_contacts.mira.completed_exchanges == 1, "A reply cancelled before playback finished earns nothing")
	model._recognition("mira", true, "Hi Mira, I just arrived.", "", {"pronunciation": 85.0, "score": 85.0})
	check(GameState.relationships.mira == 0, "Recognition alone, before the reply plays, earns nothing")
	var toasts: Array = []
	var on_feedback := func(text): toasts.append(str(text))
	model.feedback.connect(on_feedback)
	await _play_reply("mira", "Welcome. Ori keeps water at the corner store.")
	model.feedback.disconnect(on_feedback)
	check(GameState.completed_steps.has("greet_mira") and GameState.relationships.mira == 2 and GameState.memories == ["mira：MEMORY_GREET_MIRA"], "The first clear spoken exchange earns the legacy greeting reward")
	check(toasts.any(func(text): return text.contains("Mira 记住了你的问候") and text.contains("信任 +2")), "FR-47: the greeting reward is named, not silent")
	model._recognition("mira", true, "Thanks, see you later.", "", {"pronunciation": 90.0, "score": 90.0})
	await _play_reply("mira", "See you around. Come back any time.")
	check(GameState.relationships.mira == 2 and GameState.memories.size() == 1, "Later exchanges do not repeat the greeting reward")
	NpcDialogueService.cancel()
	NpcDialogueService.request_override = Callable()
	SpeechAdapter.availability_override = null

## FR-46: with NPC voice off (/health tts_configured=false) and dialogue working,
## a validated reply settles once read, so exchanges, Mira's greeting and orders
## still count; a cancel during the reading pause still voids the reply.
func _test_text_only_replies(model: Node) -> void:
	GameState.reset_run()
	GameState.presentation_state.clear()
	SpeechAdapter.availability_override = true
	SpeechAdapter.last_unavailable_reason = ""
	NpcVoice.availability_override = false
	NpcDialogueService.request_override = func(_url, _headers, _method, _body): return OK
	model.cancel_activity()
	model.location = "plaza"
	model._health_result(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify({"ok": true, "dialogue_ready": true, "asr_ready": true, "tts_configured": false}).to_utf8_buffer())
	check(NpcDialogueService.text_only_replies and not SpeechAdapter.runtime_speech_unavailable(), "Health with NPC voice off switches replies to text without arming the gesture minimum")
	model._recognition("mira", true, "Hi Mira, I just arrived.", "", {"pronunciation": 82.0, "score": 82.0})
	_inject_reply("mira", "Welcome. Take your time here.")
	model.cancel_activity()
	await get_tree().create_timer(0.3).timeout
	check(GameState.relationships.mira == 0 and not GameState.presentation_state.get("town_contacts", {}).has("mira"), "A text reply cancelled before it was read earns nothing")
	model._recognition("mira", true, "Hi Mira, I just arrived.", "", {"pronunciation": 82.0, "score": 82.0})
	_inject_reply("mira", "Welcome. Take your time here.")
	check(model.history.back().text == "Welcome. Take your time here." and GameState.relationships.mira == 0, "The reply text shows at once and settles only after the reading pause")
	await _await_settled()
	check(GameState.completed_steps.has("greet_mira") and GameState.relationships.mira == 2, "Text-only: the first clear exchange still earns Mira's greeting")
	check(GameState.presentation_state.town_contacts.mira.completed_exchanges == 1 and GameState.journey_summary().spoken_with.has("mira"), "Text-only: the exchange counts, so the ending knows Mira")
	model.travel("food")
	check(NpcDialogueService.begin_scenario("tavi", "food_counter", false), "The counter session opens")
	model._recognition("tavi", true, "Can I get a burger, please?", "", {"pronunciation": 80.0, "score": 80.0})
	serial += 1
	var reply_id := "reply-town-%d" % serial
	NpcDialogueService._streaming_response = true
	NpcDialogueService._apply_speaking({"reply_id": reply_id, "npc_id": "tavi", "text": "You got it. I'll get you the burger now.", "speech_act": "confirm_order", "gate": {"accepted": true, "violations": []}, "source": "gemini"})
	NpcDialogueService._apply_score({"reply_id": reply_id, "npc_id": "tavi", "speech_act": "confirm_order", "next_state": "closed", "source": "gemini", "player_turn": {"idiomaticity": 90.0, "transaction_complete": true, "off_inventory": false, "spoken_delivery_confirmed": true, "requested_item": "burger", "confirmed_item": "burger"}})
	await _await_settled()
	check(model.visible_items("counter").size() >= 1 and not NpcDialogueService.has_active_session(), "Text-only: a confirmed order is delivered to the counter after the read (%d)" % model.visible_items("counter").size())
	model._health_result(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify({"ok": true, "dialogue_ready": true}).to_utf8_buffer())
	check(not NpcDialogueService.text_only_replies, "Voice back on: replies wait for their audio again")
	NpcDialogueService.cancel()
	NpcDialogueService.request_override = Callable()
	SpeechAdapter.availability_override = null

func _await_settled() -> void:
	for attempt in range(80):
		if NpcDialogueService.current_reply_id.is_empty(): break
		await get_tree().create_timer(0.1).timeout
	await get_tree().process_frame

## Injects one validated reply (speaking + score) for the active turn.
func _inject_reply(npc: String, text: String) -> String:
	serial += 1
	var reply_id := "reply-town-%d" % serial
	NpcDialogueService._streaming_response = true
	NpcDialogueService._apply_speaking({"reply_id": reply_id, "npc_id": npc, "text": text, "speech_act": "acknowledge_need", "gate": {"accepted": true, "violations": []}, "source": "gemini"})
	NpcDialogueService._apply_score({"reply_id": reply_id, "npc_id": npc, "speech_act": "acknowledge_need", "next_state": "awaiting_follow_up", "source": "gemini", "player_turn": {"idiomaticity": 85.0}})
	return reply_id

## Injects one validated reply and plays its audio to the end.
func _play_reply(npc: String, text: String) -> void:
	var reply_id := _inject_reply(npc, text)
	var pcm := PackedByteArray()
	pcm.resize(9600)
	pcm.fill(0)
	for event in [
		["audio_begin", {"reply_id": reply_id, "npc_id": npc, "sample_rate": 24000}],
		["audio", {"reply_id": reply_id, "npc_id": npc, "seq": 0, "pcm_b64": Marshalls.raw_to_base64(pcm)}],
		["audio_end", {"reply_id": reply_id, "npc_id": npc, "bytes": pcm.size()}],
	]:
		NpcDialogueService._handle_sse_block("event: " + event[0] + "\ndata: " + JSON.stringify(event[1]))
	for attempt in range(30):
		if NpcVoice.playing_line_id.is_empty() and NpcDialogueService.current_reply_id.is_empty(): break
		await get_tree().create_timer(0.1).timeout
	await get_tree().process_frame
