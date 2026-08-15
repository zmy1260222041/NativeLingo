extends Node

func _ready() -> void:
	await get_tree().process_frame
	await get_tree().physics_frame
	var player := $Main/Player as PlayerController
	player.position = Vector3(1.5, 0.03, 2.8)
	player.rotation.y = 0.0
	player.get_node("CameraPivot/SpringArm3D").spring_length = 4.2
	player.get_node("CameraPivot/SpringArm3D/Camera3D").fov = 62.0
	await get_tree().physics_frame
	await get_tree().physics_frame
	if player.character_visual:
		player.character_visual.play_reaction("greet")
	for candidate in get_tree().get_nodes_in_group("interactable"):
		if candidate.target_id == "rowan":
			var visual := candidate.get_node_or_null("CharacterVisual") as CharacterVisual
			if visual:
				visual.play_reaction("greet")
			break
