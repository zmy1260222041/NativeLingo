extends Node

const InteractableScript = preload("res://scripts/interactable.gd")

var failures := 0

func _ready() -> void:
	TranslationServer.set_locale("zh_CN")
	var player := Node3D.new()
	player.name = "Player"
	player.add_to_group("player")
	add_child(player)
	player.global_position = Vector3(4.0, 0.0, 0.0)
	var npc := InteractableScript.new()
	npc.name = "Mira"
	npc.interaction_kind = "npc"
	npc.target_id = "mira"
	npc.display_name = "米拉"
	add_child(npc)
	var messages: Array[String] = []
	var handler := func(text: String, _tone: String) -> void:
		messages.append(text)
	GameState.message_requested.connect(handler)
	NpcVoice.availability_override = false
	npc._process(0.1)
	_expect(npc.npc_greeted and messages.size() == 1, "NPC greets once when the player enters the social radius")
	_expect(not messages[0].is_empty() and (messages[0].contains("米拉") or messages[0].contains("Mira")), "NPC greeting uses the localized friendly line")
	npc._process(0.1)
	_expect(messages.size() == 1, "NPC greeting is one-shot per scene")
	var token := InteractableScript.new()
	token.name = "Berry"
	token.interaction_kind = "berry"
	token.target_id = "berry_a"
	add_child(token)
	token._process(0.1)
	_expect(not token.npc_greeted, "Non-NPC world objects never emit social greetings")
	GameState.message_requested.disconnect(handler)

	# FR-32 voice-first greeting: with the voice channel available the greeting
	# is spoken only — no subtitle text is queued.
	var voice_npc := InteractableScript.new()
	voice_npc.name = "TaviVoice"
	voice_npc.interaction_kind = "npc"
	voice_npc.target_id = "tavi"
	voice_npc.display_name = "塔维"
	add_child(voice_npc)
	NpcVoice.availability_override = true
	var voice_messages: Array[String] = []
	var voice_handler := func(text: String, _tone: String) -> void:
		voice_messages.append(text)
	GameState.message_requested.connect(voice_handler)
	voice_npc._process(0.1)
	_expect(voice_npc.npc_greeted and voice_messages.is_empty(), "Available voice keeps the greeting spoken-only; no subtitle text")
	GameState.message_requested.disconnect(voice_handler)
	NpcVoice.availability_override = false

	# FR-30: guided word practice must not capture the V key during onboarding.
	GameState.persistence_enabled = false
	Dialogue.reset_all()
	Vocabulary.observe_word("food")
	Vocabulary.observe_word("water")
	GameState.onboarding_completed = false
	GameState.begin_onboarding()
	var guided_npc := InteractableScript.new()
	guided_npc.name = "OriGuide"
	guided_npc.interaction_kind = "npc"
	guided_npc.target_id = "ori"
	guided_npc.display_name = "奥里"
	add_child(guided_npc)
	guided_npc._process(0.1)
	_expect(guided_npc.npc_greeted and not Dialogue.word_practice_active, "Onboarding keeps the V key free: no guided word practice during the guide")
	GameState.skip_onboarding()
	var free_npc := InteractableScript.new()
	free_npc.name = "VeshFree"
	free_npc.interaction_kind = "npc"
	free_npc.target_id = "vesh"
	free_npc.display_name = "维什"
	add_child(free_npc)
	free_npc._process(0.1)
	_expect(free_npc.npc_greeted and Dialogue.word_practice_active, "After the guide, approaching an NPC offers guided word practice again")
	Dialogue.finish_word_practice()
	Dialogue.reset_all()
	GameState.persistence_enabled = true
	if failures == 0:
		print("PASS: Stranger NPC attention suite")
	get_tree().quit(failures)


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
