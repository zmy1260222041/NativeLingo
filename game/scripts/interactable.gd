class_name WorldInteractable
extends Node3D

@export var interaction_kind := ""
@export var target_id := ""
@export var display_name := ""
@export var one_shot := false

func _ready() -> void:
	if one_shot and GameState.completed_steps.has(target_id):
		visible = false
		return
	add_to_group("interactable")

func get_interaction_prompt() -> String:
	if interaction_kind == "npc":
		return "%s  ·  [V] 英语  [G] 手势  [E] 观察" % display_name
	return "%s  ·  [E] 互动" % display_name

func interact(communication: String) -> void:
	if interaction_kind != "npc" and communication != "action":
		return
	GameState.interact(interaction_kind, target_id, communication)
	if one_shot:
		visible = false
		remove_from_group("interactable")
