extends "res://scripts/novel/novel_controller.gd"
const CampusState := preload("res://scripts/novel/campus_state.gd")
const CampusDialogue := preload("res://scripts/novel/campus_dialogue.gd")
const CAMPUS_SAVE := "user://stranger_campus_save.json"
const PLACES := {"class": "教学区", "study": "学习空间", "club": "社团中心", "dining": "餐饮区", "sports": "运动区", "home": "我的住处"}
var campus = CampusState.new()
var conversation: Node
var scene_id := "class_before_class"
var exchange: Array = []
var topic_summary := ""
var session := ""
var pending_text := ""
var pending_pronunciation := -1.0
var pending_voice := false
var pending_turn := ""
var meaningful_turns := 0
var turn_serial := 0
var practice_context := ""
var last_coaching: Array = []
var muted := false
var pending_opening := false
var service_mode := false
var save_valid := true
var retry_text := ""
var retry_voice := false
var retry_pronunciation := -1.0

func _ready() -> void:
	var restore_saved := boot_from_save
	boot_from_save = false
	novel_save_path = CAMPUS_SAVE if novel_save_path == SAVE_PATH else novel_save_path
	super._ready()
	GameState.reset_run()
	GameState.set_process(false)
	GameState.onboarding_active = false
	GameState.save_path = novel_save_path
	if restore_saved and FileAccess.file_exists(novel_save_path):
		save_valid = GameState.load_game()
		if save_valid:
			var saved: Dictionary = GameState.presentation_state.get("campus", {})
			save_valid = campus.restore(saved)
			history = GameState.presentation_state.get("history", []).duplicate(true)
			location = str(GameState.presentation_state.get("campus_location", "class"))
			scene_id = str(GameState.presentation_state.get("campus_scene", scene_id))
	else:
		location = "class"
	if not PLACES.has(location): location = "class"
	if campus.scenario(scene_id).is_empty(): scene_id = "class_before_class"
	GameState.presentation_state["chapter"] = "campus"
	GameState.game_finished = false
	GameState.vocabulary_tier = str(campus.profile.level)
	Vocabulary.sync_from_game_state()
	conversation = CampusDialogue.new()
	add_child(conversation)
	conversation.line_ready.connect(_campus_line)
	conversation.completed.connect(_campus_complete)
	conversation.failed.connect(func(text): pending_turn = ""; feedback.emit(text); progression_changed.emit())
	conversation.busy_changed.connect(func(): progression_changed.emit())
	boot_from_save = restore_saved
	if restore_saved: _check_local_service()

func start(_play_voice := true) -> void:
	var saved: Dictionary = campus.conversation
	if saved.get("scenario_id") == scene_id and int(saved.get("day", -1)) == GameState.day:
		exchange = saved.get("history", []).duplicate(true)
		topic_summary = str(saved.get("topic_summary", ""))
		session = str(saved.get("session_id", ""))
		meaningful_turns = int(saved.get("meaningful_turns", 0))
		turn_serial = int(saved.get("turn_serial", 0))
		practice_context = str(saved.get("practice_context", ""))
	else: new_session()
	scene_changed.emit()
	_offer_opening.call_deferred()
	if not save_valid: feedback.emit("校园存档无法读取，已停止自动保存以保护原文件。请先备份并检查存档。")

func npc_id() -> String:
	if service_mode: return "tavi"
	var scene := campus.scenario(scene_id)
	return str(scene.get("participants", [""])[0])

func scene() -> Dictionary:
	return campus.scenario(scene_id)

func new_session() -> void:
	exchange.clear()
	topic_summary = ""
	pending_text = ""
	pending_turn = ""
	meaningful_turns = 0
	retry_text = ""
	campus.conversation.clear()
	session = "campus-%d-%d" % [GameState.day, Time.get_ticks_usec()]

func select_scene(id: String) -> void:
	if campus.scenario(id).is_empty(): return
	cancel_activity()
	scene_id = id
	service_mode = false
	new_session()
	save()
	scene_changed.emit()
	_offer_opening.call_deferred()

func travel(destination: String) -> bool:
	if not PLACES.has(destination) or destination == location: return false
	cancel_activity()
	location = destination
	service_mode = false
	advance_hours(float(campus.catalog.tuning.get("travel_hours", 0.25)))
	var domain := "class" if destination == "study" else destination
	var choices: Array = campus.ranked_scenes(domain)
	if not choices.is_empty(): scene_id = str(choices[0].id)
	new_session()
	save()
	scene_changed.emit()
	_offer_opening.call_deferred()
	return true

func cancel_activity() -> void:
	if conversation != null: conversation.cancel()
	pending_turn = ""
	pending_text = ""
	super.cancel_activity()

func conversation_block_reason() -> String:
	if conversation != null and conversation.busy: return "正在回应"
	return super.conversation_block_reason()

func record() -> void:
	if not practice_word.is_empty() or service_mode:
		super.record()
		return
	if location == "home":
		feedback.emit("住处没有交流对象。可以练习单词，或去校园找人聊聊。")
		return
	if SpeechAdapter.is_recording(): SpeechAdapter.finish_recording(); return
	if not conversation_block_reason().is_empty(): return
	SpeechAdapter.start_recording("campus:" + npc_id())

func _recognition(target: String, accepted: bool, transcript: String, reason: String, expression: Dictionary) -> void:
	if service_mode: super._recognition(target, accepted, transcript, reason, expression); return
	if target != "campus:" + npc_id() or _changing: return
	if transcript.strip_edges().is_empty(): feedback.emit("没有听清，可以免费重试。"); return
	submit_text(transcript, true, float(expression.get("pronunciation", -1)))

func submit_text(text: String, voice := false, pronunciation := -1.0, opening := false) -> void:
	if location == "home":
		feedback.emit("住处没有交流对象。去校园选择一个情景，再开始交流。")
		return
	if not conversation_block_reason().is_empty() or text.strip_edges().is_empty(): return
	if service_mode:
		if not voice:
			feedback.emit("柜台购买仍使用录音成交；语音不可用时可领取最低份量。文字练习可在其它校园情景进行。")
		return
	if text.length() > 1000: feedback.emit("这次输入请控制在 1000 字符以内。"); return
	pending_opening = opening
	turn_serial += 1
	pending_turn = "%s:%d" % [session, turn_serial]
	pending_text = text.strip_edges()
	pending_pronunciation = pronunciation if voice else -1.0
	pending_voice = voice
	retry_text = "" if opening else pending_text
	retry_voice = voice
	retry_pronunciation = pending_pronunciation
	var card := scene()
	var relations := {}
	for id in card.participants: relations[id] = campus.relationship_for(id)
	var body := {"session_id": session, "turn_id": pending_turn, "turn_index": turn_serial - 1, "scenario_id": scene_id,
		"participants": card.participants, "transcript": pending_text, "history": exchange.slice(maxi(0, exchange.size() - 16)),
		"topic_summary": topic_summary, "practice_context": practice_context.left(400),
		"profile": campus.relevant_profile(card), "memories": campus.relevant_memories(card), "relationships": relations,
		"chain_context": campus.chain_context(card), "game_time": {"day": GameState.day, "hour": GameState.clock_hours()}}
	if card.has("base_scenario_id"):
		body["base_scenario_id"] = card.base_scenario_id
		body["practice_card"] = {"title": card.title, "trigger": card.trigger, "player_goal": card.player_goal}
	body["turn_kind"] = "opening" if opening else "reply"
	if not opening: say("you", pending_text)
	conversation.submit(body, muted or not NpcVoice.is_available())

func _campus_line(line: Dictionary) -> void:
	if line.get("turn_id") != pending_turn: return
	say(str(line.speaker_id), str(line.text))
	_replay = {"npc": line.speaker_id, "reply": line.reply_id}

func _campus_complete(receipt: Dictionary, lines: Array) -> void:
	if receipt.get("turn_id") != pending_turn or receipt.get("session_id") != session or receipt.get("scenario_id") != scene_id: return
	if receipt.get("source") not in ["gemini", "grok"] or lines.is_empty() or lines.size() > 2: return
	var speakers: Array = []
	for line in lines:
		if line.get("speaker_id") not in scene().participants or line.get("speaker_id") in speakers: return
		if line.get("reply_to") not in scene().participants + ["player", "group"]: return
		speakers.append(line.speaker_id)
	if pending_opening:
		for line in lines:
			exchange.append({"speaker_id": line.speaker_id, "reply_to": line.reply_to, "text": line.text})
		topic_summary = str(receipt.get("topic_summary", ""))
		pending_opening = false
		pending_text = ""
		pending_turn = ""
		retry_text = ""
		save()
		progression_changed.emit()
		return
	var text := pending_text
	exchange.append({"speaker_id": "player", "reply_to": "group", "text": text})
	var records: Array = [{"speaker_id": "player", "reply_to": "group", "text": text}]
	for line in lines:
		exchange.append({"speaker_id": line.speaker_id, "reply_to": line.reply_to, "text": line.text})
		records.append({"speaker_id": line.speaker_id, "reply_to": line.reply_to, "text": line.text})
	for record in records:
		record.merge({"day": GameState.day, "session_id": session, "scenario_id": scene_id})
		campus.dialogue_log.append(record)
	topic_summary = str(receipt.get("topic_summary", ""))
	if receipt.get("activity_candidate", {}).get("meaningful") == true: meaningful_turns += 1
	campus.settle_conversation(scene_id, GameState.day, exchange, receipt)
	campus.remember_exchange(scene_id, GameState.day, text, lines, receipt)
	last_coaching = receipt.get("coaching", [])
	var log := {"scenario": scene_id, "day": GameState.day, "text": text, "coaching": last_coaching, "mode": "voice" if pending_voice else "text"}
	if pending_pronunciation >= 0: log["pronunciation"] = pending_pronunciation
	campus.practice_log.append(log)
	if pending_voice: Vocabulary.record_words_used_from_text(text)
	exchange = exchange.slice(maxi(0, exchange.size() - 16))
	pending_text = ""
	pending_turn = ""
	retry_text = ""
	if receipt.get("closed") == true: feedback.emit("这段交谈自然结束了。可以选择下一件事，或开始新的对话。")
	save()
	progression_changed.emit()

func retry_last() -> void:
	if retry_text.is_empty(): return
	submit_text(retry_text, retry_voice, retry_pronunciation)

func advance_hours(hours: float, resting := false) -> void:
	var available := maxf(0, 22.0 - GameState.clock_hours())
	var elapsed := minf(maxf(hours, 0), available)
	var extra := campus.advance_social(elapsed)
	var seconds := elapsed / 14.0 * GameState.DAY_DURATION
	var original_time: float = GameState.day_time
	super.advance_time(seconds * (0.2 if resting else 1.0))
	GameState.day_time = minf(GameState.DAY_DURATION, original_time + seconds)
	GameState.energy = maxf(0, GameState.energy - extra)
	if GameState.energy <= 0: GameState.faint()
	GameState.state_changed.emit()

func study(kind: String) -> void:
	if kind == "class" and location != "class": return
	if kind == "study" and location not in ["study", "home"]: return
	if GameState.clock_hours() > 21: feedback.emit("今天已晚，先休息，明天继续。"); return
	cancel_activity()
	if campus.complete_study(kind, GameState.day):
		campus.record_schedule(GameState.day, GameState.clock_hours(), kind, "课堂活动" if kind == "class" else "自主学习")
		advance_hours(float(campus.catalog.tuning.get("activity_hours", 1)))
		feedback.emit("学习活动已完成 · 本周学业 +10。按完成度累计，不评口音或专业知识。")
	else: feedback.emit("今天这项学习已完成，或本周该类五次已完成。可以自由练习，不重复计分。")
	save()
	progression_changed.emit()

func joint_activity(offline := false) -> void:
	if GameState.clock_hours() > 21: feedback.emit("今天已晚，先休息。"); return
	if not conversation_block_reason().is_empty(): return
	if campus.complete_activity(scene_id, GameState.day, offline, meaningful_turns):
		campus.record_schedule(GameState.day, GameState.clock_hours(), "activity", str(scene().title) + (" · 离线" if offline else ""))
		advance_hours(float(campus.catalog.tuning.get("activity_hours", 1)))
		campus.remember_quote("We took part in " + str(scene().title) + " together.", scene().participants, scene_id, GameState.day)
		feedback.emit("已完成离线共同活动，没有生成口语成绩。" if offline else "共同活动完成，已记录这次经历。")
	else: feedback.emit("今天这项活动已完成，或还需要两次有效交流。也可明确选择离线活动。")
	save()
	progression_changed.emit()

func wait_until_evening() -> void:
	if location != "home": return
	cancel_activity()
	advance_hours(maxf(0, 20 - GameState.clock_hours()), true)
	save()
	progression_changed.emit()
	feedback.emit("已休息到晚上，可以睡觉开始新一天。")

func sleep() -> bool:
	if location != "home": return false
	if GameState.clock_hours() < 20 and GameState.energy >= 40:
		feedback.emit("还不困，可以先在住处休息到晚上。")
		return false
	cancel_activity()
	var overnight := 24.0 - GameState.clock_hours() + 8.0
	var extra := campus.advance_social(overnight)
	GameState.day += 1
	GameState.day_time = 0
	GameState.energy = maxf(0, 100 - extra)
	GameState.warmth = minf(100, GameState.warmth + 30 + GameState.items.sleep_warmth_bonus())
	GameState.game_finished = false
	campus.begin_day(GameState.day)
	new_session()
	save()
	progression_changed.emit()
	scene_changed.emit()
	_offer_opening.call_deferred()
	feedback.emit("第 %d 天，休息好了。可以安排今天的学习和生活。" % GameState.day)
	return true

func save() -> bool:
	if not save_valid: return false
	if not service_mode:
		campus.conversation = {"scenario_id": scene_id, "day": GameState.day, "session_id": session, "history": exchange.duplicate(true), "topic_summary": topic_summary, "meaningful_turns": meaningful_turns, "turn_serial": turn_serial, "practice_context": practice_context}
	GameState.presentation_state["chapter"] = "campus"
	GameState.presentation_state["campus"] = campus.serialize()
	GameState.presentation_state["campus_location"] = location
	GameState.presentation_state["campus_scene"] = scene_id
	return super.save()

func open_counter() -> void:
	if location != "dining": travel("dining")
	cancel_activity()
	location = "dining"
	scene_id = "dining_order"
	service_mode = true
	new_session()
	scene_changed.emit()
	_offer_opening.call_deferred()
	say("tavi", "Hey. What can I get you?")

func inventory_guidance() -> Dictionary:
	return {"text": "到校园餐饮柜台领取食物和饮品；可以当场使用，也可以放进行囊。住处收纳箱可存放暂时不用的物品。", "links": [["去校园餐饮柜台", "dining"]]}

func item_description(id: String) -> String:
	if id == "drink_bottled_water": return "随身带一瓶水，需要时喝下补充精力，也可以先存放在住处。"
	return super.item_description(id).replace("小屋", "住处")

func _service_settled(npc: String, detail: Dictionary) -> void:
	super._service_settled(npc, detail)
	if not service_mode or npc != "tavi" or detail.get("outcome") != "success": return
	campus.reward_event("talk:%d:dining_order" % GameState.day, campus.scenario("dining_order"), ["tavi"], GameState.day, 8)
	save()
	progression_changed.emit()

func _practice_words() -> Array:
	var words: Array = super._practice_words()
	for word in ["class", "project", "outline", "example", "club", "invite", "join", "prefer", "explain", "practice", "agree", "together"]:
		if not words.has(word): words.append(word)
	return words

func update_profile(values: Dictionary) -> void:
	cancel_activity()
	campus.set_profile(values)
	GameState.vocabulary_tier = str(campus.profile.level)
	Vocabulary.sync_from_game_state()
	new_session()
	save()
	scene_changed.emit()
	_offer_opening.call_deferred()

func create_practice(brief: String, domain: String, title := "", goal := "") -> bool:
	var id: String = campus.create_practice(brief, domain, title, goal)
	if id.is_empty(): feedback.emit("先填写用于练习的摘要，完整经历会继续只保存在本机。"); return false
	travel(domain)
	select_scene(id)
	return true

func change_memory(id: String, text: String, erase := false) -> void:
	cancel_activity()
	if erase: campus.delete_memory(id)
	else: campus.edit_memory(id, text)
	# Clear the active extractive summary too: edited/deleted text must not linger there.
	new_session()
	save()

func _day_started(_day: int) -> void:
	pass

func _offer_opening() -> void:
	var overlay = get_parent().get("modal")
	if overlay is Window and overlay.visible: return
	if not boot_from_save or location == "home" or service_mode or not exchange.is_empty(): return
	if not conversation_block_reason().is_empty() or not practice_word.is_empty(): return
	submit_text("[NPC opens conversation]", false, -1.0, true)
