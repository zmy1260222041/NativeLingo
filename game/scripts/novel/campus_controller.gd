extends "res://scripts/novel/novel_controller.gd"
const CampusState := preload("res://scripts/novel/campus_state.gd")
const CampusDialogue := preload("res://scripts/novel/campus_dialogue.gd")
const PLACES := {"class": "教学区", "study": "学习空间", "club": "社团中心", "dining": "餐饮区", "sports": "运动区", "home": "我的住处"}
## P3-10: what still works while online dialogue is down, named the same way everywhere.
const OFFLINE_OPTIONS := "可以上课、自主学习、参加离线活动（不评口语），或到餐饮柜台补充食物。服务恢复后，在「设置」里重新检查连接。"
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
	other_chapter_save_path = SAVE_PATH if other_chapter_save_path == CAMPUS_SAVE else other_chapter_save_path
	super._ready()
	GameState.reset_run()
	GameState.set_process(false)
	GameState.onboarding_active = false
	GameState.save_path = novel_save_path
	var carried: Dictionary = GameState.vocabulary_entries
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
	if restore_saved: _share_vocabulary(carried)
	GameState.vocabulary_tier = str(campus.profile.level)
	Vocabulary.sync_from_game_state()
	conversation = CampusDialogue.new()
	add_child(conversation)
	conversation.line_ready.connect(_campus_line)
	conversation.completed.connect(_campus_complete)
	conversation.failed.connect(_campus_failed)
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
	faint_note.clear()
	location = destination
	service_mode = false
	if not advance_hours(float(campus.catalog.tuning.get("travel_hours", 0.25))): return true
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
	if transcript.strip_edges().is_empty():
		feedback.emit(_campus_failure_text(reason))
		progression_changed.emit()
		return
	submit_text(transcript, true, float(expression.get("pronunciation", -1)))

## P3-11: the town's causes (A2). Only speech that was really unclear reads as
## 没有听清; a service or microphone fault is never the player's English.
func _campus_failure_text(reason: String) -> String:
	var text := _failure_cause(reason) + "。"
	if reason in PLAYER_UNCLEAR_REASONS:
		return text + "再点「录音」说一次就好，也可以直接输入英语；重试不消耗任何东西。"
	text += "这不是你说得不好。"
	if reason == "VOICE_REASON_MIC_UNAVAILABLE":
		return text + "检查麦克风后再录一次；现在也可以直接输入英语。"
	if reason in ["VOICE_REASON_CLOUD_NOT_ACTIVATED", "VOICE_REASON_CLOUD_UNAUTHORIZED"]:
		return text + "在小镇设置中激活后就能开口；现在也可以上课、自主学习或参加离线活动。"
	if online_dialogue:
		return text + "现在可以直接输入英语交流，稍后再点「录音」免费重试。"
	return text + "在线交谈也暂时连不上。" + OFFLINE_OPTIONS

## P3-10: a failed turn says what failed and offers only what still works.
func _campus_failed(kind: String) -> void:
	var opening := pending_opening
	pending_turn = ""
	pending_opening = false
	var retry := "" if retry_text.is_empty() else "可以点「免费重试」，"
	var speaker := str(campus.catalog.profiles.get(npc_id(), {}).get("name", "对方"))
	if kind == "cloud":
		feedback.emit("云端语音还没有激活，这不是你的问题。请先在小镇设置中激活；现在也可以上课、自主学习或参加离线活动。")
	elif kind == "audio":
		feedback.emit("角色语音没能播放完，这一轮没有结算。这不是你说得不好。" + (retry + "也" if not retry.is_empty() else "") + "可以打开「仅文字」只看文字回复。")
	elif kind == "invalid":
		feedback.emit(("%s 这次没能组织好开场白。可以直接开口或输入英语。" % speaker) if opening else ("对方这次没能组织好回应，没有结算。这不是你说得不好。" + (retry + "或换个说法再说一次。" if not retry.is_empty() else "换个说法再说一次就好。")))
	else:
		# The model or the service is down: no more automatic openings until a
		# check or a completed turn proves otherwise, and the counter's minimum
		# meal is armed like any other voice outage (FR-28).
		online_dialogue = false
		SpeechAdapter.mark_runtime_unavailable("VOICE_REASON_SERVICE_UNAVAILABLE")
		var what := ("%s 这次没能先开口。" % speaker) if opening else "这句话还没有送达，没有结算。"
		feedback.emit(what + "在线交谈暂时连不上，这不是你说得不好。" + ("恢复后" + retry.trim_suffix("，") + "。" if not retry.is_empty() else "") + "现在" + OFFLINE_OPTIONS)
	progression_changed.emit()

## P3-10: the persistent campus note while online dialogue is down; "" when it works.
func offline_note() -> String:
	if online_dialogue or location == "home" or service_mode: return ""
	return "在线交谈暂时连不上，校园生活照常继续。" + OFFLINE_OPTIONS

## P3-10: the dialogue header follows the last /health check and the latest turn,
## judging online dialogue, recognition and NPC voice separately (FR-46).
func connection_text() -> String:
	if not online_dialogue: return "在线交谈暂不可用"
	if SpeechAdapter.runtime_speech_unavailable(): return "录音暂不可用，可打字"
	if muted or not NpcVoice.is_available() or not npc_voice_ready: return "文字交流"
	return "语音与文字均可用"

## P3-10: the same /health facts in campus terms; the town's 听日常 does not exist here.
func _voice_status_text(reachable: bool, asr_ready: bool, dialogue_reason: String) -> String:
	var voice := "" if npc_voice_ready or not reachable else "角色语音暂未开启，回复以文字显示。"
	if not reachable:
		return "语音服务还没有启动。校园生活照常继续：" + OFFLINE_OPTIONS
	if not online_dialogue:
		return "在线交谈暂时连不上%s。校园生活照常继续：%s%s" % ["（服务商不支持当前地区）" if dialogue_reason == "region_unsupported" else "", OFFLINE_OPTIONS, voice]
	if not asr_ready:
		return "录音可以进行，但语音识别暂不可用。可以直接输入英语交流，也可以参加离线活动。" + voice
	return "语音识别和在线交谈都已连接，可以开口或输入英语交流。" + voice

## P3-10: a scoring outage keeps the town's honest wording, without pointing to
## the town's 小剧场.
func _word_score(word: String, accepted: bool, expression: Dictionary, reason: String) -> void:
	if not _changing and word == practice_word and not accepted and reason in SpeechAdapter.RUNTIME_UNAVAILABLE_REASONS and reason != "VOICE_REASON_MIC_UNAVAILABLE":
		feedback.emit("单词评分暂时不可用，这不是你的发音问题。可以先重听示范；稍后再录也不消耗任何东西。")
		save()
		progression_changed.emit()
		return
	super._word_score(word, accepted, expression, reason)

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
	conversation.submit(body, muted or not NpcVoice.is_available() or not npc_voice_ready)

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
	online_dialogue = true
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

## Returns false when the player fainted: the faint ends the action and the
## player wakes in their room (P3-18).
func advance_hours(hours: float, resting := false) -> bool:
	# C1-10: an explicit campus action always costs its needs; no leftover
	# interaction freeze may turn it into free time.
	GameState.set_interaction_time_frozen(false)
	var available := maxf(0, 22.0 - GameState.clock_hours())
	var elapsed := minf(maxf(hours, 0), available)
	var extra := campus.advance_social(elapsed)
	var seconds := elapsed / 14.0 * GameState.DAY_DURATION
	var original_time: float = GameState.day_time
	var faints: int = GameState.faints
	super.advance_time(seconds * (0.2 if resting else 1.0))
	# The faint's own time stands; the action's full hour never rewinds it.
	if GameState.faints == faints:
		GameState.day_time = minf(GameState.DAY_DURATION, original_time + seconds)
		GameState.energy = maxf(0, GameState.energy - extra)
		if GameState.energy <= 0: GameState.faint()
	GameState.state_changed.emit()
	if GameState.faints == faints: return true
	_wake_after_faint()
	return false

func study(kind: String) -> void:
	if kind == "class" and location != "class": return
	if kind == "study" and location not in ["study", "home"]: return
	if GameState.clock_hours() > 21: feedback.emit("今天已晚，先休息，明天继续。"); return
	cancel_activity()
	faint_note.clear()
	if campus.complete_study(kind, GameState.day):
		campus.record_schedule(GameState.day, GameState.clock_hours(), kind, "课堂活动" if kind == "class" else "自主学习")
		if not advance_hours(float(campus.catalog.tuning.get("activity_hours", 1))): return
		feedback.emit("学习活动已完成 · 本周学业 +10。按完成度累计，不评口音或专业知识。")
	else: feedback.emit("今天这项学习已完成，或本周该类五次已完成。可以自由练习，不重复计分。")
	save()
	progression_changed.emit()

func joint_activity(offline := false) -> void:
	if GameState.clock_hours() > 21: feedback.emit("今天已晚，先休息。"); return
	if not conversation_block_reason().is_empty(): return
	cancel_activity()
	if campus.complete_activity(scene_id, GameState.day, offline, meaningful_turns):
		campus.record_schedule(GameState.day, GameState.clock_hours(), "activity", str(scene().title) + (" · 离线" if offline else ""))
		if not advance_hours(float(campus.catalog.tuning.get("activity_hours", 1))): return
		# P3-13: the activity stays a local schedule entry (and a chain milestone);
		# it never becomes a quote the player did not say.
		feedback.emit("已完成离线共同活动，没有生成口语成绩。" if offline else "共同活动完成，已记录这次经历。")
	else: feedback.emit("今天这项活动已完成，或还需要两次有效交流。也可明确选择离线活动。")
	save()
	progression_changed.emit()

func wait_until_evening() -> void:
	if location != "home": return
	cancel_activity()
	faint_note.clear()
	if not advance_hours(maxf(0, 20 - GameState.clock_hours()), true): return
	save()
	progression_changed.emit()
	feedback.emit("已休息到晚上，可以睡觉开始新一天。")

func sleep() -> bool:
	if location != "home": return false
	if clock_minutes() < 20 * 60 and GameState.energy >= 40:
		feedback.emit("还不困，可以先在住处休息到晚上。")
		return false
	cancel_activity()
	faint_note.clear()
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
	if location != "dining":
		travel("dining")
		# P3-18: a faint on the way wakes the player at home, not at the counter.
		if location != "dining": return
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
	var before: Array = campus.memories.map(func(memory): return str(memory.text))
	if erase: campus.delete_memory(id)
	else: campus.edit_memory(id, text)
	var kept: Array = campus.memories.map(func(memory): return str(memory.text))
	var stale: Array = before.filter(func(quote): return quote not in kept)
	# P3-14: the old words leave the recent history and the extractive summary, so
	# they never reach the model again; the conversation and its count carry on.
	var mentions := func(line: String) -> bool: return stale.any(func(quote): return line.contains(quote))
	exchange = exchange.filter(func(turn): return not mentions.call(str(turn.get("text", ""))))
	topic_summary = "\n".join(Array(topic_summary.split("\n")).filter(func(line): return not mentions.call(line)))
	save()

func _day_started(_day: int) -> void:
	pass

## P3-19: campus times compare and show in whole minutes. A saved 20:00 can
## reload a hair earlier, because the save keeps 15 significant digits.
func clock_minutes() -> int:
	return roundi(GameState.clock_hours() * 60.0)

## P3-18: the town's faint presentation (A3) in campus words. The faint ends the
## action, the player wakes in their room, and the note stays on the home card.
func _wake_after_faint() -> void:
	cancel_activity()
	location = "home"
	service_mode = false
	new_session()
	var faint: Dictionary = GameState.last_faint
	var lost := str(faint.get("lost", ""))
	var lost_text := "昏倒时丢了随身的%s。" % GameState.items.Catalog.label(GameState.items.definitions[lost].name) if not lost.is_empty() else "随身物品都还在。"
	var cause := str(faint.get("cause", ""))
	var text := "你%s，昏倒了。醒来时已经回到住处，时间到了 %02d:%02d。%s" % [{"food": "饿得撑不住", "warmth": "冻得撑不住"}.get(cause, "累得撑不住"), clock_minutes() / 60, clock_minutes() % 60, lost_text]
	var advice: String = {"food": "饮食只剩 %d。去餐饮柜台吃点东西，或吃掉行囊里的食物。" % int(GameState.food), "warmth": "温暖只剩 %d。吃顿热饭，或早点休息。" % int(GameState.warmth)}.get(cause, "精力只剩 %d。早点休息%s。" % [int(GameState.energy), "；社交需求太低也会消耗精力，和同学聊聊或参加活动能缓过来" if campus.social < float(campus.catalog.tuning.social_low_threshold) else ""])
	faint_note = {"title": "你刚才昏倒了 · 第 %d 次" % GameState.faints, "detail": lost_text + advice}
	save()
	scene_changed.emit()
	say("", text + advice)
	feedback.emit(text + advice)
	progression_changed.emit()

func _message(text: String, tone: String) -> void:
	# P3-18: _wake_after_faint words the campus faint; the town's 庇护所 line never shows.
	if text == tr("MSG_FAINTED"): return
	super._message(text, tone)

func _offer_opening() -> void:
	var overlay = get_parent().get("modal")
	if overlay is Window and overlay.visible: return
	if not boot_from_save or location == "home" or service_mode or not exchange.is_empty(): return
	# P3-10: dialogue known to be down is not asked again on every scene or panel.
	if not online_dialogue: return
	if not conversation_block_reason().is_empty() or not practice_word.is_empty(): return
	submit_text("[NPC opens conversation]", false, -1.0, true)
