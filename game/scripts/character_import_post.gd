@tool
extends EditorScenePostImport
## Post-import hook for runtime character GLBs.
##
## Godot's glTF importer sets every animation's ``loop_mode`` to ``LOOP_NONE``.
## The character-asset contract (``game/tests/test_character_asset.gd``) requires
## the locomotion animations to loop, so this hook flips ``loop_mode`` to
## ``LOOP_LINEAR`` for any animation whose name signals looping — either the
## ``_loop`` suffix convention or the ``idle``/``walk`` locomotion stems.

const _LOOP_STEMS := ["idle", "walk", "run", "jog", "swim", "float"]


func _post_import(scene: Node) -> Object:
	var player := _find_first(scene, "AnimationPlayer") as AnimationPlayer
	if player != null:
		for anim_name in player.get_animation_list():
			if anim_name == "RESET":
				continue
			var anim := player.get_animation(anim_name)
			if anim == null:
				continue
			if _should_loop(anim_name):
				anim.loop_mode = Animation.LOOP_LINEAR
	return scene


func _should_loop(anim_name: String) -> bool:
	var lower := anim_name.to_lower()
	if lower.ends_with("_loop"):
		return true
	for stem in _LOOP_STEMS:
		if stem in lower:
			return true
	return false


func _find_first(node: Node, type_name: String) -> Node:
	if node.is_class(type_name):
		return node
	for child in node.get_children():
		var found := _find_first(child, type_name)
		if found != null:
			return found
	return null
