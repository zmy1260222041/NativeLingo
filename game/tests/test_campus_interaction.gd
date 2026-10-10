extends Node
## Regression cases reproduced during the campus art playtest.
var failures := 0
var assertions := 0
var screen: Control
var model: Node

func check(ok: bool, message: String) -> void:
	assertions += 1
	if not ok:
		failures += 1
		push_error(message)

func _ready() -> void:
	TranslationServer.set_locale("zh_CN")
	GameState.persistence_enabled = false
	SpeechAdapter.availability_override = false
	NpcVoice.availability_override = false
	screen = preload("res://scenes/Campus.tscn").instantiate()
	screen.boot_from_save = false
	add_child(screen)
	model = screen.model
	await get_tree().process_frame
	check(screen.transcript.selection_enabled and screen.transcript.focus_mode == Control.FOCUS_NONE and screen.situation.focus_mode == Control.FOCUS_NONE, "P2-02: selectable campus text is never a hidden Tab stop")
	screen._inventory("bag")
	var guidance: Dictionary = model.inventory_guidance()
	check(guidance.links.size() == 1 and guidance.links[0][1] == "dining", "Campus has one accurate dining-counter supply link")
	check(not guidance.text.contains("便利店"), "Campus inventory does not advertise the town store")
	check(not model.item_description("drink_bottled_water").contains("罗文"), "Campus water does not reference a town-only character")
	screen.inventory_view.travel_requested.emit("dining")
	await get_tree().process_frame
	check(model.service_mode and model.location == "dining" and model.npc_id() == "tavi", "Supply link opens the real service counter rather than a social scene")
	check(not screen.modal.visible, "Supply travel dismisses the inventory modal")
	check(screen.send_button.disabled and not screen.input.editable, "Voice-only counter explains its input mode without accepting discarded typed text")
	model.greet()
	await get_tree().process_frame
	var items: Array = model.visible_items("counter")
	check(items.size() == 1, "Offline minimum item remains available at the campus counter")
	if not items.is_empty():
		var id: String = items[0].id
		GameState.food = 98
		GameState.warmth = 100
		GameState.energy = 100
		screen._inventory("counter")
		screen.inventory_view.action_requested.emit("consume", id, false)
		check(not screen.inventory_view.confirmation.is_empty(), "Partial-effect consumption exposes the confirmation that used to be ignored")
		check(screen.inventory_view.notice_label.visible, "Failure/confirmation feedback is visible inside the modal")
		check(GameState.food == 98 and model.visible_items("counter").size() == 1, "Requesting confirmation does not consume the item")
		await capture_inventory("inventory-confirmation")
		for button in screen.inventory_view.action_buttons:
			if button.text == "先留着": button.pressed.emit(); break
		check(screen.inventory_view.confirmation.is_empty() and model.visible_items("counter").size() == 1, "Keep-for-later cancels without consuming")
		screen.inventory_view.action_requested.emit("consume", id, false)
		screen.inventory_view._confirm()
		check(GameState.food == 100 and model.visible_items("counter").is_empty(), "Explicit confirmation consumes exactly one item and applies its capped effect")
		check(screen.inventory_view.notice_label.text.contains("已使用"), "Successful item use has a visible receipt")
		await capture_inventory("inventory-used")
		screen.inventory_view.action_requested.emit("consume", id, true)
		check(model.visible_items("counter").is_empty(), "Repeated stale item action cannot consume or mint another item")
	screen._close_modal()
	model.travel("class")
	model.select_scene("class_project_roles")
	model.travel("home")
	var turn_before: int = model.turn_serial
	model.submit_text("Are you still there?")
	check(model.pending_turn.is_empty() and model.turn_serial == turn_before, "Home cannot send to participants from the previous campus scene")
	check(screen.send_button.disabled and not screen.input.editable and screen.record_button.disabled, "Home composer does not promise unavailable conversation")
	check(not screen.scene_picker.visible and screen.visual.people.is_empty(), "Home does not expose remote scenario selection or portraits")
	screen._scenarios()
	check(not screen.modal.visible, "Home scenario picker cannot open even via a queued callback")
	var score: int = model.campus.academic
	model.study("study")
	check(model.campus.academic == score + 10, "Home conversation guard preserves independent study")
	model.travel("club")
	check(not screen.send_button.disabled and screen.input.editable and screen.scene_picker.visible, "Leaving home restores normal campus conversation")
	model.travel("class")
	model.select_scene("class_project_roles")
	model.muted = true
	screen._line("you", "What would you each like to do?")
	screen._line("alex", "I can prepare the outline.")
	screen._line("jules", "I can gather the evidence.")
	check(screen.transcript.text.contains("I can prepare") and screen.transcript.text.contains("I can gather"), "Text-only group replies remain readable together")
	check(screen.transcript.text.contains("Alex") and screen.transcript.text.contains("Jules"), "Retained replies identify each speaker")
	if DisplayServer.get_name() != "headless":
		await get_tree().process_frame
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png("res://../docs/reviews/campus_art_2026-09-12/group-text-replies.png")
	screen._line("you", "What is next?")
	screen._line("alex", "Let us compare our notes.")
	check(not screen.transcript.text.contains("I can prepare") and screen.transcript.text.contains("compare our notes"), "A new player turn starts a fresh reply group")
	# A completed proactive opening is NPC history, not player practice.
	model.new_session()
	var practice_before: int = model.campus.practice_log.size()
	var social_before: float = model.campus.social
	model.pending_turn = "opening-regression"
	model.pending_text = "[NPC opens conversation]"
	model.pending_opening = true
	model._campus_complete({"turn_id": "opening-regression", "session_id": model.session, "scenario_id": model.scene_id, "source": "gemini"}, [{"speaker_id": "alex", "reply_to": "player", "text": "I like starting with an outline because it gives us something to question."}])
	check(model.exchange.size() == 1 and model.exchange[0].speaker_id == "alex", "Proactive opening persists only NPC speech")
	check(model.campus.practice_log.size() == practice_before and model.campus.social == social_before, "Listening to an opening cannot forge practice or social rewards")
	model.new_session()
	model.boot_from_save = true
	screen._open("Test panel")
	model._offer_opening()
	check(model.pending_turn.is_empty(), "An open modal suppresses proactive speech")
	screen._close_modal()
	model.boot_from_save = false
	_test_offline_honesty()
	screen.queue_free()
	await get_tree().process_frame
	print("CampusInteractionTest: %d assertions, %d failures" % [assertions, failures])
	get_tree().quit(1 if failures else 0)

## P3-10 / P3-11: campus failures name their real cause, and an offline campus
## says once, persistently, what still works.
func _test_offline_honesty() -> void:
	model.travel("class")
	model.select_scene("class_before_class")
	var target: String = "campus:" + model.npc_id()
	model._recognition(target, false, "", "VOICE_REASON_SERVICE_UNAVAILABLE", {})
	check(not screen.status.text.contains("没有听清") and screen.status.text.contains("这不是你说得不好"), "P3-11: a recognition outage is not worded as unclear speech: " + screen.status.text)
	model._recognition(target, false, "", "VOICE_REASON_TOO_SHORT", {})
	check(screen.status.text.contains("没有听清"), "P3-11: genuinely unclear speech still says so")
	model.practice_word = "class"
	model._word_score("class", false, {}, "VOICE_REASON_SERVICE_UNAVAILABLE")
	check(screen.status.text.contains("单词评分暂时不可用") and not screen.status.text.contains("小剧场"), "P3-10: campus word scoring outage points to nothing the campus lacks")
	model.cancel_activity()
	# /health: the model is down; campus wording, not the town's 听日常 / 角色会显示写好的台词.
	model._health_result(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify({"ok": true, "dialogue_ready": false, "tts_configured": false}).to_utf8_buffer())
	check(not model.voice_status.contains("听日常") and not model.voice_status.contains("写好的台词") and model.voice_status.contains("离线活动"), "P3-10: campus health status names campus options: " + model.voice_status)
	check(screen.status.text == model.voice_status, "P3-10: the health result is stated once in the status line")
	check(screen.connection_label.text != "语音与文字均可用" and screen.connection_label.text.contains("不可用"), "P3-10: the header no longer contradicts the status: " + screen.connection_label.text)
	check(screen.transcript.text.contains("离线活动") and screen.transcript.text.contains("校园生活照常继续"), "P3-10: the dialogue paper keeps a persistent offline note")
	model.boot_from_save = true
	model._offer_opening()
	check(model.pending_turn.is_empty() and not model.conversation.busy, "P3-10: no automatic opening request while online dialogue is known down")
	model.boot_from_save = false
	model.select_scene("class_notes")
	check(screen.transcript.text.contains("校园生活照常继续"), "P3-10: the offline note survives a scene change")
	# A turn that fails because the model is unreachable: honest, no text-mode advice.
	model._health_result(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify({"ok": true, "dialogue_ready": true, "tts_configured": true}).to_utf8_buffer())
	check(model.online_dialogue and screen.connection_label.text != "在线交谈暂不可用" and not screen.transcript.text.contains("校园生活照常继续"), "A healthy check restores the online invitation")
	model.pending_opening = true
	model.pending_turn = "opening-offline"
	model.conversation.failed.emit("service")
	check(not model.online_dialogue and screen.status.text.contains("在线交谈暂时连不上") and not screen.status.text.contains("切换文字") and not screen.status.text.contains("免费重试"), "P3-10: a failed opening promises no retry button or text mode: " + screen.status.text)
	check(screen.retry_button.visible == false and screen.connection_label.text == "在线交谈暂不可用", "P3-10: no retry control for an opening, header follows the failure")
	model.retry_text = "Could you say that again?"
	model.pending_turn = "reply-invalid"
	model.conversation.failed.emit("invalid")
	check(screen.status.text.contains("没有结算") and screen.status.text.contains("免费重试") and screen.retry_button.visible, "A rejected reply offers the real retry")
	model.pending_turn = "reply-audio"
	model.conversation.failed.emit("audio")
	check(screen.status.text.contains("角色语音") and screen.status.text.contains("仅文字"), "An unplayable reply is named as audio, with the text-only option")
	# Exhausted content repairs (422 campus_rejected) are a free retry, not an outage.
	model._health_result(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify({"ok": true, "dialogue_ready": true, "tts_configured": true}).to_utf8_buffer())
	SpeechAdapter.last_unavailable_reason = ""
	model.pending_turn = "reply-rejected"
	model.conversation.busy = true
	model.conversation._json_finished(HTTPRequest.RESULT_SUCCESS, 422, PackedStringArray(), JSON.stringify({"ok": false, "reason": "campus_rejected"}).to_utf8_buffer())
	check(model.online_dialogue and SpeechAdapter.last_unavailable_reason.is_empty() and screen.status.text.contains("免费重试"), "A 422 rejection keeps online dialogue on and arms no gesture minimum: " + screen.status.text)
	model.conversation.busy = true
	model.conversation.active_turn = "reply-rejected-sse"
	model.conversation.accept_event("error", {"turn_id": "reply-rejected-sse", "reason": "campus_rejected"})
	check(model.online_dialogue and SpeechAdapter.last_unavailable_reason.is_empty(), "A streamed campus_rejected error is a rejection, not an outage")
	# An unreachable check proves nothing about NPC voice; only an explicit tts_configured=false mutes replies.
	NpcVoice.availability_override = true
	model.muted = false
	model._health_result(HTTPRequest.RESULT_CANT_CONNECT, 0, PackedStringArray(), PackedByteArray())
	check(not model.replies_text_only(), "An unreachable /health does not mute campus replies for the rest of the session")
	model._health_result(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify({"ok": true, "dialogue_ready": true, "tts_configured": false}).to_utf8_buffer())
	check(model.replies_text_only(), "Health that says NPC voice is off keeps campus replies text-only")
	model._health_result(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), JSON.stringify({"ok": true, "dialogue_ready": true, "tts_configured": true}).to_utf8_buffer())
	NpcVoice.availability_override = false
	model.retry_text = ""
	model.open_counter()
	check(screen.situation.text.contains("手势领取") and screen.action_row.get_children().any(func(b): return b is Button and b.text.begins_with("手势领取")), "P3-10: the counter's offline card names the real 手势领取 button")
	model.travel("class")

func capture_inventory(name: String) -> void:
	if DisplayServer.get_name() == "headless": return
	await get_tree().process_frame
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	screen.modal.get_texture().get_image().save_png("res://../docs/reviews/campus_art_2026-09-12/" + name + ".png")
