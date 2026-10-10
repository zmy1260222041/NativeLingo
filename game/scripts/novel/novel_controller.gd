extends Node
## FR-46: 2D action boundary. The original domain owns all rewards and items.
signal scene_changed
signal line_changed(speaker: String, text: String)
signal feedback(text: String)
signal progression_changed
const Content := preload("res://scripts/novel/novel_content.gd")
const SAVE_PATH := "user://stranger_novel_save.json"
const CAMPUS_SAVE := "user://stranger_campus_save.json"
var location := "plaza"
var history: Array = []
var social_index := -1
var social_line := -1
var practice_word := ""
var boot_from_save := true
var novel_save_path := SAVE_PATH
## FR-35: the other chapter's save; its copy of the shared vocabulary merges in on load.
var other_chapter_save_path := CAMPUS_SAVE
var old_process := true
var old_save_path := ""
var _changing := false
var health_request: HTTPRequest
var voice_status := "尚未检查语音连接"
var _listening := false
var _replay: Dictionary = {}
var _pending_spoken_reply: Dictionary = {}
var _preparing_opening := false
var order_note: Dictionary = {}
var social_openings: Dictionary = {}
## FR-46: what the last /health check proved. Online dialogue and NPC voice are
## judged separately so an arrival never retries a path already known to be down.
var online_dialogue := true
var npc_voice_ready := true
var _status_pending := false
var _failed_openings: Dictionary = {}
## C1-01: the player's recognition score for the social turn now in flight.
var _spoken_scores: Dictionary = {}
## X1-01: the last faint, kept on the home panel until the next explicit action.
var faint_note: Dictionary = {}
const PLAYER_UNCLEAR_REASONS := ["VOICE_REASON_CLARIFY", "VOICE_REASON_TOO_SHORT", "VOICE_REASON_LENGTH", "VOICE_REASON_SCORE_LOW"]
## P1-01 / G1-01: resting at home until evening still costs REST_HUNGER_COST of
## the hunger drain; indoors, warmth and energy keep REST_SHELTER_COST. Without
## a meal a day, food runs out before the third night ends.
const REST_HUNGER_COST := 0.4
const REST_SHELTER_COST := 0.2

func _ready() -> void:
	Content.load_daily_life()
	add_to_group("novel_world")
	old_process = GameState.is_processing()
	old_save_path = GameState.save_path
	GameState.set_process(false)
	if boot_from_save:
		var carried: Dictionary = GameState.vocabulary_entries
		GameState.save_path = novel_save_path if FileAccess.file_exists(novel_save_path) else old_save_path
		GameState.load_game()
		GameState.save_path = novel_save_path
		_share_vocabulary(carried)
		var state: Dictionary = GameState.presentation_state
		location = str(Content.place(str(state.get("location", "plaza"))).id)
		history = state.get("history", []).duplicate(true)
		social_openings = state.get("social_openings", {}).duplicate(true)
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
	NpcDialogueService.town_exchange_finished.connect(_remember_town_exchange)
	NpcDialogueService.dialogue_failed.connect(_dialogue_failed)
	NpcDialogueService.service_turn_updated.connect(_service_turn_updated)
	NpcScenarioRunner.service_settled.connect(_service_settled)
	Dialogue.session_changed.connect(func(_npc, _state, _line): progression_changed.emit())
	NpcDialogueService.player_turn_displayed.connect(func(_npc, text): say("you", text))
	SpeechAdapter.recognition_finished.connect(_recognition)
	SpeechAdapter.word_score_finished.connect(_word_score)
	NpcVoice.line_audio_ready.connect(_reply_audio_started)
	NpcVoice.line_audio_finished.connect(_listening_finished)
	NpcVoice.line_audio_failed.connect(_listening_failed)
	if boot_from_save:
		_check_local_service()

func start(play_voice := true) -> void:
	scene_changed.emit()
	_present_opening(play_voice)

func _present_opening(play_voice := true) -> void:
	var entry := Content.place(location)
	var opening_key := "%s:%d" % [npc_id(), GameState.day]
	# X1-02 / C1-17: dialogue already known to be down (health, or a failed opening
	# today) is not asked again; the authored line greets instead.
	if play_voice and boot_from_save and online_dialogue and NpcDialogueService.is_available() and not _failed_openings.has(opening_key) and npc_id() in ["mira", "rowan"] and not GameState.game_finished and not social_openings.has(opening_key) and conversation_block_reason().is_empty():
		# Set first: a failure reported during the call takes the authored-line path.
		_preparing_opening = true
		if NpcDialogueService.start_social_opening(npc_id(), _spoken_scenario(npc_id()), GameState.day):
			line_changed.emit("", "正在准备开场语音…")
			feedback.emit("%s 向你搭了句话。可以接话，也可以随时离开。" % npc_id().capitalize())
			return
		_preparing_opening = false
		if _failed_openings.has(opening_key):
			return
	say(npc_id(), str(entry.opening))
	if play_voice and not npc_id().is_empty() and not GameState.game_finished:
		_listen(npc_id(), str(entry.get("opening_id", "")), [], true)
	if GameState.game_finished:
		feedback.emit("三夜已度过。%s可在设置中开始新旅程。" % ("你已不再是陌生人。" if not GameState.journey_summary().spoken_with.is_empty() else ""))
	elif play_voice and _status_pending:
		# G1-09 / P1-14: the first scene after a degraded check states it once.
		_status_pending = false
		feedback.emit(voice_status)

func npc_id() -> String:
	return str(Content.place(location).npc)

func travel(destination: String) -> bool:
	if GameState.game_finished or destination == location:
		return false
	var selected := Content.place(destination)
	if selected.id != destination:
		return false
	cancel_activity()
	order_note.clear()
	faint_note.clear()
	location = destination
	var faints: int = GameState.faints
	advance_time(6.0)
	if GameState.faints != faints:
		_wake_after_faint()
		return true
	save()
	scene_changed.emit()
	_present_opening()
	return true

func cancel_activity() -> void:
	# FR-46 cancels the delivery; FR-48 says so instead of leaving 店员已确认 on screen.
	# The clerk may have spoken the named handoff before its score arrived (NFR-9).
	var service := NpcDialogueService
	var handoff: bool = service.current_transaction_complete or (not service.current_reply_id.is_empty() \
		and not service._concrete_item_named_in_reply(service.current_reply_text, service.current_reply_speech_act).is_empty())
	var interrupted: bool = GameState.can_start_service_dialogue(npc_id()) and service.is_session_active_for(npc_id()) and handoff
	_changing = true
	_pending_spoken_reply.clear()
	_preparing_opening = false
	SpeechAdapter.cancel_recording()
	SpeechAdapter.clear_recovery()
	NpcDialogueService.cancel()
	NpcVoice.stop_all()
	_listening = false
	_replay.clear()
	order_note.clear()
	_spoken_scores.clear()
	Dialogue.finish_word_practice()
	practice_word = ""
	social_index = -1
	social_line = -1
	GameState.set_interaction_time_frozen(false)
	_changing = false
	if interrupted:
		order_note = {"title": "交谈被打断，这次没有交付物品", "detail": "店员刚才的确认已经取消。想要的话，再点「录音」说一次商品名，不消耗任何东西。"}
		# Deferred so a panel opened by this cancel can show it in its own status line.
		call_deferred("emit_signal", "feedback", "和 %s 的交谈被打断，这次没有交付物品。再说一次商品名就好，不消耗任何东西。" % npc_id().capitalize())
	progression_changed.emit()

func advance_time(seconds: float, hunger_cost := 1.0, shelter_cost := 1.0) -> void:
	# All reading is free. Only explicit travel/wait commands advance survival.
	var remaining := seconds
	var faints: int = GameState.faints
	# X1-01: a faint ends the walk or rest; the player wakes instead of fainting again.
	while remaining > 0.0 and not GameState.game_finished and GameState.faints == faints:
		var step := minf(remaining, 1.0)
		GameState.pass_time(step, hunger_cost, shelter_cost)
		remaining -= step
	progression_changed.emit()

func greet() -> void:
	if npc_id().is_empty() or GameState.game_finished:
		return
	if not _can_start_conversation_action(): return
	cancel_activity()
	var channel := "gesture_fallback" if SpeechAdapter.runtime_speech_unavailable() else "gesture"
	GameState.interact("npc", npc_id(), channel)
	save()

func talk() -> void:
	if npc_id().is_empty() or GameState.game_finished:
		return
	if not _can_start_conversation_action(): return
	if social_index >= 0 or not practice_word.is_empty():
		cancel_activity()
		scene_changed.emit()
	if npc_id() in ["mira", "rowan"]:
		if not NpcDialogueService.is_session_active_for(npc_id()):
			# The NPC speaks first, so a failure falls back like an arrival opening.
			_preparing_opening = true
			if not NpcDialogueService.start_social_opening(npc_id(), _spoken_scenario(npc_id()), GameState.day):
				_preparing_opening = false
		else:
			feedback.emit("点录音接着聊，不必重新打招呼。")
	elif GameState.can_start_service_dialogue(npc_id()):
		NpcDialogueService.begin_scenario(npc_id(), GameState.service_scenario_for(npc_id()))
	else:
		GameState.interact("npc", npc_id(), "action")
		feedback.emit("当前语音不可用，可点「手势」继续交流。" if SpeechAdapter.runtime_speech_unavailable() else "点「录音」，用英语向 %s 问好；再点一次结束。" % npc_id().capitalize())

func conversation_block_reason() -> String:
	if SpeechAdapter.is_recording(): return "正在录音"
	if NpcVoice.audio_player != null and NpcVoice.audio_player.playing:
		return "对方正在说话"
	if not NpcVoice.playing_line_id.is_empty(): return "对方正在说话"
	if _listening or not NpcVoice.pending_line_id.is_empty() or not NpcVoice.pending_reply_id.is_empty() or not NpcVoice.line_queue.is_empty():
		return "正在准备语音"
	if Dialogue.state_for(npc_id()) in ["generating", "speaking"]:
		return "正在等待回应"
	if SpeechAdapter._request_in_flight(): return "正在处理录音"
	return ""

func _can_start_conversation_action() -> bool:
	var reason := conversation_block_reason()
	if reason.is_empty(): return true
	feedback.emit(reason + "，结束后再操作。")
	return false

func recording_block_reason() -> String:
	# The player's stop button stays usable while other speech actions are locked.
	return "" if SpeechAdapter.is_recording() else conversation_block_reason()

func _spoken_scenario(target: String) -> String:
	return {"mira": "market_conversation", "rowan": "neighbor_conversation"}.get(target, GameState.service_scenario_for(target))

func record() -> void:
	if SpeechAdapter.is_recording():
		SpeechAdapter.finish_recording()
		return
	if GameState.game_finished or npc_id().is_empty():
		return
	var blocked := recording_block_reason()
	if not blocked.is_empty():
		feedback.emit(blocked + "，结束后再录音。")
		return
	if social_index >= 0:
		cancel_activity()
	if not practice_word.is_empty():
		SpeechAdapter.start_word_recording(practice_word)
		return
	if SpeechAdapter.cloud_mode_enabled() and not SpeechAdapter.cloud_activated():
		feedback.emit("可在设置中激活语音；现在也可以用手势继续生活。")
		return
	if not _spoken_scenario(npc_id()).is_empty() and not NpcDialogueService.is_session_active_for(npc_id()):
		# Entry audio was already presented on arrival. Opening the session for
		# a recording must never start that greeting again.
		if not NpcDialogueService.begin_scenario(npc_id(), _spoken_scenario(npc_id()), false):
			feedback.emit("暂时无法开始交谈，请稍后重试。")
			return
	if SpeechAdapter.start_recording(npc_id()):
		order_note.clear()
		NpcDialogueService.prewarm(npc_id())
	elif not SpeechAdapter.is_recovery_active():
		# A refused start that already reported its cause (e.g. no microphone) is not repeated.
		feedback.emit("暂时无法录音。可以免费重试，或用手势交流。")

func _recognition(target: String, accepted: bool, transcript: String, reason: String, expression: Dictionary) -> void:
	if _changing or target != npc_id() or GameState.game_finished:
		return
	if transcript.is_empty():
		if NpcDialogueService.is_session_active_for(target):
			# Keeps the role card open in clarify; _dialogue_failed explains it once.
			NpcDialogueService.reject_empty_transcript(reason)
		else:
			feedback.emit(_failure_text(reason))
			progression_changed.emit()
		return
	if not _spoken_scenario(target).is_empty() and NpcDialogueService.enabled():
		if not NpcDialogueService.is_session_active_for(target):
			NpcDialogueService.begin_scenario(target, _spoken_scenario(target), false)
		if NpcDialogueService.submit_transcript(transcript, {"pronunciation": float(expression.get("pronunciation", expression.get("score", -1.0)))}):
			# C1-01: the same recognition score the legacy voice greeting is gated on.
			_spoken_scores[target] = float(expression.get("score", expression.get("pronunciation", -1.0)))
		else:
			feedback.emit("这次录音已识别，但对话未能提交。请稍后免费重试。")
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
		# Text can arrive seconds before cold TTS. Start the typewriter with
		# playback, also handling audio that started before this signal.
		_pending_spoken_reply = {"npc": npc, "reply": reply_id, "text": text}
		_replay = {"npc": npc, "reply": reply_id}
		if NpcVoice.playing_npc_id == npc and NpcVoice.playing_line_id == reply_id and NpcVoice.audio_player.playing:
			_reply_audio_started(npc, reply_id)
		else:
			feedback.emit("正在准备语音…")

func _reply_audio_started(npc: String, reply_id: String) -> void:
	if _changing or npc != npc_id() or _pending_spoken_reply.get("npc") != npc or _pending_spoken_reply.get("reply") != reply_id:
		return
	var text := str(_pending_spoken_reply.text)
	_pending_spoken_reply.clear()
	_preparing_opening = false
	feedback.emit("")
	say(npc, text)

func _dialogue_failed(npc: String, reason: String) -> void:
	if npc != npc_id() or _changing:
		return
	_spoken_scores.erase(npc)
	var text_only := false
	var opening := _preparing_opening and _pending_spoken_reply.is_empty()
	_preparing_opening = false
	if _pending_spoken_reply.get("npc") == npc:
		var text := str(_pending_spoken_reply.text)
		_pending_spoken_reply.clear()
		say(npc, text)
		text_only = true
	elif opening:
		# C1-17: the authored opening stays readable. It is written content shown
		# as-is, never a stand-in model reply, and earns nothing.
		_failed_openings["%s:%d" % [npc, GameState.day]] = true
		say(npc, str(Content.place(location).opening))
		_listen(npc, str(Content.place(location).get("opening_id", "")), [], true)
	if not GameState.can_start_service_dialogue(npc):
		order_note.clear()
		if text_only: feedback.emit("语音未能播放，已保留文字。可以点「重听」重试。")
		elif opening: feedback.emit("%s 的在线问候这次没能生成，先显示写好的台词。可以用手势回应，也可以去听听日常。" % npc.capitalize())
		else: feedback.emit(_failure_text(reason))
		progression_changed.emit()
		return
	order_note = {"title": _failure_cause(reason), "detail": ("店员的回应没能播放，已保留文字。" if text_only else "") + _failure_detail(reason, true)}
	feedback.emit(str(order_note.title) + "。" + str(order_note.detail))
	progression_changed.emit()

## FR-46/48, NFR-8 UI duty: name the real cause in plain 2D Chinese. Service
## faults never read as a problem with the player's English.
func _failure_cause(reason: String) -> String:
	match reason:
		"VOICE_REASON_CLARIFY", "VOICE_REASON_TOO_SHORT", "VOICE_REASON_LENGTH", "VOICE_REASON_SCORE_LOW": return "这次没有听清"
		"VOICE_REASON_MIC_UNAVAILABLE": return "麦克风暂时不可用"
		"VOICE_REASON_DIALOGUE_TIMEOUT": return "交谈先告一段落"
		"VOICE_REASON_DIALOGUE_REJECTED": return "对方这次没能组织好回应"
		"VOICE_REASON_CLOUD_NOT_ACTIVATED", "VOICE_REASON_CLOUD_UNAUTHORIZED": return "云端语音需要在设置中激活"
	return "语音服务暂时没有回应"

func _failure_detail(reason: String, service := false) -> String:
	var text := "" if reason in PLAYER_UNCLEAR_REASONS else "这不是你说得不好。"
	if reason == "VOICE_REASON_DIALOGUE_TIMEOUT":
		text = "等了一会儿没有新的话，这段交谈先结束了。"
	if service:
		text += "还没有交付物品。"
	if service and SpeechAdapter.runtime_speech_unavailable():
		return text + "可以点「手势领取」获得最低份量，也可以稍后点「录音」免费重试。"
	return text + ("再点「录音」说出想要的商品就好，重试不消耗任何东西。" if service else "再点「录音」接着说就好，重试不消耗任何东西。")

func _failure_text(reason: String) -> String:
	return _failure_cause(reason) + "。" + _failure_detail(reason)

func _service_turn_updated(npc: String, detail: Dictionary) -> void:
	if not GameState.can_start_service_dialogue(npc): return
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
	if not GameState.can_start_service_dialogue(npc): return
	if npc != npc_id() or _changing: return
	if detail.outcome == "success":
		order_note.clear()
		save()
	elif detail.confirmed and float(detail.score) < GameState.SCORE_SPARSE_MIN:
		# FR-41 keeps the <40 rule; FR-45 keeps the number off screen.
		order_note = {"title": "这次还没能确认点单", "detail": "店员这次没能确认你要的东西，所以还没有交付物品，也没有消耗任何东西。再说一次商品名就好，重试是免费的。"}
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
	if state == "generating" or SpeechAdapter.is_busy(): return {"title": "正在听清并确认你的话", "detail": "稍等店员回应。这时不用再录一次，确认后会提示你领取。"}
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

func _word_score(word: String, accepted: bool, expression: Dictionary, reason: String) -> void:
	if _changing or word != practice_word:
		return
	if accepted and Vocabulary.record_word_spoken(word, float(expression.get("score", 0.0))):
		# R-32 G-C: a known starting-profile word is praised but never advanced.
		if Vocabulary.word_state(word) == "initial":
			feedback.emit("你说出了「%s」。这是你已有的词汇，在真实对话里放心用它吧。" % word)
		else:
			feedback.emit("你说出了「%s」。在之后的真实对话里用用它吧。" % word)
	elif reason == "VOICE_REASON_MIC_UNAVAILABLE":
		feedback.emit("麦克风暂时不可用，这不是你的发音问题。检查麦克风后再录一次；也可以先重听示范。")
	elif reason in ["VOICE_REASON_CLARIFY", "VOICE_REASON_TOO_SHORT", "VOICE_REASON_LENGTH"]:
		feedback.emit("这次没有听到清楚的声音。靠近麦克风，再说一次「%s」就好，没有惩罚。" % word)
	elif reason in SpeechAdapter.RUNTIME_UNAVAILABLE_REASONS:
		# P1-07 / C1-11: a scoring outage is never presented as weak pronunciation.
		feedback.emit("单词评分暂时不可用，这不是你的发音问题。可以先重听示范，或去「小剧场」听听这个词怎么用；稍后再录也不消耗任何东西。")
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

func inventory_guidance() -> Dictionary:
	return {"text": "餐摊的食物恢复饱腹；便利店的饮品补充精力。毯子、零件和电池带回小屋再安放。", "links": [["去餐摊看看", "food"], ["去便利店补给", "store"]]}

func item_description(id: String) -> String:
	var definition: Dictionary = GameState.items.definitions[id]
	match id:
		"drink_canteen": return "路上慢慢喝。水壶可以喝两次，用过一次后仍能留在行囊里。"
		"drink_bottled_water": return "给自己补充一点精力。也可以带去罗文的门廊，点「送一份水给罗文」送给他。"
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
	if action == "give":
		context["recipient"] = npc_id()
	if not validate_item_context(context):
		return {"ok": false, "reason": "location"}
	var result: Dictionary = GameState.item_command(action, [id], context, allow_waste)
	if result.get("ok", false):
		save()
	return result

## Town rule 5 / C1-02: carried water Rowan can still receive here and now.
func water_gifts() -> Array:
	if npc_id() != "rowan" or GameState.game_finished or GameState.completed_steps.has("help_rowan"):
		return []
	return visible_items("bag").filter(func(record): return npc_id() in GameState.items.definitions[record.item_id].transfer_to)

## C1-02 / C1-03: the explicit local item action, the same with or without voice.
## Rowan thanks the gift with his authored, server-known line.
func give_water() -> Dictionary:
	var gifts := water_gifts()
	if gifts.is_empty():
		return {"ok": false, "reason": "given" if GameState.completed_steps.has("help_rowan") else "missing"}
	if not _can_start_conversation_action():
		return {"ok": false, "reason": "busy"}
	cancel_activity()
	var result := use_item("give", str(gifts[0].id))
	if result.get("ok", false):
		say(npc_id(), "You brought water. I will not forget.")
		# Quiet like an arrival line while NPC voice is off, so the named result stays.
		_listen(npc_id(), "remembers", [], true)
	return result

func wait_until_evening() -> void:
	if location != "home" or GameState.game_finished:
		return
	cancel_activity()
	faint_note.clear()
	# Resting at home runs the clock to evening. Hunger keeps most of its pace;
	# indoors, warmth and energy drain slowly.
	var seconds := maxf(0.0, (GameState.SLEEP_HOUR - GameState.DAY_START_HOUR) / (GameState.DAY_END_HOUR - GameState.DAY_START_HOUR) * GameState.DAY_DURATION - GameState.day_time + 0.1)
	var faints: int = GameState.faints
	advance_time(seconds, REST_HUNGER_COST, REST_SHELTER_COST)
	if GameState.faints != faints:
		_wake_after_faint()
		return
	save()
	scene_changed.emit()
	feedback.emit("灯亮起来了。天色已晚，可以睡觉了。")
	progression_changed.emit()

func sleep() -> bool:
	if location != "home" or GameState.game_finished:
		return false
	cancel_activity()
	faint_note.clear()
	var previous: int = GameState.day
	GameState.interact("shelter", "shelter")
	save()
	return GameState.day != previous

func _day_started(day: int) -> void:
	scene_changed.emit()
	say("", ending_text() if GameState.game_finished else "第 %d 天。新的一天，从一句问候开始。" % day)

## X1-01: a faint ends the action at home ("回到安全点并推进时间"). It is told in
## the dialogue box and the review log, and stays on the home panel, so the
## scene change cannot wipe it.
func _wake_after_faint() -> void:
	location = "home"
	order_note.clear()
	var faint: Dictionary = GameState.last_faint
	var time: Vector2i = GameState.clock_hms()
	var lost := str(faint.get("lost", ""))
	var lost_text := "昏倒时丢了随身的%s。" % GameState.items.Catalog.label(GameState.items.definitions[lost].name) if not lost.is_empty() else "随身物品都还在。"
	var cause := str(faint.get("cause", ""))
	var text := "你%s，昏倒了。醒来时已经回到小屋，时间到了 %02d:%02d。%s" % [{"food": "饿得撑不住", "warmth": "冻得撑不住"}.get(cause, "累得撑不住"), time.x, time.y, lost_text]
	var advice: String = {"food": "饱腹只剩 %d。去餐摊吃点东西，或吃掉行囊里的食物。" % int(GameState.food), "warmth": "温暖只剩 %d。吃顿热饭、喝杯热咖啡，或铺好毯子再睡。" % int(GameState.warmth)}.get(cause, "精力只剩 %d。早点休息。" % int(GameState.energy))
	faint_note = {"title": "你刚才昏倒了 · 第 %d 次" % GameState.faints, "detail": lost_text + advice}
	save()
	scene_changed.emit()
	say("", text + advice)
	feedback.emit(text)
	progression_changed.emit()

## P1-01 / P2-07 / G1-01: the ending names only what this run actually did.
func ending_text() -> String:
	var summary: Dictionary = GameState.journey_summary()
	var text := "三夜过去了。"
	if summary.spoken_supplies: text += "你靠开口换来了补给。"
	elif summary.gesture_supplies: text += "你靠手势领到了最低份量的补给。"
	else: text += "你没有从店里领到吃的喝的。"
	if int(summary.faints) > 0: text += "途中你昏倒过 %d 次。" % int(summary.faints)
	var names := func(ids: Array) -> String: return "、".join(ids.map(func(id): return str(id).capitalize()))
	if not summary.spoken_with.is_empty():
		return text + "你用英语和 %s 说上了话，开始记得这些名字。欢迎回家。" % names.call(summary.spoken_with)
	if not summary.known.is_empty():
		return text + "%s 记得你，但你们还没有用英语说上话。下一次，试着开口吧。" % names.call(summary.known)
	return text + "这里还没有人认识你。下一次，试着开口打个招呼吧。"

## FR-35: vocabulary is one learner asset across both chapters. Loading a chapter
## keeps the furthest state of every word from memory, this chapter's save and the
## other chapter's save, so switching chapters or relaunching never rolls words back.
func _share_vocabulary(carried: Dictionary) -> void:
	var merged := VocabularyState.merge_entries(GameState.vocabulary_entries, carried)
	GameState.vocabulary_entries = VocabularyState.merge_entries(merged, GameState.saved_vocabulary_entries(other_chapter_save_path))

func save() -> bool:
	GameState.presentation_state["location"] = location
	GameState.presentation_state["history"] = history
	GameState.presentation_state["social_openings"] = social_openings
	return GameState.save_game()

func restart(play_voice := true) -> void:
	cancel_activity()
	GameState.reset_run()
	location = "plaza"
	faint_note.clear()
	history.clear()
	social_openings.clear()
	GameState.presentation_state.clear()
	save()
	start(play_voice)

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
	var json := JSON.new()
	var data = json.data if json.parse(body.get_string_from_utf8()) == OK else null
	var reachable := result == HTTPRequest.RESULT_SUCCESS and code == 200 and data is Dictionary
	# C2-08: recognition is judged on its own. Older services omit asr_ready and
	# tts_configured; a missing field keeps the previous meaning (available).
	var asr_ready := reachable and bool(data.get("asr_ready", true))
	online_dialogue = reachable and bool(data.get("dialogue_ready", false))
	npc_voice_ready = reachable and bool(data.get("tts_configured", true))
	var healthy := asr_ready and online_dialogue
	voice_status = _voice_status_text(reachable, asr_ready, str(data.get("dialogue_reason", "")) if reachable else "")
	if healthy:
		SpeechAdapter.last_unavailable_reason = ""
		_failed_openings.clear()
	else:
		# FR-46: recognition or dialogue down means voice cannot complete an
		# order, so the gesture minimum applies until a later check or attempt.
		SpeechAdapter.mark_runtime_unavailable("VOICE_REASON_SERVICE_UNAVAILABLE")
	_status_pending = not healthy or not npc_voice_ready
	feedback.emit(voice_status)
	progression_changed.emit()

## One player-facing sentence for what the last /health check proved. The campus
## names its own options for the same facts (P3-10).
func _voice_status_text(reachable: bool, asr_ready: bool, dialogue_reason: String) -> String:
	if not reachable:
		return "语音服务还没有启动。现在可以看文字、听日常，用「手势领取」最低份量；启动后在设置里重新检查。"
	var text := ""
	if asr_ready and online_dialogue:
		text = "语音识别和在线交谈都已连接，可以进入商店开口交谈。"
	else:
		var missing: Array[String] = []
		if not asr_ready: missing.append("语音识别")
		if not online_dialogue: missing.append("在线交谈")
		text = ("录音可以进行，但%s暂不可用" if not asr_ready else "%s暂时连不上") % "和".join(missing)
		if not online_dialogue and dialogue_reason == "region_unsupported":
			text += "（服务商不支持当前地区）"
		text += "%s。现在可以用「手势领取」最低份量，也可以看文字、听日常。" % ("，角色会显示写好的台词" if not online_dialogue else "")
	if not npc_voice_ready:
		text += "角色语音暂未开启，台词以文字显示。"
	return text

func _practice_words() -> Array:
	var words: Array = []
	for entry in Content.SOCIAL:
		for word in entry.words:
			if not words.has(word): words.append(word)
	return words

## FR-36 practice-corner label, shared by both chapters.
func word_progress(word: String) -> String:
	var state: String = Vocabulary.word_state(word)
	return {"": "尚未听见", "initial": "已有词汇", "heard": "听见", "spoken": "说出", "used": "使用"}.get(state, state)

func _listen(npc: String, line: String, options: Array = [], arrival := false) -> void:
	_replay = {"npc": npc, "line": line, "options": options.duplicate(), "arrival": arrival}
	_listening = true
	# A refused request reports through line_audio_failed -> _listening_failed.
	if not NpcVoice.request_line(npc, line, "", "wav", options):
		_listening = false

func listen_again() -> void:
	if _replay.is_empty() or SpeechAdapter.is_busy() or Dialogue.state_for(npc_id()) in ["generating", "speaking"]:
		return
	if not _can_start_conversation_action(): return
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
	# P1-05 / P1-14: once the status says NPC voice is off, arrivals stay quiet
	# and an explicit replay says why instead of inviting another retry.
	if npc_voice_ready:
		feedback.emit("语音暂时无法播放，可以点「重听」再试。")
	elif not _replay.get("arrival", false):
		feedback.emit("角色语音暂未开启，台词以文字显示。")

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

func _remember_town_exchange(npc: String, player_text: String, reply_text: String, opening: bool) -> void:
	if _changing or npc != npc_id() or GameState.presentation_state.get("chapter") == "campus": return
	var contacts: Dictionary = GameState.presentation_state.get("town_contacts", {})
	var contact: Dictionary = contacts.get(npc, {"completed_exchanges": 0, "days": [], "history": []})
	var transcript: Array = contact.get("history", [])
	if not opening:
		# C1-01 / X1-06: the first clear spoken exchange with Mira is her greeting.
		GameState.record_spoken_exchange(npc, float(_spoken_scores.get(npc, -1.0)))
		_spoken_scores.erase(npc)
		contact["completed_exchanges"] = mini(1000, int(contact.get("completed_exchanges", 0)) + 1)
		var days: Array = contact.get("days", [])
		if GameState.day not in days: days.append(GameState.day)
		contact["days"] = days.slice(maxi(0, days.size() - 30))
		transcript.append({"role": "player", "text": player_text.left(1000)})
	else:
		social_openings["%s:%d" % [npc, GameState.day]] = true
	transcript.append({"role": "npc", "text": reply_text.left(1000)})
	contact["history"] = transcript.slice(maxi(0, transcript.size() - 8))
	contacts[npc] = contact
	GameState.presentation_state["town_contacts"] = contacts
	save()
