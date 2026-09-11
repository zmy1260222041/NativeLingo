extends Node
## FR-46: 2D action boundary. The original domain owns all rewards and items.
signal scene_changed
signal line_changed(speaker: String, text: String)
signal feedback(text: String)
signal progression_changed
const Content := preload("res://scripts/novel/novel_content.gd")
const SAVE_PATH := "user://stranger_novel_save.json"
var location := "plaza"
var history: Array = []
var social_index := -1
var social_line := -1
var practice_word := ""
var boot_from_save := true
var novel_save_path := SAVE_PATH
var old_process := true
var old_save_path := ""
var _changing := false
var health_request: HTTPRequest
var voice_status := "尚未检查语音连接"
var _listening := false
var _replay: Dictionary = {}
var order_note: Dictionary = {}

func _ready() -> void:
	Content.load_daily_life()
	add_to_group("novel_world")
	old_process = GameState.is_processing()
	old_save_path = GameState.save_path
	GameState.set_process(false)
	if boot_from_save:
		GameState.save_path = novel_save_path if FileAccess.file_exists(novel_save_path) else old_save_path
		GameState.load_game()
		GameState.save_path = novel_save_path
		var state: Dictionary = GameState.presentation_state
		location = str(Content.place(str(state.get("location", "plaza"))).id)
		history = state.get("history", []).duplicate(true)
	GameState.onboarding_active = false
	GameState.set_interaction_time_frozen(false)
	Vocabulary.sync_from_game_state()
	GameState.message_requested.connect(_message)
	GameState.npc_line_presented.connect(func(npc, text):
		if npc == npc_id() and not _changing: say(npc, text))
	GameState.state_changed.connect(func(): progression_changed.emit())
	GameState.items_changed.connect(func(): progression_changed.emit())
	GameState.day_started.connect(_day_started)
	NpcDialogueService.scenario_opened.connect(_scenario_opened)
	NpcDialogueService.dialogue_ready.connect(_reply)
	NpcDialogueService.dialogue_failed.connect(_dialogue_failed)
	NpcDialogueService.service_turn_updated.connect(_service_turn_updated)
	NpcScenarioRunner.service_settled.connect(_service_settled)
	Dialogue.session_changed.connect(func(_npc, _state, _line): progression_changed.emit())
	NpcDialogueService.player_turn_displayed.connect(func(_npc, text): say("you", text))
	SpeechAdapter.recognition_finished.connect(_recognition)
	SpeechAdapter.word_score_finished.connect(_word_score)
	NpcVoice.line_audio_finished.connect(_listening_finished)
	NpcVoice.line_audio_failed.connect(_listening_failed)
	if boot_from_save:
		_check_local_service()

func start() -> void:
	scene_changed.emit()
	say(npc_id(), str(Content.place(location).opening))
	if GameState.game_finished:
		feedback.emit("三夜已度过。你已不再是陌生人。可在设置中开始新旅程。")

func npc_id() -> String:
	return str(Content.place(location).npc)

func travel(destination: String) -> bool:
	if GameState.game_finished or destination == location:
		return false
	var selected := Content.place(destination)
	if selected.id != destination:
		return false
	cancel_activity()
	location = destination
	advance_time(6.0)
	save()
	scene_changed.emit()
	say(npc_id(), str(selected.opening))
	return true

func cancel_activity() -> void:
	_changing = true
	SpeechAdapter.cancel_recording()
	SpeechAdapter.clear_recovery()
	NpcDialogueService.cancel()
	NpcVoice.stop_all()
	_listening = false
	_replay.clear()
	order_note.clear()
	Dialogue.finish_word_practice()
	practice_word = ""
	social_index = -1
	social_line = -1
	GameState.set_interaction_time_frozen(false)
	_changing = false

func advance_time(seconds: float) -> void:
	# All reading is free. Only explicit travel/wait commands advance survival.
	var remaining := seconds
	while remaining > 0.0 and not GameState.game_finished:
		var step := minf(remaining, 1.0)
		GameState._process(step)
		remaining -= step
	progression_changed.emit()

func greet() -> void:
	if npc_id().is_empty() or GameState.game_finished:
		return
	cancel_activity()
	var channel := "gesture_fallback" if SpeechAdapter.runtime_speech_unavailable() else "gesture"
	GameState.interact("npc", npc_id(), channel)
	save()

func talk() -> void:
	if npc_id().is_empty() or GameState.game_finished:
		return
	if social_index >= 0 or not practice_word.is_empty():
		cancel_activity()
		scene_changed.emit()
	if GameState.can_start_service_dialogue(npc_id()):
		NpcDialogueService.begin_scenario(npc_id(), GameState.service_scenario_for(npc_id()))
	else:
		GameState.interact("npc", npc_id(), "action")
		feedback.emit("当前语音不可用，可点「手势」继续交流。" if SpeechAdapter.runtime_speech_unavailable() else "点「录音」，用英语向 %s 问好；再点一次结束。" % npc_id().capitalize())

func record() -> void:
	if SpeechAdapter.is_recording():
		SpeechAdapter.finish_recording()
		return
	if GameState.game_finished or npc_id().is_empty():
		return
	if social_index >= 0:
		cancel_activity()
	if _listening or not NpcVoice.playing_line_id.is_empty() or not NpcVoice.pending_line_id.is_empty():
		feedback.emit("先听完示范，再开口。")
		return
	if not practice_word.is_empty():
		SpeechAdapter.start_word_recording(practice_word)
		return
	if Dialogue.state_for(npc_id()) in ["generating", "speaking"]:
		feedback.emit("等对方说完，再继续。")
		return
	if SpeechAdapter.cloud_mode_enabled() and not SpeechAdapter.cloud_activated():
		feedback.emit("可在设置中激活语音；现在也可以用手势继续生活。")
		return
	if GameState.can_start_service_dialogue(npc_id()) and not NpcDialogueService.is_session_active_for(npc_id()):
		talk()
		if _listening:
			feedback.emit("先听对方招呼，再点录音回答。")
			return
	if SpeechAdapter.start_recording(npc_id()):
		order_note.clear()
		NpcDialogueService.prewarm(npc_id())
	else:
		feedback.emit("暂时无法录音。可以免费重试，或用手势交流。")

func _recognition(target: String, accepted: bool, transcript: String, reason: String, expression: Dictionary) -> void:
	if _changing or target != npc_id() or GameState.game_finished:
		return
	if transcript.is_empty():
		NpcDialogueService.reject_empty_transcript(reason)
		feedback.emit("没有听清，点录音再试一次。练习不消耗时间。")
		return
	if GameState.can_start_service_dialogue(target) and NpcDialogueService.enabled():
		if not NpcDialogueService.is_session_active_for(target):
			NpcDialogueService.begin_scenario(target, GameState.service_scenario_for(target))
		NpcDialogueService.submit_transcript(transcript, {"pronunciation": float(expression.get("pronunciation", expression.get("score", -1.0)))})
	elif accepted:
		say("you", transcript)
		GameState.interact("npc", target, "voice", expression)
		save()
	else:
		feedback.emit("没关系，再试一次。")

func _scenario_opened(npc: String, _scenario: String, text: String) -> void:
	if npc == npc_id():
		say(npc, text)
		_listen(npc, "service_entry")

func _reply(npc: String, reply_id: String, text: String) -> void:
	if npc == npc_id() and not _changing:
		say(npc, text)
		_replay = {"npc": npc, "reply": reply_id}

func _dialogue_failed(npc: String, reason: String) -> void:
	if npc == npc_id() and not _changing:
		order_note = {"title": "这次还没有交付物品", "detail": "回应或语音未能完成。可以免费重试；语音不可用时，也能用手势领取。"}
		if reason == "VOICE_REASON_CLARIFY":
			feedback.emit("没有听清，点录音再试一次。")
		else:
			feedback.emit("连接暂时中断。可以重试，或用手势领取最低份量。 " + tr(reason))
		progression_changed.emit()

func _service_turn_updated(npc: String, detail: Dictionary) -> void:
	if npc != npc_id() or _changing: return
	var item := _order_item_name(str(detail.item))
	if detail.confirmed:
		order_note = {"title": "店员已确认" + item, "detail": "听完这句回应，物品就会放到柜台。再选择现在使用或装进行囊。"}
	elif detail.off_inventory:
		order_note = {"title": "这家店没有你说的那件物品", "detail": "打开「菜单 / 柜台」看看能买到什么，再说出你想要的商品。"}
	else:
		order_note = {"title": "还在确认这份点单", "detail": ("已听到「%s」。回答店员的问题即可，不必重新打招呼。" % item) if not item.is_empty() else "请说出具体商品名。比如 “A burger, please.”，也可以只说 “Burger.”。"}
	progression_changed.emit()

func _service_settled(npc: String, detail: Dictionary) -> void:
	if npc != npc_id() or _changing: return
	if detail.outcome == "success":
		order_note.clear()
		save()
	elif detail.confirmed and float(detail.score) < GameState.SCORE_SPARSE_MIN:
		order_note = {"title": "这次还没能确认点单 · %d 分" % roundi(detail.score), "detail": "沟通得分达到 40 分才能领取。这次没有消耗物品，可以免费再说一次商品名。"}
		feedback.emit(str(order_note.title) + "。" + str(order_note.detail))
	else:
		order_note = {"title": "这次还没有交付物品", "detail": "可以重新说出想要的商品，或打开柜台查看已经备好的物品。"}
	progression_changed.emit()

func _order_item_name(alias: String) -> String:
	var id: String = alias if GameState.items.definitions.has(alias) else GameState.items.resolve_item(alias)
	return GameState.items.Catalog.label(GameState.items.definitions[id].name) if not id.is_empty() else ""

func order_guidance() -> Dictionary:
	if social_index >= 0 or not practice_word.is_empty() or GameState.game_finished or not GameState.can_start_service_dialogue(npc_id()): return {}
	var waiting: Array = visible_items("counter")
	if not waiting.is_empty():
		var titles: Array[String] = []
		for group in item_groups("counter"):
			titles.append("%s ×%d" % [_order_item_name(str(group.record.item_id)), group.ids.size()])
		var summary: String = titles[0] if titles.size() == 1 else "%s 等 %d 件" % [titles[0], waiting.size()]
		return {"title": "已备好 · " + summary, "detail": "点「领取」打开柜台，选择现在使用或装进行囊。领取前，物品会一直留在这里。"}
	if SpeechAdapter.is_recording(): return {"title": "正在听你说", "detail": "说完后，再点一次「结束录音」。不用完整句式，说清想要的商品就好。"}
	var state: String = Dialogue.state_for(npc_id())
	if state == "generating" or SpeechAdapter.is_interaction_active(): return {"title": "正在听清并确认你的话", "detail": "稍等店员回应。这时不用再录一次，确认后会提示你领取。"}
	if state == "speaking" or _listening: return {"title": "听听店员的回应", "detail": "对方说完后，继续回答或领取物品。还没有物品放到柜台。"}
	if not order_note.is_empty(): return order_note
	if SpeechAdapter.runtime_speech_unavailable(): return {"title": "语音暂时不可用，也能继续生活", "detail": "点「手势领取」获得最低份量，再到柜台使用或装包。也可以在设置中重试语音。"}
	var example: String = {"tavi": "A burger, please.", "ori": "Water, please.", "vesh": "A blanket, please."}.get(npc_id(), "")
	return {"title": "想要哪一样，告诉店员就好", "detail": "点「录音」说 “%s” 等自然表达。\n店员确认后，到柜台使用或装包。" % example}

func _message(text: String, _tone: String) -> void:
	if _changing:
		return
	# The old domain emits localized NPC lines and system feedback separately.
	feedback.emit(text.replace("靠近物品", "打开柜台").replace("走近", "前往"))

func say(speaker: String, text: String) -> void:
	history.append({"speaker": speaker, "text": text, "day": GameState.day})
	if history.size() > 160:
		history.pop_front()
	line_changed.emit(speaker, text)

func play_social(index: int) -> bool:
	if index < 0 or index >= Content.SOCIAL.size() or GameState.game_finished:
		return false
	cancel_activity()
	social_index = index
	social_line = -1
	scene_changed.emit()
	feedback.emit(str(Content.SOCIAL[index].hint))
	return next_social()

func next_social() -> bool:
	if social_index < 0:
		return false
	social_line += 1
	var scene: Dictionary = Content.SOCIAL[social_index]
	var lines: Array = scene.lines
	if social_line >= lines.size():
		cancel_activity()
		scene_changed.emit()
		say("", "「%s」听完了。下次遇到类似情境，可以试着说：\n%s" % [scene.title, scene.phrase])
		save()
		return false
	var line: Array = lines[social_line]
	NpcVoice.stop_all()
	say(str(line[0]), str(line[2]))
	for word in Content.SOCIAL[social_index].words:
		if str(word) in str(line[2]).to_lower().replace(".", "").replace("?", "").replace(",", "").split(" "):
			Vocabulary.observe_word(str(word))
	_listen(str(line[0]), str(line[1]))
	return true

func begin_practice(word: String) -> void:
	if not _practice_words().has(word):
		return
	cancel_activity()
	practice_word = word
	scene_changed.emit()
	Vocabulary.observe_word(word)
	say(npc_id(), word)
	feedback.emit("先听示范，再点「录音」说出这个词，点第二次结束。可以重听，练习不消耗时间。")
	_listen(npc_id(), "word_practice_model", [word])

func _word_score(word: String, accepted: bool, expression: Dictionary, _reason: String) -> void:
	if _changing or word != practice_word:
		return
	if accepted and Vocabulary.record_word_spoken(word, float(expression.get("score", 0.0))):
		feedback.emit("你说出了「%s」。在之后的真实对话里用用它吧。" % word)
	else:
		feedback.emit("听一听，再试一次。没有惩罚。")
	save()
	progression_changed.emit()

func visible_items(mode: String) -> Array:
	var result: Array = []
	for record in GameState.items.records():
		if mode == "bag" and record.state == "carried":
			result.append(record)
		elif mode == "counter" and record.state == "counter" and record.location == npc_id():
			result.append(record)
		elif mode == "home" and location == "home" and (record.state == "carried" or (record.location.begins_with("home_") and record.state in ["placed", "active", "storage"])):
			result.append(record)
	return result

func item_groups(mode: String, category := "all") -> Array:
	var grouped := {}
	for record in visible_items(mode):
		var definition: Dictionary = GameState.items.definitions[record.item_id]
		var family: String = definition.category if definition.category in ["food", "drink"] else "home"
		if category != "all" and category != family: continue
		# Keep partly used canteens and different storage states separate.
		var key := "%s|%s|%s|%d" % [record.item_id, record.state, record.location, record.uses]
		if not grouped.has(key): grouped[key] = {"key": key, "record": record, "ids": []}
		grouped[key].ids.append(record.id)
	return grouped.values()

func item_description(id: String) -> String:
	var definition: Dictionary = GameState.items.definitions[id]
	match id:
		"drink_canteen": return "路上慢慢喝。水壶可以喝两次，用过一次后仍能留在行囊里。"
		"drink_bottled_water": return "给自己补充一点精力。也可以带去罗文的门廊，在交流时送给他。"
		"home_blanket": return "铺在小屋床上，每次入睡时额外恢复 20 点温暖。收起后不再生效。"
		"component_alloy_part": return "带回小屋，先放到维修位再安装。两件零件修好加热器，往后的日子会暖一些。"
		"home_batteries": return "带回小屋，放到电力位再使用，恢复精力。每件电池使用一次。"
		"drink_coffee": return "喝杯热咖啡，暖和一点，也提提神。"
		_:
			return "饿的时候吃一份，也可以留作下一餐。每次只吃一件。" if definition.category == "food" else "休息一下，喝点东西补充精力。每次只喝一件。"

func validate_item_context(context: Dictionary) -> bool:
	var target := str(context.get("location", "player"))
	return not GameState.game_finished and not SpeechAdapter.is_interaction_active() and not NpcDialogueService.has_active_session() and (target == "player" or (target == npc_id() and not target.is_empty()) or (location == "home" and target.begins_with("home_")))

func use_item(action: String, id: String, allow_waste := false) -> Dictionary:
	if not GameState.items.instances.has(id):
		return {"ok": false, "reason": "missing"}
	var record: Dictionary = GameState.items.instances[id]
	var definition: Dictionary = GameState.items.definitions[record.item_id]
	var target: String = record.location if record.state != "carried" else "player"
	if action in ["place", "use_home", "deactivate", "reclaim"]:
		target = str(definition.home_slot)
	if action == "store":
		target = "home_storage"
		action = "place"
	var context := {"safe": true, "location": target, "at_home": location == "home", "revision": GameState.items.revision}
	if not validate_item_context(context):
		return {"ok": false, "reason": "location"}
	var result: Dictionary = GameState.item_command(action, [id], context, allow_waste)
	if result.get("ok", false):
		save()
	return result

func wait_until_evening() -> void:
	if location != "home" or GameState.game_finished:
		return
	cancel_activity()
	# Resting at home progresses the clock, with a reduced but real need cost.
	var seconds := maxf(0.0, (GameState.SLEEP_HOUR - GameState.DAY_START_HOUR) / (GameState.DAY_END_HOUR - GameState.DAY_START_HOUR) * GameState.DAY_DURATION - GameState.day_time + 0.1)
	advance_time(seconds * 0.2)
	GameState.day_time += seconds * 0.8
	GameState.clock_changed.emit(GameState.day, int(GameState.day_time))
	feedback.emit("灯亮起来了。天色已晚，可以睡觉了。")
	save()
	progression_changed.emit()

func sleep() -> bool:
	if location != "home" or GameState.game_finished:
		return false
	cancel_activity()
	var previous: int = GameState.day
	GameState.interact("shelter", "shelter")
	save()
	return GameState.day != previous

func _day_started(day: int) -> void:
	scene_changed.emit()
	say("", "三夜过去，你开始记得每一个名字。欢迎回家。" if GameState.game_finished else "第 %d 天。新的一天，从一句问候开始。" % day)

func save() -> bool:
	GameState.presentation_state["location"] = location
	GameState.presentation_state["history"] = history
	return GameState.save_game()

func restart() -> void:
	cancel_activity()
	GameState.reset_run()
	location = "plaza"
	history.clear()
	save()
	start()

func _check_local_service() -> void:
	if SpeechAdapter.cloud_mode_enabled() or not SpeechAdapter.is_available():
		return
	if health_request != null:
		health_request.cancel_request()
		health_request.queue_free()
	health_request = HTTPRequest.new()
	health_request.timeout = 10.0
	add_child(health_request)
	voice_status = "正在检查语音连接…"
	health_request.request_completed.connect(_health_result)
	health_request.request("http://127.0.0.1:17831/health?refresh=1")

func _health_result(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var data = JSON.parse_string(body.get_string_from_utf8())
	if result != HTTPRequest.RESULT_SUCCESS or code != 200 or not data is Dictionary:
		voice_status = "本地语音服务未连接。启动服务后可重新检查。"
		SpeechAdapter.mark_runtime_unavailable("VOICE_REASON_SERVICE_UNAVAILABLE")
	elif not bool(data.get("dialogue_ready", false)):
		var reason := str(data.get("dialogue_reason", "not_checked"))
		voice_status = "录音服务已连接；在线交谈暂不可用。" + ("服务商拒绝了当前地区的请求。" if reason == "region_unsupported" else "请检查模型服务配置后重试。")
		SpeechAdapter.mark_runtime_unavailable("VOICE_REASON_SERVICE_UNAVAILABLE")
	else:
		voice_status = "本地语音和对话模型已连接。可以进入商店开口交谈。"
		SpeechAdapter.last_unavailable_reason = ""
	feedback.emit(voice_status)
	progression_changed.emit()

func _practice_words() -> Array:
	var words: Array = []
	for entry in Content.SOCIAL:
		for word in entry.words:
			if not words.has(word): words.append(word)
	return words

func _listen(npc: String, line: String, options: Array = []) -> void:
	_replay = {"npc": npc, "line": line, "options": options.duplicate()}
	_listening = true
	if not NpcVoice.request_line(npc, line, "", "wav", options):
		_listening = false

func listen_again() -> void:
	if _replay.is_empty() or SpeechAdapter.is_interaction_active() or Dialogue.state_for(npc_id()) in ["generating", "speaking"]:
		return
	NpcVoice.stop_all()
	_listening = true
	if _replay.has("reply"):
		if not NpcVoice.request_reply(str(_replay.npc), str(_replay.reply)): _listening = false
	else:
		_listen(str(_replay.npc), str(_replay.line), _replay.options)

func _listening_finished(npc: String, line: String) -> void:
	if npc != str(_replay.get("npc", "")) or line != str(_replay.get("line", _replay.get("reply", ""))):
		return
	_listening = false
	progression_changed.emit()
	if not practice_word.is_empty():
		feedback.emit("轮到你了。点录音说出「%s」，再点一次结束；也可以重听示范。" % practice_word)

func _listening_failed(npc: String, line: String, _reason: String) -> void:
	if npc != str(_replay.get("npc", "")) or line != str(_replay.get("line", _replay.get("reply", ""))):
		return
	_listening = false
	progression_changed.emit()
	feedback.emit("示范语音暂时无法播放，可以点重听再试。")

func _exit_tree() -> void:
	cancel_activity()
	GameState.set_process(old_process)
	GameState.save_path = old_save_path

func pack_counter() -> Dictionary:
	var ids: Array = []
	for record in visible_items("counter"):
		ids.append(record.id)
	var context := {"safe": true, "location": npc_id(), "revision": GameState.items.revision}
	var result: Dictionary = GameState.item_command("pack", ids, context)
	if result.get("ok", false): save()
	return result
