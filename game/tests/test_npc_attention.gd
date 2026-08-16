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
	if failures == 0:
		print("PASS: Stranger NPC attention suite")
	get_tree().quit(failures)


func _expect(condition: bool, label: String) -> void:
	if condition:
		print("  OK  ", label)
	else:
		failures += 1
		push_error("FAIL: " + label)
