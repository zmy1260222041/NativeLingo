@tool
extends EditorScenePostImport
## Post-import hook for the runtime player FBX (Tencent cloud rig).
##
## The Tencent FBX carries cloud action names like
## "Armature|87863..._remap". Map them to the contract animation names
## (game/tests/test_character_asset.gd) and set loop mode on locomotion.
## The -90°X root rotation Godot applies on FBX import is already correct
## (Z-up → Y-up), so we leave transforms alone.

const IDLE_ACTION_HASH := "87863afffd9fcbef3afb7f04b6005c1d"
const WALK_ACTION_HASH := "32795ddb244644eac67ccfd8b84060c3"

const RENAME_MAP := {
	IDLE_ACTION_HASH: "anim_chr_player_idle_neutral",
	WALK_ACTION_HASH: "anim_chr_player_walk_forward",
}


func _post_import(scene: Node) -> Object:
	var player := _find_first(scene, "AnimationPlayer") as AnimationPlayer
	if player == null:
		return scene
	for anim_name in player.get_animation_list():
		if anim_name == "RESET":
			continue
		var mapped := _map_name(anim_name)
		if mapped != anim_name:
			var anim := player.get_animation(anim_name)
			player.remove_animation(anim_name)
			if anim != null:
				anim.resource_name = mapped
				player.add_animation(mapped, anim)
				if mapped.ends_with("idle_neutral") or mapped.ends_with("walk_forward"):
					anim.loop_mode = Animation.LOOP_LINEAR
	return scene


func _map_name(name: String) -> String:
	for hash_key in RENAME_MAP:
		if name.contains(hash_key):
			return RENAME_MAP[hash_key]
	return name


func _find_first(node: Node, type_name: String) -> Node:
	if node.is_class(type_name):
		return node
	for child in node.get_children():
		var found := _find_first(child, type_name)
		if found != null:
			return found
	return null
